#!/usr/bin/env zsh
# Reliable launcher for BabelDOC Korean -> Simplified Chinese PDF translation.
# It deliberately avoids BabelDOC 0.6.4's --pages + split-parts bug.

set -euo pipefail

ROOT_DIR=${0:A:h}
CONFIG_FILE="$ROOT_DIR/babeldoc.ko-zh.toml"
OUTPUT_ROOT="$ROOT_DIR/output"
WORK_ROOT="$ROOT_DIR/work"

# Limits concurrency. These are not hard RSS caps: the layout model itself uses
# about 1 GB, but they prevent additional worker / math-library parallelism.
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

usage() {
  cat <<'EOF'
Usage:
  ./translate-book.zsh test /absolute/path/book.pdf 50-54
  ./translate-book.zsh full /absolute/path/book.pdf

Commands:
  test  Extracts the requested physical PDF pages to a temporary small PDF,
        then translates that file. This avoids BabelDOC 0.6.4's broken
        combination of --pages and split translation.
  full  Translates the complete PDF. Default is 25 pages per internal part.

Optional environment variables:
  BABELDOC_PAGES_PER_PART=10  Lower peak per-part work at the cost of more time
                              and disk use. Default: 25.
EOF
}

[[ -f "$CONFIG_FILE" ]] || { print -u2 "Missing local config: $CONFIG_FILE"; exit 1; }
[[ $# -ge 2 ]] || { usage >&2; exit 2; }

MODE=$1
SOURCE_PDF=${2:A}
[[ -f "$SOURCE_PDF" ]] || { print -u2 "PDF not found: $SOURCE_PDF"; exit 1; }

FILE_NAME=${SOURCE_PDF:t}
BOOK_NAME=${FILE_NAME:r}
SAFE_NAME=$(print -rn -- "$BOOK_NAME" | tr -cs 'A-Za-z0-9._-' '_')
[[ -n "$SAFE_NAME" ]] || SAFE_NAME="book"

run_babeldoc() {
  local input_pdf=$1 output_dir=$2 work_dir=$3 pages_per_part=$4 log_file=$5
  local -a cache_args
  if [[ ${BABELDOC_IGNORE_CACHE:-0} = 1 ]]; then
    cache_args=(--ignore-cache)
  else
    cache_args=()
  fi
  mkdir -p "$output_dir" "$work_dir"
  print "\nInput:  $input_pdf"
  print "Output: $output_dir"
  print "Log:    $log_file\n"
  (
    cd "$ROOT_DIR"
    uv run --no-dev babeldoc --config "$CONFIG_FILE" \
      --files "$input_pdf" \
      --qps 1 --pool-max-workers 1 \
      --max-pages-per-part "$pages_per_part" \
      "${cache_args[@]}" \
      --output "$output_dir" --working-dir "$work_dir"
  ) 2>&1 | tee "$log_file"
  return ${pipestatus[1]}
}

case "$MODE" in
  test)
    [[ $# -eq 3 ]] || { usage >&2; exit 2; }
    PAGE_RANGE=$3
    if [[ ! "$PAGE_RANGE" =~ '^[1-9][0-9]*-[1-9][0-9]*$' ]]; then
      print -u2 "Test range must be N-M, for example 50-54."
      exit 2
    fi
    START_PAGE=${PAGE_RANGE%-*}
    END_PAGE=${PAGE_RANGE#*-}
    (( START_PAGE <= END_PAGE )) || { print -u2 "Range start must not exceed end."; exit 2; }

    SAMPLE_DIR="$WORK_ROOT/samples/$SAFE_NAME"
    SAMPLE_PDF="$SAMPLE_DIR/${SAFE_NAME}.pages-${START_PAGE}-${END_PAGE}.pdf"
    mkdir -p "$SAMPLE_DIR"
    export SOURCE_PDF START_PAGE END_PAGE SAMPLE_PDF
    (
      cd "$ROOT_DIR"
      uv run --no-dev python - <<'PY'
import os
import fitz

src_path = os.environ['SOURCE_PDF']
start = int(os.environ['START_PAGE'])
end = int(os.environ['END_PAGE'])
out_path = os.environ['SAMPLE_PDF']
src = fitz.open(src_path)
if end > src.page_count:
    raise SystemExit(f'PDF has {src.page_count} pages; requested {start}-{end}.')
out = fitz.open()
out.insert_pdf(src, from_page=start - 1, to_page=end - 1)
out.save(out_path, garbage=4, deflate=True)
print(f'Created test PDF: {out_path} ({out.page_count} pages)')
PY
    )

    TEST_OUTPUT="$OUTPUT_ROOT/$SAFE_NAME/test-${START_PAGE}-${END_PAGE}"
    TEST_WORK="$WORK_ROOT/$SAFE_NAME/test-${START_PAGE}-${END_PAGE}"
    # A self-contained sample has no internal split and no --pages flag.
    run_babeldoc "$SAMPLE_PDF" "$TEST_OUTPUT" "$TEST_WORK" 0 "$TEST_WORK/run.log"
    ;;
  full)
    [[ $# -eq 2 ]] || { usage >&2; exit 2; }
    PAGES_PER_PART=${BABELDOC_PAGES_PER_PART:-25}
    [[ "$PAGES_PER_PART" =~ '^[1-9][0-9]*$' ]] || { print -u2 "BABELDOC_PAGES_PER_PART must be a positive integer."; exit 2; }
    FULL_OUTPUT="$OUTPUT_ROOT/$SAFE_NAME/full"
    FULL_WORK="$WORK_ROOT/$SAFE_NAME/full"
    run_babeldoc "$SOURCE_PDF" "$FULL_OUTPUT" "$FULL_WORK" "$PAGES_PER_PART" "$FULL_WORK/run.log"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
