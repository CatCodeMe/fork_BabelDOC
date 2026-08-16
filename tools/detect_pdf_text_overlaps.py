#!/usr/bin/env python3
"""Report rendered-text line overlaps in a PDF half/page range.

Use after rendering: this operates on the final glyph geometry, rather than
assuming the pre-typesetting paragraph boxes accurately represent CJK metrics.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def overlaps(a: fitz.Rect, b: fitz.Rect) -> bool:
    vertical = min(a.y1, b.y1) - max(a.y0, b.y0)
    horizontal = min(a.x1, b.x1) - max(a.x0, b.x0)
    return vertical > min(a.height, b.height) * 0.15 and horizontal > 12


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--right-half", action="store_true")
    parser.add_argument("--pages", default="")
    args = parser.parse_args()
    pdf = fitz.open(args.pdf)
    selected = {int(value) - 1 for value in args.pages.split(",") if value.strip()} or set(range(pdf.page_count))
    total = 0
    for index in sorted(selected):
        page = pdf[index]
        midpoint = page.rect.width / 2
        lines = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                rect = fitz.Rect(line["bbox"])
                text = "".join(span["text"] for span in line["spans"]).strip()
                if text and (not args.right_half or rect.x0 >= midpoint):
                    lines.append((rect, text))
        for left in range(len(lines)):
            for right in range(left + 1, len(lines)):
                if overlaps(lines[left][0], lines[right][0]):
                    total += 1
                    print(f"page={index + 1} overlap={lines[left][1]!r} <> {lines[right][1]!r}")
    print(f"overlaps={total}")


if __name__ == "__main__":
    main()
