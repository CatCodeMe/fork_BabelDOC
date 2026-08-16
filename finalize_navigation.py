#!/usr/bin/env python3
"""Create a navigable merged dual PDF with an explicit safe fallback.

Preference order:
1. restore embedded source outline and numeric internal links;
2. when the source has no usable outline, generate sidebar bookmarks from
   high-confidence numbered bold headings on the translated/right-hand page.

The fallback never invents in-page TOC links or chapter wording.  Its provenance
is printed so callers can record whether navigation came from the source or was
generated from observed headings.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import fitz


HEADING = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(.+)$")
NUMBER_START = re.compile(r"(?:^|\s)\d+(?:\.\d+)+\.?\s+")


def generated_outline(pdf: fitz.Document) -> list[list[object]]:
    outline: list[list[object]] = []
    seen, chapters = set(), set()
    for page_number, page in enumerate(pdf, start=1):
        midpoint = page.rect.width / 2
        page_text = page.get_text().lower()
        # A contents page can itself contain perfect-looking section numbers,
        # but its destinations are printed page labels, not its own physical
        # page. It is never a safe source for generated bookmarks.
        if "contents" in page_text or "目录" in page_text:
            continue
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans, box = line["spans"], line["bbox"]
                text = "".join(span["text"] for span in spans).strip()
                match = HEADING.match(text)
                # A numerical expression in normal body text is not a heading.
                # This fallback only accepts hierarchical, bold section labels;
                # publishers that lose that evidence safely get no generated
                # outline rather than an incorrect navigation tree.
                if (
                    not match
                    or box[0] < midpoint
                    or len(NUMBER_START.findall(text)) != 1
                    or not any(span["flags"] & 16 for span in spans)
                ):
                    continue
                number = match.group(1)
                if number in seen:
                    continue
                seen.add(number)
                chapter = number.split(".", 1)[0]
                if chapter not in chapters:
                    chapters.add(chapter)
                    outline.append([1, f"第 {chapter} 章", page_number])
                outline.append([number.count(".") + 1, text, page_number])
    return outline


def restore_numeric_links(source: fitz.Document, dual: fitz.Document) -> int:
    restored = 0
    for page_no in range(source.page_count):
        src_page, dst_page = source[page_no], dual[page_no]
        sx, sy = (dst_page.rect.width / 2) / src_page.rect.width, dst_page.rect.height / src_page.rect.height
        for link in src_page.get_links():
            target_page = link.get("page")
            if not isinstance(target_page, int) or target_page < 0:
                continue
            origin, target = link["from"], link.get("to", fitz.Point(0, 0))
            dst_page.insert_link({
                "kind": fitz.LINK_GOTO,
                "from": fitz.Rect(origin.x0 * sx, origin.y0 * sy, origin.x1 * sx, origin.y1 * sy),
                "page": target_page,
                "to": fitz.Point(target.x * sx, target.y * sy),
            })
            restored += 1
    return restored


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("dual", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source, dual = fitz.open(args.source), fitz.open(args.dual)
    if source.page_count != dual.page_count:
        raise SystemExit(f"Page count differs: source={source.page_count}, dual={dual.page_count}.")
    source_toc = source.get_toc(simple=True)
    if source_toc:
        dual.set_toc(source_toc)
        restored = restore_numeric_links(source, dual)
        provenance = "source-outline"
    else:
        dual.set_toc(generated_outline(dual))
        restored = 0
        provenance = "generated-numbered-bold-headings"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dual.save(args.output, garbage=3, deflate=True)
    print(f"navigation_provenance={provenance} bookmarks={len(dual.get_toc())} restored_internal_links={restored}")


if __name__ == "__main__":
    main()
