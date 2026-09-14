# EPUB input support — task plan

## Decision (2026-09-13, revised)

**Translate EPUB natively. No PDF conversion.**

The earlier "EPUB → PDF → reuse the PDF pipeline" plan is rejected. See
`findings.md` §2 for the evidence: the PDF pipeline spends ~41% of its runtime
recovering structure that EPUB already has, and every one of the 22 fork-local
commits to date is a fix for that recovery machinery.

Scope is deliberately **DOM-level, with no intermediate representation**. The PDF
IL exists to express *geometry*; EPUB needs none.

## Goal

Translate EPUB books with BabelDOC's speed and output quality, producing a
**reflowable bilingual EPUB** (plus a mono translated EPUB) rather than a
bilingual PDF.

## Deliverable

**Bilingual EPUB, side by side.** Original on the left, translation on the
right, in one flex row per paragraph pair, with the translation keeping the
source block's tag and class so headings, code and lists look the same on both
sides.

This replaces the interleaved ("source paragraph, then translation paragraph")
layout, which interrupts reading every few lines.

**Constraint to be explicit about:** an EPUB has no pages, so "two columns on a
page" can only be expressed as "two columns per block". The columns therefore do
not align line-by-line the way a fixed-layout PDF can align them. What you get
instead is two continuously readable columns. Below 45em the stylesheet collapses
to stacked layout, because two columns of prose on a phone is unreadable.

Acceptance criteria:

- Output is a valid EPUB 3 that passes `epubcheck`.
- Every internal `href`, `id` and `src` in the source survives unchanged.
- No source text is silently lost (asserted by the conservation check).
- Bilingual reading works: reflow, font scaling, dark mode, TOC, footnotes,
  images at native resolution, searchable text.
- Code is never translated; inline code and code blocks stay byte-identical.

## Phases

1. [x] **Phase 0 — analysis layer.** EPUB container → spine → XHTML DOM, plus
   CSS/corpus role inference (`archive.py`, `style_profile.py`) and the block
   stream. Measured end to end by `tools/epub_probe.py`.
2. [x] **Phase 1 — reflow normalizer.** Fold typeset lines back into
   paragraphs, undo line-break hyphenation, drop print page numbers and page
   lists, merge code runs, recover list markers (`normalize.py`).
3. [x] **Phase 3 — write-back and packaging.** `side_by_side`, `bilingual` and
   `replace` modes, injected stylesheet, ZIP repackaging that re-serialises only
   the documents that changed (`writer.py`).
4. [x] **Phase 2 — translation client.** `client.py`: reuses
   `OpenAITranslator` + `Glossary` + the prompt files, batches segments as JSON
   (validated against the returned ids), and degrades to per-segment retries and
   then to source text rather than aborting a book.
5. [ ] **Phase 4 — CLI wiring.** `babeldoc --epub book.epub`. Chapters are
   independent documents, so work is chunked by chapter: no page-count splitting
   and no merge step.

Still to do before Phase 4: lift the format-agnostic prompt/glossary/config code
out of `format/pdf/` so both paths share it instead of the EPUB path carrying its
own copy (see Guardrails).

## Guardrails

- **Do not build a new IL and do not touch `document_il/`.** If a change seems
  to need the PDF layout model, the design has gone wrong.
- The EPUB modules must not import from `babeldoc.format.pdf.*` except for the
  two genuinely shared modules below.
- Reuse, do not fork: `babeldoc/translator/translator.py` (377 lines, zero PDF
  imports), `babeldoc/translator/cache.py`, `babeldoc/glossary.py`,
  `prompts/*.txt`, `glossaries/*.csv`.
- Only re-serialize XHTML documents that actually changed; copy every other ZIP
  entry byte-for-byte.
- Never drop a block because of its CSS class alone — confirm against the block
  text. Dropping real prose is far worse than keeping a stray page number.
- Do not commit generated EPUBs, `output/`, `work/`, `tmp/`, or any local
  `babeldoc.*.toml` (API key). A `pre-commit` credential scan is installed.
- Do not disturb the uncommitted PDF-path changes that predate this branch.

## Acceptance evidence so far

Two real books, deliberately chosen as opposite extremes.

**PDF reflow** — *Cracking the AI Agent Interview* (2.2 MB, 55 documents, 11,382
`<p>` that are typeset lines, no `<pre>`/`<ul>`/`<table>` at all):

```
book shape      : PDF reflow (continuation ratio 23.2%, fragment ratio 40.9%)
blocks in       : 11399
segments out    : 1797   (9394 lines folded into paragraphs)
dropped         : 333    (print page numbers and page lists)
conservation    : missing 0, duplicated 0
```

**Native EPUB** — *AI Agents in Action, 2nd ed.* (10 MB, 23 documents, real
`<h2>`–`<h5>`, `<pre>`, `<code>`, `<ul>`, `<td>`, 118 images):

```
book shape      : native EPUB (continuation ratio 4.6%, fragment ratio 43.4%)
blocks in       : 4602
segments out    : 4183   (no joining: paragraphs stay paragraphs)
dropped         : 0
conservation    : missing 0, duplicated 0
```

**End-to-end packaging** on a 5-document slice of the native EPUB (14,024
characters, `tools/epub_bilingual.py --dry-run`):

```
segments        : 278 (278 written)
conservation    : source 14024 = segments 14024 + dropped 0 (missing 0, duplicated 0)
output          : tmp/ai-agents-5pages.epub
  documents rewritten: 7    (5 documents + OPF + stylesheet)
  entries copied     : 139
  zip integrity      : OK
  XML well-formedness: OK
  binary assets      : 118/118 byte-identical
```

Verified in the output: `mimetype` first and stored, stylesheet registered in the
OPF and linked as `../babeldoc-bilingual.css` from `OEBPS/Text/*.html`, and 244
`bdoc-pair` rows in the table of contents alone.

**Real translation** on a 7-document slice of the native EPUB (150 segments,
`deepseek-v4-flash`, batch size 8, `prompts/en-zh-technical.txt`):

```
segments        : 319 (150 translated)
conservation    : source 25629 = segments 25629 + dropped 0 (missing 0, duplicated 0)
model calls     : 20 (0 cache hits after a prompt change)
wall clock      : 24 s
output          : tmp/ai-agents-real-few-pages.epub
  zip integrity      : OK
  XML well-formedness: OK
```

Quality check over the 150 pairs: 143 carry a Chinese translation, the 7 that do
not are headings and proper nouns. Remaining English words are all recognised
technical terms the prompt asks to keep (`agent`, `guardrails`, `prompt`,
`token`, `temperature`, `persona`). One real defect was found and fixed:
"photocopying" came back untranslated inside an otherwise Chinese sentence,
which the batch rules now forbid explicitly.

Extrapolated cost for the whole book (4,183 segments): roughly 560 requests,
about 11 minutes at the observed 1.2 s per request.

74 unit tests pass (`tests/test_epub_format.py`, `tests/test_epub_client.py`,
`tests/test_check_secrets.py`).

## Open questions

- Mono output too, or bilingual only?
- Code blocks: leave them source-only, or duplicate code in the right column so
the columns stay aligned around a listing?
- Footnotes and figure captions: pair them, or leave them untranslated in place?
- Should the EPUB and PDF paths share a CLI (`babeldoc --files` sniffing the
format) or stay separate entry points?
