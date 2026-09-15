from babeldoc.format.pdf.document_il.utils.formular_helper import is_formulas_font


def test_txfonts_math_italic_is_protected_as_formula_text():
    assert is_formulas_font("txmiaX", None)
