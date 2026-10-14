# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Archive metadata (.zenodo.json) stays consistent with CITATION.cff."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
ZENODO = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
CITATION = (ROOT / "CITATION.cff").read_text(encoding="utf-8")


def citation_keywords() -> list[str]:
    block = CITATION.split("keywords:", 1)[1]
    return re.findall(r"^  - (.+)$", block, flags=re.MULTILINE)


def test_zenodo_required_fields() -> None:
    for field in ("title", "upload_type", "description", "creators", "license"):
        assert ZENODO[field], field
    assert ZENODO["upload_type"] == "software"
    assert ZENODO["license"] == "bsd-3-clause"


def test_every_creator_has_a_name_and_nothing_personal() -> None:
    # Zenodo requires a name per creator; the project publishes an alias
    # only: no affiliation, ORCID or other identifying field.
    for creator in ZENODO["creators"]:
        assert set(creator) == {"name"}
    names = [c["name"] for c in ZENODO["creators"]]
    assert names == re.findall(r"^  - alias: (.+)$", CITATION, flags=re.MULTILINE)


def test_title_and_keywords_match_the_citation_file() -> None:
    assert f"title: {ZENODO['title']}" in CITATION
    assert ZENODO["keywords"] == citation_keywords()


def test_version_is_left_to_the_release_tag() -> None:
    assert "version" not in ZENODO
