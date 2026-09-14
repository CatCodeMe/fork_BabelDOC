#!/usr/bin/env python3
"""Translate a PDF's bookmark titles, keeping the original page destinations.

Why this is needed: BabelDOC's ``migrate_toc`` copies the *source* PDF's outline
into the translated PDF verbatim, so the bookmarks stay in the source language,
and it deliberately skips the mono PDF entirely (that call is commented out
upstream). Page counts are identical between source and translation, so the
destinations are already correct — only the labels need work.

Reuses the EPUB translation client, which was written to be format-agnostic.

Usage:
    uv run --no-dev python tools/translate_outline.py SOURCE.pdf TARGET.pdf ... \
        --config babeldoc.en-zh.toml --source-lang en --target-lang zh-CN \
        --prompt prompts/en-zh-technical.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402
from babeldoc.format.epub.client import EpubTranslator  # noqa: E402
from babeldoc.format.epub.client import TranslationSettings  # noqa: E402
from babeldoc.format.epub.client import build_system_prompt  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="PDF to read the outline from")
    parser.add_argument("targets", type=Path, nargs="+", help="PDFs to relabel")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, default=None)
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh-CN")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="overwrite the targets (default writes *.nav-<lang>.pdf)",
    )
    args = parser.parse_args(argv[1:])

    with fitz.open(args.source) as source:
        toc = source.get_toc(simple=True)
    if not toc:
        print(f"no outline in {args.source}; nothing to do")
        return 0

    titles = [entry[1] for entry in toc]
    unique = sorted(set(titles))
    print(f"outline entries : {len(titles)} ({len(unique)} unique titles)")

    settings = TranslationSettings.from_toml(
        args.config,
        lang_in=args.source_lang,
        lang_out=args.target_lang,
        batch_size=args.batch_size,
    )
    client = EpubTranslator(
        settings,
        build_system_prompt(settings, args.prompt),
        settings.load_glossaries(),
    )

    context = (
        "These are book outline / table-of-contents entries from a technical book. "
        "Keep numbering such as '1.2.3' and any trailing page number unchanged."
    )
    mapping: dict[str, str] = {}
    for start in range(0, len(unique), settings.batch_size):
        batch = unique[start : start + settings.batch_size]
        for original, translated in zip(
            batch, client.translate_many(batch, context=context), strict=False
        ):
            mapping[original] = translated
        print(
            f"  translated {min(start + settings.batch_size, len(unique))}/{len(unique)}"
        )

    localized = [[level, mapping.get(title, title), page] for level, title, page in toc]

    for target in args.targets:
        if args.in_place:
            # PyMuPDF refuses to save over the file it opened, and an
            # interrupted run must not leave a half-written deliverable.
            # Write a sibling, then swap it in.
            output = target.with_name(target.name + ".outline-tmp")
        else:
            output = target.with_suffix(f".nav-{args.target_lang}.pdf")
        with fitz.open(target) as document:
            document.set_toc(localized)
            document.save(output, garbage=3, deflate=True)
        if args.in_place:
            output.replace(target)
            output = target
        with fitz.open(output) as check:
            written = check.get_toc(simple=True)
        print(f"  {output.name}: {len(written)} bookmarks")
        for entry in written[:3]:
            print(f"      {entry}")

    stats = client.stats()
    print(
        f"model calls     : {stats['translate_calls']} (cache hits {stats['cache_hits']})"
    )
    if stats["failed_segments"]:
        print(
            f"WARNING         : {stats['failed_segments']} titles kept the source text"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
