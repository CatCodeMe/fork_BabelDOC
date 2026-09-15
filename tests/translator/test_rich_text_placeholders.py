import re

from babeldoc.format.pdf.document_il import PdfSameStyleCharacters
from babeldoc.format.pdf.document_il import PdfStyle
from babeldoc.format.pdf.document_il.midend.il_translator import ILTranslator
from babeldoc.format.pdf.document_il.midend.il_translator import RichTextPlaceholder
from babeldoc.tools.executor.translator import ExecutorTranslator
from babeldoc.translator.translator import OpenAITranslator


def _assert_opaque_style_markers(translator_type):
    translator = translator_type.__new__(translator_type)
    left, left_pattern = translator.get_rich_text_left_placeholder(7)
    right, right_pattern = translator.get_rich_text_right_placeholder(7)

    assert left == "{{bdoc_style_7}}"
    assert right == "{{/bdoc_style}}"
    assert "<" not in left and "<" not in right
    assert re.fullmatch(left_pattern, left)
    assert re.fullmatch(right_pattern, right)


def test_openai_rich_text_markers_are_opaque_tokens():
    _assert_opaque_style_markers(OpenAITranslator)


def test_executor_rich_text_markers_are_opaque_tokens():
    _assert_opaque_style_markers(ExecutorTranslator)


def _parser_with_style_patterns():
    parser = ILTranslator.__new__(ILTranslator)
    parser._formula_placeholder_pattern = re.compile(r"\{\s*v\s*\d+\s*\}")
    parser._style_left_placeholder_pattern = re.compile(
        r"\{\{\s*bdoc_style_\d+\s*\}\}", re.IGNORECASE
    )
    parser._style_right_placeholder_pattern = re.compile(
        r"\{\{\s*/\s*bdoc_style\s*\}\}", re.IGNORECASE
    )
    return parser


def _style_input():
    style = PdfStyle(font_id="Bold", font_size=11)
    placeholder = RichTextPlaceholder(
        1,
        PdfSameStyleCharacters(pdf_style=style),
        "{{bdoc_style_1}}",
        "{{/bdoc_style}}",
        r"\{\{\s*bdoc_style_1\s*\}\}",
        r"\{\{\s*/\s*bdoc_style\s*\}\}",
    )
    return ILTranslator.TranslateInput(
        "{{bdoc_style_1}}source{{/bdoc_style}}", [placeholder], PdfStyle()
    ), style


def test_rich_text_output_restores_the_style_without_visible_markers():
    parser = _parser_with_style_patterns()
    input_text, style = _style_input()

    result = parser.parse_translate_output(
        input_text, "{{bdoc_style_1}}译文{{/bdoc_style}}"
    )

    text = result[0].pdf_same_style_unicode_characters
    assert text.unicode == "译文"
    assert text.pdf_style is style


def test_unpaired_internal_style_marker_is_removed_from_visible_text():
    parser = _parser_with_style_patterns()
    input_text, _ = _style_input()

    result = parser.parse_translate_output(input_text, "译文{{bdoc_style_1}}")

    assert result[0].pdf_same_style_unicode_characters.unicode == "译文"


def test_hallucinated_style_marker_is_removed_without_source_style():
    parser = _parser_with_style_patterns()
    input_text = ILTranslator.TranslateInput("source", [], PdfStyle())

    result = parser.parse_translate_output(
        input_text, "译文{{bdoc_style_1}}一致性模型{{/bdoc_style}}"
    )

    assert result[0].pdf_same_style_unicode_characters.unicode == "译文一致性模型"
