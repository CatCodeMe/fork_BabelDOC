#!/usr/bin/env python3
"""Replace bibliography pages in a bilingual paper PDF with source pages."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz


def main(source_path: Path, dual_path: Path, output_path: Path) -> None:
    source, dual, result = fitz.open(source_path), fitz.open(dual_path), fitz.open()
    first_reference_page = next(
        index
        for index, page in enumerate(source)
        if index >= 15 and re.match(r"\s*\[\d+\]", page.get_text("text"))
    )
    reference_pages = set(range(first_reference_page, source.page_count))
    for index in range(source.page_count):
        result.insert_pdf(
            source if index in reference_pages else dual, from_page=index, to_page=index
        )
    result.set_toc(source.get_toc(simple=False))
    result.save(output_path, garbage=4, deflate=True)
    print(
        f"pages={result.page_count} original_reference_pages={sorted(i + 1 for i in reference_pages)}"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
