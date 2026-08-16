#!/usr/bin/env python3
"""Audit saved BabelDOC translation trackers for collapsed structural content.

This is deliberately read-only: it identifies high-value regression samples
without modifying completed translations.  A tracker cannot recover source line
coordinates, so its findings are candidates for visual/source-PDF validation,
not a claim that every flagged paragraph is malformed.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator


TOC = re.compile(r"\b(table of contents|contents|brief contents)\b", re.I)
CHAPTER_LIST = re.compile(r"\bthis chapter covers\b", re.I)
BULLET = re.compile(r"(?:^|\s)[■▪•◦](?:\s|$)")
NUMBERED = re.compile(r"(?:^|\s)\d+(?:\.\d+)*[.)]?\s+\S")


def paragraphs(node: object) -> Iterator[dict]:
    if isinstance(node, dict):
        # A paragraph tracker includes source reconstruction text. Nested LLM
        # trackers also have input/output, but contain the whole prompt and
        # would turn the corpus report into a prompt-frequency report.
        if "pdf_unicode" in node and "input" in node and "output" in node:
            yield node
            return
        for value in node.values():
            yield from paragraphs(value)
    elif isinstance(node, list):
        for value in node:
            yield from paragraphs(value)


def classify(text: str) -> list[str]:
    labels = []
    if TOC.search(text):
        labels.append("toc-heading")
    if CHAPTER_LIST.search(text):
        labels.append("chapter-cover-list")
    if BULLET.search(text):
        labels.append("bullet-list")
    if len(NUMBERED.findall(text)) >= 3:
        labels.append("numbered-run")
    # Long, flattened sequence with multiple likely item endings.  It catches
    # unnumbered publisher contents rows, but is intentionally only a review
    # signal because trackers have already lost original line geometry.
    if len(text) >= 180 and len(re.findall(r"\s(?:\d{1,4}|[ivxlcdm]{1,8})\s", text, re.I)) >= 3:
        labels.append("possible-collapsed-rows")
    return labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="work/chunks-style directory")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    by_book: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[tuple[str, str], tuple[Path, str]] = {}
    tracker_count = 0
    for tracker in sorted(args.root.rglob("translate_tracking.json")):
        try:
            raw = tracker.read_bytes().decode("utf-8", errors="replace")
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(raw.lstrip())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"skip {tracker}: {exc}")
            continue
        tracker_count += 1
        book = tracker.relative_to(args.root).parts[0]
        for entry in paragraphs(data):
            text = str(entry.get("pdf_unicode") or entry.get("input") or "").replace("\n", " ")
            for label in classify(text):
                by_book[book][label] += 1
                examples.setdefault((book, label), (tracker, text))

    lines = [
        "# Translation structure corpus audit",
        "",
        "This report is generated from `translate_tracking.json` and is read-only.",
        "Flags are regression candidates, not proof of a visual defect: trackers do not retain source line geometry.",
        "",
        f"Trackers scanned: {tracker_count}",
        "",
        "| Book | TOC heading | Chapter list | Bullet list | Numbered run | Possible collapsed rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for book, counts in sorted(by_book.items()):
        lines.append(
            f"| `{book}` | {counts['toc-heading']} | {counts['chapter-cover-list']} | "
            f"{counts['bullet-list']} | {counts['numbered-run']} | {counts['possible-collapsed-rows']} |"
        )
    lines.extend(["", "## Representative candidates", ""])
    for (book, label), (tracker, text) in sorted(examples.items()):
        relative = tracker.relative_to(args.root)
        excerpt = re.sub(r"\s+", " ", text)[:360]
        lines.extend([f"- `{book}` — **{label}** (`{relative}`): {excerpt}", ""])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.output} for {tracker_count} trackers")


if __name__ == "__main__":
    main()
