"""Format-agnostic translation client for the EPUB pipeline.

Reuses the three pieces of BabelDOC that were already independent of the PDF
layout model: ``babeldoc.translator.translator`` (OpenAI client, on-disk cache,
rate limiting, retry), ``babeldoc.glossary`` (term matching) and the prompt files
under ``prompts/``.

What it deliberately does **not** reuse is the placeholder protocol. In the PDF
path a paragraph has to be flattened into text with ``{{bdoc_style_N}}`` tokens
so inline styling can survive a round trip through the model. Here the markup
never leaves the DOM, so segments are plain text and there is nothing to
protect, parse back, or repair.

Batching is done with JSON rather than delimited text: segment text is single-line
prose, so JSON escaping cannot corrupt it, and a malformed or truncated reply is
detectable by checking the returned ids instead of guessing.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from babeldoc.glossary import Glossary
from babeldoc.glossary import GlossaryEntry
from babeldoc.translator.translator import OpenAITranslator

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"

DEFAULT_BATCH_SIZE = 6
MAX_GLOSSARY_ROWS = 40


@dataclass
class TranslationSettings:
    """Everything needed to talk to the model, read from a BabelDOC toml."""

    lang_in: str = "en"
    lang_out: str = "zh-CN"
    model: str = ""
    base_url: str | None = None
    api_key: str | None = None
    thinking: str | None = None
    reasoning: str | None = None
    system_prompt: str = ""
    glossary_files: list[Path] = field(default_factory=list)
    qps: int = 1
    batch_size: int = DEFAULT_BATCH_SIZE

    @classmethod
    def from_toml(cls, path: Path, **overrides) -> TranslationSettings:
        import toml

        raw = toml.loads(path.read_text(encoding="utf-8"))
        section = raw.get("babeldoc", raw)
        settings = cls(
            lang_in=str(section.get("lang-in", "en")),
            lang_out=str(section.get("lang-out", "zh-CN")),
            model=str(section.get("openai-model", "")),
            base_url=section.get("openai-base-url"),
            api_key=section.get("openai-api-key"),
            thinking=section.get("openai-thinking"),
            reasoning=section.get("openai-reasoning-effort"),
            system_prompt=str(section.get("custom-system-prompt", "") or ""),
            glossary_files=_split_paths(section.get("glossary-files")),
            qps=int(section.get("qps", 1) or 1),
        )
        for key, value in overrides.items():
            if value is not None:
                setattr(settings, key, value)
        return settings

    def load_system_prompt(self, prompt_file: Path | None = None) -> str:
        """Use an explicit prompt file, else the config prompt, else the default."""
        if prompt_file is not None:
            return prompt_file.read_text(encoding="utf-8").strip()
        if self.system_prompt.strip():
            return self.system_prompt.strip()
        default = (
            PROMPT_DIR / f"{self.lang_in}-{self.lang_out.split('-')[0]}-technical.txt"
        )
        if default.exists():
            return default.read_text(encoding="utf-8").strip()
        return (
            f"You are a professional {self.lang_out} native translator. "
            f"Translate fluently into {self.lang_out}."
        )

    def load_glossaries(self) -> list[Glossary]:
        glossaries: list[Glossary] = []
        for path in self.glossary_files:
            if not path.exists():
                logger.warning("glossary file not found: %s", path)
                continue
            glossaries.append(load_glossary_csv(path, self.lang_out))
        return glossaries


def _split_paths(value) -> list[Path]:
    if not value:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,\n]", value)
    else:
        parts = list(value)
    return [Path(part.strip()) for part in parts if part and part.strip()]


def load_glossary_csv(path: Path, target_lang: str) -> Glossary:
    """Read a BabelDOC glossary CSV, tolerating a UTF-8 BOM."""
    entries: list[GlossaryEntry] = []
    text = path.read_text(encoding="utf-8-sig")
    for row in csv.DictReader(text.splitlines()):
        source = (row.get("source") or "").strip()
        target = (row.get("target") or "").strip()
        if not source or not target:
            continue
        row_lang = (row.get("tgt_lng") or "").strip()
        if row_lang and row_lang.lower() != target_lang.lower():
            continue
        entries.append(
            GlossaryEntry(source=source, target=target, target_language=row_lang)
        )
    return Glossary(path.stem, entries)


def build_system_prompt(
    settings: TranslationSettings, prompt_file: Path | None = None
) -> str:
    base = settings.load_system_prompt(prompt_file)
    if "Follow all rules strictly." not in base:
        base = base.rstrip() + "\n\nFollow all rules strictly."
    return base


def build_batch_prompt(
    settings: TranslationSettings,
    system_prompt: str,
    texts: list[str],
    glossaries: list[Glossary],
    context: str = "",
) -> str:
    """Assemble one request: role, glossary, context, then the JSON payload."""
    parts = [system_prompt, ""]
    parts.append("## Task")
    parts.append(
        f"Translate each `text` value into {settings.lang_out}. "
        "Return JSON only, with exactly the same ids and no others."
    )
    parts.append("")
    parts.append("## Rules")
    parts.append(
        "- Translate ordinary prose into natural \u201c"
        + settings.lang_out
        + "\u201d. Do not leave an\n"
        "  English word untranslated just because it looks technical: if a normal\n"
        "  equivalent exists, use it. Only names, identifiers, paths, URLs, commands,\n"
        "  and established terms stay as they are.\n"
        "- Leave identifiers, file paths, URLs, commands, API and library names, and\n"
        "  version strings exactly as they are.\n"
        "- Return one entry per input; never merge, split, drop or reorder entries.\n"
        "- Do not add explanations, notes or markdown fences."
    )

    glossary_block = build_glossary_block(glossaries, texts)
    if glossary_block:
        parts.append("")
        parts.append(glossary_block)

    if context:
        parts.append("")
        parts.append("## Context")
        parts.append(context)

    parts.append("")
    parts.append("## Input")
    parts.append(
        json.dumps(
            {"segments": [{"id": i, "text": t} for i, t in enumerate(texts)]},
            ensure_ascii=False,
        )
    )
    parts.append("")
    parts.append('Respond with: {"translations": [{"id": 0, "text": "..."}, ...]}')
    return "\n".join(parts)


def build_glossary_block(glossaries: list[Glossary], texts: list[str]) -> str:
    if not glossaries:
        return ""
    combined = "\n".join(texts)
    rows: list[tuple[str, str]] = []
    for glossary in glossaries:
        rows.extend(glossary.get_active_entries_for_text(combined))
    if not rows:
        return ""
    rows = sorted(set(rows))[:MAX_GLOSSARY_ROWS]
    lines = [
        "## Glossary",
        "",
        "Always use the Target Term for an occurrence of its Source Term.",
        "",
        "| Source Term | Target Term |",
        "|-------------|-------------|",
    ]
    lines.extend(f"| {source} | {target} |" for source, target in rows)
    return "\n".join(lines)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)
_JSON_START_RE = re.compile(r"[{[]")


def _decode_json(text: str):
    """Decode JSON, tolerating a model that wrapped it in prose."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_error:
        start = _JSON_START_RE.search(text)
        if start is None:
            raise ValueError(f"response is not JSON: {first_error}") from first_error
        try:
            payload, _end = json.JSONDecoder().raw_decode(text[start.start() :])
            return payload
        except json.JSONDecodeError as second_error:
            raise ValueError(f"response is not JSON: {second_error}") from second_error


def parse_batch_response(raw: str, expected: list[int]) -> dict[int, str]:
    """Extract ``{id: text}`` from a model reply, or raise ``ValueError``.

    Anything that does not map one-to-one onto ``expected`` is rejected, which
    lets the caller retry rather than silently mismatching translations.
    """
    if raw is None:
        raise ValueError("empty response")
    text = raw.strip()
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1)
    payload = _decode_json(text)

    if isinstance(payload, dict) and "translations" in payload:
        items = payload["translations"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("response has no translations list")

    result: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            raise ValueError(f"malformed entry: {item!r}")
        try:
            key = int(item["id"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"non-integer id: {item['id']!r}") from error
        value = item.get("text")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"empty translation for id {key}")
        result[key] = value.strip()

    if set(result) != set(expected):
        raise ValueError(
            f"id mismatch: got {sorted(result)}, expected {sorted(expected)}"
        )
    return result


class EpubTranslator:
    """Translate EPUB segments in batches, degrading instead of failing."""

    def __init__(
        self,
        settings: TranslationSettings,
        system_prompt: str,
        glossaries: list[Glossary],
        translator: OpenAITranslator | None = None,
    ) -> None:
        self.settings = settings
        self.system_prompt = system_prompt
        self.glossaries = glossaries
        self.translator = translator or OpenAITranslator(
            lang_in=settings.lang_in,
            lang_out=settings.lang_out,
            model=settings.model,
            base_url=settings.base_url,
            api_key=settings.api_key,
            thinking=settings.thinking,
            reasoning=settings.reasoning,
            enable_json_mode_if_requested=True,
            send_temperature=False,
        )
        self.failed: list[str] = []
        self._register_cache_identity()

    def _register_cache_identity(self) -> None:
        """Tie the on-disk cache to our prompt and glossary.

        ``BaseTranslator`` keys its cache on the text plus explicitly registered
        parameters. The PDF path registers its own prompt; without doing the same
        here, editing the system prompt or a glossary row would silently return
        stale translations from cache.
        """
        self.translator.add_cache_impact_parameters(
            "epub_system_prompt", self.system_prompt
        )
        signature = "\n".join(
            f"{source}\u0000{target}"
            for source, target in sorted(self.glossary_pairs())
        )
        self.translator.add_cache_impact_parameters("epub_glossary", signature)

    def glossary_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for glossary in self.glossaries:
            pairs.extend(
                (entry.source, entry.target or "") for entry in glossary.entries
            )
        return pairs

    def translate_many(self, texts: list[str], context: str = "") -> list[str]:
        """Translate ``texts``, preserving order.

        A batch that comes back malformed is retried one segment at a time; a
        segment that still fails keeps its source text and is recorded in
        ``failed`` so the caller can report it rather than shipping a silent gap.
        """
        if not texts:
            return []
        ids = list(range(len(texts)))
        prompt = build_batch_prompt(
            self.settings, self.system_prompt, texts, self.glossaries, context
        )
        try:
            raw = self.translator.llm_translate(
                prompt, rate_limit_params={"request_json_mode": True}
            )
            mapping = parse_batch_response(raw, ids)
            return [mapping[i] for i in ids]
        except Exception as error:  # noqa: BLE001 - degrade, never abort the book
            logger.warning(
                "batch of %d failed (%s); retrying individually", len(texts), error
            )
        return [self._translate_one(text, context) for text in texts]

    def _translate_one(self, text: str, context: str) -> str:
        prompt = build_batch_prompt(
            self.settings, self.system_prompt, [text], self.glossaries, context
        )
        try:
            raw = self.translator.llm_translate(
                prompt, rate_limit_params={"request_json_mode": True}
            )
            return parse_batch_response(raw, [0])[0]
        except Exception as error:  # noqa: BLE001
            logger.warning("segment failed, keeping source: %s", error)
            self.failed.append(text)
            return text

    def stats(self) -> dict[str, int]:
        return {
            "translate_calls": self.translator.translate_call_count,
            "cache_hits": self.translator.translate_cache_call_count,
            "failed_segments": len(self.failed),
        }
