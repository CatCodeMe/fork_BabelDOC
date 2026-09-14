"""Tests for the EPUB format module.

These run against synthetic documents so they stay fast and deterministic; the
end-to-end behaviour on a real book is exercised by ``tools/epub_probe.py``.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from babeldoc.format.epub.archive import EpubArchive
from babeldoc.format.epub.normalize import NormalizationPolicy
from babeldoc.format.epub.normalize import WordVocabulary
from babeldoc.format.epub.normalize import check_conservation
from babeldoc.format.epub.normalize import is_page_list_segment
from babeldoc.format.epub.normalize import iter_blocks
from babeldoc.format.epub.normalize import looks_like_label_document
from babeldoc.format.epub.normalize import merge_blocks
from babeldoc.format.epub.style_profile import Role
from babeldoc.format.epub.style_profile import StyleProfile
from babeldoc.format.epub.style_profile import is_page_number_text
from babeldoc.format.epub.style_profile import parse_stylesheet
from lxml import etree

XHTML = "http://www.w3.org/1999/xhtml"


# --- fixtures --------------------------------------------------------------


def make_epub(tmp_path: Path, documents: dict[str, str], css: str = "") -> Path:
    """Build a minimal but valid EPUB 3 container."""
    path = tmp_path / "book.epub"
    items = "\n".join(
        f'<item id="d{i}" href="{href}" media-type="application/xhtml+xml"/>'
        for i, href in enumerate(documents, start=1)
    )
    spine = "\n".join(f'<itemref idref="d{i}"/>' for i in range(1, len(documents) + 1))
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title><dc:language>en</dc:language>
    <dc:identifier id="i">urn:uuid:test</dc:identifier>
  </metadata>
  <manifest>{items}</manifest>
  <spine>{spine}</spine>
</package>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr("OEBPS/content.opf", opf)
        if css:
            archive.writestr("OEBPS/style.css", css)
        for href, body in documents.items():
            archive.writestr(
                f"OEBPS/{href}",
                f'<?xml version="1.0" encoding="utf-8"?><html xmlns="{XHTML}">'
                f"<head><title>{href}</title></head><body>{body}</body></html>",
            )
    return path


def doc(html: str):
    """Parse a body fragment into a stand-in EpubDocument."""
    from babeldoc.format.epub.archive import EpubDocument

    root = etree.fromstring(  # noqa: S320 - a literal in this file
        f'<html xmlns="{XHTML}"><head><title>t</title></head><body>{html}</body></html>'
    )
    return EpubDocument(href="doc.xhtml", tree=etree.ElementTree(root), spine_index=0)


def body_text(node) -> str:
    """Visible text of a document or element, excluding <title>."""
    root = getattr(node, "root", node)
    body = root.find(f"{{{XHTML}}}body")
    return "".join((body if body is not None else root).itertext())


def profile_for(*documents, css: str = "") -> StyleProfile:
    return StyleProfile.build([css] if css else [], list(documents))


# --- archive ---------------------------------------------------------------


def test_archive_reads_spine_in_reading_order(tmp_path: Path):
    path = make_epub(
        tmp_path,
        {"a.xhtml": "<p>first</p>", "b.xhtml": "<p>second</p>"},
    )
    with EpubArchive.open(path) as archive:
        assert archive.version == "3.0"
        assert archive.metadata["title"] == "Test Book"
        assert archive.opf_path == "OEBPS/content.opf"
        assert [Path(h).name for h in archive.spine] == ["a.xhtml", "b.xhtml"]
        assert [d.title for d in archive.documents()] == ["a.xhtml", "b.xhtml"]


def test_archive_resolves_relative_hrefs():
    archive = EpubArchive(path=Path("x"), opf_path="", opf_dir="OEBPS", version="")
    assert archive.resolve("chap.xhtml") == "OEBPS/chap.xhtml"
    assert archive.resolve("../img/x.png") == "img/x.png"
    assert archive.resolve("chap.xhtml#p3") == "OEBPS/chap.xhtml"
    assert archive.split_fragment("chap.xhtml#p3") == ("OEBPS/chap.xhtml", "p3")


def test_non_linear_spine_items_are_skipped(tmp_path: Path):
    path = make_epub(tmp_path, {"a.xhtml": "<p>a</p>"})
    with EpubArchive.open(path) as archive:
        assert len(archive.spine) == 1


# --- stylesheet parsing ----------------------------------------------------


def test_stylesheet_parsing_covers_the_useful_declarations():
    parsed = parse_stylesheet(
        ".class_s17 {font-size: 2em; font-weight: bold; margin-top: 0.5em}"
        ".class_s6X {text-align: right}"
        ".class_s1CT {margin-left: 3.125%}"
        "@media print {.ignored {font-size: 99em}}"
    )
    assert parsed["class_s17"].font_size == 2.0
    assert parsed["class_s17"].is_bold
    assert parsed["class_s6X"].is_right_aligned
    assert parsed["class_s1CT"].margin_left_percent == pytest.approx(3.125)
    assert "ignored" not in parsed


# --- role inference --------------------------------------------------------


def test_undeclared_classes_do_not_drag_the_body_size():
    """The mode must fall on the 1em default, not on a rare decorated class."""
    css = ".small {font-size: 0.6em}"
    documents = [doc("<p>prose one.</p>" * 20 + "<p class='small'>caption</p>")]
    profile = profile_for(*documents, css=css)
    assert profile.body_font_size == 1.0


def test_headings_page_numbers_and_code_are_separated():
    css = ".h {font-size: 1.8em; font-weight: bold}\n.pg {text-align: right}"
    body = (
        "<p>This is ordinary prose that ends a sentence.</p>" * 5
        + "<p class='h'>Chapter One</p>"
        + "<p class='pg'>42</p>" * 6
        + '<p class=\'c\'>12 {"role": "user", "content": "hi"},</p>' * 6
    )
    profile = profile_for(doc(body), css=css)
    assert profile.roles["h"] is Role.HEADING
    assert profile.roles["pg"] is Role.PAGE_NUMBER
    assert profile.roles["c"] is Role.CODE


def test_run_in_labels_are_not_headings():
    """ "Situation:" is bold and short but belongs to the next paragraph."""
    css = ".label {font-weight: bold}"
    body = "<p class='label'>Situation:</p>" * 6 + "<p>Body prose here.</p>" * 4
    profile = profile_for(doc(body), css=css)
    assert profile.roles["label"] is Role.BODY


def test_unclassed_blocks_default_to_translatable_prose():
    profile = profile_for(doc("<p>no class here</p>"))
    assert profile.role_for_paragraph(None) is Role.BODY


@pytest.mark.parametrize(
    "text,expected",
    [("42", True), ("xiv", True), ("needed later", False), ("100", True), ("", False)],
)
def test_page_number_text_is_shape_based(text: str, expected: bool):
    assert is_page_number_text(text) is expected


def test_prose_in_a_page_number_class_is_not_dropped():
    """A right-aligned class can hold a few prose fragments; never drop them."""
    css = ".pg {text-align: right}"
    body = "".join(f"<p class='pg'>{n}</p>" for n in range(1, 10)) + (
        "<p class='pg'>needed later</p>"
    )
    profile = profile_for(doc(body), css=css)
    blocks = iter_blocks(doc(body), profile)
    assert profile.roles["pg"] is Role.PAGE_NUMBER
    assert [b.role for b in blocks][-1] is Role.BODY


# --- normalization ---------------------------------------------------------


def test_tails_are_collected_so_inline_markup_keeps_its_text():
    """The bulk of a reflowed book lives in span tails, not in text nodes."""
    body = (
        "<p><span class='m'>•</span> <span class='b'>Bold</span> rest of sentence.</p>"
    )
    profile = profile_for(
        doc(body), css=".m {font-style: italic}\n.b {font-weight: bold}"
    )
    blocks = iter_blocks(doc(body), profile)
    assert len(blocks) == 1
    assert blocks[0].text == "• Bold rest of sentence."


def test_line_fragments_are_joined_into_paragraphs():
    body = (
        "<p>Situation anchors the answer in a real scenario the interviewer can</p>"
        "<p>visualize. It sets the stage.</p>"
    )
    profile = profile_for(doc(body))
    blocks = iter_blocks(doc(body), profile)
    segments, dropped = merge_blocks(
        blocks, WordVocabulary(), NormalizationPolicy(join_lines=True)
    )
    assert len(segments) == 1
    assert segments[0].text == (
        "Situation anchors the answer in a real scenario the interviewer can "
        "visualize. It sets the stage."
    )
    assert dropped == []


def test_line_break_hyphen_is_removed_but_real_compounds_survive():
    vocabulary = WordVocabulary()
    vocabulary.counts.update({"engineers": 3, "multi-agent": 4, "agent": 9})
    assert vocabulary.resolve_hyphen("engi", "neers") == ""
    assert vocabulary.resolve_hyphen("multi", "agent") == "-"


def test_inline_hyphen_only_joined_when_the_book_uses_the_joined_form():
    vocabulary = WordVocabulary()
    vocabulary.counts.update({"consistency": 28, "state-of-the-art": 5})
    assert vocabulary.dehyphenate_inline("cross-validated for consis-tency:") == (
        "cross-validated for consistency:"
    )
    assert vocabulary.dehyphenate_inline("a state-of-the-art system") == (
        "a state-of-the-art system"
    )


def test_page_numbers_are_dropped_and_a_real_paragraph_is_not():
    body = "".join(f"<p class='pg'>{n}</p>" for n in range(1, 9)) + (
        "<p class='pg'>needed later</p>"
    )
    profile = profile_for(doc(body), css=".pg {text-align: right}")
    blocks = iter_blocks(doc(body), profile)
    segments, dropped = merge_blocks(blocks, WordVocabulary())
    assert len(dropped) == 8
    assert all(d.reason == "page number" for d in dropped)
    assert [s.text for s in segments] == ["needed later"]


def test_code_lines_merge_into_one_verbatim_run():
    body = "".join(f"<p class='c'>{n} print(\"x\" + str({n}))</p>" for n in range(1, 6))
    profile = profile_for(doc(body), css=".c {margin-left: 3.125%}")
    blocks = iter_blocks(doc(body), profile)
    segments, _ = merge_blocks(blocks, WordVocabulary())
    assert len(segments) == 1
    assert segments[0].role is Role.CODE
    assert segments[0].text.splitlines()[0] == '1 print("x" + str(1))'


def test_reflow_detection_distinguishes_pdf_reflow_from_native_epub():
    """The decision signal is whether the *next* paragraph continues the line.

    Fragment ratio alone cannot separate the two: native books measure 43%
    fragments because headings, table cells and list items also skip final
    punctuation. The continuation ratio measures ~23% vs ~5%.
    """
    reflow = doc(
        "<p>The questions in this book come from multiple high quality</p>"
        "<p>sources that were cross validated for consistency across</p>"
        "<p>the whole field and then generalised to architectural</p>"
        "<p>understanding rather than product specific knowledge and</p>"
        "<p>we prioritised questions that appeared in many places so</p>"
        "<p>that the resulting list is broadly representative of the</p>"
        "<p>kinds of things interviewers actually tend to ask about</p>"
        "<p>when they evaluate candidates for senior agent roles in</p>"
        "<p>production settings across a range of organisations now</p>"
        "<p>and in the years that follow this particular edition</p>"
    )
    native = doc(
        "<p>The questions in this book come from several sources.</p>"
        "<p>They were cross validated for consistency.</p>"
        "<p>Questions were then generalised to test architecture.</p>"
        "<p>Company specific ones were deliberately excluded.</p>"
        "<p>Questions appearing in many places were prioritised.</p>"
        "<p>The resulting list is broadly representative.</p>"
        "<p>It reflects what interviewers actually ask about.</p>"
        "<p>Senior agent roles are the focus throughout.</p>"
        "<p>Production settings are covered in detail too.</p>"
        "<p>This edition reflects the state of the field.</p>"
    )
    assert NormalizationPolicy.detect(
        iter_blocks(reflow, profile_for(reflow))
    ).is_reflow
    assert not NormalizationPolicy.detect(
        iter_blocks(native, profile_for(native))
    ).is_reflow


def test_a_native_table_of_contents_is_never_glued_into_one_paragraph():
    """Regression: a 244-entry TOC was merged into a single 7,000-char blob."""
    entries = "".join(
        f"<p>1.{n} A chapter section heading that is fairly short</p>"
        for n in range(1, 40)
    )
    document = doc(entries)
    profile = profile_for(document)
    blocks = iter_blocks(document, profile)
    policy = NormalizationPolicy.detect(blocks)
    segments, _ = merge_blocks(blocks, WordVocabulary(), policy)
    assert not policy.is_reflow
    assert len(segments) == 39


def test_table_cells_are_never_merged_across_cells():
    body = (
        "<table><tr><td><p>Cell one text that is long enough to be prose</p></td>"
        "<td><p>Cell two text that is also long enough here</p></td></tr></table>"
    )
    document = doc(body)
    profile = profile_for(document)
    blocks = iter_blocks(document, profile)
    segments, _ = merge_blocks(
        blocks, WordVocabulary(), NormalizationPolicy(join_lines=True)
    )
    assert len(segments) == 2


def test_pre_blocks_are_verbatim_regardless_of_their_class():
    body = "<pre class='readable-text'>def f():\n    return 1</pre>"
    document = doc(body)
    blocks = iter_blocks(document, profile_for(document))
    assert blocks[0].role is Role.CODE


def test_list_items_are_not_merged_into_each_other():
    body = (
        "<ul>"
        + "".join(f"<li>Item {n} of an unordered list</li>" for n in range(1, 12))
        + "</ul>"
    )
    document = doc(body)
    blocks = iter_blocks(document, profile_for(document))
    assert all(b.role is Role.LIST_ITEM for b in blocks)
    segments, _ = merge_blocks(
        blocks, WordVocabulary(), NormalizationPolicy(join_lines=True)
    )
    assert len(segments) == 11


def test_join_limit_counts_the_whole_segment_not_just_the_last_block():
    lines = "".join(
        f"<p>line {n} that keeps going on and on without end</p>" for n in range(1, 60)
    )
    document = doc(lines)
    blocks = iter_blocks(document, profile_for(document))
    segments, _ = merge_blocks(
        blocks,
        WordVocabulary(),
        NormalizationPolicy(join_lines=True, max_join_chars=200),
    )
    assert all(len(s.text) <= 260 for s in segments)
    assert len(segments) > 1


def test_native_epub_paragraphs_are_not_glued_together():
    body = "<p>First paragraph here.</p><p>Second paragraph here.</p>"
    profile = profile_for(doc(body))
    blocks = iter_blocks(doc(body), profile)
    policy = NormalizationPolicy.detect(blocks)
    segments, _ = merge_blocks(blocks, WordVocabulary(), policy)
    assert [s.text for s in segments] == [
        "First paragraph here.",
        "Second paragraph here.",
    ]


def test_page_list_segments_are_recognized():
    assert is_page_list_segment("iv 1 25 51 74 133 165 205")
    assert not is_page_list_segment("Chapter 1 covers agents and tools.")


def test_conservation_reports_no_lost_text():
    body = (
        "<p><span class='m'>•</span> <span class='b'>Bold</span> prose that runs on</p>"
        "<p>and finishes here.</p>"
    )
    document = doc(body)
    profile = profile_for(document)
    blocks = iter_blocks(document, profile)
    segments, dropped = merge_blocks(blocks, WordVocabulary())
    report = check_conservation(blocks, segments, dropped)
    assert report.ok, report.describe()
    assert report.source_chars > 0


# --- write-back ------------------------------------------------------------


def test_replace_mode_writes_the_translation_in_place():
    body = "<p><span class='b'>Bold</span> rest of it.</p>"
    document = doc(body)
    profile = profile_for(document, css=".b {font-weight: bold}")
    blocks = iter_blocks(document, profile)
    segments, _ = merge_blocks(blocks, WordVocabulary())
    segments[0].apply("翻译结果。", mode="replace")
    assert body_text(document) == "翻译结果。"


def test_replace_mode_removes_the_lines_it_absorbed():
    body = "<p>first line of</p><p>the paragraph</p><p>after it.</p>"
    document = doc(body)
    profile = profile_for(document)
    blocks = iter_blocks(document, profile)
    segments, _ = merge_blocks(
        blocks, WordVocabulary(), NormalizationPolicy(join_lines=True)
    )
    assert len(segments[0].blocks) == 3
    segments[0].apply("译文。", mode="replace")
    assert body_text(document) == "译文。"


def test_bilingual_mode_keeps_the_source_and_adds_a_translation():
    body = "<p>Source sentence.</p>"
    document = doc(body)
    profile = profile_for(document)
    blocks = iter_blocks(document, profile)
    segments, _ = merge_blocks(blocks, WordVocabulary())
    segments[0].apply("译文。", mode="bilingual")
    paragraphs = list(document.root.iter(f"{{{XHTML}}}p"))
    assert [p.text for p in paragraphs] == ["Source sentence.", "译文。"]
    assert "bdoc-translation" in paragraphs[1].get("class")


def test_write_back_preserves_inline_markup_in_the_source():
    body = "<p>Keep <b>this bold</b> markup.</p>"
    document = doc(body)
    profile = profile_for(document)
    blocks = iter_blocks(document, profile)
    segments, _ = merge_blocks(blocks, WordVocabulary())
    segments[0].apply("保留这段译文。", mode="bilingual")
    html = etree.tostring(document.root, encoding="unicode")
    assert "<b>this bold</b>" in html


# --- side-by-side bilingual layout -----------------------------------------


def _side_by_side(body: str, translation: str, css: str = "", lang: str = "zh-CN"):
    document = doc(body)
    profile = profile_for(document, css=css)
    blocks = iter_blocks(document, profile)
    segments, _ = merge_blocks(
        blocks, WordVocabulary(), NormalizationPolicy(join_lines=True)
    )
    segments[0].apply(translation, mode="side_by_side", lang=lang)
    return document


def _first_pair(node):
    root = getattr(node, "root", node)
    return root.find(f".//{{{XHTML}}}div[@class='bdoc-pair']")


def test_side_by_side_puts_the_source_left_and_the_translation_right():
    document = _side_by_side("<p>A single source paragraph.</p>", "一段译文。")
    pair = _first_pair(document)
    cells = [c.get("class") for c in pair]
    assert cells == ["bdoc-src", "bdoc-dst"]
    assert body_text(pair[0]).strip() == "A single source paragraph."
    assert body_text(pair[1]).strip() == "一段译文。"


def test_side_by_side_keeps_every_source_block_in_the_left_cell():
    """A folded paragraph keeps its original lines, so nothing is destroyed."""
    document = _side_by_side(
        "<p>first line of the</p><p>paragraph that continues</p><p>here.</p>",
        "译文。",
    )
    pair = _first_pair(document)
    source_lines = [p.text for p in pair[0].findall(f"{{{XHTML}}}p")]
    assert source_lines == ["first line of the", "paragraph that continues", "here."]


def test_side_by_side_keeps_the_block_tag_and_class_for_the_translation():
    """Same layout as the original: a heading stays a heading."""
    document = _side_by_side(
        "<p class='readable-text-h3'>Chapter One</p>",
        "第一章",
        css=".readable-text-h3 {font-weight: bold}",
    )
    pair = _first_pair(document)
    translated = pair[1].find(f"{{{XHTML}}}p")
    assert translated.tag == f"{{{XHTML}}}p"
    # The original class survives, with the marker class appended.
    assert "readable-text-h3" in translated.get("class")


def test_side_by_side_tags_the_translation_with_the_target_language():
    document = _side_by_side("<p>Source.</p>", "译文。", lang="zh-CN")
    assert _first_pair(document)[1].get("lang") == "zh-CN"


def test_side_by_side_preserves_inline_markup_and_links_in_the_source():
    body = "<p>See <a href='other.xhtml#x'>this link</a> and <b>bold</b> text.</p>"
    document = _side_by_side(body, "译文。")
    pair = _first_pair(document)
    assert pair[0].find(f".//{{{XHTML}}}a").get("href") == "other.xhtml#x"
    assert pair[0].find(f".//{{{XHTML}}}b") is not None


def test_side_by_side_inside_a_list_item_does_not_break_the_list():
    """A div may not sit between ul and li, so the pair goes inside the li."""
    body = "<ul><li>An item of the list that is long enough</li></ul>"
    document = _side_by_side(body, "列表项译文。")
    unordered = document.root.find(f".//{{{XHTML}}}ul")
    items = unordered.findall(f"{{{XHTML}}}li")
    assert len(items) == 1
    assert "bdoc-paired" in items[0].get("class")
    assert _first_pair(document) is not None
    # The list marker must survive: the li is still a list item, not a flex row.
    collapsed = "".join(body_text(items[0]).split())
    assert collapsed == "Anitemofthelistthatislongenough列表项译文。"


def test_side_by_side_inside_a_table_cell_keeps_the_cell():
    body = (
        "<table><tr><td><p>Cell text that is long enough to count</p></td></tr></table>"
    )
    document = _side_by_side(body, "单元格译文。")
    cell = document.root.find(f".//{{{XHTML}}}td")
    assert cell is not None
    assert _first_pair(cell) is not None


def test_side_by_side_does_not_translate_a_code_block():
    body = "<pre class='code-area'>x = compute(1)</pre>"
    document = doc(body)
    profile = profile_for(document, css=".code-area {font-size: 0.8rem}")
    blocks = iter_blocks(document, profile)
    assert blocks[0].role is Role.CODE
    assert blocks[0].slots and blocks[0].slots[0].is_code


# --- repackaging -----------------------------------------------------------


def _roundtrip(tmp_path: Path, documents: dict[str, str], css: str = ""):
    from babeldoc.format.epub.writer import inject_stylesheet
    from babeldoc.format.epub.writer import repack
    from babeldoc.format.epub.writer import stylesheet_href_for

    source = make_epub(tmp_path, documents, css=css)
    output = tmp_path / "out.epub"
    with EpubArchive.open(source) as archive:
        changed = {}
        for document in archive.documents():
            inject_stylesheet(stylesheet_href_for(document.href, archive.opf_dir))(
                document.tree
            )
            changed[document.href] = document.tree
        result = repack(archive, output, changed)
    return source, output, result


def test_repack_writes_mimetype_first_and_uncompressed(tmp_path: Path):
    _source, output, _result = _roundtrip(tmp_path, {"a.xhtml": "<p>hi</p>"})
    with zipfile.ZipFile(output) as archive:
        infos = archive.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"


def test_repack_only_rewrites_changed_documents(tmp_path: Path):
    """Untouched entries keep their exact bytes, so images can never be damaged."""
    from babeldoc.format.epub.writer import repack

    source = make_epub(tmp_path, {"a.xhtml": "<p>a</p>", "b.xhtml": "<p>b</p>"})
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr("OEBPS/photo.jpg", b"\xff\xd8\xff\xe0binary-jpeg-payload")
    output = tmp_path / "out.epub"
    with EpubArchive.open(source) as archive:
        # Only rewrite document b.
        tree = etree.ElementTree(archive.parse_xhtml("OEBPS/b.xhtml"))
        repack(archive, output, {"OEBPS/b.xhtml": tree}, bilingual=False)
    with zipfile.ZipFile(output) as archive:
        assert archive.read("OEBPS/photo.jpg") == b"\xff\xd8\xff\xe0binary-jpeg-payload"
        assert b"<p>a</p>" in archive.read("OEBPS/a.xhtml")


def test_repack_registers_and_links_the_bilingual_stylesheet(tmp_path: Path):
    from babeldoc.format.epub.writer import BILINGUAL_CSS
    from babeldoc.format.epub.writer import BILINGUAL_CSS_NAME

    _source, output, result = _roundtrip(tmp_path, {"a.xhtml": "<p>hi</p>"})
    assert result.stylesheet_added
    with zipfile.ZipFile(output) as archive:
        assert archive.read(f"OEBPS/{BILINGUAL_CSS_NAME}").decode() == BILINGUAL_CSS
        opf = archive.read("OEBPS/content.opf").decode()
        assert "text/css" in opf and BILINGUAL_CSS_NAME in opf
        document = archive.read("OEBPS/a.xhtml").decode()
        # a.xhtml sits next to the stylesheet, so the href is a bare filename
        assert BILINGUAL_CSS_NAME in document


def test_stylesheet_href_is_relative_to_each_document():
    from babeldoc.format.epub.writer import BILINGUAL_CSS_NAME
    from babeldoc.format.epub.writer import stylesheet_href_for
    from babeldoc.format.epub.writer import stylesheet_path

    # The stylesheet lives beside the OPF, so siblings need no path prefix.
    assert stylesheet_path("OEBPS") == f"OEBPS/{BILINGUAL_CSS_NAME}"
    assert stylesheet_href_for("OEBPS/a.xhtml", "OEBPS") == BILINGUAL_CSS_NAME
    assert (
        stylesheet_href_for("OEBPS/chapters/a.xhtml", "OEBPS")
        == f"../{BILINGUAL_CSS_NAME}"
    )


def test_bilingual_stylesheet_collapses_to_one_column_on_narrow_screens():
    """Two columns of prose on a phone would be unreadable."""
    from babeldoc.format.epub.writer import BILINGUAL_CSS

    assert "@media (max-width: 45em)" in BILINGUAL_CSS
    assert "display: block" in BILINGUAL_CSS
    assert "bdoc-paired" in BILINGUAL_CSS or "bdoc-pair" in BILINGUAL_CSS


def test_label_documents_are_detected_so_a_table_of_contents_is_not_paired():
    """A 244-entry TOC in two columns is a wall of text, not a reading aid."""
    from babeldoc.format.epub.normalize import MergeMode
    from babeldoc.format.epub.normalize import Segment

    def segments(texts):
        return [
            Segment(
                href="contents.html",
                index=i,
                role=Role.BODY,
                text=t,
                blocks=[],
                mode=MergeMode.SINGLE,
            )
            for i, t in enumerate(texts)
        ]

    toc = segments([f"1.{n} A short section heading" for n in range(1, 40)])
    assert looks_like_label_document(toc)

    prose = segments(
        [
            "This is a full sentence that ends with a full stop.",
            "Another complete sentence that also ends properly.",
        ]
        * 6
    )
    assert not looks_like_label_document(prose)

    # Too few segments to judge anything.
    assert not looks_like_label_document(toc[:3])
