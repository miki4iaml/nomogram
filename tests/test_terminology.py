# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The words of physical assumptions, as the glossary of docs/rosetta.md writes them."""

import re
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]

#: The variants the glossary ("Physical assumptions") leaves to citations,
#: with the form nomogram writes.
VARIANTS = {
    "perfect gas": "ideal gas",
    "dry-adiabatic": "dry adiabatic",
    "moist-adiabatic": "moist adiabatic",
    "saturation-adiabatic": "saturated adiabatic",
    "pseudo-adiabatic": "pseudoadiabatic",
    "pseudo adiabatic": "pseudoadiabatic",
    "lapse-rate": "lapse rate",
}
PATTERN = re.compile("|".join(re.escape(v) for v in VARIANTS), re.IGNORECASE)

#: Parts of a catalog file that report what a source writes, kept as written.
QUOTING = {"citations", "references", "trade_terms", "cross_checks"}

#: Quoted text, code and titles (in italics, the names of glossary entries)
#: in the documentation, kept as written.
QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”|`[^`\n]*`|\*[^*]+\*')


def catalog_variants(document: Any, where: str = "") -> list[str]:
    """The variants in the texts of a catalog file, outside what quotes a source."""
    found: list[str] = []
    if isinstance(document, dict):
        for key, value in document.items():
            if key not in QUOTING:
                found += catalog_variants(value, f"{where}.{key}" if where else key)
    elif isinstance(document, list):
        for index, value in enumerate(document):
            found += catalog_variants(value, f"{where}[{index}]")
    elif isinstance(document, str):
        found += [f"{where}: {m.group(0)}" for m in PATTERN.finditer(document)]
    return found


def text_variants(text: str) -> list[str]:
    """The variants in a page of documentation, outside quotes, code and titles."""
    return [m.group(0) for m in PATTERN.finditer(QUOTED.sub("", text))]


CATALOG_FILES = sorted(
    (
        p
        for p in files("nomogram").joinpath("data/catalog").iterdir()
        if p.name.endswith(".toml")
    ),
    key=lambda p: p.name,
)


@pytest.mark.parametrize("path", CATALOG_FILES, ids=lambda p: p.name)
def test_the_catalog_writes_the_forms_of_the_glossary(path: Any) -> None:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    assert catalog_variants(document) == []


@pytest.mark.parametrize(
    "path",
    [*sorted((ROOT / "docs").glob("*.md")), ROOT / "README.md"],
    ids=lambda p: p.name,
)
def test_the_documentation_writes_the_forms_of_the_glossary(path: Path) -> None:
    assert text_variants(path.read_text(encoding="utf-8")) == []


def test_a_variant_is_found_outside_a_citation_only() -> None:
    document = {
        "formulations": {
            "f": {
                "label": "Density of a perfect gas",
                "citations": [{"assumptions": ["A dry-adiabatic ascent."]}],
            }
        },
        "references": {"r": {"note": "The source writes perfect gas."}},
    }
    assert catalog_variants(document) == ["formulations.f.label: perfect gas"]
    assert text_variants('A pseudo-adiabatic ascent, "a dry-adiabatic one".') == [
        "pseudo-adiabatic"
    ]
