#!/usr/bin/env python3
"""Generate conservative PDF bookmarks from numbered bold headings on the Chinese side."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import fitz

HEADING = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(.+)$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dual", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    pdf = fitz.open(args.dual)
    toc, seen, chapters = [], set(), set()
    for page_number, page in enumerate(pdf, start=1):
        midpoint = page.rect.width / 2
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans, box = line["spans"], line["bbox"]
                text = "".join(span["text"] for span in spans).strip()
                match = HEADING.match(text)
                # Font flag 16 is bold. Restrict to the Chinese/right page and
                # numbered bold headings so body references do not become TOC.
                if not match or box[0] < midpoint or not any(span["flags"] & 16 for span in spans):
                    continue
                number = match.group(1)
                if number in seen:
                    continue
                seen.add(number)
                chapter = number.split(".", 1)[0]
                if chapter not in chapters:
                    chapters.add(chapter)
                    toc.append([1, f"第 {chapter} 章", page_number])
                toc.append([number.count(".") + 1, text, page_number])
    pdf.set_toc(toc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(args.output, garbage=3, deflate=True)
    print(f"generated_bookmarks={len(toc)}")


if __name__ == "__main__":
    main()
