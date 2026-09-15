#!/usr/bin/env python3
"""Reflow translated bibliography pages into one readable right-hand column."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz


def right_text(page: fitz.Page) -> str:
    mid = page.rect.width / 2
    blocks = sorted(page.get_text("blocks"), key=lambda block: (block[1], block[0]))
    return "\n".join(
        block[4].strip() for block in blocks if block[0] >= mid and block[4].strip()
    )


def entries(text: str) -> list[str]:
    text = re.sub(r"(?<!\n)\s*(\[\d+\])", r"\n\1", text)
    return [item.strip() for item in re.split(r"(?=\[\d+\])", text) if item.strip()]


def main(source: Path, dual: Path, target: Path) -> None:
    src, doc = fitz.open(source), fitz.open(dual)
    ref_pages = [
        index
        for index, page in enumerate(src)
        if index >= 15 and re.match(r"\s*\[\d+\]", page.get_text("text"))
    ]
    if not ref_pages:
        raise SystemExit("No bibliography pages found")
    queue = entries("\n".join(right_text(doc[index]) for index in ref_pages))
    for index in ref_pages:
        page = doc[index]
        rect = page.rect
        area = fitz.Rect(rect.width / 2 + 8, 36, rect.width - 16, rect.height - 28)
        page.draw_rect(area, color=None, fill=(1, 1, 1), overlay=True)
        text = ""
        while queue:
            candidate = text + ("\n\n" if text else "") + queue[0]
            if (
                page.insert_textbox(
                    area,
                    candidate,
                    fontname="china-s",
                    fontsize=6.3,
                    lineheight=1.25,
                    color=(0, 0, 0),
                    overlay=True,
                )
                < 0
            ):
                break
            text, queue = candidate, queue[1:]
            page.draw_rect(area, color=None, fill=(1, 1, 1), overlay=True)
        if text:
            page.insert_textbox(
                area,
                text,
                fontname="china-s",
                fontsize=6.3,
                lineheight=1.25,
                color=(0, 0, 0),
                overlay=True,
            )
    if queue:
        raise SystemExit(f"Bibliography overflow: {len(queue)} entries remain")
    doc.save(target, garbage=4, deflate=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
