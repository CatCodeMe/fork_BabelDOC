"""Infer what each CSS class means, so blocks can be classified structurally.

A PDF->EPUB reflow has no ``<h2>``, ``<pre>`` or ``<ul>``: headings, body lines,
page numbers and code all arrive as ``<p class="class_s17">``. The class names
are opaque and differ per book, so their meaning has to be recovered from the
stylesheet plus corpus statistics.

The stylesheet gives typography (a heading is bigger, a page number is
right-aligned). The corpus gives shape (a page number is all digits, a code line
is symbol-dense). Neither is sufficient alone; together they are reliable enough
to classify a whole book using a handful of examples per class.
"""

from __future__ import annotations

import enum
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from dataclasses import field

from lxml import etree

# Characters that are common in code and rare in prose.
_CODE_SYMBOLS = frozenset("{}()[];=<>|&$#\\/`*_@~^")
# A literal list marker: bullets, "1.", "1)", "(a)", "iv".
_MARKER_RE = re.compile(r"^(?:[•◦▪▫‣·※]|\(?[0-9ivxlcIVXLC]{1,4}[.)]|[a-zA-Z][.)])$")
_NUMBERED_LINE_RE = re.compile(r"^\s*\d{1,4}\s+\S")
_PURE_NUMBER_RE = re.compile(r"^\s*[0-9]{1,4}\s*$")
_ROMAN_RE = re.compile(r"^\s*[ivxlcdm]{1,7}\s*$", re.IGNORECASE)
_QUOTED_FRAGMENT_RE = re.compile(r"""["'][^"']{2,}["']""")
_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")
_DOTTED_PATH_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*(?:\.|\()"
)
# Only ``=`` counts as an assignment. Prose is full of run-in labels
# ("Note: ...") and treating ``:`` as an assignment flags them as code.
_ASSIGNMENT_RE = re.compile(r"(?:^|[\s,(])\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*[\[{\"'0-9]")


def is_page_number_text(text: str) -> bool:
    """True for a standalone print page number ("42", "xiv") and nothing else.

    Deliberately shape-based rather than class-based: dropping real prose is a
    much worse failure than keeping a stray page number, so this only fires on
    text that cannot be anything but a folio.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 8:
        return False
    return bool(_PURE_NUMBER_RE.match(stripped) or _ROMAN_RE.match(stripped))


LIST_MARKERS = frozenset("•◦▪▫‣·※-–—*")


class Role(enum.Enum):
    HEADING = "heading"
    BODY = "body"
    CODE = "code"
    PAGE_NUMBER = "page_number"
    CAPTION = "caption"
    LIST_ITEM = "list_item"
    LIST_MARKER = "list_marker"
    EMPHASIS = "emphasis"
    UNKNOWN = "unknown"

    @property
    def is_translatable(self) -> bool:
        return self in {
            Role.HEADING,
            Role.BODY,
            Role.CAPTION,
            Role.LIST_ITEM,
            Role.EMPHASIS,
        }

    @property
    def is_verbatim(self) -> bool:
        return self in {Role.CODE, Role.PAGE_NUMBER, Role.LIST_MARKER}


@dataclass
class ClassDeclarations:
    """Typography declared for a CSS class."""

    font_size: float | None = None
    font_weight: str | None = None
    font_style: str | None = None
    text_align: str | None = None
    margin_left: str | None = None
    text_indent: str | None = None
    font_family: str | None = None

    @property
    def is_bold(self) -> bool:
        return (self.font_weight or "").lower() in {
            "bold",
            "bolder",
            "600",
            "700",
            "800",
            "900",
        }

    @property
    def is_italic(self) -> bool:
        return (self.font_style or "").lower() in {"italic", "oblique"}

    @property
    def is_monospace(self) -> bool:
        family = (self.font_family or "").lower()
        return any(
            token in family
            for token in ("mono", "courier", "consolas", "menlo", "code", "typewriter")
        )

    @property
    def is_right_aligned(self) -> bool:
        return (self.text_align or "").lower() in {"right", "end"}

    @property
    def margin_left_percent(self) -> float:
        value = (self.margin_left or "").strip()
        match = re.match(r"^(-?[0-9.]+)%$", value)
        return float(match.group(1)) if match else 0.0


@dataclass
class ClassStats:
    """Observed shape of the text belonging to one CSS class."""

    count: int = 0
    lengths: list[int] = field(default_factory=list)
    ends_with_punctuation: int = 0
    pure_number: int = 0
    numbered_line: int = 0
    code_like: int = 0
    marker: int = 0
    uppercase_heavy: int = 0
    single_line_words: list[int] = field(default_factory=list)

    def observe(self, text: str) -> None:
        stripped = text.strip()
        if not stripped:
            return
        self.count += 1
        self.lengths.append(len(stripped))
        self.single_line_words.append(len(stripped.split()))
        if stripped[-1] in ".!?:;\"'”’)]}":
            self.ends_with_punctuation += 1
        if _PURE_NUMBER_RE.match(stripped) or _ROMAN_RE.match(stripped):
            self.pure_number += 1
        if _NUMBERED_LINE_RE.match(stripped):
            self.numbered_line += 1
        if _MARKER_RE.match(stripped):
            self.marker += 1
        if _looks_like_code(stripped):
            self.code_like += 1
        letters = [c for c in stripped if c.isalpha()]
        if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
            self.uppercase_heavy += 1

    # -- derived ratios ----------------------------------------------------

    @property
    def median_length(self) -> float:
        return statistics.median(self.lengths) if self.lengths else 0.0

    @property
    def median_words(self) -> float:
        return (
            statistics.median(self.single_line_words) if self.single_line_words else 0.0
        )

    def ratio(self, attribute: str) -> float:
        if not self.count:
            return 0.0
        return getattr(self, attribute) / self.count

    @property
    def symbol_ratio(self) -> float:
        """Fraction of characters that are code-ish punctuation."""
        if not self.lengths:
            return 0.0
        return self.code_like / self.count


def _looks_like_code(text: str) -> bool:
    if not text:
        return False
    symbols = sum(1 for c in text if c in _CODE_SYMBOLS)
    if symbols / len(text) >= 0.12:
        return True
    stripped = text.lstrip()
    if stripped.startswith(("#", "//", "/*", "*", ">>>", "...", "$", "def ", "class ")):
        return True
    if _NUMBERED_LINE_RE.match(text) and symbols >= 2:
        return True
    # Opaque tokens that prose does not contain: quoted fragments, snake_case
    # identifiers, dotted paths, calls, assignments, JSON keys.
    if _QUOTED_FRAGMENT_RE.search(text):
        return True
    if _SNAKE_CASE_RE.search(text):
        return True
    if _DOTTED_PATH_RE.search(text):
        return True
    if _ASSIGNMENT_RE.search(text):
        return True
    return False


def parse_stylesheet(css: str) -> dict[str, ClassDeclarations]:
    """Build ``class name -> declarations`` from a stylesheet.

    Only flat rules are handled, which is what generated EPUB stylesheets use.
    At-rules (``@media``, ``@supports``) are skipped along with everything
    nested inside them, so conditional styles cannot leak into the profile.
    """
    declarations: dict[str, ClassDeclarations] = {}
    for selector, body in _iter_top_level_rules(css):
        props = _parse_declarations(body)
        if not props:
            continue
        for class_name in re.findall(r"\.([A-Za-z0-9_-]+)", selector):
            declarations[class_name] = props
    return declarations


def _iter_top_level_rules(css: str) -> list[tuple[str, str]]:
    """Return ``(selector, declarations)`` for rules outside any at-rule."""
    rules: list[tuple[str, str]] = []
    index = 0
    while index < len(css):
        start = css.find("{", index)
        if start == -1:
            break
        selector = css[index:start].strip()
        if selector.startswith("@"):
            index = _skip_block(css, start)
            continue
        end = css.find("}", start)
        if end == -1:
            break
        # A nested brace means malformed styling; take the innermost span.
        nested = css.find("{", start + 1, end)
        body_start = nested + 1 if nested != -1 else start + 1
        rules.append((selector, css[body_start:end]))
        index = end + 1
    return rules


def _skip_block(css: str, open_index: int) -> int:
    """Return the index just past the block opened at ``open_index``."""
    depth = 0
    for index in range(open_index, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(css)


def _parse_declarations(body: str) -> ClassDeclarations | None:
    found: dict[str, str] = {}
    for part in body.split(";"):
        if ":" not in part:
            continue
        prop, _, value = part.partition(":")
        found[prop.strip().lower()] = value.strip().lower()
    if not found:
        return None
    return ClassDeclarations(
        font_size=_parse_font_size(found.get("font-size")),
        font_weight=found.get("font-weight"),
        font_style=found.get("font-style"),
        text_align=found.get("text-align"),
        margin_left=found.get("margin-left"),
        text_indent=found.get("text-indent"),
        font_family=found.get("font-family"),
    )


def _parse_font_size(value: str | None) -> float | None:
    if not value:
        return None
    match = re.match(r"^(-?[0-9.]+)(em|rem|%|pt|px)?$", value.strip())
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or "em"
    if unit in {"em", "rem"}:
        return number
    if unit == "%":
        return number / 100.0
    if unit == "pt":
        return number / 12.0
    if unit == "px":
        return number / 16.0
    return None


@dataclass
class StyleProfile:
    """Maps CSS classes to structural roles for one book."""

    declarations: dict[str, ClassDeclarations] = field(default_factory=dict)
    paragraph_stats: dict[str, ClassStats] = field(default_factory=dict)
    span_stats: dict[str, ClassStats] = field(default_factory=dict)
    body_font_size: float = 1.0
    roles: dict[str, Role] = field(default_factory=dict)
    span_roles: dict[str, Role] = field(default_factory=dict)
    unclassed_blocks: int = 0
    diagnostics: dict[str, object] = field(default_factory=dict)

    # -- construction ------------------------------------------------------

    @classmethod
    def build(
        cls,
        stylesheets: list[str],
        documents,
        block_tags: frozenset[str] | None = None,
    ) -> StyleProfile:
        profile = cls()
        for css in stylesheets:
            profile.declarations.update(parse_stylesheet(css))
        profile._collect_stats(documents, block_tags or DEFAULT_BLOCK_TAGS)
        profile._infer()
        return profile

    def _collect_stats(self, documents, block_tags: frozenset[str]) -> None:
        for document in documents:
            for element in document.root.iter():
                if not isinstance(element.tag, str):
                    continue
                tag = etree.QName(element).localname
                is_block = tag in block_tags
                if not is_block and tag != "span":
                    continue
                class_name = element.get("class") or ""
                text = "".join(element.itertext())
                if not is_block:
                    for name in class_name.split():
                        self.span_stats.setdefault(name, ClassStats()).observe(text)
                    continue
                if not class_name:
                    # Unclassed blocks still vote on the body font size.
                    self.unclassed_blocks += 1
                    continue
                for name in class_name.split():
                    self.paragraph_stats.setdefault(name, ClassStats()).observe(text)

        weighted: Counter[float] = Counter()
        for name, stats in self.paragraph_stats.items():
            declaration = self.declarations.get(name)
            # Undeclared classes inherit the 1em root size. Without this the
            # mode lands on whichever decorated class happens to be common.
            size = (
                declaration.font_size
                if declaration is not None and declaration.font_size is not None
                else 1.0
            )
            weighted[size] += stats.count
        # Blocks with no class are also 1em, and in many books they are the
        # majority. Leaving them out skews the body size badly.
        if self.unclassed_blocks:
            weighted[1.0] += self.unclassed_blocks
        self.body_font_size = weighted.most_common(1)[0][0] if weighted else 1.0

    # -- inference ---------------------------------------------------------

    def _infer(self) -> None:
        for name, stats in self.paragraph_stats.items():
            self.roles[name] = self._infer_paragraph_role(name, stats)
        for name, stats in self.span_stats.items():
            self.span_roles[name] = self._infer_span_role(name, stats)

        counts = Counter(self.roles.values())
        self.diagnostics = {
            "body_font_size": self.body_font_size,
            "role_counts": {role.value: n for role, n in counts.items()},
            "distinct_paragraph_classes": len(self.paragraph_stats),
            "distinct_span_classes": len(self.span_stats),
        }

    def _infer_paragraph_role(self, name: str, stats: ClassStats) -> Role:
        declaration = self.declarations.get(name, ClassDeclarations())
        size = declaration.font_size if declaration.font_size is not None else 1.0

        if declaration.is_monospace:
            return Role.CODE
        # A class is only a page-number class when every one of its members is
        # short and numeric. Prose fragments in a small, mixed class must never
        # end up verbatim, because verbatim blocks are dropped, not translated.
        if (
            stats.count >= 5
            and stats.median_length <= 8
            and stats.ratio("pure_number") >= 0.75
            and (declaration.is_right_aligned or declaration.margin_left_percent >= 15)
        ):
            return Role.PAGE_NUMBER
        if stats.count >= 5 and stats.ratio("code_like") >= 0.35:
            return Role.CODE
        if size >= self.body_font_size * 1.15:
            return Role.HEADING
        if declaration.is_bold:
            # A run-in label such as "Situation:" is bold and short but belongs
            # to the following paragraph, not to the outline. Italic+bold still
            # counts: Mannings h4/h5 are declared exactly that way.
            is_label = (
                stats.count > 0
                and stats.median_words <= 4
                and stats.ratio("ends_with_punctuation") >= 0.5
            )
            if not is_label and (not stats.count or stats.median_words <= 12):
                return Role.HEADING
        if (
            stats.count >= 3
            and stats.ratio("uppercase_heavy") >= 0.6
            and stats.median_words <= 10
        ):
            return Role.HEADING
        if stats.count and size <= self.body_font_size * 0.7:
            return Role.CAPTION
        # Anything else that carries text is translatable prose. Defaulting to
        # BODY is deliberate: refusing to translate is the expensive mistake.
        return Role.BODY

    def _infer_span_role(self, name: str, stats: ClassStats) -> Role:
        decl = self.declarations.get(name, ClassDeclarations())
        if stats.count < 3:
            return Role.UNKNOWN
        if decl.is_monospace:
            return Role.CODE
        if stats.ratio("marker") >= 0.5:
            return Role.LIST_MARKER
        # A declared bold/italic run is emphasis by definition: inline code is
        # rarely styled that way, and prose emphasis often contains parentheses.
        if decl.is_bold or decl.is_italic:
            return Role.EMPHASIS
        if stats.ratio("code_like") >= 0.5:
            return Role.CODE
        if (
            decl.font_size is not None
            and decl.font_size <= self.body_font_size * 0.9
            and stats.ratio("code_like") >= 0.2
        ):
            return Role.CODE
        return Role.UNKNOWN

    # -- queries -----------------------------------------------------------

    def role_for_paragraph(self, class_name: str | None) -> Role:
        if not class_name:
            # An unclassed text block is prose that must be translated; refusing
            # to translate is the expensive mistake.
            return Role.BODY
        # A block may carry several classes; take the most specific known one.
        roles = [self.roles.get(n) for n in class_name.split()]
        known = [r for r in roles if r and r is not Role.UNKNOWN]
        if known:
            return known[0]
        return Role.BODY

    def role_for_span(self, class_name: str | None) -> Role:
        if not class_name:
            return Role.UNKNOWN
        roles = [self.span_roles.get(n) for n in class_name.split()]
        known = [r for r in roles if r and r is not Role.UNKNOWN]
        if known:
            return known[0]
        return Role.UNKNOWN

    def describe(self) -> str:
        lines = [
            f"body font size: {self.body_font_size}em",
            f"paragraph classes: {len(self.paragraph_stats)}, "
            f"span classes: {len(self.span_stats)}",
            "",
            f"{'class':<22}{'role':<14}{'count':>7}  sample",
        ]
        for name, stats in sorted(
            self.paragraph_stats.items(), key=lambda kv: -kv[1].count
        )[:40]:
            role = self.roles.get(name, Role.UNKNOWN).value
            lines.append(f"{name:<22}{role:<14}{stats.count:>7}")
        return "\n".join(lines)


# Elements that directly carry text. Container tags (div/section/article) are
# excluded so their children's text is not counted twice.
DEFAULT_BLOCK_TAGS = frozenset(
    {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "dd",
        "dt",
        "td",
        "th",
        "blockquote",
        "figcaption",
        "caption",
        "pre",
        "aside",
    }
)
