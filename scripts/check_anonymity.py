# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Pre-commit hook: reject personal or internal information.

Two sources of patterns (regular expressions, case-insensitive):

- generic patterns, versioned here, which name nobody (home directory
  paths);
- personal patterns (legal name, domain, work email address…), read
  from files outside the repository so they are never published.
  Default path: ``~/.config/anonymity/deny-patterns.txt`` (under
  ``$XDG_CONFIG_HOME`` when it is set to an absolute path), overridden
  by the ``ANONYMITY_DENY_PATTERNS`` environment variable, which may
  list several files separated by ``os.pathsep``. The names are tied to
  the tool, not to a project: one personal list can serve every
  repository. One expression per line, UTF-8; blank lines and lines
  starting with ``#`` are ignored. ``--init`` creates a commented
  starter file.

The patterns file itself must never be published:

- a patterns file located inside the repository is refused;
- the starter file carries a marker line, and any file containing that
  marker is reported, whatever the configured patterns (also in CI).
  The marker is assembled at run time so that this script does not
  report itself.

The script never succeeds without checking:

- text file not UTF-8 or unreadable: failure;
- binary file (contains a null byte): search in its raw bytes, which
  covers plain-text metadata but not compressed contents (docx,
  compressed PDF…);
- file path: checked like its contents;
- environment variable set but one of its files missing, unreadable or
  invalid, or a patterns file inside the repository: failure (a
  configured file is never skipped silently);
- neither variable nor default file, or empty file: warning, only the
  generic patterns apply.

With ``--commit-msg``, the file received is a commit message: comment
lines and everything after the scissors line of ``git commit -v`` are
ignored, as Git does.

Matches are reported as ``file:line`` only, without reproducing the
text found; in displayed paths, matching parts are masked and
non-printable characters are replaced.

Not covered: compressed contents, history already pushed, branch and
tag names, and anything typed on GitHub (pull request titles and
descriptions, issues, comments).
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


def config_home() -> Path:
    """User configuration directory: ``$XDG_CONFIG_HOME`` if absolute, else ``~/.config``."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    # The XDG specification says relative values must be ignored.
    return Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"


# Tool-level names, not tied to a project: one personal list can serve
# every repository that uses this hook.
ENV_VAR = "ANONYMITY_DENY_PATTERNS"
DEFAULT_PATTERNS_FILE = config_home() / "anonymity" / "deny-patterns.txt"

SCISSORS = "# ------------------------ >8 ------------------------"
FINDING = "personal or internal information"

# Assembled at run time: written as one word, this script would report
# itself.
CANARY = "-".join(("anonymity", "deny", "patterns", "file"))  # noqa: FLY002
CANARY_FINDING = "deny patterns file content: never commit it"

STARTER = f"""\
# {CANARY}
#
# Personal deny patterns for the anonymity pre-commit hook.
# This file must stay OUTSIDE any repository: the line above makes the
# hook reject any copy of it that would be about to be committed.
# It can serve all your repositories: list here what must never be
# public anywhere (legal name, employer, work email domain...).
#
# One regular expression per line, case-insensitive. Blank lines and
# lines starting with "#" are ignored. Any committed line matching one
# of these patterns is rejected; the hook reports file:line only and
# never prints the pattern.
#
# Tips:
# - \\b marks a word boundary: \\bdoe\\b matches "Doe" but not "Doerr".
# - Escape dots: example\\.org (a bare dot matches any character).
# - No Unicode normalization: list accented and unaccented variants,
#   for example h[eé]l[eè]ne.
# - Do not list your public pseudonym if it appears on purpose in the
#   repository (author field, URLs): every commit would be rejected.
# - Avoid nested quantifiers such as (a+)+: they can make the hook hang.
#
# Examples, commented out: adapt them, then remove the leading "# ".
# \\bjane\\W*doe\\b
# \\bjdoe\\b
# example-corp\\.com
# \\bproject-codename\\b
"""


class ConfigError(Exception):
    """Unusable personal patterns file."""


def patterns_paths() -> tuple[list[Path], bool]:
    """Return the patterns file paths and whether they were configured.

    The environment variable may list several files, separated like
    ``PATH`` (``os.pathsep``: ``;`` on Windows, ``:`` elsewhere), for
    example a list shared by all repositories plus a project-specific
    one. Empty entries are ignored.
    """
    configured = os.environ.get(ENV_VAR, "")
    paths = [Path(entry) for entry in configured.split(os.pathsep) if entry.strip()]
    return (paths, True) if paths else ([DEFAULT_PATTERNS_FILE], False)


def repository_root() -> Path:
    """Closest directory holding ``.git`` from the working directory, else the latter.

    pre-commit runs hooks from the repository root; searching upwards
    also covers a manual run from a subdirectory.
    """
    cwd = Path.cwd().resolve()
    return next((d for d in (cwd, *cwd.parents) if (d / ".git").exists()), cwd)


def inside_repository(path: Path) -> bool:
    """Whether ``path`` lies under the repository root."""
    return path.resolve().is_relative_to(repository_root())


def load_personal_patterns() -> list[re.Pattern[str]]:
    """Read and compile the personal patterns.

    Return an empty list, after a warning, if no file is configured or
    if they hold no pattern. Raise ``ConfigError`` if a designated file
    is inside the repository, missing, unreadable or holds an invalid
    pattern: a configured file is never skipped silently.
    """
    paths, configured = patterns_paths()
    patterns = []
    for path in paths:
        shown = printable(str(path))
        if inside_repository(path):
            raise ConfigError(
                f"the patterns file must stay outside the repository: {shown}"
            )
        if not path.exists():
            if configured:
                raise ConfigError(f"{ENV_VAR} points to a missing file: {shown}")
            warn(
                f"no personal patterns file ({ENV_VAR} or {shown}); create one with --init"
            )
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigError(f"unreadable patterns file: {shown}") from exc

        for number, line in enumerate(text.splitlines(), start=1):
            source = line.strip()
            if not source or source.startswith("#"):
                continue
            try:
                patterns.append(re.compile(source, re.IGNORECASE))
            except re.error:
                # The error text may quote the pattern: do not repeat it.
                raise ConfigError(
                    f"invalid pattern on line {number} of {shown}"
                ) from None
    if not patterns:
        warn(
            f"personal patterns file is empty: {printable(os.pathsep.join(map(str, paths)))}"
        )
    return patterns


def init_patterns_file() -> int:
    """Create a commented starter patterns file (first configured path); never overwrite."""
    path = patterns_paths()[0][0]
    shown = printable(str(path))
    if inside_repository(path):
        print(
            f"anonymity: refusing to create the patterns file inside the repository: {shown}",
            file=sys.stderr,
        )
        return 2
    if path.exists():
        print(f"anonymity: the patterns file already exists: {shown}", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STARTER, encoding="utf-8")
    print(f"anonymity: created {shown}")
    print(
        "anonymity: edit it to add your own patterns; it stays outside the repository."
    )
    return 0


def warn(message: str) -> None:
    print(f"anonymity: {message}; only generic patterns apply.", file=sys.stderr)


def mask(text: str, patterns: list[re.Pattern[str]]) -> str:
    """Mask the parts of ``text`` that match a pattern."""
    for pattern in patterns:
        text = pattern.sub("***", text)
    return text


def printable(text: str) -> str:
    """Replace non-printable characters, so that names cannot drive the terminal."""
    return "".join(char if char.isprintable() else "?" for char in text)


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
    shown = printable(mask(name, patterns))
    findings = []
    if not commit_msg and matches(name, patterns):
        findings.append(f"{shown}: path: {FINDING}")

    try:
        data = Path(name).read_bytes()
    except OSError:
        return [*findings, f"{shown}: unreadable, not checked"]

    if CANARY.encode("ascii") in data:
        findings.append(f"{shown}: {CANARY_FINDING}")

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
    if argv[:1] == ["--init"]:
        return init_patterns_file()
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
