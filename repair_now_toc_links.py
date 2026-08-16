#!/usr/bin/env python3
"""Add bookmarks and TOC-row links for a NOW Publishers dual PDF.

The source used here has no embedded outline or links after physical chunking,
but its first pages contain numbered, aligned TOC rows. This recovery is explicit
for that layout and writes a sibling PDF without modifying the merged original.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import fitz

ROW = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s+(\d{1,4})\s*$")


def rows(page: fitz.Page):
    grouped: dict[float, list[tuple[fitz.Rect, str]]] = defaultdict(list)
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        grouped[round(y0, 1)].append((fitz.Rect(x0, y0, x1, y1), text))
    for words in grouped.values():
        words.sort(key=lambda item: item[0].x0)
        text = " ".join(word for _, word in words)
        match = ROW.match(text)
        if match:
            rect = fitz.Rect(words[0][0])
            for word_rect, _ in words[1:]:
                rect |= word_rect
            yield match, rect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("dual", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--contents-pages", type=int, default=3)
    parser.add_argument("--printed-page-offset", type=int, default=200)
    args = parser.parse_args()
    source, dual = fitz.open(args.source), fitz.open(args.dual)
    if source.page_count != dual.page_count:
        raise SystemExit("Source and dual page counts differ")
    outline, inserted = [], 0
    for source_index in range(min(args.contents_pages, source.page_count)):
        src_page, dst_page = source[source_index], dual[source_index]
        sx, sy = (dst_page.rect.width / 2) / src_page.rect.width, dst_page.rect.height / src_page.rect.height
        for match, rect in rows(src_page):
            number, title, printed = match.groups()
            destination = int(printed) - args.printed_page_offset
            if not 0 <= destination < dual.page_count:
                continue
            level = number.count(".") + 1
            outline.append([level, f"{number} {title}", destination + 1])
            left = fitz.Rect(rect.x0 * sx, rect.y0 * sy, rect.x1 * sx, rect.y1 * sy)
            for link_rect in (left, fitz.Rect(left.x0 + dst_page.rect.width / 2, left.y0, left.x1 + dst_page.rect.width / 2, left.y1)):
                dst_page.insert_link({"kind": fitz.LINK_GOTO, "from": link_rect, "page": destination, "to": fitz.Point(0, 0)})
                inserted += 1
    dual.set_toc(outline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dual.save(args.output, garbage=3, deflate=True)
    print(f"bookmarks={len(outline)} toc_links={inserted}")


if __name__ == "__main__":
    main()
