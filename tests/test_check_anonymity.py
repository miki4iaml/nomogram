"""Tests du hook d'anonymisation ``scripts/check_anonymity.py``."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_anonymity.py"
SPEC = importlib.util.spec_from_file_location("check_anonymity", SCRIPT)
check_anonymity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_anonymity)

# Motif personnel fictif. Les chemins génériques sont assemblés à
# l'exécution pour que ce fichier ne déclenche pas lui-même le hook.
SECRET = "zorglub"
UNIX_HOME = "/" + "home/quelquun/projet"


@pytest.fixture(autouse=True)
def in_tmp_path(tmp_path, monkeypatch):
    # pre-commit transmet des chemins relatifs au dépôt ; un chemin absolu
    # vers le répertoire temporaire contiendrait le répertoire personnel.
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def patterns_file(tmp_path, monkeypatch):
    path = tmp_path / "motifs.txt"
    path.write_text(f"# commentaire\n{SECRET}\n", encoding="utf-8")
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(path))
    return path


def run(capsys, *args):
    names = [str(a.relative_to(Path.cwd())) if isinstance(a, Path) else a for a in args]
    status = check_anonymity.main(names)
    out, err = capsys.readouterr()
    return status, out, err


def test_clean_file_passes(tmp_path, patterns_file, capsys):
    f = tmp_path / "ok.txt"
    f.write_text("rien a signaler\n", encoding="utf-8")
    assert run(capsys, f) == (0, "", "")


def test_personal_pattern_reported_without_copying_it(tmp_path, patterns_file, capsys):
    f = tmp_path / "doc.txt"
    f.write_text("ligne 1\nsigne : Zorglub\n", encoding="utf-8")
    status, out, _ = run(capsys, f)
    assert status == 1
    assert ":2: information nominative ou interne" in out
    assert SECRET not in out.lower()


def test_generic_pattern_reported(tmp_path, patterns_file, capsys):
    f = tmp_path / "conf.txt"
    f.write_text(f"racine = {UNIX_HOME}\n", encoding="utf-8")
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "quelquun" not in out


def test_placeholder_path_passes(tmp_path, patterns_file, capsys):
    f = tmp_path / "doc.txt"
    f.write_text("/home/<utilisateur>/projet\n", encoding="utf-8")
    assert run(capsys, f)[0] == 0


def test_non_utf8_file_fails(tmp_path, patterns_file, capsys):
    f = tmp_path / "latin1.txt"
    f.write_bytes("été\n".encode("latin-1"))
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "non UTF-8, non verifie" in out


def test_utf16_file_fails(tmp_path, patterns_file, capsys):
    f = tmp_path / "utf16.txt"
    f.write_bytes("texte\n".encode("utf-16"))
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "non UTF-8" in out


def test_unreadable_file_fails(tmp_path, patterns_file, capsys):
    status, out, _ = run(capsys, tmp_path / "absent.txt")
    assert status == 1
    assert "illisible, non verifie" in out


def test_binary_with_pattern_fails(tmp_path, patterns_file, capsys):
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG\0\0\0Author\0ZORGLUB\0\xff\xfe")
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "binaire" in out
    assert SECRET not in out.lower()


def test_binary_without_pattern_passes(tmp_path, patterns_file, capsys):
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG\0\0\0\xff\xfe\x00")
    assert run(capsys, f)[0] == 0


def test_path_is_checked_and_masked(tmp_path, patterns_file, capsys):
    folder = tmp_path / f"rapport-{SECRET}"
    folder.mkdir()
    f = folder / "notes.txt"
    f.write_text("rien\n", encoding="utf-8")
    status, out, _ = run(capsys, f)
    assert status == 1
    assert "chemin" in out
    assert "***" in out
    assert SECRET not in out.lower()


def test_configured_but_missing_patterns_file_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(tmp_path / "faute.txt"))
    f = tmp_path / "ok.txt"
    f.write_text("rien\n", encoding="utf-8")
    status, _, err = run(capsys, f)
    assert status == 2
    assert "fichier absent" in err


def test_default_patterns_file_missing_warns(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(check_anonymity.ENV_VAR, raising=False)
    monkeypatch.setattr(check_anonymity, "DEFAULT_PATTERNS_FILE", tmp_path / "x.txt")
    f = tmp_path / "ok.txt"
    f.write_text("rien\n", encoding="utf-8")
    status, _, err = run(capsys, f)
    assert status == 0
    assert "aucun fichier de motifs personnels" in err


def test_empty_patterns_file_warns(tmp_path, monkeypatch, capsys):
    path = tmp_path / "motifs.txt"
    path.write_text("# rien\n\n", encoding="utf-8")
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(path))
    f = tmp_path / "ok.txt"
    f.write_text("rien\n", encoding="utf-8")
    status, _, err = run(capsys, f)
    assert status == 0
    assert "vide" in err


def test_invalid_pattern_fails_without_copying_it(tmp_path, monkeypatch, capsys):
    path = tmp_path / "motifs.txt"
    path.write_text(f"ok\n({SECRET}\n", encoding="utf-8")
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(path))
    status, _, err = run(capsys, tmp_path)
    assert status == 2
    assert "ligne 2" in err
    assert SECRET not in err.lower()


def test_non_utf8_patterns_file_fails(tmp_path, monkeypatch, capsys):
    path = tmp_path / "motifs.txt"
    path.write_bytes("é\n".encode("latin-1"))
    monkeypatch.setenv(check_anonymity.ENV_VAR, str(path))
    status, _, err = run(capsys, tmp_path)
    assert status == 2
    assert "illisible" in err


def test_commit_msg_ignores_comments_and_diff(tmp_path, patterns_file, capsys):
    f = tmp_path / "COMMIT_EDITMSG"
    f.write_text(
        f"feat: ajout\n\n# Author: {SECRET}\n{check_anonymity.SCISSORS}\n+ {SECRET}\n",
        encoding="utf-8",
    )
    assert run(capsys, "--commit-msg", f)[0] == 0


def test_commit_msg_body_is_checked(tmp_path, patterns_file, capsys):
    f = tmp_path / "COMMIT_EDITMSG"
    f.write_text(f"feat: ajout\n\nmerci a {SECRET}\n", encoding="utf-8")
    status, out, _ = run(capsys, "--commit-msg", f)
    assert status == 1
    assert ":3: information nominative ou interne" in out
