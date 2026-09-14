"""Repair the damage a PDF->EPUB reflow does, then cut the result into segments.

A reflowed book has no paragraphs: every *typeset line* becomes its own ``<p>``.
On the sample book 11,382 ``<p>`` elements hold 4,548 lines that do not end a
sentence, 632 that end in a hyphen and 618 that are bare print page numbers.

Joining those lines back together is a *text* problem, not a geometry problem:
document order is already correct, so no column detection, overlap analysis or
layout model is needed.

The hyphenator uses the book itself as its dictionary. A line-final ``-`` is
only removed when the joined word occurs unhyphenated somewhere else in the same
book, which keeps ``multi-`` + ``agent`` as ``multi-agent`` while turning
``engi-`` + ``neers`` into ``engineers``.
"""

from __future__ import annotations

import copy
import enum
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from dataclasses import field

from lxml import etree

from babeldoc.format.epub.archive import EpubDocument
from babeldoc.format.epub.style_profile import DEFAULT_BLOCK_TAGS
from babeldoc.format.epub.style_profile import Role
from babeldoc.format.epub.style_profile import StyleProfile
from babeldoc.format.epub.style_profile import is_page_number_text

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']{1,}")
_SENTENCE_END_RE = re.compile(r"[.!?:;\"'”’)\]}]\s*$")
_TRAILING_HYPHEN_RE = re.compile(r"([A-Za-z])-\s*$")
_TRAILING_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*$")
_INLINE_HYPHEN_RE = re.compile(r"\b([A-Za-z]{2,})-([a-z]{2,})\b")
_LEADING_LOWER_RE = re.compile(r"^\s*[a-z]")
_MARKER_PREFIX_RE = re.compile(
    r"^\s*(?:[•◦▪▫‣※]|\(?[0-9ivxlcIVXLC]{1,4}[.)]|[a-zA-Z][.)])\s+"
)

# Inline spans that must never be translated or rewritten.
CODE_TAGS = frozenset({"code", "pre", "kbd", "samp", "tt", "var"})
# Block-level tags that hold verbatim content whatever their CSS class says.
VERBATIM_TAGS = frozenset({"pre", "code"})
# Elements whose text is never user-visible prose.
OPAQUE_TAGS = frozenset({"script", "style", "svg", "math", "img", "image", "title"})
HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


class MergeMode(enum.Enum):
    """How a segment's blocks were combined."""

    SINGLE = "single"
    JOINED_LINES = "joined_lines"
    CODE_RUN = "code_run"


@dataclass
class TextSlot:
    """A text node (or tail) whose content belongs to a segment.

    Inline markup splits a paragraph into several text nodes *and their tails*:
    ``<p><span>•</span> <span>Bold</span> rest of the sentence</p>`` puts the real
    prose in the spans' tails. Both halves must be collected, or most of the
    book's body text is silently lost.
    """

    node: etree._Element
    field: str  # "text" or "tail"
    original: str
    is_code: bool = False

    def set(self, value: str) -> None:
        setattr(self.node, self.field, value)

    def remove(self) -> None:
        self.set("")

    @property
    def is_tail(self) -> bool:
        return self.field == "tail"


@dataclass
class Block:
    """One text-bearing block element, classified."""

    href: str
    index: int
    element: etree._Element
    role: Role
    class_name: str | None
    slots: list[TextSlot] = field(default_factory=list)
    page_anchor: str | None = None

    @property
    def text(self) -> str:
        return "".join(slot.original for slot in self.slots)

    @property
    def stripped_text(self) -> str:
        return self.text.strip()

    @property
    def is_marker_only(self) -> bool:
        stripped = self.stripped_text
        return bool(stripped) and stripped in "•◦▪▫‣※-–—*"


@dataclass
class DroppedBlock:
    href: str
    index: int
    role: Role
    text: str
    reason: str


@dataclass
class Segment:
    """A translatable unit: one or more source blocks merged into one request."""

    href: str
    index: int
    role: Role
    text: str
    blocks: list[Block]
    mode: MergeMode = MergeMode.SINGLE
    marker: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.text)

    def translatable_slots(self) -> list[TextSlot]:
        return [
            slot
            for block in self.blocks
            for slot in block.slots
            if not slot.is_code and slot.original.strip()
        ]

    def apply(
        self, translation: str, mode: str = "side_by_side", lang: str | None = None
    ) -> None:
        """Write ``translation`` back into the DOM.

        ``side_by_side``
            Keep every source block and place the translation next to it in a
            two-column row (left source, right translation). This is the
            default because interleaving whole paragraphs interrupts reading.
        ``bilingual``
            Keep the source and append the translation as the next block.
        ``replace``
            Replace the source text with the translation (mono output).
        """
        if mode == "replace":
            self._apply_replace(translation)
        elif mode == "bilingual":
            self._apply_bilingual(translation)
        elif mode == "side_by_side":
            self._apply_side_by_side(translation, lang)
        else:
            raise ValueError(f"unknown output mode: {mode}")

    def _apply_replace(self, translation: str) -> None:
        slots = self.translatable_slots()
        if not slots:
            return
        head = slots[0]
        prefix = _leading_whitespace(head.original)
        head.set(prefix + translation)
        for slot in slots[1:]:
            slot.remove()
        for block in self.blocks[1:]:
            _remove_element(block.element)

    def _apply_bilingual(self, translation: str) -> None:
        slots = self.translatable_slots()
        if not slots:
            return
        # Clone the first block as the carrier of the translation and insert it
        # straight after the source block, so reading order stays source then
        # translation.
        carrier = _clone_for_translation(self.blocks[0].element, translation)
        parent = self.blocks[0].element.getparent()
        if parent is None:
            return
        anchor = self.blocks[-1].element
        parent.insert(parent.index(anchor) + 1, carrier)

    def _apply_side_by_side(self, translation: str, lang: str | None) -> None:
        """Place the source and its translation in a two-column row.

        The source keeps its original markup, so links, emphasis and anchors
        survive. When several source blocks were folded into this segment they
        all go in the left cell, which is what makes the columns line up the way
        a side-by-side PDF does.

        A ``<div>`` may not be inserted between ``<ul>`` and ``<li>`` (or inside
        a table row), so in those containers the pair goes *inside* the element
        instead of around it.
        """
        if not self.translatable_slots():
            return
        head = self.blocks[0].element
        parent = head.getparent()
        if parent is None:
            return
        if etree.QName(parent).localname in _STRICT_CONTAINERS:
            self._pair_inside(head, translation, lang)
        else:
            self._pair_around(head, parent, translation, lang)

    def _pair_around(self, head, parent, translation: str, lang: str | None) -> None:
        source_cell = _new_div("bdoc-src")
        target_cell = _new_div("bdoc-dst", lang=lang)
        pair = _new_div("bdoc-pair")

        index = parent.index(head)
        parent.insert(index, pair)
        # Move every source block of the segment into the left cell, preserving
        # document order, markup and inter-block whitespace.
        for block in self.blocks:
            _move(block.element, source_cell)
        target_cell.append(_clone_for_translation(head, translation))
        pair.append(source_cell)
        pair.append(target_cell)

    def _pair_inside(self, head, translation: str, lang: str | None) -> None:
        existing = head.get("class") or ""
        head.set("class", f"{existing} bdoc-paired".strip())
        source_cell = _new_div("bdoc-src")
        source_cell.text = head.text
        head.text = None
        for child in list(head):
            _move(child, source_cell)
        target_cell = _new_div("bdoc-dst", lang=lang)
        target_cell.text = translation
        pair = _new_div("bdoc-pair")
        pair.append(source_cell)
        pair.append(target_cell)
        head.append(pair)


class WordVocabulary:
    """Words that occur unhyphenated in the book, used to resolve soft hyphens."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    @classmethod
    def build(cls, documents) -> WordVocabulary:
        vocabulary = cls()
        for document in documents:
            for text in document.root.itertext():
                if not text:
                    continue
                for word in _WORD_RE.findall(text):
                    vocabulary.counts[word.lower()] += 1
        return vocabulary

    def resolve_hyphen(self, left: str, right: str) -> str:
        """Resolve a hyphen that sits at a *line break* between two fragments.

        A hyphen at the end of a line is a typesetting artefact by default, so it
        is removed unless the book uses the hyphenated form elsewhere
        (``multi-`` + ``agent`` stays ``multi-agent``).
        """
        joined = f"{left}{right}".lower()
        hyphenated = f"{left}-{right}".lower()
        if hyphenated in self.counts and joined not in self.counts:
            return "-"
        return ""

    def resolve_inline_hyphen(self, left: str, right: str) -> str:
        """Resolve a hyphen that sits *inside* a block, where it may be real.

        The bar is deliberately higher: the joined form must actually occur in
        this book, otherwise the hyphen is kept. That repairs ``consis-tency``
        without touching ``state-of-the-art``.
        """
        joined = f"{left}{right}".lower()
        hyphenated = f"{left}-{right}".lower()
        if joined in self.counts and hyphenated not in self.counts:
            return ""
        return "-"

    def dehyphenate_inline(self, text: str) -> str:
        """Repair soft hyphens that survived inside a single block."""

        def replace(match: re.Match) -> str:
            left, right = match.group(1), match.group(2)
            return left + self.resolve_inline_hyphen(left, right) + right

        return _INLINE_HYPHEN_RE.sub(replace, text)


def _leading_whitespace(text: str) -> str:
    return text[: len(text) - len(text.lstrip())]


def _remove_element(element: etree._Element) -> None:
    parent = element.getparent()
    if parent is None:
        return
    parent.remove(element)


# Containers that may not gain a <div> child in place of their own children.
_STRICT_CONTAINERS = frozenset(
    {"ul", "ol", "dl", "menu", "tr", "table", "thead", "tbody", "tfoot", "select"}
)


def _move(element: etree._Element, new_parent: etree._Element) -> None:
    """Move an element, preserving its tail text.

    libxml2 drops the tail text node when a node is unlinked and re-linked, so
    the whitespace that separated sibling blocks disappears and words end up
    glued together. Saving and restoring the tail keeps the document intact.
    """
    tail = element.tail
    old_parent = element.getparent()
    if old_parent is not None:
        old_parent.remove(element)
    new_parent.append(element)
    element.tail = tail


def _new_div(class_name: str, lang: str | None = None) -> etree._Element:
    element = etree.Element("{http://www.w3.org/1999/xhtml}div")
    element.set("class", class_name)
    if lang:
        element.set("lang", lang)
        element.set("{http://www.w3.org/XML/1998/namespace}lang", lang)
    return element


def _clone_for_translation(element: etree._Element, translation: str) -> etree._Element:
    """A copy of ``element`` carrying the translated text.

    Deep-copied rather than serialised and re-parsed: the round trip fails on
    documents that use named entities, and it is slower.
    """
    clone = copy.deepcopy(element)
    for child in list(clone):
        clone.remove(child)
    clone.text = translation
    clone.tail = None
    existing = clone.get("class") or ""
    clone.set("class", (existing + " bdoc-translation").strip())
    for name in ("id", "lang"):
        if clone.get(name) is not None:
            del clone.attrib[name]
    return clone


# --- block extraction ------------------------------------------------------


def _is_inside_opaque(element: etree._Element) -> bool:
    parent = element.getparent()
    while parent is not None:
        if isinstance(parent.tag, str):
            tag = etree.QName(parent).localname
            if tag in OPAQUE_TAGS or tag in CODE_TAGS:
                return True
        parent = parent.getparent()
    return False


def _is_inside_code(element: etree._Element) -> bool:
    parent = element.getparent()
    while parent is not None:
        if isinstance(parent.tag, str) and etree.QName(parent).localname in CODE_TAGS:
            return True
        parent = parent.getparent()
    return False


def _collect_slots(element: etree._Element, profile: StyleProfile) -> list[TextSlot]:
    """Collect a block's translatable text (texts *and* tails) in document order."""
    slots: list[TextSlot] = []

    def emit(node: etree._Element, field: str, inside_code: bool) -> None:
        value = getattr(node, field)
        if not value:
            return
        # Whitespace-only slots are kept: dropping them glues words together
        # across inline markup ("•Real"). They are never written back because
        # ``translatable_slots`` filters on ``strip()``.
        slots.append(
            TextSlot(node=node, field=field, original=value, is_code=inside_code)
        )

    def walk(node: etree._Element, inside_code: bool) -> None:
        if isinstance(node.tag, str):
            tag = etree.QName(node).localname
            if tag in OPAQUE_TAGS:
                return
            if tag in CODE_TAGS:
                inside_code = True
            span_role = profile.role_for_span(node.get("class"))
            if span_role is Role.CODE or span_role is Role.LIST_MARKER:
                inside_code = True
        emit(node, "text", inside_code)
        for child in node:
            if not isinstance(child.tag, str):
                continue
            walk(child, inside_code)
            emit(child, "tail", inside_code)

    walk(element, _is_inside_code(element))
    return slots


def _has_block_descendant(element: etree._Element, block_tags: frozenset[str]) -> bool:
    """True when a nested block element already carries this element's text.

    ``<li><p>text</p></li>`` and ``<td><p>text</p></td>`` must yield one block,
    not two, or the sentence is queued for translation twice.
    """
    for child in element.iterdescendants():
        if not isinstance(child.tag, str):
            continue
        if etree.QName(child).localname in block_tags:
            if any(part.strip() for part in child.itertext()):
                return True
    return False


def iter_blocks(document: EpubDocument, profile: StyleProfile) -> list[Block]:
    """Flatten a document into classified, ordered blocks."""
    blocks: list[Block] = []
    for element in document.root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = etree.QName(element).localname
        if tag not in DEFAULT_BLOCK_TAGS:
            continue
        if _is_inside_opaque(element):
            continue
        if _has_block_descendant(element, DEFAULT_BLOCK_TAGS):
            continue
        slots = _collect_slots(element, profile)
        if not any(slot.original.strip() for slot in slots):
            continue
        class_name = element.get("class")
        role = profile.role_for_paragraph(class_name)
        if tag in HEADING_TAGS:
            role = Role.HEADING
        elif tag in VERBATIM_TAGS:
            # Structural, not stylistic: <pre> is a code block whatever the CSS
            # says, and translating it would corrupt the listing.
            role = Role.CODE
        elif tag == "li" and role is Role.BODY:
            role = Role.LIST_ITEM
        if role is Role.UNKNOWN and tag not in VERBATIM_TAGS:
            # Unclassed blocks are prose that must be translated; refusing to
            # translate is the expensive mistake.
            role = Role.BODY
        text = "".join(slot.original for slot in slots)
        # Confirm verbatim roles against the actual block text. A class is a
        # hint; a page-number class on this book also holds a few right-aligned
        # prose fragments, and dropping real prose is far worse than keeping a
        # stray folio.
        if role is Role.PAGE_NUMBER and not is_page_number_text(text):
            role = Role.BODY
        if role is Role.CODE and not any(slot.is_code for slot in slots):
            role = Role.CODE
        blocks.append(
            Block(
                href=document.href,
                index=len(blocks),
                element=element,
                role=role,
                class_name=class_name,
                slots=slots,
                page_anchor=element.get("id"),
            )
        )
    return blocks


# --- merging ---------------------------------------------------------------


def _normalize_marker(text: str) -> str:
    """Repair a literal list marker that lost its spacing during extraction."""
    marker, _, rest = text.partition(" ")
    if marker and not rest:
        return text
    return text


@dataclass
class NormalizationPolicy:
    """Book-level decisions about how aggressively to reconstruct prose.

    A book converted from PDF has paragraphs split into typeset lines and needs
    aggressive joining. A native EPUB already has real paragraphs, and joining
    them would destroy the structure the format went to the trouble of keeping.
    """

    join_lines: bool = True
    drop_page_numbers: bool = True
    dehyphenate: bool = True
    max_join_chars: int = 1200
    continuation_ratio: float = 0.0
    fragment_ratio: float = 0.0

    @classmethod
    def detect(cls, blocks: list[Block]) -> NormalizationPolicy:
        continuation, fragment = measure_reflow(blocks)
        return cls(
            join_lines=continuation >= CONTINUATION_THRESHOLD,
            continuation_ratio=continuation,
            fragment_ratio=fragment,
        )

    @property
    def is_reflow(self) -> bool:
        return self.join_lines

    def describe(self) -> str:
        verdict = "PDF reflow" if self.is_reflow else "native EPUB"
        return (
            f"{verdict} (continuation ratio {self.continuation_ratio:.1%}, "
            f"fragment ratio {self.fragment_ratio:.1%})"
        )


# A paragraph ending mid-sentence only proves a PDF reflow when the *next*
# paragraph continues it. Measured on real books: 23% for a PDF reflow, 5% for a
# native EPUB. Fragment ratio alone cannot separate them, because native books
# are full of headings, table cells and list items that also skip final
# punctuation (measured 43% fragments in both).
CONTINUATION_THRESHOLD = 0.10
_CONTINUES_RE = re.compile(
    r"^\s*(?:[a-z]|[,;:)\]}]|and\b|or\b|but\b|the\b|of\b|to\b|in\b|a\b)"
)
_TABLE_TAGS = frozenset({"table", "tr", "td", "th"})


def in_table(element: etree._Element) -> bool:
    parent = element.getparent()
    while parent is not None:
        if isinstance(parent.tag, str) and etree.QName(parent).localname in _TABLE_TAGS:
            return True
        parent = parent.getparent()
    return False


def measure_reflow(blocks: list[Block]) -> tuple[float, float]:
    """Return ``(continuation_ratio, fragment_ratio)`` over prose ``<p>`` blocks."""
    prose = [
        block
        for block in blocks
        if block.role is Role.BODY
        and etree.QName(block.element).localname == "p"
        and not in_table(block.element)
        and len(block.stripped_text) >= 40
    ]
    if len(prose) < 8:
        return 0.0, 0.0
    pairs = fragments = continuations = 0
    for previous, following in zip(prose, prose[1:], strict=False):
        if previous.href != following.href:
            continue
        pairs += 1
        if _SENTENCE_END_RE.search(previous.stripped_text):
            continue
        fragments += 1
        if _CONTINUES_RE.match(following.stripped_text):
            continuations += 1
    if not pairs:
        return 0.0, 0.0
    return continuations / pairs, fragments / pairs


def merge_blocks(
    blocks: list[Block],
    vocabulary: WordVocabulary,
    policy: NormalizationPolicy | None = None,
) -> tuple[list[Segment], list[DroppedBlock]]:
    """Fold typeset lines back into paragraphs, code runs and list items."""
    if policy is None:
        policy = NormalizationPolicy.detect(blocks)
    segments: list[Segment] = []
    dropped: list[DroppedBlock] = []
    pending: list[Block] = []
    joined_chars = 0

    def flush(role: Role) -> None:
        if not pending:
            return
        segments.append(_build_segment(pending, role, vocabulary, policy))
        pending.clear()

    for block in blocks:
        if block.role is Role.PAGE_NUMBER and policy.drop_page_numbers:
            flush(_current_role(pending))
            dropped.append(
                DroppedBlock(
                    href=block.href,
                    index=block.index,
                    role=block.role,
                    text=block.stripped_text,
                    reason="page number",
                )
            )
            continue
        if block.role is Role.LIST_MARKER:
            flush(_current_role(pending))
            dropped.append(
                DroppedBlock(
                    href=block.href,
                    index=block.index,
                    role=block.role,
                    text=block.stripped_text,
                    reason="bare marker",
                )
            )
            continue

        if pending and _should_join(pending[-1], block, policy, joined_chars):
            pending.append(block)
            joined_chars += len(block.stripped_text)
            continue

        flush(_current_role(pending))
        pending.append(block)
        joined_chars = len(block.stripped_text)

    flush(_current_role(pending))
    for index, segment in enumerate(segments):
        segment.index = index
    return segments, dropped


def _should_join(
    previous: Block,
    block: Block,
    policy: NormalizationPolicy,
    joined_chars: int,
) -> bool:
    if previous.role is not block.role:
        return False
    role = block.role
    if role is Role.CODE:
        return True
    if role not in {Role.BODY, Role.HEADING, Role.CAPTION}:
        return False
    # The limit is on the *segments* accumulated length, not just the previous
    # block, or a table of contents joins itself into a 7,000-character blob.
    if joined_chars + len(block.stripped_text) > policy.max_join_chars:
        return False
    if not policy.join_lines:
        # Native EPUB: blocks already are paragraphs, so never join. Leaving two
        # halves of a sentence apart is a minor translation defect; glueing a
        # table of contents or a list into one paragraph is a structural one.
        return False
    # A PDF reflow is not a licence to cross structural boundaries either.
    if in_table(previous.element) or in_table(block.element):
        return previous.element.getparent() is block.element.getparent()
    return True


def _current_role(pending: list[Block]) -> Role:
    return pending[-1].role if pending else Role.BODY


def _build_segment(
    blocks: list[Block],
    role: Role,
    vocabulary: WordVocabulary,
    policy: NormalizationPolicy,
) -> Segment:
    if role is Role.CODE:
        text = "\n".join(block.stripped_text for block in blocks)
        mode = MergeMode.CODE_RUN if len(blocks) > 1 else MergeMode.SINGLE
    elif len(blocks) == 1:
        text = blocks[0].stripped_text
        mode = MergeMode.SINGLE
    else:
        text = _join_line_texts([block.stripped_text for block in blocks], vocabulary)
        mode = MergeMode.JOINED_LINES

    if policy.dehyphenate and role is not Role.CODE:
        text = vocabulary.dehyphenate_inline(text)

    marker = None
    match = _MARKER_PREFIX_RE.match(text)
    if match:
        marker = match.group(0).strip()
    return Segment(
        href=blocks[0].href,
        index=blocks[0].index,
        role=role,
        text=text,
        blocks=list(blocks),
        mode=mode,
        marker=marker,
    )


def _join_line_texts(parts: list[str], vocabulary: WordVocabulary) -> str:
    """Join line fragments, undoing hyphenation at the seam."""
    result = parts[0].rstrip()
    for part in parts[1:]:
        chunk = part.lstrip()
        if not chunk:
            continue
        hyphen = _TRAILING_HYPHEN_RE.search(result)
        if hyphen and _LEADING_LOWER_RE.match(chunk):
            left = hyphen.group(1)
            right = _WORD_RE.match(chunk)
            if right is not None:
                replacement = vocabulary.resolve_hyphen(left, right.group(0))
                result = result[: hyphen.start(1)] + left + replacement + chunk
                continue
        result = f"{result} {chunk}"
    return re.sub(r"\s+", " ", result).strip()


# --- conservation check ----------------------------------------------------


def normalize_text(text: str) -> str:
    """Reduce text to what a translation must account for."""
    decomposed = unicodedata.normalize("NFKC", text)
    collapsed = re.sub(r"\s+", "", decomposed)
    return collapsed.replace("\u00ad", "")


@dataclass
class ConservationReport:
    source_chars: int
    segment_chars: int
    dropped_chars: int
    missing_chars: int
    duplicated_chars: int = 0

    @property
    def ok(self) -> bool:
        return self.missing_chars == 0 and self.duplicated_chars == 0

    def describe(self) -> str:
        return (
            f"source {self.source_chars} = segments {self.segment_chars} + "
            f"dropped {self.dropped_chars} "
            f"(missing {self.missing_chars}, duplicated {self.duplicated_chars})"
        )


def check_conservation(
    blocks: list[Block],
    segments: list[Segment],
    dropped: list[DroppedBlock],
    hyphens_removed: int = 0,
) -> ConservationReport:
    """Verify that no source text silently vanished during normalization.

    Counted against the *blocks*, not the raw document, so that metadata such as
    ``<title>`` is not mistaken for lost content. Removing a soft hyphen
    intentionally deletes one character, so those are reported separately and
    the residual is what actually matters.
    """
    source = Counter()
    for block in blocks:
        for slot in block.slots:
            source.update(normalize_text(slot.original))

    produced = Counter()
    for segment in segments:
        produced.update(normalize_text(segment.text))
    dropped_counter = Counter()
    for item in dropped:
        dropped_counter.update(normalize_text(item.text))

    missing = 0
    for char, count in source.items():
        if char == "-":
            # Hyphens may be removed or added by joining and de-hyphenation.
            continue
        accounted = produced[char] + dropped_counter[char]
        if accounted < count:
            missing += count - accounted
    # Duplicated text is the failure a missing-only check cannot see: emitting a
    # nested block twice queues the same sentence for translation twice.
    duplicated = 0
    for char, count in produced.items():
        if char == "-":
            continue
        if count > source[char]:
            duplicated += count - source[char]
    return ConservationReport(
        source_chars=sum(source.values()),
        segment_chars=sum(produced.values()),
        dropped_chars=sum(dropped_counter.values()),
        missing_chars=max(0, missing - hyphens_removed),
        duplicated_chars=duplicated,
    )


LABEL_DOCUMENT_THRESHOLD = 0.6


def looks_like_label_document(segments: list[Segment]) -> bool:
    """True for navigational documents: table of contents, index, list of figures.

    Pairing 244 short entries into two columns produces a dense wall of text and
    buys nothing, because a table of contents is navigation rather than reading
    material. Such documents are translated in place instead. Prose is the
    opposite shape: long blocks that end sentences.
    """
    if len(segments) < 8:
        return False
    labels = sum(
        1
        for segment in segments
        if len(segment.text) < 60
        and not segment.text.rstrip().endswith((".", "!", "?", ":", ";", "\u201d"))
    )
    return labels / len(segments) >= LABEL_DOCUMENT_THRESHOLD


_NUMERIC_RUN_RE = re.compile(
    r"^(?:[0-9]{1,4}|[ivxlcdm]{1,7})(?:[\s,;]+(?:[0-9]{1,4}|[ivxlcdm]{1,7}))+$", re.I
)


def is_page_list_segment(text: str) -> bool:
    """True for a block that is nothing but a run of folio numbers.

    Front matter often ships the print page list as body text. No real paragraph
    consists only of numbers separated by spaces, so this is safe to drop.
    """
    stripped = text.strip()
    return (
        bool(stripped)
        and len(stripped) <= 400
        and bool(_NUMERIC_RUN_RE.match(stripped))
    )


__all__ = [
    "Block",
    "ConservationReport",
    "DroppedBlock",
    "MergeMode",
    "CONTINUATION_THRESHOLD",
    "NormalizationPolicy",
    "Segment",
    "TextSlot",
    "WordVocabulary",
    "check_conservation",
    "in_table",
    "is_page_list_segment",
    "looks_like_label_document",
    "iter_blocks",
    "measure_reflow",
    "merge_blocks",
    "normalize_text",
]
