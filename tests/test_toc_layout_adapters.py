from types import SimpleNamespace

from babeldoc.format.pdf.document_il.midend.paragraph_finder import ParagraphFinder
from babeldoc.format.pdf.document_il.midend.paragraph_finder import TocLayoutAdapter


def _composition(text: str, right_edge: float):
    return SimpleNamespace(
        pdf_line=SimpleNamespace(
            pdf_character=[SimpleNamespace(char_unicode=char) for char in text],
            box=SimpleNamespace(x=0.0, x2=right_edge),
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


def test_oreilly_rows_keep_wrapped_titles_with_their_page_number():
    rows = [
        _composition("DeepSeek Scales to 680-Billion Parameter Models", 381.0),
        _composition("Despite Hardware Restrictions in China 9", 432.0),
        _composition("Toward 100-Trillion-Parameter Models 11", 432.0),
        _composition("Key Takeaways 20", 432.0),
    ]
    assert ParagraphFinder._oreilly_toc_row_ranges(rows, TocLayoutAdapter("oreilly")) == [(0, 1), (2, 2), (3, 3)]


def test_manning_chapter_cover_bullets_remain_separate_items():
    rows = [_composition(text, 300.0) for text in ("■ What reasoning means", "■ Reviewing pretraining", "■ Introducing key approaches")]
    assert ParagraphFinder._bullet_list_ranges(rows) == [(0, 0), (1, 1), (2, 2)]


def test_manning_inverted_exclamation_bullets_remain_separate_items():
    rows = [_composition(text, 300.0) for text in ("¡ What reasoning means", "¡ Reviewing pretraining", "¡ Introducing key approaches")]
    assert ParagraphFinder._bullet_list_ranges(rows) == [(0, 0), (1, 1), (2, 2)]


def test_manning_appendix_label_stays_with_its_square_marker_row():
    rows = [
        _composition("■ Understanding reasoning models", 300.0),
        _composition("appendix A", 300.0),
        _composition("■ References and further reading 305", 300.0),
        _composition("appendix B", 300.0),
        _composition("■ Exercise solutions 314", 300.0),
    ]
    assert ParagraphFinder._manning_row_ranges(rows) == [(0, 0), (1, 2), (3, 4)]


def test_traction_ordinal_bullet_contents_rows_are_separate():
    rows = [
        _composition("Prologue v", 400.0),
        _composition("Traction Channels 1 1 •", 400.0),
        _composition("The Bullseye Framework 9 2 •", 400.0),
        _composition("Traction Thinking 19 3 •", 400.0),
        _composition("Afterword 249 25 •", 400.0),
    ]
    assert ParagraphFinder._traction_toc_row_ranges(rows) == [
        (0, 0),
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
    ]


def test_generic_body_list_requires_three_matching_items_and_keeps_wrapped_lines():
    rows = [
        _composition("- First item", 300.0),
        _composition("  continuation", 300.0),
        _composition("- Second item", 300.0),
        _composition("- Third item", 300.0),
    ]
    assert ParagraphFinder._generic_list_item_ranges(rows) == [(0, 1), (2, 2), (3, 3)]
