#!/usr/bin/env python3
"""Fail a commit when staged content looks like a real credential.

Designed as a pre-commit hook (``pre-commit`` passes the staged file names as
arguments). When run without arguments it inspects everything staged via
``git diff --cached``.

The scanner is deliberately small, offline and dependency-free. It is a
backstop, not a replacement for rotating a leaked key.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

_GIT = shutil.which("git") or "git"

# --- Detection rules -------------------------------------------------------

# High-signal provider token shapes. These are safe to match anywhere because
# the prefixes are unique enough that false positives are rare.
TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI / DeepSeek style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenRouter key", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{32,}")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}")),
    (
        "JSON Web Token",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    ),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

# Assignment-shaped rules: only flag when a credential-ish key gets an opaque
# literal value. Code such as ``token = self._tokens.pop(0)`` must not match, so
# both the key name and the value shape are checked strictly.
SENSITIVE_LAST_WORDS = frozenset(
    {
        "key",
        "keys",
        "token",
        "tokens",
        "secret",
        "secrets",
        "password",
        "passwd",
        "pwd",
        "credential",
        "credentials",
        "passphrase",
    }
)
SENSITIVE_JOINED_KEYS = frozenset(
    {
        "apikey",
        "api_key",
        "secretkey",
        "accesstoken",
        "authtoken",
        "refreshtoken",
        "clientsecret",
        "privatekey",
        "password",
    }
)

_ASSIGNMENT_RE = re.compile(
    r"""(?x)
    (?P<key>[A-Za-z0-9_.\-]*(?:key|token|secret|password|passwd|pwd|credential|passphrase)[A-Za-z0-9_.\-]*)
    \s*[:=]\s*
    (?P<quote>["']?)
    (?P<value>[^\s"'#,;)\]}]+)
    """
)

# An opaque secret literal: no whitespace, no code punctuation, no attribute
# access, no call syntax. Dotted values (JWTs) are covered by TOKEN_PATTERNS.
_SECRET_VALUE_RE = re.compile(r"^[A-Za-z0-9+/=_\-]{16,}$")
_SNAKE_CASE_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")

# Values that are obviously placeholders, not credentials.
PLACEHOLDER_RE = re.compile(
    r"""(?ix)^(
        |\$\{?[A-Za-z0-9_]+\}?          # ${ENV_VAR} / $ENV_VAR
        |\$\{?[A-Za-z0-9_]+:-[^}]*\}?   # ${VAR:-default}
        |<[^>]*>                        # <your-key>
        |\.\.\.|xxx+|yyy+|zzz+
        |changeme|change_me|placeholder|redacted|removed
        |example|sample|dummy|fake|test|todo|none|null|true|false
        |your[-_]?[a-z0-9_]*|my[-_]?[a-z0-9_]*
        |paste[_-]?your[a-z0-9_]*
        |env\.[a-z0-9_]+
    )$"""
)

# An explicit, greppable escape hatch. Files holding credential *shapes* as
# test data need it; nothing in tests/ is skipped implicitly, because a real key
# committed inside a test is exactly the accident this hook exists to catch.
ALLOW_FILE_MARKER = "check-secrets: allow-file"
ALLOW_LINE_MARKER = "check-secrets: allow"

SECRET_EXTENSIONS = {".pem", ".key", ".p12", ".pfx"}
SECRET_NAMES = {".env", ".netrc", "credentials", "id_rsa", "id_ed25519", "secring.gpg"}


def _is_credential_carrier(path: Path) -> bool:
    name = path.name
    if name == ".env.example" or "template" in name:
        return False
    if name.startswith(".env"):
        return True
    if path.suffix.lower() in SECRET_EXTENSIONS:
        return True
    return name in SECRET_NAMES


MAX_BYTES = 2 * 1024 * 1024


def _split_key_words(key: str) -> list[str]:
    """Split ``openai_api_key`` / ``openaiApiKey`` / ``openai-api-key`` into words."""
    words: list[str] = []
    for part in re.split(r"[.\-_]+", key):
        found = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+", part)
        words.extend(w.lower() for w in (found or [part.lower()]) if w)
    return words


def _sensitive_key(key: str) -> bool:
    words = _split_key_words(key)
    if not words:
        return False
    if (
        "_".join(words) in SENSITIVE_JOINED_KEYS
        or "".join(words) in SENSITIVE_JOINED_KEYS
    ):
        return True
    # ``paragraph_token_count`` ends in ``count`` -> not a credential name.
    # ``self.tokenizer`` ends in ``tokenizer`` -> not a credential name.
    return words[-1] in SENSITIVE_LAST_WORDS


def _looks_like_placeholder(value: str) -> bool:
    cleaned = value.strip().strip("\"'`")
    if not cleaned:
        return True
    if PLACEHOLDER_RE.match(cleaned):
        return True
    for marker in ("placeholder", "example", "your", "paste_", "changeme", "redacted"):
        if marker in cleaned.lower():
            return True
    return False


def _looks_like_secret_value(value: str) -> bool:
    if not _SECRET_VALUE_RE.match(value):
        return False
    if _looks_like_placeholder(value):
        return False
    # Pure snake_case identifiers are code (``my_api_key_constant``), not secrets.
    if _SNAKE_CASE_IDENTIFIER_RE.match(value):
        return False
    has_digit = any(c.isdigit() for c in value)
    has_alpha = any(c.isalpha() for c in value)
    if has_digit and has_alpha:
        return True
    # Long, mixed-case, purely alphabetic blobs are still suspect.
    if len(value) >= 32:
        return True
    return False


def _read_text(path: Path) -> str | None:
    """Return the file as text, or None when it is binary or too large."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096] or len(raw) > MAX_BYTES:
        return None
    return raw.decode("utf-8", errors="replace")


def scan_file(path: Path) -> list[str]:
    text = _read_text(path)
    if text is None or ALLOW_FILE_MARKER in text:
        return []
    findings: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or ALLOW_LINE_MARKER in line:
            continue
        for label, pattern in TOKEN_PATTERNS:
            if pattern.search(line):
                findings.append(f"{path}:{lineno}: {label}")
                break
        else:
            for match in _ASSIGNMENT_RE.finditer(line):
                if not _sensitive_key(match.group("key")):
                    continue
                if not _looks_like_secret_value(match.group("value")):
                    continue
                findings.append(
                    f"{path}:{lineno}: credential-like assignment to "
                    f"'{match.group('key')}'"
                )
                break
    return findings


def discover_staged_files() -> list[Path]:
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [_GIT, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    names = [n for n in out.decode("utf-8", errors="replace").split("\0") if n]
    return [Path(n) for n in names if Path(n).is_file()]


def discover_tracked_files() -> list[Path]:
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [_GIT, "ls-files", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    names = [n for n in out.decode("utf-8", errors="replace").split("\0") if n]
    return [Path(n) for n in names if Path(n).is_file()]


def main(argv: list[str]) -> int:
    args = argv[1:]
    whole_tree = "--tracked" in args
    if whole_tree:
        # Whole-tree sweep, used from the pre-push stage.
        targets = discover_tracked_files()
    else:
        targets = [Path(a) for a in args] or discover_staged_files()
    findings: list[str] = []
    for path in targets:
        findings.extend(scan_file(path))

    if findings:
        print("Secret scan failed. Refusing to commit:\n", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print(
            "\nRemove the value, use an environment variable, and rotate the key"
            " if it was ever real.",
            file=sys.stderr,
        )
        return 1

    # Warn (without failing) about files whose whole purpose is to hold secrets.
    if not whole_tree:
        for path in targets:
            if _is_credential_carrier(path):
                print(
                    f"note: '{path}' is a credential-carrying file \u2014 make sure"
                    " it is intentional and contains no live key.",
                    file=sys.stderr,
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
