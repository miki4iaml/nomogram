# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Archive metadata (.zenodo.json) stays consistent with CITATION.cff, and
every file that credits the bundled data names the versions extracted."""

import json
import re
from pathlib import Path

import pytest

from nomogram.semantics import semantic_catalog

ROOT = Path(__file__).parents[1]
ZENODO = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
CITATION = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
SEMANTICS = semantic_catalog()
NOTICE = "src/nomogram/data/NOTICE.md"

#: The versioned page of the CF standard name table.
CF_TABLE = "cf-standard-names/{cf}/build/cf-standard-name-table.html"

#: How each file credits QUDT and the CF standard name table, by version.
CREDITS = {
    "README.md": (
        "by QUDT.org (<https://qudt.org>), release {qudt}",
        "version {cf}",
        CF_TABLE,
    ),
    "README.fr.md": (
        "par QUDT.org (<https://qudt.org>), version {qudt}",
        "version {cf}",
        CF_TABLE,
    ),
    NOTICE: (
        "by QUDT.org (<https://qudt.org>), release {qudt}",
        "version {cf}",
        CF_TABLE,
    ),
    "CITATION.cff": ('version: "{qudt}"', 'version: "{cf}"', CF_TABLE),
}


def text_of(name: str) -> str:
    """The file's text with its line breaks folded into spaces."""
    return " ".join((ROOT / name).read_text(encoding="utf-8").split())


def credits(text: str, expected: str) -> bool:
    """Whether ``text`` holds ``expected``, not followed by another digit."""
    return re.search(re.escape(expected) + r"(?!\d)", text) is not None


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


@pytest.mark.parametrize("name", sorted(CREDITS))
def test_bundled_data_is_credited_with_the_extracted_versions(name: str) -> None:
    text = text_of(name)
    for credit in CREDITS[name]:
        expected = credit.format(qudt=SEMANTICS.qudt_version, cf=SEMANTICS.cf_version)
        assert credits(text, expected), (name, expected)


def test_zenodo_references_the_bundled_data() -> None:
    references = " ".join(ZENODO["references"])
    qudt = "QUDT — Quantities, Units, Dimensions and Types"
    cf = SEMANTICS.cf_version
    assert credits(references, f"{qudt}, release {SEMANTICS.qudt_version}")
    assert credits(references, f"CF Standard Name Table, version {cf}")
    assert credits(references, CF_TABLE.format(cf=cf))


def test_a_version_prefix_is_not_a_credit() -> None:
    assert credits("release 3.5.2, licensed", "release 3.5.2")
    assert not credits("release 3.5.21, licensed", "release 3.5.2")


@pytest.mark.parametrize("name", ["README.md", "README.fr.md", NOTICE])
def test_ucum_codes_are_credited(name: str) -> None:
    # The units carry UCUM codes, which QUDT identifies as third-party
    # material under the UCUM license.
    assert any(unit.ucum for unit in SEMANTICS.units.values())
    text = text_of(name)
    assert "Regenstrief Institute, Inc." in text
    assert "https://ucum.org/license" in text
