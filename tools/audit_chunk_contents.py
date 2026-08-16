#!/usr/bin/env python3
"""Audit the current deliverable PDF for every book under ``output/chunks``.

The report deliberately chooses one canonical PDF per book (the navigable
merged PDF when available, otherwise the ordinary merged PDF, otherwise the
first original chunk).  It flags rendered right-page line collisions only on
pages whose original/left half identifies itself as a contents page.  This
makes the output a small visual-review queue rather than a noisy scan of every
body paragraph or historical retry artifact.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import fitz


CONTENTS_HEADING = re.compile(r"^(?:table of |brief )?contents$|^目录$", re.I)
TOC_ROW = re.compile(r"(?:\.{4,}|\s(?:\d{1,4}|[ivxlcdm]{1,8})\s*$)", re.I)


def boxes_overlap(a: fitz.Rect, b: fitz.Rect) -> bool:
    vertical = min(a.y1, b.y1) - max(a.y0, b.y0)
    horizontal = min(a.x1, b.x1) - max(a.x0, b.x0)
    return vertical > min(a.height, b.height) * 0.15 and horizontal > 12


@dataclass(frozen=True)
class AuditRow:
    book: str
    pdf: Path
    pages: int
    contents_pages: tuple[int, ...]
    right_overlaps: int


def canonical_pdf(book_dir: Path) -> Path | None:
    merged = book_dir / "merged"
    for pattern in ("*.dual.navigable.pdf", "*.dual.pdf"):
        choices = sorted(merged.glob(pattern)) if merged.is_dir() else []
        if choices:
            return choices[0]
    first_chunk = book_dir / "chunk-1-pages-1-50"
    choices = sorted(first_chunk.glob("*.dual.pdf")) if first_chunk.is_dir() else []
    return choices[0] if choices else None


def right_overlap_count(page: fitz.Page) -> int:
    midpoint = page.rect.width / 2
    lines: list[tuple[fitz.Rect, str]] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            rect = fitz.Rect(line["bbox"])
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text and rect.x0 >= midpoint:
                lines.append((rect, text))
    return sum(
        boxes_overlap(lines[left][0], lines[right][0])
        for left in range(len(lines))
        for right in range(left + 1, len(lines))
    )


def audit(pdf_path: Path, book: str) -> AuditRow:
    pdf = fitz.open(pdf_path)
    contents_pages, overlaps = [], 0
    following_contents = False
    for index, page in enumerate(pdf, start=1):
        midpoint = page.rect.width / 2
        left_text = page.get_text("text", clip=fitz.Rect(0, 0, midpoint, page.rect.height))
        left_lines = [line.strip() for line in left_text.splitlines() if line.strip()]
        has_heading = any(CONTENTS_HEADING.fullmatch(line) for line in left_lines)
        looks_like_continuation = sum(bool(TOC_ROW.search(line)) for line in left_lines) >= 4
        is_contents = has_heading or (following_contents and looks_like_continuation)
        following_contents = is_contents
        if not is_contents:
            continue
        contents_pages.append(index)
        overlaps += right_overlap_count(page)
    return AuditRow(book, pdf_path, pdf.page_count, tuple(contents_pages), overlaps)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="output/chunks directory")
    parser.add_argument("output", type=Path, help="Markdown report path")
    args = parser.parse_args()

    rows = []
    for book_dir in sorted(path for path in args.root.iterdir() if path.is_dir()):
        pdf = canonical_pdf(book_dir)
        if pdf is not None:
            rows.append(audit(pdf, book_dir.name))

    report = [
        "# Current chunk contents audit",
        "",
        "One current deliverable is selected per book: navigable merged, merged, then original first chunk.",
        "Rendered overlap counts apply only to pages whose left/original half contains a contents heading.",
        "A zero means no detected text-box collision, not a claim that the publisher layout is aesthetically identical.",
        "",
        "| Book | Selected PDF | Pages | Contents pages | Right-page overlaps | Review |",
        "| --- | --- | ---: | --- | ---: | --- |",
    ]
    for row in rows:
        review = "inspect" if row.right_overlaps else "clear"
        pages = ", ".join(map(str, row.contents_pages)) or "none detected"
        report.append(
            f"| `{row.book}` | `{row.pdf.relative_to(args.root)}` | {row.pages} | {pages} | {row.right_overlaps} | {review} |"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"wrote {args.output} for {len(rows)} books")


if __name__ == "__main__":
    main()
