"""Tests for the EPUB translation client.

No network access: the batch protocol, the glossary plumbing and the entire
degradation path are exercised with a fake translator.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from babeldoc.format.epub.client import EpubTranslator
from babeldoc.format.epub.client import TranslationSettings
from babeldoc.format.epub.client import build_batch_prompt
from babeldoc.format.epub.client import build_glossary_block
from babeldoc.format.epub.client import build_system_prompt
from babeldoc.format.epub.client import load_glossary_csv
from babeldoc.format.epub.client import parse_batch_response

# --- batch protocol --------------------------------------------------------


def test_parses_the_documented_shape():
    raw = json.dumps(
        {"translations": [{"id": 0, "text": "甲"}, {"id": 1, "text": "乙"}]}
    )
    assert parse_batch_response(raw, [0, 1]) == {0: "甲", 1: "乙"}


def test_parses_a_bare_list_and_a_fenced_block():
    assert parse_batch_response(json.dumps([{"id": 0, "text": "甲"}]), [0]) == {0: "甲"}
    fenced = '```json\n{"translations": [{"id": 0, "text": "甲"}]}\n```'
    assert parse_batch_response(fenced, [0]) == {0: "甲"}


def test_tolerates_string_ids_and_surrounding_prose():
    raw = 'Sure!\n{"translations": [{"id": "0", "text": " 甲 "}]}\nHope that helps.'
    assert parse_batch_response(raw, [0]) == {0: "甲"}


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json at all",
        json.dumps({"nope": 1}),
        json.dumps({"translations": [{"id": 0, "text": "甲"}]}),  # id 1 missing
        json.dumps({"translations": [{"id": 0, "text": " "}]}),  # empty text
        json.dumps({"translations": [{"text": "甲"}]}),  # no id
        json.dumps(
            {"translations": [{"id": 0, "text": "甲"}, {"id": 0, "text": "乙"}]}
        ),
    ],
)
def test_rejects_anything_that_does_not_map_one_to_one(raw: str):
    with pytest.raises(ValueError):
        parse_batch_response(raw, [0, 1])


# --- prompt assembly -------------------------------------------------------


def test_prompt_carries_the_role_the_rules_and_a_json_payload():
    settings = TranslationSettings(lang_in="en", lang_out="zh-CN")
    prompt = build_batch_prompt(settings, "ROLE TEXT", ["Hello", "World"], [])
    assert "ROLE TEXT" in prompt
    assert "zh-CN" in prompt
    payload = json.loads(prompt.split("## Input")[1].split("\n\n")[0].strip())
    assert payload == {
        "segments": [{"id": 0, "text": "Hello"}, {"id": 1, "text": "World"}]
    }


def test_system_prompt_always_ends_with_the_compliance_line():
    settings = TranslationSettings(system_prompt="Be careful.")
    assert build_system_prompt(settings).startswith("Be careful.")
    assert build_system_prompt(settings).endswith("Follow all rules strictly.")
    # Not duplicated when the configured prompt already has it.
    settings = TranslationSettings(
        system_prompt="Be careful.\n\nFollow all rules strictly."
    )
    assert build_system_prompt(settings).count("Follow all rules strictly.") == 1


def test_explicit_prompt_file_wins_over_the_config_prompt(tmp_path: Path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("FROM FILE", encoding="utf-8")
    settings = TranslationSettings(system_prompt="FROM CONFIG")
    assert build_system_prompt(settings, prompt_file).startswith("FROM FILE")


# --- glossary --------------------------------------------------------------


def _write_glossary(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "glossary.csv"
    path.write_text(rows, encoding="utf-8")
    return path


def test_glossary_csv_is_read_with_a_bom_and_filtered_by_language(tmp_path: Path):
    path = _write_glossary(
        tmp_path,
        "\ufeffsource,target,tgt_lng\n"
        "Transformer,Transformer,zh-CN\n"
        "agent,智能体,zh-CN\n"
        "only-korean,某词,ko\n",
    )
    glossary = load_glossary_csv(path, "zh-CN")
    sources = {entry.source for entry in glossary.entries}
    assert sources == {"Transformer", "agent"}


def test_glossary_block_only_lists_terms_present_in_the_batch(tmp_path: Path):
    path = _write_glossary(
        tmp_path,
        "source,target,tgt_lng\nagent,智能体,zh-CN\nlatency,延迟,zh-CN\n",
    )
    glossary = load_glossary_csv(path, "zh-CN")
    block = build_glossary_block([glossary], ["The agent runs here."])
    assert "智能体" in block
    assert "延迟" not in block


def test_no_glossary_yields_no_block(tmp_path: Path):
    assert build_glossary_block([], ["anything"]) == ""
    path = _write_glossary(tmp_path, "source,target,tgt_lng\n")
    assert build_glossary_block([load_glossary_csv(path, "zh-CN")], ["x"]) == ""


# --- settings --------------------------------------------------------------


def test_settings_are_read_from_a_babeldoc_toml(tmp_path: Path):
    config = tmp_path / "babeldoc.test.toml"
    config.write_text(
        '[babeldoc]\nlang-in = "en"\nlang-out = "zh-CN"\nqps = 4\n'
        'openai-model = "m"\nopenai-base-url = "https://x/v1"\n'
        'openai-api-key = "k"\nopenai-thinking = "disabled"\n'
        'custom-system-prompt = "ROLE"\n'
        f'glossary-files = "{tmp_path / "g.csv"}"\n',
        encoding="utf-8",
    )
    settings = TranslationSettings.from_toml(config)
    assert (settings.lang_in, settings.lang_out, settings.qps) == ("en", "zh-CN", 4)
    assert settings.model == "m" and settings.thinking == "disabled"
    assert settings.glossary_files == [tmp_path / "g.csv"]
    # An override wins over the file.
    assert TranslationSettings.from_toml(config, lang_out="ja").lang_out == "ja"


# --- degradation path ------------------------------------------------------


class FakeTranslator:
    """Stands in for OpenAITranslator, scripted per call."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.translate_call_count = 0
        self.translate_cache_call_count = 0
        self.params: dict = {}

    def add_cache_impact_parameters(self, key, value):
        self.params[key] = value

    def llm_translate(self, prompt, rate_limit_params=None, **_kwargs):
        self.prompts.append(prompt)
        self.translate_call_count += 1
        reply = self.replies.pop(0) if self.replies else RuntimeError("no reply left")
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return reply(prompt)
        return reply


def _translator_with(replies, **kwargs) -> tuple[EpubTranslator, FakeTranslator]:
    fake = FakeTranslator(replies)
    client = EpubTranslator(
        TranslationSettings(lang_in="en", lang_out="zh-CN", batch_size=2),
        "ROLE",
        [],
        translator=fake,
        **kwargs,
    )
    return client, fake


def _reply_for(prompt: str, prefix: str = "译") -> str:
    payload = json.loads(prompt.split("## Input")[1].split("\n\n")[0].strip())
    return json.dumps(
        {
            "translations": [
                {"id": item["id"], "text": f"{prefix}{item['text']}"}
                for item in payload["segments"]
            ]
        },
        ensure_ascii=False,
    )


def test_a_good_batch_is_translated_in_one_call():
    client, fake = _translator_with([_reply_for])
    assert client.translate_many(["Hello", "World"]) == ["译Hello", "译World"]
    assert len(fake.prompts) == 1
    assert client.stats()["failed_segments"] == 0


def test_a_malformed_batch_falls_back_to_one_request_per_segment():
    """A truncated batch must not lose the whole batch."""
    client, fake = _translator_with(["{truncated", _reply_for, _reply_for])
    result = client.translate_many(["Hello", "World"])
    assert result == ["译Hello", "译World"]
    assert len(fake.prompts) == 3
    assert client.stats()["failed_segments"] == 0


def test_a_segment_that_keeps_failing_keeps_its_source_text():
    """Degrade, never abort: the book still ships, and the gap is reported."""
    client, fake = _translator_with(["nope", "nope", _reply_for])
    result = client.translate_many(["Hello", "World"])
    assert result == ["Hello", "译World"]
    assert client.failed == ["Hello"]
    assert client.stats()["failed_segments"] == 1


def test_a_transport_error_is_treated_as_a_failure_not_a_crash():
    client, _fake = _translator_with(
        [RuntimeError("connection reset"), _reply_for, _reply_for]
    )
    assert client.translate_many(["Hello", "World"]) == ["译Hello", "译World"]


def test_empty_input_makes_no_call():
    client, fake = _translator_with([])
    assert client.translate_many([]) == []
    assert fake.prompts == []


def test_context_lines_reach_the_prompt():
    client, fake = _translator_with([_reply_for])
    client.translate_many(["Hello", "World"], context="Chapter 1: Basics")
    assert "Chapter 1: Basics" in fake.prompts[0]


def test_prompt_forbids_leaving_ordinary_words_untranslated():
    """Observed defect: "photocopying" came back untranslated in a real run."""
    prompt = build_batch_prompt(TranslationSettings(), "ROLE", ["text"], [])
    assert "Do not leave an" in prompt
    assert "untranslated" in prompt


class CacheAwareFake(FakeTranslator):
    def __init__(self, replies):
        super().__init__(replies)
        self.params: dict = {}

    def add_cache_impact_parameters(self, key, value):
        self.params[key] = value


def test_cache_is_keyed_on_the_prompt_and_the_glossary(tmp_path: Path):
    """Otherwise editing either would silently reuse stale translations."""
    path = _write_glossary(tmp_path, "source,target,tgt_lng\nagent,智能体,zh-CN\n")
    glossary = load_glossary_csv(path, "zh-CN")

    fake = FakeTranslator([])
    EpubTranslator(TranslationSettings(), "PROMPT A", [glossary], translator=fake)
    assert fake.params["epub_system_prompt"] == "PROMPT A"
    assert "agent" in fake.params["epub_glossary"]

    other = FakeTranslator([])
    EpubTranslator(TranslationSettings(), "PROMPT B", [glossary], translator=other)
    assert other.params["epub_system_prompt"] != fake.params["epub_system_prompt"]
