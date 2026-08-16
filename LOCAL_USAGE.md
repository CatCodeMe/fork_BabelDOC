# BabelDOC local usage (Korean to Simplified Chinese)

This checkout uses `uv`; run every command from this folder.

## First-time setup

1. Only if `babeldoc.ko-zh.toml` does not already exist, copy the template
   without changing the original:

   ```zsh
   cp babeldoc.ko-zh.template.toml babeldoc.ko-zh.toml
   ```

2. Edit `babeldoc.ko-zh.toml` and replace `PASTE_YOUR_DEEPSEEK_API_KEY_HERE`.
   This file is deliberately not part of Git tracking.

## Recommended launcher

Use the included launcher rather than calling `babeldoc` directly:

```zsh
chmod +x ./translate-book.zsh
./translate-book.zsh test "/absolute/path/to/book.pdf" 50-54
./translate-book.zsh full "/absolute/path/to/book.pdf"
```

`test` first creates a small physical-PDF-page sample, then translates it. Do
not use BabelDOC's `--pages` option together with `max-pages-per-part`: BabelDOC
0.6.4 can fail after the first split part with an empty-page `AssertionError`.
Open both test PDFs and check Korean text order, figures, and Chinese font
rendering before starting the full job.

### Code and terminology rules

The local configuration includes a technical-translation prompt and the
editable glossary `glossaries/ko-zh-technical.csv`. It preserves filenames,
code, commands, paths, identifiers, schema fields, and listed technical terms.
Computer-science terminology is deliberately rendered in standard English while
explanatory prose remains Chinese. Add a row as `source,target,zh-CN`: use the
same source and target to preserve text, or use the accepted English name (for
example `트랜스포머,Transformer,zh-CN`).

After changing the prompt or glossary, bypass older translation-cache entries
for the next test so the new rules are actually evaluated:

```zsh
BABELDOC_IGNORE_CACHE=1 ./translate-chunks.zsh test "/absolute/path/to/book.pdf" 1
```

### English technical books

For an English technical book, use the dedicated English prompt while reusing
the same local API configuration and chunk launcher:

```zsh
BABELDOC_LANG_IN=en \
BABELDOC_SYSTEM_PROMPT_FILE="/Users/hulj/tools_wp/babeldoc/prompts/en-zh-technical.txt" \
BABELDOC_PARALLEL=3 \
./translate-chunks.zsh parallel "/absolute/path/to/english-book.pdf"
```

When all chunks succeed, `parallel` automatically merges them, repairs the
original-side navigation, and stages the final dual PDF outside the transient
chunk tree. `merge` remains available after a targeted `one` retry.

## Recommended large-book route: local 50-page chunks

For a several-hundred-page book, the most restartable route is to physically
split it first and translate each chunk as an independent job:

```zsh
./translate-chunks.zsh all "/absolute/path/to/book.pdf"
```

It creates at most 50-page PDFs under `work/input-chunks/`, then translates
them sequentially with one worker and one request per second. If one chunk
fails or the Mac sleeps, rerun exactly the same command: completed chunks are
detected and skipped. Each chunk has its own output folder and `run.log`.

Successful `run`, `parallel`, and `all` commands create a stable, incrementing
handoff directory at `output/final/<queue-id>--<book>/`. It contains the
Zotero-ready `<book>.zh-CN.dual.navigable.pdf` and `handoff.json` with page,
TOC, and link evidence. `output/chunks/` remains resumable working state and
can be removed only after the handoff has been reviewed and imported. Set
`BABELDOC_FINAL_ROOT` to change the final staging location.

## Full translation

The launcher fixes API concurrency at one worker and one request per second. It
uses 25 pages per internal part by default; lower it if the Mac is under memory
pressure:

```zsh
BABELDOC_PAGES_PER_PART=10 ./translate-book.zsh full "/absolute/path/to/book.pdf"
```

This reduces per-part processing but is not a hard memory cap: BabelDOC's
layout model itself needs roughly 1 GB. Smaller parts increase runtime and disk
usage. The configured translation model is `deepseek-v4-flash`, with DeepSeek
thinking explicitly disabled because BabelDOC requires normal chat-content
output.

## Images and OCR

BabelDOC reconstructs the translated PDF and preserves PDF images and graphics at their original locations. It does not translate text embedded inside those images. It has one OpenAI-compatible **text translation** provider per run, so it cannot be configured to send images to a separate Qwen OCR API and place the resulting Chinese back into the image. That requires a separate image-OCR/translation/inpainting pipeline.

## Privacy

The PDF remains local, but each text segment is sent to DeepSeek because this configuration uses the DeepSeek API. For zero egress, replace the OpenAI endpoint with a local Ollama-compatible endpoint and a local model.
