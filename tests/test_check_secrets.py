"""Tests for the commit-time credential scanner in ``tools/check_secrets.py``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# check-secrets: allow-file - this module holds credential *shapes* as fixtures.
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_secrets", _REPO_ROOT / "tools" / "check_secrets.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_secrets"] = module
    spec.loader.exec_module(module)
    return module


check_secrets = _load_module()


def _scan(tmp_path: Path, content: str) -> list[str]:
    target = tmp_path / "probe.py"
    target.write_text(content, encoding="utf-8")
    return check_secrets.scan_file(target)


@pytest.mark.parametrize(
    "line",
    [
        'openai_api_key = "sk-abc123def456ghi789jkl012mno345"',
        'api-key = "abcdef1234567890abcdef1234567890"',
        'ANTHROPIC_API_KEY="sk-ant-api03-abcdefghijklmnopqrstuvwxyz"',
        'password = "hunter2correcthorsebattery9"',
        'aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"',
        'gh_token = "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"',
        'google = "AIzaSyA1234567890abcdefghijklmnopqrstu"',
        'hf_token = "hf_abcdefghijklmnopqrstuvwxyz0123456789"',
        "-----BEGIN RSA PRIVATE KEY-----",
        'token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.abcdef1234567890"',
    ],
)
def test_real_looking_credentials_are_flagged(tmp_path: Path, line: str):
    assert _scan(tmp_path, line + "\n"), f"expected a finding for: {line}"


@pytest.mark.parametrize(
    "line",
    [
        # Placeholders and environment indirection must never fail a commit.
        'openai-api-key = "PASTE_YOUR_DEEPSEEK_API_KEY_HERE"',
        'api_key = "${OPENAI_API_KEY}"',
        'api_key = "${OPENAI_API_KEY:-}"',
        'api_key = "<your-key-here>"',
        'api_key = "changeme"',
        # Ordinary code that merely mentions a sensitive word.
        "token = self._tokens.pop(0)",
        "numeric_token = self._read_numeric_token()",
        "completion_tokens = counter.value if counter else 0",
        "password_b = self._normalize_password(password)",
        "api_key=args.openai_term_extraction_api_key or args.openai_api_key",
        "paragraph_token_count = self.calc_token_count(paragraph.unicode)",
        "self.tokenizer = build_tokenizer()",
        "tokenize_content_stream = True",
        "my_api_key_constant = some_other_constant",
    ],
)
def test_placeholders_and_code_are_not_flagged(tmp_path: Path, line: str):
    assert _scan(tmp_path, line + "\n") == [], f"unexpected finding for: {line}"


def test_sensitive_key_word_matching():
    for key in ("api_key", "apiKey", "openai-api-key", "TOKEN", "client_secret"):
        assert check_secrets._sensitive_key(key), key
    # Names that merely contain a sensitive word as a prefix/suffix are not
    # credential names; ``completion_tokens`` is caught by the value gate.
    for key in ("tokenizer", "token_count", "password_b", "keyboard"):
        assert not check_secrets._sensitive_key(key), key
    assert check_secrets._sensitive_key("completion_tokens")


def test_binary_and_oversized_files_are_skipped(tmp_path: Path):
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\x00\x01sk-abc123def456ghi789jkl012mno345")
    assert check_secrets.scan_file(binary) == []


def test_whole_tracked_tree_is_clean():
    """The repository as committed must pass its own gate."""
    findings: list[str] = []
    for path in check_secrets.discover_tracked_files():
        findings.extend(check_secrets.scan_file(path))
    assert findings == []


def test_allow_file_pragma_skips_a_file(tmp_path: Path):
    """The escape hatch is explicit; tests/ is not skipped implicitly."""
    path = tmp_path / "fixtures.py"
    path.write_text(
        '# check-secrets: allow-file\nkey = "sk-abc123def456ghi789jkl012mno345"\n',
        encoding="utf-8",
    )
    assert check_secrets.scan_file(path) == []


def test_allow_line_pragma_skips_one_line_only(tmp_path: Path):
    path = tmp_path / "probe.py"
    path.write_text(
        'a = "sk-abc123def456ghi789jkl012mno345"  # check-secrets: allow\n'
        'b = "sk-zzz999yyy888xxx777www666vvv555"\n',
        encoding="utf-8",
    )
    findings = check_secrets.scan_file(path)
    assert len(findings) == 1
    assert ":2:" in findings[0]


def test_the_scanner_does_not_skip_a_real_key_in_a_test_file(tmp_path: Path):
    """A key committed inside tests/ must still be caught."""
    path = tmp_path / "test_helpers.py"
    path.write_text(
        'TOKEN = "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"\n', encoding="utf-8"
    )
    assert check_secrets.scan_file(path)
