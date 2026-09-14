# BabelDOC local usage (PDF books to Simplified Chinese)

This checkout uses `uv`; run every command from this folder. One translation
config drives everything and the source language is a property of the book, not
of the script.

## First-time setup

1. Only if `babeldoc.ko-zh.toml` does not already exist, copy the template
   without changing the original:

   ```zsh
   cp babeldoc.ko-zh.template.toml babeldoc.ko-zh.toml
   ```

2. Edit it and replace `PASTE_YOUR_DEEPSEEK_API_KEY_HERE`. The file is
   deliberately not part of Git tracking.

For English books, a second config with `lang-in = "en"` is convenient, but it
is not required: `BABELDOC_CONFIG` selects any config file and
`BABELDOC_LANG_IN` overrides the language on top of it.

```zsh
BABELDOC_CONFIG=babeldoc.en-zh.toml ./translate-chunks.zsh parallel book.pdf
# or, reusing the Korean config and overriding only what differs:
BABELDOC_LANG_IN=en \
BABELDOC_SYSTEM_PROMPT_FILE="$PWD/prompts/en-zh-technical.txt" \
  ./translate-chunks.zsh parallel book.pdf
```

## Environment overrides

| Variable | Effect |
| --- | --- |
| `BABELDOC_CONFIG` | Config file (default `babeldoc.ko-zh.toml`) |
| `BABELDOC_LANG_IN` / `BABELDOC_LANG_OUT` | Source / target language (target default `zh-CN`) |
| `BABELDOC_SYSTEM_PROMPT_FILE` | Prompt file, overriding `custom-system-prompt` |
| `BABELDOC_CHUNK_SIZE` | Maximum physical pages per chunk (default 50) |
| `BABELDOC_PARALLEL` | Simultaneous chunks in `parallel` mode (default 3) |
| `BABELDOC_TOC_LAYOUT_ADAPTER` | `auto` (default), `oreilly`, `manning`, `now-publishers` |
| `BABELDOC_OUTPUT_ROOT` / `BABELDOC_FINAL_ROOT` | Chunk working state / staged deliverables |
| `BABELDOC_FORCE_RERUN=1` | Rebuild a chunk that already completed |
| `BABELDOC_IGNORE_CACHE=1` | Ignore the translation cache for this run |
| `BABELDOC_MONO=1` | Also merge a full-book mono PDF (off by default) |
| `BABELDOC_TRANSLATE_OUTLINE=0` | Keep source-language bookmarks |
| `BABELDOC_STAGE_FINAL=0` | Skip the staged delivery and `handoff.json` |

## Long books: chunked, parallel, resumable

This is the main route and the one the local Skill uses.

```zsh
./translate-chunks.zsh prepare  "/absolute/path/book.pdf"
./translate-chunks.zsh parallel "/absolute/path/book.pdf"
```

`prepare` cuts at most `BABELDOC_CHUNK_SIZE` physical pages into standalone PDFs
under `work/input-chunks/`. `parallel` translates unfinished chunks with
`BABELDOC_PARALLEL` workers and then merges. If a chunk fails or the Mac sleeps,
rerun the same command: completed chunks are detected and skipped, and each
chunk keeps its own output folder and `run.log`.

`merge` rebuilds the aggregate without translating anything, which is what you
want after a targeted `one SOURCE INDEX` retry:

```zsh
./translate-chunks.zsh one   "/absolute/path/book.pdf" 3
./translate-chunks.zsh merge "/absolute/path/book.pdf"
```

Do not use BabelDOC's `--pages` option together with `max-pages-per-part`:
0.6.4 can fail after the first split part with an empty-page `AssertionError`.
That is why the scripts sample and split with physical PDFs instead.

## What a run produces

`output/chunks/<book>/merged/` is working state. It holds exactly one
user-facing file, `output/final/` holds the reviewed delivery:

```text
output/final/<queue-id>--<book>/
  <book>.zh-CN.dual.navigable.pdf   one navigable bilingual PDF
  handoff.json                      page, TOC and link evidence + queue id
```

- **One deliverable, not four.** The mono PDF is opt-in via `BABELDOC_MONO=1`,
  and the unrepaired dual PDF is deleted once navigation is repaired.
- **The outline is relabelled in place.** BabelDOC copies the source PDF's
  bookmarks verbatim, so without this the deliverable navigates in English.
  Restore source-language bookmarks with `BABELDOC_TRANSLATE_OUTLINE=0`.
- **The queue id is stable and never reused**, so a library import can sort
  deliveries in review order. It lives in `handoff.json` and is stored as the
  item's call number downstream.
- `output/chunks/` can be removed only after `handoff.json` has been reviewed,
  because it is the only thing that makes a retry cheap.

`handoff.json` is consumed by the `zotero-library-curator` skill; do not
hand-edit it.

## Short documents

A paper or a chapter needs no chunk orchestration:

```zsh
./translate-paper.zsh "/absolute/path/paper.pdf"
```

It runs one BabelDOC job with no internal part splitting and writes to
`output/papers/<name>/`. Everything else, including a 5-page book, is fine
through the chunked route: it simply becomes a single chunk and still gains
resume, merge, outline relabelling and the handoff sidecar.

## Checking a book before translating it

```zsh
uv run --no-dev python tools/epub_probe.py "/absolute/path/book.epub"   # EPUB only
```

`translate-chunks.zsh test SOURCE INDEX` translates exactly one prepared chunk,
which is the cheapest way to judge a prompt or glossary change.

## Code and terminology rules

The local configuration includes a technical-translation prompt and the
editable glossary `glossaries/ko-zh-technical.csv`. It preserves filenames,
code, commands, paths, identifiers, schema fields, and listed technical terms.
Computer-science terminology is deliberately rendered in standard English while
explanatory prose remains Chinese. Add a row as `source,target,zh-CN`: use the
same source and target to preserve text, or use the accepted English name (for
example `트랜스포머,Transformer,zh-CN`).

After changing the prompt or glossary, bypass older cache entries for the next
test so the new rules are actually evaluated:

```zsh
BABELDOC_IGNORE_CACHE=1 ./translate-chunks.zsh test "/absolute/path/book.pdf" 1
```

Do not set `auto-extract-glossary` in the TOML: BabelDOC 0.6.4 serializes it
incorrectly. Use the CLI flag `--no-auto-extract-glossary` instead.

## EPUB books

EPUB does not go through this pipeline. It is translated natively, with a
side-by-side bilingual layout, by `tools/epub_bilingual.py`; see
`.planning/2026-09-13-epub-support/findings.md` for why converting to PDF first
is the wrong trade.

## Images and OCR

BabelDOC reconstructs the translated PDF and preserves PDF images and graphics
at their original locations. It does not translate text embedded inside those
images. It has one OpenAI-compatible **text translation** provider per run, so
it cannot be configured to send images to a separate Qwen OCR API and place the
resulting Chinese back into the image. That requires a separate
image-OCR/translation/inpainting pipeline.

## Privacy

The PDF remains local, but each text segment is sent to DeepSeek because this
configuration uses the DeepSeek API. For zero egress, replace the OpenAI
endpoint with a local Ollama-compatible endpoint and a local model.
