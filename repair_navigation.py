#!/usr/bin/env python3
"""Restore outline bookmarks and original-side internal links to a dual PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def scale_rect(rect: fitz.Rect, sx: float, sy: float) -> fitz.Rect:
    return fitz.Rect(rect.x0 * sx, rect.y0 * sy, rect.x1 * sx, rect.y1 * sy)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Original PDF with navigation")
    parser.add_argument("dual", type=Path, help="Merged bilingual PDF")
    parser.add_argument("output", type=Path, help="New navigable bilingual PDF")
    args = parser.parse_args()

    source = fitz.open(args.source)
    dual = fitz.open(args.dual)
    if source.page_count != dual.page_count:
        raise SystemExit(
            f"Page count differs: source={source.page_count}, dual={dual.page_count}."
        )

    toc = source.get_toc(simple=True)
    if toc:
        dual.set_toc(toc)

    restored = 0
    for page_no in range(source.page_count):
        src_page = source[page_no]
        dst_page = dual[page_no]
        # Dual pages keep the original page in the left half.
        sx = (dst_page.rect.width / 2) / src_page.rect.width
        sy = dst_page.rect.height / src_page.rect.height
        for link in src_page.get_links():
            # Some PDFs expose named destinations as strings rather than
            # numeric page indexes.  Only numeric internal destinations can
            # be copied safely into the rebuilt bilingual PDF.
            target_page = link.get("page")
            if not isinstance(target_page, int) or target_page < 0:
                continue
            link_data = {
                "kind": fitz.LINK_GOTO,
                "from": scale_rect(link["from"], sx, sy),
                "page": target_page,
                "to": fitz.Point(link.get("to", fitz.Point(0, 0)).x * sx,
                                 link.get("to", fitz.Point(0, 0)).y * sy),
            }
            dst_page.insert_link(link_data)
            restored += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    dual.save(args.output, garbage=3, deflate=True)
    print(
        f"Created {args.output}\n"
        f"pages={dual.page_count} toc_entries={len(toc)} restored_internal_links={restored}"
    )


if __name__ == "__main__":
    main()
