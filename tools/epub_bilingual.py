#!/usr/bin/env python3
"""Produce a bilingual EPUB from a source EPUB.

Examples:
    # Layout preview: no API calls, the right column echoes the source text.
    uv run --no-dev python tools/epub_bilingual.py BOOK.epub --dry-run \
        --subset-chars 16000 --output tmp/preview.epub

    # Real translation (uses the same prompts/glossary/cache as the PDF path).
    uv run --no-dev python tools/epub_bilingual.py BOOK.epub \
        --config babeldoc.ko-zh.toml --output output/book.zh-CN.bilingual.epub
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from babeldoc.format.epub.archive import EpubArchive  # noqa: E402
from babeldoc.format.epub.normalize import NormalizationPolicy  # noqa: E402
from babeldoc.format.epub.normalize import WordVocabulary  # noqa: E402
from babeldoc.format.epub.normalize import check_conservation  # noqa: E402
from babeldoc.format.epub.normalize import is_page_list_segment  # noqa: E402
from babeldoc.format.epub.normalize import iter_blocks  # noqa: E402
from babeldoc.format.epub.normalize import looks_like_label_document  # noqa: E402
from babeldoc.format.epub.normalize import merge_blocks  # noqa: E402
from babeldoc.format.epub.style_profile import Role  # noqa: E402
from babeldoc.format.epub.style_profile import StyleProfile  # noqa: E402
from babeldoc.format.epub.writer import inject_stylesheet  # noqa: E402
from babeldoc.format.epub.writer import repack  # noqa: E402
from babeldoc.format.epub.writer import stylesheet_href_for  # noqa: E402
from lxml import etree  # noqa: E402


def segment_to_drop(segment):
    """Record a page-list segment as intentionally dropped."""
    from babeldoc.format.epub.normalize import DroppedBlock

    return DroppedBlock(
        href=segment.href,
        index=segment.index,
        role=segment.role,
        text=segment.text,
        reason="page list",
    )


def document_context(document) -> str:
    """Give the model the chapter and section it is translating inside."""
    titles = []
    for element in document.root.iter():
        if not isinstance(element.tag, str):
            continue
        if etree.QName(element).localname in {"h1", "h2", "h3", "title"}:
            text = "".join(element.itertext()).strip()
            if text:
                titles.append(text)
        if len(titles) >= 3:
            break
    return " > ".join(titles)


def collect_stylesheets(archive: EpubArchive) -> list[str]:
    return [
        archive.read_bytes(item.href).decode("utf-8", errors="replace")
        for item in archive.manifest.values()
        if item.media_type == "text/css"
    ]


def subtree_char_count(archive: EpubArchive, href: str) -> int:
    return len("".join(archive.parse_xhtml(href).itertext()))


def choose_subset(archive: EpubArchive, budget: int) -> list[str]:
    """Take spine documents from the front until ``budget`` characters is met."""
    chosen: list[str] = []
    total = 0
    for href in archive.spine:
        chosen.append(href)
        total += subtree_char_count(archive, href)
        if total >= budget:
            break
    return chosen


def choose_range(archive: EpubArchive, start: int, end: int) -> list[str]:
    """Select spine documents by 1-based inclusive index."""
    count = len(archive.spine)
    if start < 1 or end < start or start > count:
        raise SystemExit(
            f"invalid spine range {start}:{end} (book has {count} documents)"
        )
    return archive.spine[start - 1 : min(end, count)]


class EchoTranslator:
    """Stand-in client so the layout can be reviewed without API calls."""

    failed: list[str] = []

    def translate_many(self, texts: list[str], context: str = "") -> list[str]:
        return list(texts)

    def stats(self) -> dict[str, int]:
        return {"translate_calls": 0, "cache_hits": 0, "failed_segments": 0}


def build_client(args):
    """A real batched client, or an echo stand-in for --dry-run."""
    if args.dry_run:
        return EchoTranslator(), None

    from babeldoc.format.epub.client import EpubTranslator
    from babeldoc.format.epub.client import TranslationSettings
    from babeldoc.format.epub.client import build_system_prompt

    settings = TranslationSettings(lang_in=args.source_lang, lang_out=args.target_lang)
    if args.config is not None:
        settings = TranslationSettings.from_toml(
            args.config,
            lang_in=args.source_lang,
            lang_out=args.target_lang,
            batch_size=args.batch_size,
        )
    elif args.prompt is not None:
        settings.batch_size = args.batch_size
    glossaries = settings.load_glossaries()
    system_prompt = build_system_prompt(settings, args.prompt)
    client = EpubTranslator(settings, system_prompt, glossaries)
    print(f"model           : {settings.model} @ {settings.base_url}")
    print(f"prompt          : {args.prompt or '(from config or default)'}")
    print(f"glossaries      : {[g.name for g in glossaries]}")
    print(f"batch size      : {settings.batch_size}")
    return client, settings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=["side_by_side", "bilingual", "replace"],
        default="side_by_side",
    )
    parser.add_argument("--target-lang", default="zh-CN")
    parser.add_argument(
        "--subset-chars",
        type=int,
        default=0,
        help="only translate the first N characters of the book (0 = all)",
    )
    parser.add_argument(
        "--spine-start", type=int, default=0, help="first spine document (1-based)"
    )
    parser.add_argument(
        "--spine-end", type=int, default=0, help="last spine document (inclusive)"
    )
    parser.add_argument(
        "--labels-mode",
        choices=["replace", "bilingual", "side_by_side", "keep"],
        default="replace",
        help="how to handle table-of-contents / index documents "
        "('keep' leaves them untranslated)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="echo the source into the translation column instead of calling the API",
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--prompt", type=Path, default=None)
    parser.add_argument(
        "--batch-size", type=int, default=6, help="segments per model request"
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=0,
        help="stop after translating N segments (0 = the whole subset)",
    )
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv[1:])

    with EpubArchive.open(args.epub) as archive:
        stylesheets = collect_stylesheets(archive)
        all_documents = list(archive.documents())
        profile = StyleProfile.build(stylesheets, all_documents)

        if args.spine_start:
            selected = choose_range(
                archive, args.spine_start, args.spine_end or len(archive.spine)
            )
            targets = set(selected)
        elif args.subset_chars:
            targets = set(choose_subset(archive, args.subset_chars))
        else:
            targets = set(archive.spine)

        per_document = []
        for document in all_documents:
            if document.href not in targets:
                continue
            per_document.append((document, iter_blocks(document, profile)))
        all_blocks = [block for _doc, blocks in per_document for block in blocks]

        policy = NormalizationPolicy.detect(all_blocks)
        print(f"book shape      : {policy.describe()}")
        print(f"documents       : {len(per_document)} of {len(all_documents)}")

        translator, _settings = build_client(args)

        # A whole-book run takes many minutes; print progress and flush, or a
        # redirected log stays empty until the process exits.
        import time

        changed: dict[str, etree._ElementTree] = {}
        started = time.monotonic()
        document_count = len(per_document)
        translated_documents = 0
        segments_total = 0
        translated_total = 0
        dropped_total = 0
        all_kept: list = []
        all_dropped: list = []
        label_documents: list[str] = []

        for document, blocks in per_document:
            translated_documents += 1
            label = document.href.split("/")[-1]
            segments, dropped = merge_blocks(blocks, WordVocabulary(), policy)
            kept = [s for s in segments if not is_page_list_segment(s.text)]
            dropped_total += len(dropped) + (len(segments) - len(kept))
            segments_total += len(kept)

            pending = [
                segment
                for segment in kept
                if segment.role is not Role.CODE and segment.translatable_slots()
            ]
            if args.max_segments:
                remaining = args.max_segments - translated_total
                pending = pending[: max(0, remaining)]

            # A table of contents paired into two columns is a wall of short
            # entries; translate those in place and report which decision was made.
            label_document = looks_like_label_document(kept)
            if label_document:
                document_mode = args.labels_mode
                if document_mode == "keep":
                    inject_stylesheet(
                        stylesheet_href_for(document.href, archive.opf_dir)
                    )(document.tree)
                    changed[document.href] = document.tree
                    label_documents.append(document.href)
                    all_kept.extend(kept)
                    all_dropped.extend(dropped)
                    continue
            else:
                document_mode = args.mode
            if label_document:
                label_documents.append(document.href)

            context = document_context(document)
            for start in range(0, len(pending), args.batch_size):
                batch = pending[start : start + args.batch_size]
                translations = translator.translate_many(
                    [segment.text for segment in batch], context=context
                )
                for segment, translated in zip(batch, translations, strict=False):
                    if translated and translated.strip():
                        segment.apply(
                            translated, mode=document_mode, lang=args.target_lang
                        )
                        translated_total += 1

            inject_stylesheet(stylesheet_href_for(document.href, archive.opf_dir))(
                document.tree
            )
            changed[document.href] = document.tree

            all_kept.extend(kept)
            all_dropped.extend(dropped)
            all_dropped.extend(segment_to_drop(s) for s in segments if s not in kept)

            elapsed = time.monotonic() - started
            rate = translated_total / elapsed if elapsed > 0 else 0.0
            print(
                f"[{translated_documents}/{document_count}] {label:<28} "
                f"{len(kept):>4} segments, {translated_total} translated, "
                f"{elapsed:5.0f}s elapsed, {rate:4.1f} seg/s",
                flush=True,
            )

        conservation = check_conservation(all_blocks, all_kept, all_dropped)
        result = repack(archive, args.output, changed, bilingual=args.mode != "replace")

    print(f"segments        : {segments_total} ({translated_total} translated)")
    print(f"dropped         : {dropped_total}")
    print(f"conservation    : {conservation.describe()}")
    if label_documents:
        print(
            f"label documents : {len(label_documents)} "
            f"(translated in place as {args.labels_mode})"
        )
        for href in label_documents:
            print(f"  - {href.split('/')[-1]}")
    stats = translator.stats()
    print(
        f"model calls     : {stats['translate_calls']} (cache hits {stats['cache_hits']})"
    )
    if stats["failed_segments"]:
        print(
            f"WARNING         : {stats['failed_segments']} segments kept the source text"
        )
    print(f"output          : {result.output}")
    print(f"  documents rewritten: {result.documents_written}")
    print(f"  entries copied     : {result.entries_copied}")

    with zipfile.ZipFile(result.output) as check:
        bad = check.testzip()
        print(f"  zip integrity      : {'OK' if bad is None else bad}")
        for name in check.namelist():
            if name.endswith((".xhtml", ".opf", ".ncx")):
                try:
                    etree.fromstring(check.read(name))  # noqa: S320 - our own output
                except etree.XMLSyntaxError as error:
                    print(f"  MALFORMED XML {name}: {error}")
                    return 1
        print("  XML well-formedness: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
