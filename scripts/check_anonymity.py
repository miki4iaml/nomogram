# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Pre-commit hook: reject personal or internal information.

Two sources of patterns (regular expressions, case-insensitive):

- generic patterns, versioned here, which name nobody (home directory
  paths);
- personal patterns (legal name, domain, work email address…), read
  from a file outside the repository so they are never published.
  Default path: ``~/.config/nomogram/deny-patterns.txt``, overridden by
  the ``NOMOGRAM_DENY_PATTERNS`` environment variable. One expression
  per line, UTF-8; blank lines and lines starting with ``#`` are
  ignored.

The script never succeeds without checking:

- text file not UTF-8 or unreadable: failure;
- binary file (contains a null byte): search in its raw bytes, which
  covers plain-text metadata but not compressed contents (docx,
  compressed PDF…);
- file path: checked like its contents;
- environment variable set but patterns file missing, unreadable or
  invalid: failure;
- neither variable nor default file, or empty file: warning, only the
  generic patterns apply.

With ``--commit-msg``, the file received is a commit message: comment
lines and everything after the scissors line of ``git commit -v`` are
ignored, as Git does.

Matches are reported as ``file:line`` only, without reproducing the
text found; in displayed paths, matching parts are masked.
"""

import os
import re
import sys
from pathlib import Path

GENERIC_PATTERNS = (
    # Windows home directory: C:\Users\<name>\ or C:/Users/<name>/
    r"\b[A-Za-z]:[\\/](?:Users)[\\/][^\\/\s<]+[\\/]",
    # Unix or macOS home directory: /home/<name>/, /Users/<name>/
    r"(?<![\w.])/(?:home|Users)/[^/\s<]+/",
)

ENV_VAR = "NOMOGRAM_DENY_PATTERNS"
DEFAULT_PATTERNS_FILE = Path.home() / ".config" / "nomogram" / "deny-patterns.txt"

SCISSORS = "# ------------------------ >8 ------------------------"
FINDING = "personal or internal information"


class ConfigError(Exception):
    """Unusable personal patterns file."""


def load_personal_patterns() -> list[re.Pattern[str]]:
    """Read and compile the personal patterns.

    Return an empty list, after a warning, if no file is configured or
    if it holds no pattern. Raise ``ConfigError`` if the designated file
    is missing, unreadable or holds an invalid pattern.
    """
    configured = os.environ.get(ENV_VAR)
    path = Path(configured) if configured else DEFAULT_PATTERNS_FILE
    if not path.exists():
        if configured:
            raise ConfigError(f"{ENV_VAR} points to a missing file: {path}")
        warn(f"no personal patterns file ({ENV_VAR} or {path})")
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"unreadable patterns file: {path}") from exc

    patterns = []
    for number, line in enumerate(text.splitlines(), start=1):
        source = line.strip()
        if not source or source.startswith("#"):
            continue
        try:
            patterns.append(re.compile(source, re.IGNORECASE))
        except re.error:
            # The error text may quote the pattern: do not repeat it.
            raise ConfigError(f"invalid pattern on line {number} of {path}") from None
    if not patterns:
        warn(f"personal patterns file is empty: {path}")
    return patterns


def warn(message: str) -> None:
    print(f"anonymity: {message}; only generic patterns apply.", file=sys.stderr)


def mask(text: str, patterns: list[re.Pattern[str]]) -> str:
    """Mask the parts of ``text`` that match a pattern."""
    for pattern in patterns:
        text = pattern.sub("***", text)
    return text


def matches(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def message_lines(text: str) -> list[str]:
    """Lines of a commit message as Git will keep them."""
    lines = text.splitlines()
    if SCISSORS in lines:
        lines = lines[: lines.index(SCISSORS)]
    return [line if not line.startswith("#") else "" for line in lines]


def check_file(
    name: str, patterns: list[re.Pattern[str]], *, commit_msg: bool = False
) -> list[str]:
    """Return the findings for file ``name`` (empty if compliant)."""
    shown = mask(name, patterns)
    findings = []
    if not commit_msg and matches(name, patterns):
        findings.append(f"{shown}: path: {FINDING}")

    try:
        data = Path(name).read_bytes()
    except OSError:
        return [*findings, f"{shown}: unreadable, not checked"]

    if b"\0" in data and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raw = (data.decode("latin-1"), data.decode("utf-8", errors="replace"))
        if any(matches(text, patterns) for text in raw):
            findings.append(f"{shown}: binary: {FINDING}")
        return findings

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [*findings, f"{shown}: not UTF-8, not checked"]

    lines = message_lines(text) if commit_msg else text.splitlines()
    findings.extend(
        f"{shown}:{number}: {FINDING}"
        for number, line in enumerate(lines, start=1)
        if matches(line, patterns)
    )
    return findings


def main(argv: list[str]) -> int:
    commit_msg = bool(argv) and argv[0] == "--commit-msg"
    names = argv[1:] if commit_msg else argv
    try:
        personal = load_personal_patterns()
    except ConfigError as exc:
        print(f"anonymity: {exc}", file=sys.stderr)
        return 2
    patterns = [re.compile(p, re.IGNORECASE) for p in GENERIC_PATTERNS] + personal

    status = 0
    for name in names:
        for finding in check_file(name, patterns, commit_msg=commit_msg):
            print(finding)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
