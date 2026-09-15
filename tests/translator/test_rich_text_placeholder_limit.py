"""Tests for the per-paragraph rich-text placeholder limit.

A paragraph whose inline styling needs more placeholder pairs than
``max_rich_text_placeholders`` is translated as plain text. The predicates below
decide what "needs a placeholder" means; getting them wrong either loses styling
that could have been kept or inflates the count until the limit trips early.
"""

from __future__ import annotations

from babeldoc.format.pdf.document_il import GraphicState
from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il import PdfSameStyleCharacters
from babeldoc.format.pdf.document_il import PdfStyle
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator


class _MappedFont:
    def __init__(self, font_id: str) -> None:
        self.font_id = font_id


class _FontMapper:
    """Maps two source fonts to one output font, or keeps them distinct."""

    def __init__(self, collapse: bool) -> None:
        self.collapse = collapse

    def map(self, font, _size):
        if self.collapse:
            return _MappedFont("out")
        return _MappedFont(f"out-{getattr(font, 'name', 'x')}")


class _Font:
    def __init__(self, name: str) -> None:
        self.name = name


def _translator(collapse: bool = False) -> ILTranslator:
    translator = ILTranslator.__new__(ILTranslator)
    translator.font_mapper = _FontMapper(collapse)
    return translator


def _style(
    font_id: str = "F1", size: float = 10.0, emphasis: str = "plain"
) -> PdfStyle:
    # is_same_style compares font id, font size and the per-character graphics
    # instruction, so emphasis is modelled where bold/italic actually shows up.
    state = GraphicState()
    state.passthrough_per_char_instruction = emphasis
    return PdfStyle(graphic_state=state, font_id=font_id, font_size=size)


def _run(style: PdfStyle) -> PdfParagraphComposition:
    composition = PdfParagraphComposition()
    run = PdfSameStyleCharacters()
    run.pdf_style = style
    composition.pdf_same_style_characters = run
    return composition


class _Paragraph:
    def __init__(self, style: PdfStyle) -> None:
        self.pdf_style = style


FONT_MAP = {"F1": _Font("F1"), "F2": _Font("F2")}


def _needs(run_style: PdfStyle, base_style: PdfStyle, collapse: bool = False) -> bool:
    translator = _translator(collapse)
    return translator._composition_needs_placeholder(
        _run(run_style), _Paragraph(base_style), FONT_MAP
    )


def test_identical_style_needs_no_placeholder():
    """The common case: a uniform paragraph costs nothing at all."""
    assert not _needs(_style(), _style())


def test_size_only_difference_is_treated_as_a_drop_cap():
    """A size ratio strictly inside 0.7-1.3 is a visual effect, not a styled run.

    The bounds are exclusive, so 1.3 exactly is already "too different".
    """
    assert not _needs(_style(size=12.0), _style(size=10.0))
    assert not _needs(_style(size=7.5), _style(size=10.0))
    assert _needs(_style(size=13.0), _style(size=10.0))


def test_size_outside_the_drop_cap_range_does_need_one():
    assert _needs(_style(size=20.0), _style(size=10.0))
    assert _needs(_style(size=5.0), _style(size=10.0))


def test_bold_difference_needs_a_placeholder():
    """Inline emphasis is exactly what the placeholders exist to preserve."""
    assert _needs(_style(emphasis="bold"), _style(emphasis="plain"))


def test_font_only_difference_depends_on_the_output_font():
    """Two source fonts may map to one output font, in which case there is
    nothing to distinguish and no placeholder is needed."""
    assert not _needs(_style(font_id="F2"), _style(font_id="F1"), collapse=True)
    assert _needs(_style(font_id="F2"), _style(font_id="F1"), collapse=False)


def test_a_missing_font_is_conservative():
    """An unknown font id must not silently drop styling."""
    translator = _translator()
    assert translator._composition_needs_placeholder(
        _run(_style(font_id="MISSING")), _Paragraph(_style(font_id="F1")), FONT_MAP
    )


def test_a_composition_without_a_styled_run_is_ignored():
    translator = _translator()
    empty = PdfParagraphComposition()
    assert not translator._composition_needs_placeholder(
        empty, _Paragraph(_style()), FONT_MAP
    )


def test_no_page_font_map_is_conservative():
    translator = _translator()
    assert translator._composition_needs_placeholder(
        _run(_style(font_id="F2")), _Paragraph(_style(font_id="F1")), None
    )


def test_the_limit_is_configurable_and_defaults_above_the_old_hard_coded_40():
    """40 was hard-coded; measured against a real book it recovered almost
    nothing, because affected paragraphs typically need several hundred."""
    import inspect

    from babeldoc.format.pdf.translation_config import TranslationConfig

    signature = inspect.signature(TranslationConfig.__init__)
    assert "max_rich_text_placeholders" in signature.parameters
    assert signature.parameters["max_rich_text_placeholders"].default == 400
    assert "max_rich_text_placeholders" in inspect.getsource(TranslationConfig)
