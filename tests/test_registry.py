# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the registry of verdicts.

The first test is the authority: every verdict of the bundled registry is
recomputed and compared, so that the registry can neither lie nor go
stale without the continuous integration failing.
"""

import dataclasses
import json
from pathlib import Path

import pytest

from nomogram import relations
from nomogram.catalog import catalog, main
from nomogram.relations import fingerprint, load_registry, record, verdict, verify

CATALOG = catalog()


def test_bundled_registry_matches_a_fresh_verification() -> None:
    registry = load_registry()
    expected = {fingerprint(r, CATALOG): r for r in CATALOG.relations.values()}
    assert set(registry) == set(expected), (
        "registry out of date: run `uv run python -m nomogram.catalog verify --record`"
    )
    for key, relation in expected.items():
        fresh = verify(relation, CATALOG)
        recorded = registry[key]
        assert (recorded.status, recorded.method, recorded.detail) == (
            fresh.status,
            fresh.method,
            fresh.detail,
        ), relation.key
        assert recorded.value == pytest.approx(fresh.value, rel=1e-9), relation.key
        assert dict(recorded.at) == pytest.approx(dict(fresh.at), rel=1e-9), (
            relation.key
        )


def test_verdict_reads_the_registry_without_recomputing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("recomputed")

    monkeypatch.setattr(relations, "verify", refuse)
    found = verdict(CATALOG.relations["ae96_aekr_gg46"], CATALOG)
    assert found.status == "reproduced"


def test_a_changed_relation_is_recomputed() -> None:
    relation = dataclasses.replace(CATALOG.relations["ae96_aekr_gg46"], accuracy=0.5)
    assert fingerprint(relation, CATALOG) not in load_registry()
    assert verdict(relation, CATALOG).status == "held"


def test_fingerprint_follows_what_a_verdict_depends_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relation = CATALOG.relations["ae96_bu81_so90"]
    reference = fingerprint(relation, CATALOG)
    assert fingerprint(relation, CATALOG) == reference
    assert (
        fingerprint(dataclasses.replace(relation, scale="convert"), CATALOG)
        != reference
    )
    assert fingerprint(relation, CATALOG, budget=1000) != reference
    monkeypatch.setattr(relations, "VERIFIER", relations.VERIFIER + 1)
    assert fingerprint(relation, CATALOG) != reference


def test_record_computes_once_then_reuses_and_prunes(tmp_path: Path) -> None:
    path = tmp_path / "verifications.json"
    assert load_registry(path) == {}
    assert record(CATALOG, path) == (len(CATALOG.relations), 0)
    assert record(CATALOG, path) == (0, len(CATALOG.relations))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["verdicts"]["stale"] = next(iter(data["verdicts"].values()))
    path.write_text(json.dumps(data), encoding="utf-8")
    record(CATALOG, path)
    assert "stale" not in json.loads(path.read_text(encoding="utf-8"))["verdicts"]
    relation = CATALOG.relations["ae96_te30_so90"]
    assert verdict(relation, CATALOG, registry=path).value == pytest.approx(
        3.169, abs=5e-4
    )


def test_command_line_lists_the_verdicts(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["verify"]) == 0
    out = capsys.readouterr().out
    assert "ae96_sa90_gg46: exceeded 0.6098 %" in out
    assert out.count(": reproduced") == 12


def test_command_line_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "verifications.json"
    monkeypatch.setattr(relations, "_registry_path", lambda: target)
    assert main(["verify", "--record"]) == 0
    assert target.exists()
