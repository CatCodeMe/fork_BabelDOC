"""EPUB container access: OPF, manifest, spine, navigation.

Deliberately dependency-free beyond ``lxml``: an EPUB is a ZIP with a
well-specified entry point, and pulling in a framework would hide the details
we need (raw bytes for untouched documents, exact spine order, manifest
properties).
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field
from html.entities import html5
from pathlib import Path
from urllib.parse import unquote

from lxml import etree

CONTAINER_PATH = "META-INF/container.xml"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
OPS_NS = "http://www.idpf.org/2007/ops"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"

XHTML_MEDIA_TYPES = frozenset(
    {
        "application/xhtml+xml",
        "text/html",
        "application/x-dtbook+xml",
    }
)

# EPUB 2 documents use the XHTML named entity set (``&eacute;``, ``&mdash;``) and
# rely on a DOCTYPE to define it. Parsing without fetching the DTD leaves those
# as entity nodes that cannot be re-parsed and are undefined in the output, so
# they are expanded to characters up front. The five XML built-ins are left
# alone: they stay valid, and expanding them would produce a bare ``&``.
_XML_BUILTIN_ENTITIES = frozenset({"amp", "lt", "gt", "quot", "apos"})
_NAMED_ENTITY_RE = re.compile(rb"&([A-Za-z][A-Za-z0-9]{1,31});")


def expand_named_entities(data: bytes) -> bytes:
    """Replace XHTML named entities with their characters."""

    def replace(match: re.Match) -> bytes:
        name = match.group(1).decode("ascii", errors="replace")
        if name in _XML_BUILTIN_ENTITIES:
            return match.group(0)
        character = html5.get(name + ";")
        if character is None:
            return match.group(0)
        return character.encode("utf-8")

    return _NAMED_ENTITY_RE.sub(replace, data)


def localname(element) -> str:
    """Return the local name of an element, ignoring its namespace."""
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    return etree.QName(tag).localname


def iter_elements(root, name: str) -> Iterator:
    """Yield descendants whose local name matches, namespace-agnostically."""
    for element in root.iter():
        if isinstance(element.tag, str) and etree.QName(element).localname == name:
            yield element


def find_first(root, name: str):
    return next(iter_elements(root, name), None)


def _metadata_element(opf):
    """Return the ``<metadata>`` element, falling back to the OPF root."""
    metadata = find_first(opf, "metadata")
    return metadata if metadata is not None else opf


@dataclass(frozen=True)
class ManifestItem:
    id: str
    href: str
    media_type: str
    properties: frozenset[str] = frozenset()

    @property
    def is_xhtml(self) -> bool:
        return self.media_type in XHTML_MEDIA_TYPES


@dataclass
class EpubDocument:
    """One XHTML content document from the spine."""

    href: str
    tree: etree._ElementTree
    spine_index: int

    @property
    def root(self):
        return self.tree.getroot()

    @property
    def title(self) -> str:
        element = find_first(self.root, "title")
        return (element.text or "").strip() if element is not None else ""


@dataclass
class EpubArchive:
    """Read-only view over an EPUB file."""

    path: Path
    opf_path: str
    opf_dir: str
    version: str
    metadata: dict[str, str] = field(default_factory=dict)
    manifest: dict[str, ManifestItem] = field(default_factory=dict)
    spine: list[str] = field(default_factory=list)
    nav_href: str | None = None
    ncx_href: str | None = None
    _zip: zipfile.ZipFile | None = None

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path) -> EpubArchive:
        archive = cls(path=Path(path), opf_path="", opf_dir="", version="")
        archive._zip = zipfile.ZipFile(archive.path)
        archive._load_opf()
        return archive

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def __enter__(self) -> EpubArchive:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- container ---------------------------------------------------------

    @property
    def zip(self) -> zipfile.ZipFile:
        if self._zip is None:
            raise RuntimeError("EPUB archive is closed")
        return self._zip

    @property
    def names(self) -> list[str]:
        return self.zip.namelist()

    def read_bytes(self, href: str) -> bytes:
        return self.zip.read(href)

    def exists(self, href: str) -> bool:
        try:
            self.zip.getinfo(href)
        except KeyError:
            return False
        return True

    def _load_opf(self) -> None:
        container = self._parse_xml(self.read_bytes(CONTAINER_PATH))
        rootfile = find_first(container, "rootfile")
        if rootfile is None:
            raise ValueError(f"{self.path} has no rootfile in {CONTAINER_PATH}")
        self.opf_path = rootfile.get("full-path") or ""
        if not self.opf_path:
            raise ValueError(f"{self.path} has a rootfile without full-path")
        self.opf_dir = posixpath.dirname(self.opf_path)

        opf = self._parse_xml(self.read_bytes(self.opf_path))
        self.version = opf.get("version") or ""

        for element in iter_elements(_metadata_element(opf), "title"):
            self.metadata["title"] = (element.text or "").strip()
            break
        for element in iter_elements(_metadata_element(opf), "language"):
            self.metadata["language"] = (element.text or "").strip()
            break
        for element in iter_elements(_metadata_element(opf), "identifier"):
            self.metadata["identifier"] = (element.text or "").strip()
            break

        manifest_element = find_first(opf, "manifest")
        if manifest_element is None:
            raise ValueError(f"{self.path} has no manifest")
        for item in iter_elements(manifest_element, "item"):
            item_id = item.get("id") or ""
            href = item.get("href") or ""
            if not item_id or not href:
                continue
            properties = frozenset((item.get("properties") or "").split())
            resolved = self.resolve(href)
            self.manifest[item_id] = ManifestItem(
                id=item_id,
                href=resolved,
                media_type=item.get("media-type") or "",
                properties=properties,
            )
            if "nav" in properties:
                self.nav_href = resolved

        spine_element = find_first(opf, "spine")
        if spine_element is None:
            raise ValueError(f"{self.path} has no spine")
        for itemref in iter_elements(spine_element, "itemref"):
            if (itemref.get("linear") or "yes").lower() == "no":
                continue
            item = self.manifest.get(itemref.get("idref") or "")
            if item is not None and item.is_xhtml:
                self.spine.append(item.href)
        if not self.spine:
            raise ValueError(f"{self.path} has an empty spine")

        if self.nav_href is None:
            ncx = next(
                (
                    item
                    for item in self.manifest.values()
                    if item.media_type == "application/x-dtbncx+xml"
                ),
                None,
            )
            self.ncx_href = ncx.href if ncx else None
        else:
            self.ncx_href = next(
                (
                    item.href
                    for item in self.manifest.values()
                    if item.media_type == "application/x-dtbncx+xml"
                ),
                None,
            )

    def _open_opf_copy(self) -> etree._Element:
        """A freshly parsed copy of the OPF, safe to mutate."""
        return self._parse_xml(self.read_bytes(self.opf_path))

    @staticmethod
    def _parse_xml(data: bytes) -> etree._Element:
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            recover=True,
            huge_tree=True,
        )
        return etree.fromstring(  # noqa: S320 - entities disabled, no network
            expand_named_entities(data), parser=parser
        )

    # -- path handling -----------------------------------------------------

    def resolve(self, href: str, base: str | None = None) -> str:
        """Resolve an EPUB-relative href to an absolute ZIP entry name."""
        href = unquote(href.split("#", 1)[0])
        if not href:
            return base or ""
        if base is None:
            base_dir = self.opf_dir
        else:
            base_dir = posixpath.dirname(base)
        if href.startswith("/"):
            return posixpath.normpath(href.lstrip("/"))
        return posixpath.normpath(posixpath.join(base_dir, href))

    def split_fragment(self, href: str) -> tuple[str, str]:
        """Split ``doc.xhtml#anchor`` into ``(absolute href, fragment)``."""
        if "#" in href:
            path_part, fragment = href.split("#", 1)
        else:
            path_part, fragment = href, ""
        return self.resolve(path_part), fragment

    # -- documents ---------------------------------------------------------

    def documents(self) -> Iterator[EpubDocument]:
        """Yield spine documents in reading order."""
        for index, href in enumerate(self.spine):
            yield EpubDocument(
                href=href,
                tree=etree.ElementTree(self.parse_xhtml(href)),
                spine_index=index,
            )

    def parse_xhtml(self, href: str) -> etree._Element:
        data = expand_named_entities(self.read_bytes(href))
        try:
            return etree.fromstring(  # noqa: S320 - entities disabled, no network
                data,
                parser=etree.XMLParser(
                    resolve_entities=False,
                    no_network=True,
                    recover=True,
                    huge_tree=True,
                ),
            )
        except etree.XMLSyntaxError:
            # A few books ship HTML5-flavoured XHTML that is not well-formed XML.
            return etree.fromstring(  # noqa: S320 - local file, no network
                data,
                parser=etree.HTMLParser(recover=True, huge_tree=True),
            )
