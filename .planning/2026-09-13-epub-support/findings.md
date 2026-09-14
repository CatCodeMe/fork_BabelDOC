# EPUB input for BabelDOC — findings and decision

- Date: 2026-09-13 (revised after measurement)
- Branch: `codex/epub-support-20260913`
- Status: **decided — native EPUB, DOM-level, no IL, no PDF conversion**

## 中文摘要 (TL;DR)

- **结论：直接翻译 EPUB，不做 EPUB→PDF。** 需求上不要求 PDF 交付。
- 否决 PDF 路线是**用本仓库自己的数据**证明的：
  - 22 个 fork 自有 commit 里 **21 个**是 PDF 版面恢复（目录行、大纲、链接、
    项目符号），EPUB 里这些结构本来就有；
  - 官方管线权重表里 **41%（54.06/131.02）** 是纯 PDF 结构恢复机械；
  - EPUB→PDF 还会丢 MathML、断脚注链接、不保证文字抽取质量。
- 关键设计判断：**不建新的 IL。** PDF IL 是用来表达*几何*的，EPUB 不需要几何。
  `translator.py`（377 行）、`cache.py`、`glossary.py` 共 591 行**零 PDF 依赖**，
  直接复用。
- 最大收益：EPUB 的 inline 标记留在 DOM 里，翻译只写回文本节点 →
  `{{bdoc_style_N}}` 占位符机制**整体不需要存在**，占位符泄漏这类 bug
  在原理上不可能发生。
- 已实测（2.2MB / 75 万字测试书）：11,399 个 block → 1,476 个待翻译 segment，
  **字符守恒缺失 0**，55 个单测通过。
- 测试书是**最坏情况**：它其实是「PDF 重排成 EPUB」——11,382 个 `<p>` 是排版行
  而不是段落（32.4% 不以句末标点结尾）、632 行以连字符断行、618 个纯页码段落、
  没有 `<pre>`/`<ul>`/`<table>`。下面的分层设计正是为了处理它，而干净的 EPUB
  会走更简单的路径。

## 1. Why the PDF route was rejected

### 1.1 The fork's own history is 100% PDF structure recovery

```
git rev-list --count 38d3896..HEAD   →   22
```

Of those 22 commits, 21 are PDF-layout work:

| Category | Commits | What it is in EPUB |
|---|---|---|
| Contents/TOC row recovery | `c281612` `658dac3` `877d521` `7a14ae5` `b20b6e7` `83f0cce` `95e9ef5` `8c3d49b` `7892bb7` `77f494f` | `nav.xhtml` / NCX — translating a list of `<a>` labels |
| Navigation, outline, links | `e5d5c99` `c7682fa` `5537e56` `4efdc03` `869a6dc` `50746b2` | spine + outline, `<a href>` |
| Detached bullets / rows | `fbb0e2c` | `<li>` |
| Rich-text placeholder leaks | `31de4e1` | impossible by construction |

Feeding EPUB through PDF re-imports this entire bug surface.

### 1.2 41% of the pipeline is PDF-only machinery

From `babeldoc/format/pdf/high_level.py:60` (`TRANSLATE_STAGES`, progress-bar cost
weights):

| PDF-only stage | weight |
|---|---|
| Parse PDF and Create IR | 14.12 |
| DetectScannedFile | 2.45 |
| LayoutParser (doclayout ONNX) | 14.03 |
| TableParser | 1.00 |
| ParagraphFinder (1520 lines) | 6.26 |
| StylesAndFormulas (1276 lines) | 1.66 |
| Typesetting | 4.71 |
| FontMapper | 0.61 |
| PDFCreater | 1.96 |
| SubsetFont | 0.92 |
| SavePDF | 6.34 |
| **subtotal** | **54.06** |

Against `AutomaticTermExtractor` 30.00 + `ILTranslator` 46.96, i.e. **41.3% of the
pipeline is structure recovery EPUB does not need.** A large part of
`ILTranslator`'s share is the placeholder encode/decode/repair machinery, which
is also unnecessary.

### 1.3 EPUB→PDF loses things that matter for this fork

- **MathML**: WeasyPrint does not render it (`Kozea/WeasyPrint#59`, open since
  2013; #2171/#2172 closed unfixed in 2024). This fork invests heavily in
  formulas, so this alone is disqualifying for A2.
- **Footnotes**: `epub:type="noteref"` and `<aside epub:type="footnote">` break
  in EPUB→PDF (Calibre bug #1849529; pandoc #7884 drops the attribute).
- **Text extraction is not guaranteed**: WeasyPrint has a history of ToUnicode
  CMap defects (#2841 empty `bfchar`; pypdf #242).
- **No header/footer stripping exists in this fork's midend**, so any header or
  footer a converter adds becomes junk prose to translate.

## 2. Why "native EPUB" is much cheaper than it first looked

The earlier estimate said a native module needs "a new frontend and backend plus
either redefining the IL or detaching the translators from PDF geometry". That
framing is what made it look like multi-day unknown scope. Reading the code:

- `babeldoc/translator/translator.py` (377 lines) — **zero PDF imports**. It
  imports only `cache.py`, one exception class and `AtomicInteger`.
- `babeldoc/translator/cache.py` — peewee + sqlite, **zero PDF imports**.
- `babeldoc/glossary.py` (214 lines) — **zero PDF imports**.

So **591 lines are reusable as-is**, and the IL can simply be skipped: it is a
*layout* model (`Page`, mediabox, `PdfFont`, `GraphicState`).

The decisive consequence: because inline markup stays in the DOM, a paragraph
`<p>Hello <b>world</b>!</p>` is translated by writing into its three text nodes.
`<b>` is never sent to the model. No `{{bdoc_style_N}}` tokens, no
`parse_translate_output`, no `removed_hallucinated_placeholders`.

The only genuine refactor is that the prompt/glossary/config code is currently
trapped inside PDF-coupled modules: `_build_role_block`, `_build_context_block`,
`_build_glossary_block` and `generate_prompt_for_llm` live in `il_translator.py`
(~250 lines) and the glossary/prompt parts of `TranslationConfig` live in
`format/pdf/translation_config.py` (602 lines). Extracting those is mechanical
and benefits the PDF path too.

### Cost estimate (revised)

| Module | Job | Lines |
|---|---|---|
| `archive.py` | container → OPF → spine → XHTML, ZIP access | ~230 |
| `style_profile.py` | CSS + corpus → class roles | ~480 |
| `normalize.py` | block stream, line joining, de-hyphenation, drops, segments | ~560 |
| translation client | reuse `OpenAITranslator` + glossary + prompts | ~200 |
| `epub_writer.py` | write-back, bilingual, repackage | ~150 |

≈ 1,600 lines, of which ~1,270 are already written and tested.

## 3. Measured behaviour on real books

Two books, chosen as opposite extremes. This is the evidence that the whole
design hinges on, so both are measured rather than assumed.

### 3.1 Test book A — a PDF reflow

`Cracking the AI Agent Interview … .epub` — 2.2 MB, 55 spine documents, ~755k
characters, EPUB 3.0.

| Observation | Value |
|---|---|
| `<p>` elements | 11,382 (median length 56 chars → typeset lines) |
| Body lines not ending a sentence | 4,548 (**40%**) |
| Lines ending in a hyphen | 632 |
| Bare print page numbers | 618 |
| `<pre>` / `<code>` / `<ul>` / `<ol>` / `<table>` | **0** |
| `<span>` elements | 12,310 |
| `<a>` / `<img>` | 12 / 2 |

The stylesheet declares no `font-family` at all, so code cannot be detected by
typography and has to come from corpus statistics.

### 3.2 Test book B — a genuine Manning EPUB

`AI Agents in Action, Second Edition.epub` — 10 MB, 23 spine documents, EPUB 2.0,
118 images, a woff2 font, `toc.ncx`, **real semantic tags**: `<h2>` 81, `<h3>`
173, `<h4>` 34, `<h5>` 252, `<pre>` 156, `<code>` 424, `<ul>` 99, `<ol>` 69,
`<li>` 767, `<td>` 394. Class names are semantic (`readable-text`,
`readable-text-h3`, `code-area`, `_TableBody`, `listing-container-h5`).

This book is what the format is supposed to look like, and it is the reason the
detector below had to be fixed: the first version classified it as a reflow and
folded its **244-entry table of contents into a single paragraph**.

### 3.3 Distinguishing the two

A naive "fraction of blocks not ending in sentence punctuation" fails badly: the
native EPUB measures **43.4%** fragments, slightly *more* than the reflow's 32.5%,
because native books are full of headings, table cells and list items that also
skip final punctuation.

The signal that actually separates them: **a paragraph that ends mid-sentence is
only evidence of a reflow when the next paragraph continues it.** Measured over
`<p>` blocks with ≥40 characters outside tables:

| Book | continuation ratio | fragment ratio |
|---|---|---|
| PDF reflow | **23.2%** | 40.9% |
| native EPUB | **4.6%** | 16.4% |

Threshold: 10%, giving a 2.3× margin on the reflow side and 2.2× on the native
side. Separately, `max_join_chars` counts the whole accumulated segment rather
than just the previous block, and table cells never merge across cells.

### 3.4 Role inference

Classes are opaque in book A (`class_s17`, `class_s1T`, `class_s6X`) and semantic
in book B, so roles come from the stylesheet plus corpus shape, never from names:

- body font size = mode over classes, with **undeclared and unclassed blocks
  counted as 1em** (otherwise the mode lands on a decorated class);
- headings: `font-size ≥ body × 1.15`, or bold and short, with run-in labels such
  as `Situation:` excluded; bold+italic counts, because Manning's h4/h5 are
  declared exactly that way;
- page numbers: the *block text* must be a bare folio as well as the class looking
  right, because book A's right-aligned class also holds prose fragments;
- code: ≥35% of a class's members look code-like (symbol density, quoted
  fragments, snake_case, dotted paths, assignments) — needed because book A has no
  `font-family` and book B's `pre` tag has to be honoured structurally.

Result on book A: `class_s1CT` → code (1249), `class_s6X`/`class_s1FJ`/`class_s1F8`
→ page numbers (593), span `class_sBKJ` → inline code (4407), `class_sBKF` →
bullets (2762). On book B: `readable-text` → body (685), `readable-text-h2/h3` →
headings, `code-area` → code (156), `<li>` → 751 list items.

### 3.5 Normalization and packaging results

| | book A (reflow) | book B (native) |
|---|---|---|
| blocks in | 11,399 | 4,602 |
| segments out | 1,797 | 4,183 |
| dropped | 333 (page numbers, page lists) | 0 |
| conservation | missing 0, duplicated 0 | missing 0, duplicated 0 |

End-to-end packaging on a 5-document slice of book B (14,024 characters):

```
segments        : 278 (278 written)
output          : tmp/ai-agents-5pages.epub
documents rewritten: 7   (5 documents + OPF + stylesheet)
entries copied     : 139
zip integrity      : OK
XML well-formedness: OK
binary assets      : 118/118 byte-identical
```

Worked examples from book A:

- `consis-tency` → `consistency` (soft hyphen removed because the book spells it
  `consistency` elsewhere 28 times)
- `high-quality`, `cross-validated` → **kept** (the hyphenated form is in the
  book's own vocabulary)
- `<span>•</span> <span>Bold</span> rest` → `• Bold rest` (text **and tails** must
  be collected; reading only `.text` nodes loses ~32% of the book)
- a 5-line code run → one verbatim code block

## 4. Bilingual layout: how the PDF look is reproduced in EPUB

Decision: **side by side** — source left, translation right, one row per
paragraph pair, the translation keeping the source block's tag and class.

```html
<div class="bdoc-pair">
  <div class="bdoc-src"><p class="readable-text">Original text.</p></div>
  <div class="bdoc-dst" lang="zh-CN"><p class="readable-text">译文。</p></div>
</div>
```

CSS: `.bdoc-pair { display: flex; column-gap: 1.4em }` with both cells
`flex: 1 1 0%`. Below 45em it collapses to `display: block`, because two columns
of prose on a phone is unreadable. Readers without flexbox ignore
`display: flex` and get the same stacked fallback.

Two constraints are handled explicitly:

- **A `<div>` may not be inserted between `<ul>` and `<li>`, or inside a table
  row.** For those segments the pair goes *inside* the element
  (`Segment._pair_inside`), which also keeps the list marker intact.
- **An EPUB has no pages.** "Two columns on a page" can only mean "two columns
  per block", so the columns do not align line-by-line the way a fixed-layout PDF
  can align them. What is gained instead is that both columns read continuously
  rather than being interrupted every paragraph — which is the property that
  matters here.

Verified in a real output file: 244 `bdoc-pair` rows in book B's table of
contents, stylesheet registered in the OPF and linked as
`../babeldoc-bilingual.css` from `OEBPS/Text/*.html`, and all 118 images
byte-identical to the source.

## 5. Translation client

`babeldoc/format/epub/client.py`. Three decisions worth keeping:

1. **Reuse the three pieces that were already format-agnostic**
   (`translator.translator`, `glossary`, `prompts/`) and write nothing else.
   `OpenAITranslator` gives on-disk caching, rate limiting and retry for free.
2. **No placeholder protocol.** In the PDF path a paragraph is flattened into text
   with `{{bdoc_style_N}}` tokens so inline styling survives the round trip. Here
   the markup never leaves the DOM, so there is nothing to encode, parse back, or
   repair.
3. **Batch with JSON, not delimiters.** Segment text is single-line prose, so
   JSON escaping cannot corrupt it and a truncated reply is detectable by checking
   the returned ids. Anything that does not map one-to-one onto the requested ids
   is rejected and retried, then retried per segment, and only then does the
   segment keep its source text (recorded in `failed` so the caller can report it
   instead of shipping a silent gap).

**The cache has to be told about our prompt and glossary.**
`BaseTranslator` keys its cache on the text plus parameters registered with
`add_cache_impact_parameters`. The PDF path registers its own prompt; without
doing the same here, editing the system prompt or a glossary row returned stale
translations from cache. Both are now registered as `epub_system_prompt` and
`epub_glossary`.

Measured on a 7-document slice of book B (150 segments, batch size 8): 20 model
calls, 24 seconds, and 143 of 150 pairs carrying a Chinese translation (the other
seven are headings and proper nouns). Leftover English is exactly the set the
prompt asks to preserve: `agent`, `guardrails`, `prompt`, `token`, `temperature`,
`persona`. Whole-book extrapolation: ~560 requests, ~11 minutes.

One real defect surfaced and was fixed: "photocopying" came back untranslated
inside an otherwise Chinese sentence, because the preservation rules were
over-applied. The batch rules now state explicitly that an ordinary word with a
normal Chinese equivalent must be translated.

## 6. Design notes worth keeping

1. **Tail text is content.** In `<p><span>•</span> <span>Bold</span> rest</p>`, the
   prose lives in the spans' tails. The first implementation collected only
   `.text` and silently lost 211,445 of 656,866 characters (32%). The conservation
   check now also catches the reverse failure — text emitted *twice*, which is what
   a nested `<li><p>` produces if both are treated as blocks.
2. **Named entities must be expanded before parsing.** EPUB 2 uses the XHTML
   entity set (`&eacute;`) defined by a DOCTYPE. Parsing without the DTD leaves
   entity nodes that cannot be re-parsed and are undefined in the output; the five
   XML built-ins must be left alone or the output gets a bare `&`.
3. **Move elements with care.** libxml2 drops a node's tail text when it is
   unlinked and re-linked, gluing words together; `_move` saves and restores it.
4. **Deep-copy, do not serialise-and-reparse**, when cloning a block for the
   translation column: the round trip fails on the entities above.
5. **Only re-serialise what changed.** Every other ZIP entry is copied
   byte-for-byte, so a round trip through the XML parser cannot damage images or
   fonts.
6. **Correctness is mechanical, not visual.** The PDF path's only acceptance test
   is a rendered image. Here the invariants are assertable in CI: character
   conservation (both directions), unchanged bytes for untouched entries, link/id
   preservation, XML well-formedness of every rewritten document.

## 7. Honest costs and risks

- **Leaving the upstream track.** Upstream improvements to prompts/glossary/
  translator are still reusable, but this adds a second pipeline to maintain.
  Mitigation: stay thin and reuse rather than fork.
- **Segmentation is the real engineering risk**: inline markup splits text nodes,
  and the marker/joining heuristics need tuning per book family. Two books have
  already produced two detector bugs.
- **Dirty EPUBs**: `display:none` content, `<br>`-separated poetry, nested
  tables, inline footnotes. Requires a block-level allow/deny list.
- **`AutomaticTermExtractor` is IL-coupled** and needs a thin adapter.
- **The 22 PDF commits are not wasted** — real publisher PDFs still use the PDF
  path. The change is that PDF recovery machinery stops being applied to content
  that never needed it.
- **Fixed-layout EPUB** would be needed for true page-by-page column alignment,
  and that means computing pagination ourselves — a PDF by another name, with the
  reflow advantages given up. Not worth it unless the side-by-side columns turn
  out to be unusable in practice.

## 8. Security note

`babeldoc.ko-zh.toml` holds a live API key and is protected by `.gitignore`
(`babeldoc.*.toml`, with `!babeldoc.*.template.toml`) rather than only
`.git/info/exclude`. **The key was exposed in plaintext during the earlier
investigation and should be rotated.**

A credential scan now runs on commit (staged files) and on push (whole tracked
tree) via `.pre-commit-config.yaml` → `tools/check_secrets.py`, covered by
`tests/test_check_secrets.py`. The whole tracked tree currently scans clean.
