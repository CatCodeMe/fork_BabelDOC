#!/usr/bin/env zsh
# Translate a short technical paper into output/paper without chunk orchestration.
#
# Shares the environment contract with translate-chunks.zsh:
#   BABELDOC_CONFIG              config file (default: babeldoc.ko-zh.toml)
#   BABELDOC_LANG_IN             source language (default: en)
#   BABELDOC_LANG_OUT            target language (default: zh-CN)
#   BABELDOC_SYSTEM_PROMPT_FILE  prompt file, overriding custom-system-prompt
#
# Everything lives in a function so `zsh -n` is a meaningful check: at top level
# zsh still expands "$(<file)" while parsing, and with assignments unexecuted
# that reads an empty filename.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./translate-paper.zsh /absolute/path/paper.pdf

A single BabelDOC job with no internal part splitting, written to
output/papers/<name>/. Use translate-chunks.zsh for anything book-length.
EOF
}

main() {
  local ROOT_DIR=${0:A:h}
  local CONFIG_FILE=${BABELDOC_CONFIG:-"$ROOT_DIR/babeldoc.ko-zh.toml"}
  local LANG_IN=${BABELDOC_LANG_IN:-en}
  local LANG_OUT=${BABELDOC_LANG_OUT:-zh-CN}
  local PROMPT_FILE=${BABELDOC_SYSTEM_PROMPT_FILE:-"$ROOT_DIR/prompts/en-zh-technical.txt"}

  [[ $# -eq 1 ]] || { usage >&2; return 2; }
  local SOURCE_PDF=${1:A}
  [[ -f "$CONFIG_FILE" ]] || {
    print -u2 "Missing config: $CONFIG_FILE"
    print -u2 "Point BABELDOC_CONFIG at a config file."
    return 1
  }
  [[ -f "$PROMPT_FILE" ]] || { print -u2 "Missing prompt: $PROMPT_FILE"; return 1; }
  [[ -f "$SOURCE_PDF" ]] || { print -u2 "PDF not found: $SOURCE_PDF"; return 1; }

  local SAFE_NAME=$(print -rn -- "${SOURCE_PDF:t:r}" | tr -cs 'A-Za-z0-9._-' '_')
  local OUTPUT_DIR="$ROOT_DIR/output/papers/$SAFE_NAME"
  local WORK_DIR="$ROOT_DIR/work/papers/$SAFE_NAME"
  local PROMPT_TEXT=$(< "$PROMPT_FILE")

  print "Input:  $SOURCE_PDF"
  print "Output: $OUTPUT_DIR"
  print "Lang:   $LANG_IN -> $LANG_OUT\n"

  (
    cd "$ROOT_DIR"
    uv run --no-dev babeldoc --config "$CONFIG_FILE" --files "$SOURCE_PDF" \
      --qps 1 --pool-max-workers 1 --max-pages-per-part 0 \
      --lang-in "$LANG_IN" --lang-out "$LANG_OUT" \
      --custom-system-prompt "$PROMPT_TEXT" \
      --toc-layout-adapter auto --watermark-output-mode no_watermark \
      --output "$OUTPUT_DIR" --working-dir "$WORK_DIR"
  )
}

main "$@"
