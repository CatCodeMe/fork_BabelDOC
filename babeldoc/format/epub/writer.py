"""Bilingual presentation and EPUB repackaging.

The layout BabelDOC's PDF mode uses — original on the left, translation on the
right — expressed in CSS instead of coordinates.

An EPUB has no pages, so "two columns on a page" becomes "two columns per
paragraph pair": each segment becomes one flex row whose left cell holds the
source blocks and whose right cell holds the translation. The two columns are
therefore not aligned line-by-line the way a fixed-layout PDF can align them, but
both columns read continuously instead of being interrupted paragraph by
paragraph, which is the property that matters for reading.

Two constraints are handled explicitly:

* A ``<div>`` cannot be inserted between ``<ul>`` and ``<li>`` or inside a table
  row, so those segments put the pair *inside* the element (see
  ``Segment._pair_inside``).
* Two columns of text are unreadable on a phone, so the stylesheet collapses to
  stacked layout below a width threshold. Readers with no flexbox support ignore
  ``display: flex`` and get the same stacked fallback.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from babeldoc.format.epub.archive import OPF_NS
from babeldoc.format.epub.archive import XHTML_NS
from babeldoc.format.epub.archive import EpubArchive
from babeldoc.format.epub.archive import find_first
from babeldoc.format.epub.archive import iter_elements

BILINGUAL_CSS_NAME = "babeldoc-bilingual.css"

BILINGUAL_CSS = """\
/* BabelDOC bilingual layout: source left, translation right. */
.bdoc-pair {
  display: flex;
  flex-wrap: nowrap;
  align-items: flex-start;
  /* Generous gutter and vertical rhythm: two columns of prose set tight are
     hard to read, and the pair must stay visually separate from the next one. */
  column-gap: 2.2em;
  margin: 0.85em 0;
}
.bdoc-src,
.bdoc-dst {
  flex: 1 1 0%;
  min-width: 0;
  /* Nothing may bleed into the gutter. */
  overflow-wrap: break-word;
}
/* First and last pairs sit flush with the surrounding text. */
.bdoc-pair:first-child { margin-top: 0; }
/* Breathing room inside each column, so lines are not set edge to edge. */
.bdoc-src { opacity: 0.7; padding-right: 0.1em; }
.bdoc-dst { hyphens: auto; padding-left: 0.1em; }

/* Keep the pair on one page in paged readers. */
.bdoc-pair { break-inside: avoid; page-break-inside: avoid; }

/* A phone screen cannot show two columns of prose; stack instead. Text in a
   half-width column is worse than either alternative. */
@media (max-width: 45em) {
  .bdoc-pair { display: block; margin: 0.7em 0; }
  .bdoc-src { opacity: 0.6; padding-right: 0; }
  .bdoc-dst { margin-top: 0.55em; padding-left: 0; }
}
"""


def inject_stylesheet(ref: str = BILINGUAL_CSS_NAME) -> callable:
    """Return a function that links a stylesheet into a document's ``<head>``."""

    def apply(tree: etree._ElementTree) -> bool:
        root = tree.getroot()
        head = find_first(root, "head")
        if head is None:
            return False
        for element in iter_elements(head, "link"):
            if element.get("href") == ref:
                return False
        link = etree.SubElement(head, f"{{{XHTML_NS}}}link")
        link.set("rel", "stylesheet")
        link.set("type", "text/css")
        link.set("href", ref)
        return True

    return apply


def register_stylesheet(
    opf: etree._Element, item_id: str = "babeldoc-bilingual"
) -> bool:
    """Add the bilingual stylesheet to the OPF manifest if it is missing."""
    manifest = find_first(opf, "manifest")
    if manifest is None:
        return False
    for item in iter_elements(manifest, "item"):
        if item.get("id") == item_id:
            return False
    item = etree.SubElement(manifest, f"{{{OPF_NS}}}item")
    item.set("id", item_id)
    item.set("href", BILINGUAL_CSS_NAME)
    item.set("media-type", "text/css")
    return True


@dataclass
class RepackResult:
    output: Path
    documents_written: int
    entries_copied: int
    stylesheet_added: bool


def repack(
    archive: EpubArchive,
    output: Path,
    changed: dict[str, etree._ElementTree],
    *,
    bilingual: bool = True,
) -> RepackResult:
    """Write a new EPUB, re-serialising only the documents that changed.

    Every other ZIP entry is copied byte-for-byte, so images, fonts and
    untouched chapters cannot be damaged by a round-trip through the XML parser.
    ``mimetype`` is written first and uncompressed, as the EPUB specification
    requires.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    copied = 0

    with zipfile.ZipFile(output, "w") as target:
        target.writestr(
            zipfile.ZipInfo("mimetype"),
            archive.read_bytes("mimetype"),
            compress_type=zipfile.ZIP_STORED,
        )
        for name in archive.names:
            if name == "mimetype":
                continue
            if name in changed:
                target.writestr(name, _serialize(changed[name]))
                written += 1
            elif name == archive.opf_path and bilingual:
                target.writestr(name, _opf_with_stylesheet(archive))
                written += 1
            else:
                info = archive.zip.getinfo(name)
                target.writestr(
                    info, archive.read_bytes(name), compress_type=info.compress_type
                )
                copied += 1
        if bilingual:
            target.writestr(stylesheet_path(archive.opf_dir), BILINGUAL_CSS)
            written += 1

    return RepackResult(
        output=output,
        documents_written=written,
        entries_copied=copied,
        stylesheet_added=bilingual,
    )


def _opf_with_stylesheet(archive: EpubArchive) -> bytes:
    opf = archive._open_opf_copy()
    register_stylesheet(opf)
    return _serialize(etree.ElementTree(opf))


def _serialize(tree: etree._ElementTree) -> bytes:
    """Serialise XHTML/OPF with an XML declaration and no pretty-printing.

    Pretty-printing is deliberately avoided: adding whitespace between inline
    elements changes how the text renders. The original DOCTYPE is preserved
    because EPUB 2 readers look for it.
    """
    try:
        doctype = tree.docinfo.doctype or None
    except Exception:  # noqa: BLE001 - trees built from elements have no docinfo
        doctype = None
    return etree.tostring(
        tree,
        xml_declaration=True,
        encoding="utf-8",
        doctype=doctype,
    )


def stylesheet_path(opf_dir: str) -> str:
    """ZIP path of the stylesheet: next to the OPF, as EPUB convention expects."""
    return (
        posixpath.join(opf_dir, BILINGUAL_CSS_NAME) if opf_dir else BILINGUAL_CSS_NAME
    )


def stylesheet_href_for(document_href: str, opf_dir: str) -> str:
    """Relative path from a content document to the injected stylesheet."""
    document_dir = posixpath.dirname(document_href)
    return posixpath.relpath(stylesheet_path(opf_dir), document_dir or ".")


_PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}")


def strip_placeholders(text: str) -> str:
    """Remove any placeholder token that leaked into a translation."""
    return _PLACEHOLDER_RE.sub("", text)
