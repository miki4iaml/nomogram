# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the anonymity hook ``scripts/check_anonymity.py``."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_anonymity.py"
SPEC = importlib.util.spec_from_file_location("check_anonymity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check_anonymity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_anonymity)

# Fictitious personal pattern. Generic paths are assembled at run time
# so that this file does not trigger the hook itself.
SECRET = "zorglub"
UNIX_HOME = "/" + "home/someone/project"


@pytest.fixture(autouse=True)
def in_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # pre-commit passes paths relative to the repository; an absolute
    # path to the temporary directory would contain the home directory.
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def patterns_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "patterns.txt"
    path.write_text(f"# comment\n{SECRET}\n", encoding="utf-8")
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(path))
    return path


def run(capsys: pytest.CaptureFixture[str], *args: str | Path) -> tuple[int, str, str]:
    names = [str(a.relative_to(Path.cwd())) if isinstance(a, Path) else a for a in args]
    status = check_anonymity.main(names)
    out, err = capsys.readouterr()
    return status, out, err


def test_clean_file_passes(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "ok.txt"
    f.write_text("nothing to report\n", encoding="utf-8")
    assert run(capsys, f) == (0, "", "")


def test_personal_pattern_reported_without_copying_it(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "doc.txt"
    f.write_text("line 1\nsigned: Zorglub\n", encoding="utf-8")
    status, out, _ = run(capsys, f)
    assert status == 1
    assert ":2: personal or internal information" in out
    assert SECRET not in out.lower()


def test_generic_pattern_reported(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "conf.txt"
    f.write_text(f"root = {UNIX_HOME}\n", encoding="utf-8")
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "someone" not in out


def test_placeholder_path_passes(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "doc.txt"
    f.write_text("/home/<user>/project\n", encoding="utf-8")
    assert run(capsys, f)[0] == 0


def test_non_utf8_file_fails(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "latin1.txt"
    f.write_bytes("café\n".encode("latin-1"))
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "not UTF-8, not checked" in out


def test_utf16_file_fails(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "utf16.txt"
    f.write_bytes("texte\n".encode("utf-16"))
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "not UTF-8" in out


def test_unreadable_file_fails(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out, _ = run(capsys, tmp_path / "absent.txt")
    assert status == 1
    assert "unreadable, not checked" in out


def test_binary_with_pattern_fails(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG\0\0\0Author\0ZORGLUB\0\xff\xfe")
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "binary" in out
    assert SECRET not in out.lower()


def test_binary_without_pattern_passes(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG\0\0\0\xff\xfe\x00")
    assert run(capsys, f)[0] == 0


def test_path_is_checked_and_masked(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / f"report-{SECRET}"
    folder.mkdir()
    f = folder / "notes.txt"
    f.write_text("nothing\n", encoding="utf-8")
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "path" in out
    assert "***" in out
    assert SECRET not in out.lower()


def test_configured_but_missing_patterns_file_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(tmp_path / "missing.txt"))
    f = tmp_path / "ok.txt"
    f.write_text("nothing\n", encoding="utf-8")
    status, _, err = run(capsys, f)
    assert status == 2
    assert "missing file" in err


def test_default_patterns_file_missing_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(check_anonymity.ENV_VAR, raising=False)
    monkeypatch.setattr(check_anonymity, "DEFAULT_PATTERNS_FILE", tmp_path / "x.txt")
    f = tmp_path / "ok.txt"
    f.write_text("nothing\n", encoding="utf-8")
    status, _, err = run(capsys, f)
    assert status == 0
    assert "no personal patterns file" in err


def test_empty_patterns_file_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "patterns.txt"
    path.write_text("# nothing\n\n", encoding="utf-8")
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(path))
    f = tmp_path / "ok.txt"
    f.write_text("nothing\n", encoding="utf-8")
    status, _, err = run(capsys, f)
    assert status == 0
    assert "empty" in err


def test_invalid_pattern_fails_without_copying_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "patterns.txt"
    path.write_text(f"ok\n({SECRET}\n", encoding="utf-8")
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(path))
    status, _, err = run(capsys, tmp_path)
    assert status == 2
    assert "line 2" in err
    assert SECRET not in err.lower()


def test_non_utf8_patterns_file_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "patterns.txt"
    path.write_bytes("é\n".encode("latin-1"))
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(path))
    status, _, err = run(capsys, tmp_path)
    assert status == 2
    assert "unreadable" in err


def test_commit_msg_ignores_comments_and_diff(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "COMMIT_EDITMSG"
    f.write_text(
        f"feat: add\n\n# Author: {SECRET}\n{check_anonymity.SCISSORS}\n+ {SECRET}\n",
        encoding="utf-8",
    )
    assert run(capsys, "--commit-msg", f)[0] == 0


def test_commit_msg_body_is_checked(
    tmp_path: Path, patterns_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "COMMIT_EDITMSG"
    f.write_text(f"feat: add\n\nthanks to {SECRET}\n", encoding="utf-8")
    status, out, _ = run(capsys, "--commit-msg", f)
    assert status == 1
    assert ":3: personal or internal information" in out
