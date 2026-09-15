#!/usr/bin/env zsh
# Split a large PDF into independent local chunks, then translate each chunk.
# Each chunk is a standalone BabelDOC job, avoiding its internal split/page bug.

set -euo pipefail

ROOT_DIR=${0:A:h}
CONFIG_FILE=${BABELDOC_CONFIG:-"$ROOT_DIR/babeldoc.ko-zh.toml"}
# Target language, used for merged filenames and for outline relabelling.
LANG_OUT=${BABELDOC_LANG_OUT:-zh-CN}
# Where reviewed deliverables are staged, one queue directory per book.
FINAL_ROOT=${BABELDOC_FINAL_ROOT:-"$ROOT_DIR/output/final"}
CHUNK_SIZE=${BABELDOC_CHUNK_SIZE:-50}
OUTPUT_ROOT=${BABELDOC_OUTPUT_ROOT:-"$ROOT_DIR/output/chunks"}
WORK_ROOT="$ROOT_DIR/work/chunks"
INPUT_ROOT="$ROOT_DIR/work/input-chunks"

export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1

usage() {
  cat <<'EOF'
Usage:
  ./translate-chunks.zsh prepare /absolute/path/book.pdf
  ./translate-chunks.zsh test    /absolute/path/book.pdf 1
  ./translate-chunks.zsh run     /absolute/path/book.pdf
  ./translate-chunks.zsh parallel /absolute/path/book.pdf
  ./translate-chunks.zsh merge   /absolute/path/book.pdf
  ./translate-chunks.zsh all     /absolute/path/book.pdf

prepare  Create local PDFs of at most BABELDOC_CHUNK_SIZE physical pages each (default: 50).
test     Translate exactly one prepared chunk by its index (for example 1).
clean    Remove this book's babeldoc scratch and split inputs. Keeps the
         manifest, output/chunks/ and any staged delivery.
clean --staged
         Sweep every book that already has a delivery under output/final/.
run      Translate prepared chunks sequentially. Completed chunks are skipped.
parallel Translate uncompleted chunks in batches, then merge. Default: 3 simultaneous chunks.
merge    Combine completed chunk PDFs into one full dual PDF and one full mono PDF.
all      Run prepare, then run.

Set BABELDOC_CHUNK_SIZE=N before the command to use another chunk size.
Set BABELDOC_FORCE_RERUN=1 to rebuild a completed chunk deliberately.

Environment overrides:
  BABELDOC_CONFIG               Config file (default: babeldoc.ko-zh.toml).
                                Use this rather than stacking the two below.
  BABELDOC_LANG_IN              Source language, overriding the config.
  BABELDOC_SYSTEM_PROMPT_FILE   Prompt file, overriding custom-system-prompt.
  BABELDOC_TOC_LAYOUT_ADAPTER   auto | oreilly | manning | now (default: auto).
  BABELDOC_OUTPUT_ROOT          Where chunk outputs are written.
  BABELDOC_PARALLEL             Simultaneous chunks in parallel mode (default: 3).
  BABELDOC_LANG_OUT             Target language (default: zh-CN).
  BABELDOC_MONO=1               Also merge a full-book mono PDF. Off by default:
                                merge produces one navigable bilingual PDF.
  BABELDOC_TRANSLATE_OUTLINE=0  Keep source-language bookmarks instead of
                                relabelling the outline into the target language.
  BABELDOC_FINAL_ROOT           Where reviewed deliverables are staged
                                (default: output/final).
  BABELDOC_STAGE_FINAL=0        Skip the staged delivery and handoff.json.
  BABELDOC_CLEAN_AFTER_MERGE=1  Clean this book's working state right after the
                                staged delivery is written.
  BABELDOC_KEEP_CHUNK_SCRATCH=1 Keep babeldoc's per-chunk intermediates for
                                debugging instead of deleting them.
EOF
}

# babeldoc writes 65-80 MB of transient intermediates per chunk under its
# working directory -- an order of magnitude more than the finished chunk -- and
# never removes them. One 673-page book left 3.2 GB behind, which is how a 4 GB
# work/ tree accumulated across a dozen finished books.
#
# translate_tracking.json is deliberately kept: it is the evidence used to
# diagnose a TOC segmentation failure, so it must survive until delivery.
# Set BABELDOC_KEEP_CHUNK_SCRATCH=1 to keep the scratch for a debugging run.
strip_chunk_scratch() {
  local chunk_work=$1
  [[ ${BABELDOC_KEEP_CHUNK_SCRATCH:-0} = 1 ]] && return 0
  [[ -d "$chunk_work" ]] || return 0
  find "$chunk_work" -type f \
    \( -name 'temp_subset_*.pdf' \
       -o -name 'watermarked_temp_input.pdf' \
       -o -name 'mig_toc_temp.pdf' \
       -o -name 'input.pdf' \) -delete 2>/dev/null
  return 0
}

# Remove a book's working state but keep everything that is either resumable or
# already delivered: output/chunks/<book>/ still holds the translated chunks,
# manifest.tsv still lets `merge` rebuild the aggregate without re-translating,
# and output/final/ holds the reviewed deliverable.
clean_book() {
  local freed=0
  [[ -d "$BOOK_WORK" ]] && freed=$(( freed + $(du -sm "$BOOK_WORK" | cut -f1) ))
  rm -rf "$BOOK_WORK"
  if [[ -d "$CHUNK_DIR" ]]; then
    freed=$(( freed + $(du -sm "$CHUNK_DIR" | cut -f1) ))
    find "$CHUNK_DIR" -maxdepth 1 -name 'chunk-*.pdf' -delete 2>/dev/null
  fi
  print "Cleaned $SAFE_NAME (${freed} MB)."
  print "Kept: $MANIFEST, $BOOK_OUTPUT, and any staged delivery under $FINAL_ROOT."
  print "Re-run 'prepare' before retranslating a chunk; 'merge' still works as is."
}

# Sweep every book that already has a staged delivery. Books without one are
# reported and left alone, because their work state may be the only reason a
# retry is cheap.
clean_staged() {
  local freed=0 kept=0 name
  if [[ ! -d "$WORK_ROOT" ]]; then
    print "No working state at $WORK_ROOT."
    return 0
  fi
  for d in "$WORK_ROOT"/*/; do
    name=${d:t}
    [[ "$name" = "parallel-logs" ]] && continue
    [[ -n "$(find "$FINAL_ROOT" -maxdepth 1 -type d -name "*--$name" -print -quit 2>/dev/null)" ]] || {
      print "  kept    $name (no staged delivery)"
      (( kept += 1 ))
      continue
    }
    freed=$(( freed + $(du -sm "$d" | cut -f1) ))
    rm -rf "$d"
    [[ -d "$INPUT_ROOT/$name" ]] && find "$INPUT_ROOT/$name" -maxdepth 1 -name 'chunk-*.pdf' -delete 2>/dev/null
    print "  cleaned $name"
  done
  print "\nRemoved ${freed} MB of working state; kept $kept book(s) without a staged delivery."
}

[[ -f "$CONFIG_FILE" ]] || {
  print -u2 "Missing config: $CONFIG_FILE"
  print -u2 "Point BABELDOC_CONFIG at a config file, or create the default one."
  exit 1
}
[[ $# -ge 2 ]] || { usage >&2; exit 2; }
MODE=$1

# `clean --staged` is a whole-tree sweep and takes no source PDF, so it has to
# run before the per-book path derivation below.
if [[ "$MODE" = "clean" && "${2:-}" = "--staged" ]]; then
  clean_staged
  exit 0
fi

SOURCE_PDF=${2:A}
[[ -f "$SOURCE_PDF" ]] || { print -u2 "PDF not found: $SOURCE_PDF"; exit 1; }
[[ "$CHUNK_SIZE" =~ '^[1-9][0-9]*$' ]] || { print -u2 "BABELDOC_CHUNK_SIZE must be a positive integer."; exit 2; }

BOOK_NAME=${SOURCE_PDF:t:r}
SAFE_NAME=$(print -rn -- "$BOOK_NAME" | tr -cs 'A-Za-z0-9._-' '_')
[[ -n "$SAFE_NAME" ]] || SAFE_NAME="book"
CHUNK_DIR="$INPUT_ROOT/$SAFE_NAME"
BOOK_OUTPUT="$OUTPUT_ROOT/$SAFE_NAME"
BOOK_WORK="$WORK_ROOT/$SAFE_NAME"
MANIFEST="$CHUNK_DIR/manifest.tsv"

prepare() {
  mkdir -p "$CHUNK_DIR"
  SOURCE_PDF="$SOURCE_PDF" CHUNK_DIR="$CHUNK_DIR" MANIFEST="$MANIFEST" CHUNK_SIZE="$CHUNK_SIZE" \
    uv run --no-dev --directory "$ROOT_DIR" python - <<'PY'
import os
from pathlib import Path
import fitz

src_path = Path(os.environ['SOURCE_PDF'])
chunk_dir = Path(os.environ['CHUNK_DIR'])
manifest = Path(os.environ['MANIFEST'])
size = int(os.environ['CHUNK_SIZE'])
src = fitz.open(src_path)
rows = ['index\tfirst_page\tlast_page\tpath']
for index, start in enumerate(range(0, src.page_count, size), start=1):
    end = min(start + size, src.page_count)
    path = chunk_dir / f'chunk-{index:03d}-pages-{start + 1}-{end}.pdf'
    if not path.exists():
        out = fitz.open()
        out.insert_pdf(src, from_page=start, to_page=end - 1)
        out.save(path, garbage=4, deflate=True)
        out.close()
    rows.append(f'{index}\t{start + 1}\t{end}\t{path}')
manifest.write_text('\n'.join(rows) + '\n', encoding='utf-8')
print(f'Prepared {len(rows) - 1} chunks from {src.page_count} pages.')
PY
  print "Manifest: $MANIFEST"
}

translate() {
  local target_index=${1:-}
  [[ -f "$MANIFEST" ]] || { print -u2 "No chunk manifest. Run prepare first."; exit 1; }
  mkdir -p "$BOOK_OUTPUT" "$BOOK_WORK"
  local index first last chunk chunk_base chunk_output chunk_work chunk_log
  while IFS=$'\t' read -r index first last chunk; do
    [[ "$index" = "index" ]] && continue
    [[ -z "$target_index" || "$index" = "$target_index" ]] || continue
    chunk_base=${chunk:t:r}
    chunk_output="$BOOK_OUTPUT/chunk-${index}-pages-${first}-${last}"
    chunk_work="$BOOK_WORK/chunk-${index}-pages-${first}-${last}"
    chunk_log="$chunk_work/run.log"
    if [[ ${BABELDOC_FORCE_RERUN:-0} != 1 && -n "$(find "$chunk_output" -maxdepth 1 -type f -name '*.dual.pdf' -size +0c -print -quit 2>/dev/null)" ]]; then
      print "Skip completed chunk $index ($first-$last)."
      strip_chunk_scratch "$chunk_work"
      continue
    fi
    mkdir -p "$chunk_output" "$chunk_work"
    print "\n=== Translating chunk $index: pages $first-$last ==="
    local -a cache_args
    if [[ ${BABELDOC_IGNORE_CACHE:-0} = 1 ]]; then
      cache_args=(--ignore-cache)
    else
      cache_args=()
    fi
    local -a language_args prompt_args
    if [[ -n ${BABELDOC_LANG_IN:-} ]]; then
      language_args=(--lang-in "$BABELDOC_LANG_IN")
    else
      language_args=()
    fi
    if [[ -n ${BABELDOC_LANG_OUT:-} ]]; then
      language_args+=(--lang-out "$BABELDOC_LANG_OUT")
    fi
    if [[ -n ${BABELDOC_SYSTEM_PROMPT_FILE:-} ]]; then
      [[ -f "$BABELDOC_SYSTEM_PROMPT_FILE" ]] || { print -u2 "Prompt file not found: $BABELDOC_SYSTEM_PROMPT_FILE"; return 2; }
      prompt_args=(--custom-system-prompt "$(< "$BABELDOC_SYSTEM_PROMPT_FILE")")
    else
      prompt_args=()
    fi
    local toc_layout_adapter=${BABELDOC_TOC_LAYOUT_ADAPTER:-auto}
    (
      cd "$ROOT_DIR"
      uv run --no-dev babeldoc --config "$CONFIG_FILE" \
        --files "$chunk" \
        "${language_args[@]}" "${prompt_args[@]}" \
        --toc-layout-adapter "$toc_layout_adapter" \
        --qps 1 --pool-max-workers 1 --max-pages-per-part 0 --no-auto-extract-glossary \
        "${cache_args[@]}" \
        --output "$chunk_output" --working-dir "$chunk_work"
    ) 2>&1 | tee "$chunk_log"
    local result=${pipestatus[1]}
    if (( result != 0 )); then
      print -u2 "Chunk $index failed; stop here. Fix it and rerun the same command to resume."
      return "$result"
    fi
    strip_chunk_scratch "$chunk_work"
  done < "$MANIFEST"
  if [[ -n "$target_index" ]]; then
    print "\nTest chunk $target_index finished. Output root: $BOOK_OUTPUT"
  else
    print "\nAll chunks finished. Output root: $BOOK_OUTPUT"
  fi
}

parallel_translate() {
  [[ -f "$MANIFEST" ]] || { print -u2 "No chunk manifest. Run prepare first."; exit 1; }
  local parallelism=${BABELDOC_PARALLEL:-3}
  [[ "$parallelism" =~ '^[1-9][0-9]*$' ]] || { print -u2 "BABELDOC_PARALLEL must be a positive integer."; exit 2; }
  mkdir -p "$BOOK_WORK/parallel-logs"
  tail -n +2 "$MANIFEST" | cut -f1 | xargs -P "$parallelism" -I {} \
    /bin/zsh "$ROOT_DIR/translate-chunks.zsh" one "$SOURCE_PDF" {}
  merge_outputs
  print "\nAll uncompleted chunks finished and merged. Output root: $BOOK_OUTPUT"
}

# Allocate a stable four-digit queue id, shared across books. The id lets a
# downstream library import sort deliverables in the order they were reviewed,
# so it must not repeat even when two merges run at once: the counter lives in
# the final root behind a lock directory, since mkdir is atomic.
allocate_queue_id() {
  local queue_id_file="$1"
  local attempts=0
  mkdir -p "$FINAL_ROOT" "${queue_id_file:h}"
  local lock_dir="$FINAL_ROOT/.queue-id.lock"
  until mkdir "$lock_dir" 2>/dev/null; do
    (( attempts += 1 ))
    if (( attempts > 100 )); then
      print -u2 "Timed out waiting to allocate a queue id."
      return 1
    fi
    sleep 0.1
  done
  local next_file="$FINAL_ROOT/.next-queue-id"
  local next=1
  [[ -f "$next_file" ]] && next=$(< "$next_file")
  [[ "$next" =~ '^[1-9][0-9]*$' ]] || {
    rmdir "$lock_dir"
    print -u2 "Invalid queue id counter: $next_file"
    return 1
  }
  printf '%04d\n' "$next" > "$queue_id_file"
  print $(( next + 1 )) > "$next_file"
  rmdir "$lock_dir"
}

merge_outputs() {
  [[ -f "$MANIFEST" ]] || { print -u2 "No chunk manifest. Run prepare first."; exit 1; }
  local merged_dir="$BOOK_OUTPUT/merged"
  mkdir -p "$merged_dir"

  # Only the navigable bilingual PDF is a user-facing deliverable. A second
  # full-book mono PDF is opt-in: several near-identical large files make it
  # unclear which one to read.
  local kinds
  if [[ ${BABELDOC_MONO:-0} = 1 ]]; then kinds="dual,mono"; else kinds="dual"; fi

  MANIFEST="$MANIFEST" BOOK_OUTPUT="$BOOK_OUTPUT" MERGED_DIR="$merged_dir" \
    BOOK_NAME="$SAFE_NAME" KINDS="$kinds" LANG_OUT="$LANG_OUT" \
    uv run --no-dev --directory "$ROOT_DIR" python - <<'PY'
import csv
import os
from pathlib import Path
import fitz

manifest = Path(os.environ['MANIFEST'])
output_root = Path(os.environ['BOOK_OUTPUT'])
merged_dir = Path(os.environ['MERGED_DIR'])
book_name = os.environ['BOOK_NAME']
lang_out = os.environ['LANG_OUT']

rows = list(csv.DictReader(manifest.open(encoding='utf-8'), delimiter='\t'))
for kind in os.environ['KINDS'].split(','):
    inputs = []
    for row in rows:
        folder = output_root / f"chunk-{row['index']}-pages-{row['first_page']}-{row['last_page']}"
        matches = sorted(folder.glob(f'*.{kind}.pdf'))
        if not matches:
            raise SystemExit(f'Missing {kind} output for chunk {row["index"]}: {folder}')
        inputs.append(matches[0])
    result = fitz.open()
    for path in inputs:
        part = fitz.open(path)
        result.insert_pdf(part)
        part.close()
    target = merged_dir / f'{book_name}.{lang_out}.{kind}.pdf'
    result.save(target, garbage=4, deflate=True)
    print(f'Merged {kind}: {target.name} ({result.page_count} pages)')
    result.close()
PY

  local dual_pdf="$merged_dir/$SAFE_NAME.$LANG_OUT.dual.pdf"
  local navigable_pdf="$merged_dir/$SAFE_NAME.$LANG_OUT.dual.navigable.pdf"
  uv run --no-dev --directory "$ROOT_DIR" python "$ROOT_DIR/finalize_navigation.py" \
    "$SOURCE_PDF" "$dual_pdf" "$navigable_pdf"
  # `dual.pdf` is only an intermediate consumed by the navigation finalizer.
  rm -f "$dual_pdf"

  # Relabel the outline in place. BabelDOC's migrate_toc copies the *source*
  # language bookmarks verbatim, so without this the deliverable navigates in
  # English. Editing the one deliverable beats emitting a second file, and a
  # failure here is not fatal: a merge must not fail over a bookmark title.
  if [[ ${BABELDOC_TRANSLATE_OUTLINE:-1} = 1 ]]; then
    local -a outline_args
    outline_args=(--config "$CONFIG_FILE" --target-lang "$LANG_OUT")
    [[ -n ${BABELDOC_LANG_IN:-} ]] && outline_args+=(--source-lang "$BABELDOC_LANG_IN")
    [[ -n ${BABELDOC_SYSTEM_PROMPT_FILE:-} ]] && outline_args+=(--prompt "$BABELDOC_SYSTEM_PROMPT_FILE")
    if ! uv run --no-dev --directory "$ROOT_DIR" python "$ROOT_DIR/tools/translate_outline.py" \
        "$navigable_pdf" "$navigable_pdf" --in-place "${outline_args[@]}"; then
      print -u2 "warning: outline translation failed; keeping source-language bookmarks"
    fi
  fi

  print "\nFinal deliverable: $navigable_pdf"

  # Stage the reviewed delivery with its evidence sidecar. The skills hand the
  # staged path to the library importer, which reads handoff.json for the final
  # PDF plus page/TOC evidence and stores the queue id as a call number.
  if [[ ${BABELDOC_STAGE_FINAL:-1} = 0 ]]; then
    print "\nStaging is disabled (BABELDOC_STAGE_FINAL=0); output/chunks/ remains the working state."
    return 0
  fi

  local queue_id_file="$BOOK_WORK/queue-id"
  allocate_queue_id "$queue_id_file" || return 1
  local queue_id=$(< "$queue_id_file")
  local final_dir="$FINAL_ROOT/${queue_id}--$SAFE_NAME"
  local final_pdf="$final_dir/$SAFE_NAME.$LANG_OUT.dual.navigable.pdf"
  mkdir -p "$final_dir"
  cp "$navigable_pdf" "$final_pdf"

  SOURCE_PDF="$SOURCE_PDF" FINAL_PDF="$final_pdf" QUEUE_ID="$queue_id" \
    LANG_OUT="$LANG_OUT" \
    uv run --no-dev --directory "$ROOT_DIR" python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import fitz

source_path = Path(os.environ['SOURCE_PDF'])
final_path = Path(os.environ['FINAL_PDF'])
source = fitz.open(source_path)
final = fitz.open(final_path)
try:
    if source.page_count != final.page_count:
        raise SystemExit(
            f'Page count differs: source={source.page_count}, final={final.page_count}.'
        )
    payload = {
        'queue_id': os.environ['QUEUE_ID'],
        'source_pdf': str(source_path),
        'final_navigable_dual_pdf': str(final_path),
        'page_count': final.page_count,
        'toc_entries': len(final.get_toc(simple=True)),
        'internal_links': sum(len(final[i].get_links()) for i in range(final.page_count)),
        'target_language': os.environ['LANG_OUT'],
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
finally:
    source.close()
    final.close()
report = final_path.with_name('handoff.json')
report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'queue id       : {payload["queue_id"]}')
print(f'pages          : {payload["page_count"]}')
print(f'toc entries    : {payload["toc_entries"]}')
print(f'internal links : {payload["internal_links"]}')
PY

  [[ ${BABELDOC_CLEAN_AFTER_MERGE:-0} = 1 ]] && clean_book

  print "Staged delivery: $final_dir"
  print "  deliverable  : $final_pdf"
  print "  evidence     : $final_dir/handoff.json"
}


case "$MODE" in
  prepare) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; prepare ;;
  test)
    [[ $# -eq 3 && "$3" =~ '^[1-9][0-9]*$' ]] || { usage >&2; exit 2; }
    prepare
    translate "$3"
    ;;
  one)
    [[ $# -eq 3 && "$3" =~ '^[1-9][0-9]*$' ]] || { usage >&2; exit 2; }
    translate "$3"
    ;;
  run) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; translate; merge_outputs ;;
  parallel) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; parallel_translate ;;
  merge) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; merge_outputs ;;
  all) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; prepare; translate; merge_outputs ;;
  clean) [[ $# -eq 2 ]] || { usage >&2; exit 2; }; clean_book ;;
  *) usage >&2; exit 2 ;;
esac
