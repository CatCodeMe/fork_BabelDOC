#!/usr/bin/env zsh
# Split a large PDF into independent local chunks, then translate each chunk.
# Each chunk is a standalone BabelDOC job, avoiding its internal split/page bug.

set -euo pipefail

ROOT_DIR=${0:A:h}
CONFIG_FILE="$ROOT_DIR/babeldoc.ko-zh.toml"
CHUNK_SIZE=${BABELDOC_CHUNK_SIZE:-50}
OUTPUT_ROOT="$ROOT_DIR/output/chunks"
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
run      Translate prepared chunks sequentially. Completed chunks are skipped.
parallel Translate uncompleted chunks in batches, then merge. Default: 3 simultaneous chunks.
merge    Combine completed chunk PDFs into one full dual PDF and one full mono PDF.
all      Run prepare, then run.

Set BABELDOC_CHUNK_SIZE=N before the command to use another chunk size.
Set BABELDOC_FORCE_RERUN=1 to rebuild a completed chunk deliberately.
EOF
}

[[ -f "$CONFIG_FILE" ]] || { print -u2 "Missing local config: $CONFIG_FILE"; exit 1; }
[[ $# -ge 2 ]] || { usage >&2; exit 2; }
MODE=$1
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
    if [[ -n ${BABELDOC_SYSTEM_PROMPT_FILE:-} ]]; then
      [[ -f "$BABELDOC_SYSTEM_PROMPT_FILE" ]] || { print -u2 "Prompt file not found: $BABELDOC_SYSTEM_PROMPT_FILE"; return 2; }
      prompt_args=(--custom-system-prompt "$(< "$BABELDOC_SYSTEM_PROMPT_FILE")")
    else
      prompt_args=()
    fi
    (
      cd "$ROOT_DIR"
      uv run --no-dev babeldoc --config "$CONFIG_FILE" \
        --files "$chunk" \
        "${language_args[@]}" "${prompt_args[@]}" \
        --qps 1 --pool-max-workers 1 --max-pages-per-part 0 --no-auto-extract-glossary \
        "${cache_args[@]}" \
        --output "$chunk_output" --working-dir "$chunk_work"
    ) 2>&1 | tee "$chunk_log"
    local result=${pipestatus[1]}
    if (( result != 0 )); then
      print -u2 "Chunk $index failed; stop here. Fix it and rerun the same command to resume."
      return "$result"
    fi
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

merge_outputs() {
  [[ -f "$MANIFEST" ]] || { print -u2 "No chunk manifest. Run prepare first."; exit 1; }
  local merged_dir="$BOOK_OUTPUT/merged"
  mkdir -p "$merged_dir"
  MANIFEST="$MANIFEST" BOOK_OUTPUT="$BOOK_OUTPUT" MERGED_DIR="$merged_dir" BOOK_NAME="$SAFE_NAME" \
    uv run --no-dev --directory "$ROOT_DIR" python - <<'PY'
import csv
import os
from pathlib import Path
import fitz

manifest = Path(os.environ['MANIFEST'])
output_root = Path(os.environ['BOOK_OUTPUT'])
merged_dir = Path(os.environ['MERGED_DIR'])
book_name = os.environ['BOOK_NAME']

rows = list(csv.DictReader(manifest.open(encoding='utf-8'), delimiter='\t'))
for kind in ('dual', 'mono'):
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
    target = merged_dir / f'{book_name}.zh-CN.{kind}.pdf'
    result.save(target, garbage=4, deflate=True)
    print(f'Created {kind}: {target} ({result.page_count} pages)')
    result.close()
PY
  local dual_pdf="$merged_dir/$SAFE_NAME.zh-CN.dual.pdf"
  local navigable_pdf="$merged_dir/$SAFE_NAME.zh-CN.dual.navigable.pdf"
  uv run --no-dev --directory "$ROOT_DIR" python "$ROOT_DIR/finalize_navigation.py" \
    "$SOURCE_PDF" "$dual_pdf" "$navigable_pdf"
  # The plain `dual.pdf` name is the first file most users open.  Make it the
  # navigable deliverable as well, while retaining the explicit navigable name
  # as a hard-link compatibility alias without duplicating a book-sized PDF.
  mv -f "$navigable_pdf" "$dual_pdf"
  ln -f "$dual_pdf" "$navigable_pdf"
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
  *) usage >&2; exit 2 ;;
esac
