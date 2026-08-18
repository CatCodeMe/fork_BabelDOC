#!/usr/bin/env python3
"""Restore O'Reilly-style contents links when a source PDF has no outline.

The profile relies on a verified invariant, not a filename: numbered contents
rows use a printed Arabic page label and the first printed body page has a fixed
physical-page offset.  It makes the original and translated halves of each row
clickable and emits the same rows as sidebar bookmarks.
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import fitz

ARABIC_PAGE = re.compile(r"\b(\d{1,4})\s*$")


def visual_rows(page: fitz.Page):
    grouped: dict[float, list[tuple[fitz.Rect, str]]] = defaultdict(list)
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        grouped[round(y0, 1)].append((fitz.Rect(x0, y0, x1, y1), text))
    for words in grouped.values():
        words.sort(key=lambda item: item[0].x0)
        text = " ".join(value for _, value in words).strip()
        match = ARABIC_PAGE.search(text)
        if not match:
            continue
        rect = fitz.Rect(words[0][0])
        for word_rect, _ in words[1:]:
            rect |= word_rect
        title = text[: match.start()].rstrip(" .")
        if title:
            yield title, int(match.group(1)), rect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("dual", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--contents-start", type=int, default=9, help="1-based source page")
    parser.add_argument("--contents-end", type=int, default=21, help="inclusive 1-based source page")
    parser.add_argument("--printed-page-offset", type=int, default=28, help="0-based destination for printed page 1 minus 1")
    args = parser.parse_args()
    source, dual = fitz.open(args.source), fitz.open(args.dual)
    if source.page_count != dual.page_count:
        raise SystemExit("Source and dual page counts differ")
    outline, inserted, skipped = [], 0, 0
    seen = set()
    for index in range(args.contents_start - 1, min(args.contents_end, source.page_count)):
        src_page, dst_page = source[index], dual[index]
        sx = (dst_page.rect.width / 2) / src_page.rect.width
        sy = dst_page.rect.height / src_page.rect.height
        for title, printed, rect in visual_rows(src_page):
            destination = printed + args.printed_page_offset - 1
            if not 0 <= destination < dual.page_count:
                skipped += 1
                continue
            key = (title, printed)
            if key not in seen:
                seen.add(key)
                outline.append([1, title, destination + 1])
            left = fitz.Rect(rect.x0 * sx, rect.y0 * sy, rect.x1 * sx, rect.y1 * sy)
            for link_rect in (left, left + (dst_page.rect.width / 2, 0, dst_page.rect.width / 2, 0)):
                dst_page.insert_link({"kind": fitz.LINK_GOTO, "from": link_rect, "page": destination, "to": fitz.Point(0, 0)})
                inserted += 1
    dual.set_toc(outline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dual.save(args.output, garbage=3, deflate=True)
    print(f"bookmarks={len(outline)} toc_links={inserted} skipped={skipped}")


if __name__ == "__main__":
    main()
