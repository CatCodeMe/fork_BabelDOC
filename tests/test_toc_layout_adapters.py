from types import SimpleNamespace

from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.midend.paragraph_finder import TocLayoutAdapter


def _composition(text: str, right_edge: float):
    return SimpleNamespace(
        pdf_line=SimpleNamespace(
            pdf_character=[SimpleNamespace(char_unicode=char) for char in text],
            box=SimpleNamespace(x2=right_edge),
        )
    )


def test_now_style_numbered_contents_rows_are_kept_separate():
    rows = [
        _composition("1 Introduction 204", 425.0),
        _composition("1.1 Perspectives on B-trees 204", 425.0),
        _composition("1.2 Purpose and Scope 206", 425.0),
        _composition("1.3 New Hardware 207", 425.0),
    ]

    assert ParagraphFinder._toc_row_ranges(rows, TocLayoutAdapter("auto")) == [(0, 3)]


def test_body_lines_and_misaligned_numbers_are_not_treated_as_contents():
    rows = [
        _composition("This is ordinary prose ending in 2010", 425.0),
        _composition("1 Introduction 204", 425.0),
        _composition("1.1 Perspectives on B-trees 204", 449.0),
    ]

    assert ParagraphFinder._toc_row_ranges(rows, TocLayoutAdapter("auto")) == []


def test_numbered_row_requires_a_terminal_page_number():
    assert not ParagraphFinder._is_numbered_toc_row("3.1 Node Size")
    assert ParagraphFinder._is_numbered_toc_row("3.1 Node Size 232")
