#!/usr/bin/env python3
"""Inspect an EPUB and report what the translation pipeline would make of it.

Usage:
    uv run --no-dev python tools/epub_probe.py BOOK.epub [--limit N] [--documents N]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from babeldoc.format.epub.archive import EpubArchive  # noqa: E402
from babeldoc.format.epub.normalize import MergeMode  # noqa: E402
from babeldoc.format.epub.normalize import NormalizationPolicy  # noqa: E402
from babeldoc.format.epub.normalize import WordVocabulary  # noqa: E402
from babeldoc.format.epub.normalize import check_conservation  # noqa: E402
from babeldoc.format.epub.normalize import is_page_list_segment  # noqa: E402
from babeldoc.format.epub.normalize import iter_blocks  # noqa: E402
from babeldoc.format.epub.normalize import merge_blocks  # noqa: E402
from babeldoc.format.epub.style_profile import DEFAULT_BLOCK_TAGS  # noqa: E402
from babeldoc.format.epub.style_profile import Role  # noqa: E402
from babeldoc.format.epub.style_profile import StyleProfile  # noqa: E402
from lxml import etree  # noqa: E402

_SENTENCE_END_RE = re.compile(r"[.!?:;\"'”’)\]}]\s*$")


def collect_stylesheets(archive: EpubArchive) -> list[str]:
    sheets = []
    for item in archive.manifest.values():
        if item.media_type == "text/css":
            sheets.append(
                archive.read_bytes(item.href).decode("utf-8", errors="replace")
            )
    return sheets


def block_stream(document, profile: StyleProfile):
    """Yield (role, text, tag, class) for every text-bearing block, in order."""
    for element in document.root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = etree.QName(element).localname
        if tag not in DEFAULT_BLOCK_TAGS:
            continue
        text = "".join(element.itertext()).strip()
        if not text:
            continue
        yield (
            profile.role_for_paragraph(element.get("class")),
            text,
            tag,
            element.get("class"),
        )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", type=Path)
    parser.add_argument(
        "--documents", type=int, default=0, help="only scan N spine docs"
    )
    parser.add_argument("--limit", type=int, default=6, help="samples per role")
    args = parser.parse_args(argv[1:])

    with EpubArchive.open(args.epub) as archive:
        print(f"file          : {archive.path.name}")
        print(f"opf           : {archive.opf_path}  (EPUB {archive.version})")
        print(f"title         : {archive.metadata.get('title', '')[:80]}")
        print(f"language      : {archive.metadata.get('language')}")
        print(f"spine         : {len(archive.spine)} documents")
        print(f"nav           : {archive.nav_href}")
        print(f"ncx           : {archive.ncx_href}")
        media = Counter(item.media_type for item in archive.manifest.values())
        print(f"manifest      : {dict(media)}")

        stylesheets = collect_stylesheets(archive)
        documents = list(archive.documents())
        if args.documents:
            documents = documents[: args.documents]
        print(f"stylesheets   : {len(stylesheets)}, scanned docs: {len(documents)}")

        profile = StyleProfile.build(stylesheets, documents)
        print()
        print("=" * 72)
        print("INFERRED CLASS ROLES")
        print("=" * 72)
        print(profile.describe())

        print()
        print("=" * 72)
        print("SPAN CLASS ROLES")
        print("=" * 72)
        for name, stats in sorted(
            profile.span_stats.items(), key=lambda kv: -kv[1].count
        )[:15]:
            decl = profile.declarations.get(name)
            size = f"{decl.font_size}em" if decl and decl.font_size else "-"
            role = profile.span_roles.get(name, Role.UNKNOWN).value
            print(f"  {name:<16}{role:<14}{stats.count:>7}  size={size}")

        print()
        print("=" * 72)
        print("BLOCK STREAM")
        print("=" * 72)
        role_counts: Counter[Role] = Counter()
        role_chars: Counter[Role] = Counter()
        samples: dict[Role, list[str]] = {}
        body_without_end = 0
        body_total = 0
        hyphenated = 0
        for document in documents:
            for role, text, _tag, _cls in block_stream(document, profile):
                role_counts[role] += 1
                role_chars[role] += len(text)
                bucket = samples.setdefault(role, [])
                if len(bucket) < args.limit and len(text) > 2:
                    bucket.append(text)
                if role is Role.BODY:
                    body_total += 1
                    if not _SENTENCE_END_RE.search(text):
                        body_without_end += 1
                    if text.endswith("-"):
                        hyphenated += 1

        total_blocks = sum(role_counts.values())
        for role, count in role_counts.most_common():
            share = count / total_blocks * 100
            print(
                f"  {role.value:<14}{count:>7} ({share:5.1f}%)  "
                f"{role_chars[role]:>8} chars"
            )

        print()
        print("=" * 72)
        print("SAMPLES")
        print("=" * 72)
        for role in Role:
            if role not in samples:
                continue
            print(f"  [{role.value}]")
            for text in samples[role]:
                print(f"      {text[:110]}")

        print()
        print("=" * 72)
        print("REFLOW DAMAGE (relative to BODY blocks)")
        print("=" * 72)
        if body_total:
            print(
                f"  body blocks                     : {body_total}\n"
                f"  not ending a sentence           : {body_without_end} "
                f"({body_without_end / body_total * 100:.1f}%)\n"
                f"  ending with a hyphen            : {hyphenated} "
                f"({hyphenated / body_total * 100:.1f}%)"
            )
        translatable = sum(role_chars[r] for r in role_chars if r.is_translatable)
        skipped = sum(role_chars[r] for r in role_chars if r.is_verbatim)
        print(f"  translatable characters         : {translatable}")
        print(f"  verbatim characters             : {skipped}")

        # -- normalization -------------------------------------------------
        print()
        print("=" * 72)
        print("NORMALIZED SEGMENTS")
        print("=" * 72)
        vocabulary = WordVocabulary.build(documents)
        print(f"  vocabulary size                 : {len(vocabulary.counts)}")
        all_segments = []
        all_dropped = []
        # Collect every block first: the reflow decision is a property of the
        # book, not of whichever document happens to be read first.
        per_document_blocks = [
            (document, iter_blocks(document, profile)) for document in documents
        ]
        all_blocks = [b for _doc, blocks in per_document_blocks for b in blocks]
        policy = NormalizationPolicy.detect(all_blocks)
        for _document, blocks in per_document_blocks:
            segments, dropped = merge_blocks(blocks, vocabulary, policy)
            kept = []
            for segment in segments:
                if is_page_list_segment(segment.text):
                    all_dropped.append(
                        __import__(
                            "babeldoc.format.epub.normalize", fromlist=["DroppedBlock"]
                        ).DroppedBlock(
                            href=segment.href,
                            index=segment.index,
                            role=segment.role,
                            text=segment.text,
                            reason="page list",
                        )
                    )
                else:
                    kept.append(segment)
            all_segments.extend(kept)
            all_dropped.extend(dropped)
        print(
            f"  reflow detected: {policy.is_reflow} "
            f"(fragment ratio {policy.fragment_ratio:.1%})"
        )

        modes: Counter[MergeMode] = Counter(s.mode for s in all_segments)
        seg_roles: Counter[Role] = Counter(s.role for s in all_segments)
        print(f"  blocks in  : {sum(role_counts.values())}")
        print(f"  segments out: {len(all_segments)}")
        print(f"  dropped     : {len(all_dropped)}")
        print(
            "  merge modes : "
            + ", ".join(f"{m.value}={n}" for m, n in modes.most_common())
        )
        print(
            "  roles       : "
            + ", ".join(f"{r.value}={n}" for r, n in seg_roles.most_common())
        )
        joined = sum(
            len(s.blocks) for s in all_segments if s.mode is MergeMode.JOINED_LINES
        )
        print(f"  blocks folded into paragraphs: {joined}")
        print(
            f"  segment characters            : {sum(s.char_count for s in all_segments)}"
        )

        print()
        print("=" * 72)
        print("CONSERVATION")
        print("=" * 72)
        report = check_conservation(all_blocks, all_segments, all_dropped)
        print(f"  {report.describe()}")
        print(f"  verdict: {'OK' if report.ok else 'TEXT LOST'}")

        print()
        print("=" * 72)
        print("MERGED PARAGRAPH SAMPLES (hyphenation repaired)")
        print("=" * 72)
        shown = 0
        for segment in all_segments:
            if segment.mode is not MergeMode.JOINED_LINES or len(segment.blocks) < 3:
                continue
            print(
                f"  [{len(segment.blocks)} lines -> 1 paragraph] {segment.text[:230]}"
            )
            shown += 1
            if shown >= 8:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
