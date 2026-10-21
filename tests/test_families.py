# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for catalog families: selection, dependencies, personal catalogs."""

from pathlib import Path

import pytest

from nomogram.catalog import (
    FORMAT,
    CatalogError,
    Family,
    catalog,
    describe,
    load_catalog,
    main,
)

FOLDER = Path(__file__).parents[1] / "src" / "nomogram" / "data" / "catalog"


def test_bundled_families_are_layered() -> None:
    families = catalog().families
    assert set(families) == {
        "core",
        "water-vapour",
        "moist-air",
        "humidity",
        "radio",
        "sea-water",
    }
    assert families["core"].requires == ()
    assert families["water-vapour"].requires == ("core",)
    assert families["moist-air"].requires == ("water-vapour",)
    assert families["radio"].requires == ("moist-air",)
    humidity = families["humidity"]
    assert isinstance(humidity, Family)
    assert humidity.is_aggregate
    assert set(humidity.requires) == {"water-vapour", "moist-air"}
    assert not families["water-vapour"].is_aggregate


@pytest.mark.parametrize(
    ("name", "loaded"),
    [
        ("core", {"core"}),
        ("water-vapour", {"core", "water-vapour"}),
        ("moist-air", {"core", "water-vapour", "moist-air"}),
        ("humidity", {"core", "water-vapour", "moist-air", "humidity"}),
    ],
)
def test_each_family_loads_with_its_requires_only(name: str, loaded: set[str]) -> None:
    selected = catalog(name)
    assert set(selected.families) == loaded
    expected = {k for f in loaded for k in catalog().families[f].formulations}
    assert set(selected.formulations) == expected


def test_selections_are_cached_whatever_the_order() -> None:
    assert catalog() is catalog()
    assert catalog("moist-air", "core") is catalog("core", "moist-air")
    assert catalog("core") is not catalog()


def test_entries_know_their_family_from_their_file() -> None:
    c = catalog()
    assert c.formulations["iapws_sr1_86"].family == "water-vapour"
    assert c.formulations["mixing_ratio_from_vapour_pressure"].family == "moist-air"
    assert "iapws_sr1_86" in c.families["water-vapour"].formulations
    assert "its90" in c.families["core"].contents["scales"]
    assert c.families["water-vapour"].keywords


def test_unknown_family_is_refused() -> None:
    with pytest.raises(CatalogError, match="unknown families: nope"):
        catalog("nope")


def header(name: str, requires: str = "", extra: str = "") -> str:
    return f'[catalog]\nname = "{name}"\nformat = {FORMAT}\nrequires = [{requires}]\n{extra}'


BASE = (
    header("base")
    + '[references.src]\nauthors = "A."\ntitle = "T"\nstatus = "verified"\n'
)
USER = header("user", '"base"') + (
    '[constants.k]\nidentifier = "k"\nvalue = 2.0\nunit = "K"\n'
    'description = "d"\nreference = "src"\n'
)


def test_a_family_uses_what_it_requires() -> None:
    loaded = load_catalog([BASE, USER])
    assert loaded.constants["k"].reference == "src"
    assert set(loaded.families) == {"base", "user"}


@pytest.mark.parametrize(
    ("documents", "message"),
    [
        (
            [BASE, USER.replace('["base"]', "[]")],
            "constants.k uses references.src from family base",
        ),
        (
            [BASE, header("other"), USER.replace('["base"]', '["base", "other"]')],
            r"requires other but uses nothing from it; requires = \['base'\]",
        ),
        ([USER], "requires unknown family 'base'"),
        (
            [header("a", '"b"'), header("b", '"a"')],
            "requires form a cycle",
        ),
        ([BASE, BASE], "family base defined twice"),
        (
            [BASE.replace(f"format = {FORMAT}", "format = 1")],
            "format 1 is not supported",
        ),
        ([BASE.replace(f"format = {FORMAT}\n", "")], "missing keys: format"),
        (
            [BASE.replace("requires = []", 'requires = "x"')],
            "expected a list of family names",
        ),
        (
            [BASE.replace(header("base"), ""), USER.replace('["base"]', "[]")],
            "uses references.src from a document without \\[catalog\\] header",
        ),
    ],
)
def test_family_rules_are_enforced(documents: list[str], message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog(documents)


def test_documents_may_be_paths(tmp_path: Path) -> None:
    path = tmp_path / "base.toml"
    path.write_text(BASE, encoding="utf-8")
    assert "src" in load_catalog([path]).references
    broken = tmp_path / "broken.toml"
    broken.write_text("[references", encoding="utf-8")
    with pytest.raises(CatalogError, match="broken.toml: invalid TOML"):
        load_catalog([broken])


PERSONAL = header("mylab", '"water-vapour"') + (
    '[references."mylab:note"]\nauthors = "Lab"\ntitle = "Internal note"\nstatus = "verified"\n\n'
    '[formulations."mylab:twice_buck"]\nlabel = "Twice a vapour pressure"\nexpression = "2 * e"\n'
    "fixed_units = false\n"
    'output = { identifier = "y", kind = "VapourPressure", unit = "PA", description = "out" }\n'
    'inputs = [{ identifier = "e", kind = "SaturationVapourPressureOverWater", unit = "PA", '
    'description = "in" }]\n'
    'keywords = ["laboratory"]\n'
    '[[formulations."mylab:twice_buck".citations]]\nreference = "mylab:note"\n'
)


def test_personal_catalogs_extend_the_bundled_ones(tmp_path: Path) -> None:
    path = tmp_path / "mylab.toml"
    path.write_text(PERSONAL, encoding="utf-8")
    extended = catalog(extra=[path])
    formulation = extended.formulations["mylab:twice_buck"]
    assert formulation.family == "mylab"
    assert formulation.keywords == ("laboratory",)
    # Only the families it requires come along when one is chosen.
    small = catalog("core", extra=[path])
    assert set(small.families) == {"core", "water-vapour", "mylab"}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            ('[references."mylab:note"]', "[references.note]"),
            "references.note must start with 'mylab:'",
        ),
        (('name = "mylab"', 'name = "core"'), "core is the name of a bundled family"),
        (
            ('keywords = ["laboratory"]', 'keywords = "laboratory"'),
            "expected a list of non-empty strings",
        ),
    ],
)
def test_personal_catalog_rules(
    tmp_path: Path, change: tuple[str, str], message: str
) -> None:
    path = tmp_path / "mylab.toml"
    path.write_text(PERSONAL.replace(*change), encoding="utf-8")
    with pytest.raises(CatalogError, match=message):
        catalog(extra=[path])


@pytest.mark.parametrize("name", ["core", "water-vapour", "moist-air", "humidity"])
def test_describe_gives_the_header_of_each_bundled_family(name: str) -> None:
    text = (FOLDER / f"{name}.toml").read_text(encoding="utf-8")
    described = describe(FOLDER / f"{name}.toml")
    for line in described.splitlines():
        assert line in text, line


def test_describe_computes_the_requires_of_a_new_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "mylab.toml"
    path.write_text(
        PERSONAL.replace('requires = ["water-vapour"]', "requires = []"),
        encoding="utf-8",
    )
    assert 'requires = ["water-vapour"]' in describe(path)
    no_header = tmp_path / "draft.toml"
    no_header.write_text(
        PERSONAL.split("[references", 1)[1].join(["[references", ""]), encoding="utf-8"
    )
    assert 'name = "draft"' in describe(no_header)
    assert main(["describe", str(path)]) == 0
    assert 'name = "mylab"' in capsys.readouterr().out


def test_a_physical_domain_counts_as_a_use_of_its_reference() -> None:
    formulation = header("dom") + (
        '[formulations.f]\nlabel = "F"\nexpression = "2 * t"\nfixed_units = false\n'
        'output = { identifier = "e", kind = "TemperatureDifference", unit = "K", '
        'description = "out" }\n'
        'inputs = [{ identifier = "t", kind = "TemperatureDifference", unit = "K", '
        'description = "in" }]\n'
        '[[formulations.f.domains]]\nbounds = { t = [0.0, 1.0] }\nreference = "src"\n'
    )
    with pytest.raises(
        CatalogError, match="formulations.f uses references.src from family base"
    ):
        load_catalog([BASE, formulation])
    fixed = formulation.replace("requires = []", 'requires = ["base"]')
    assert load_catalog([BASE, fixed]).formulations["f"].family == "dom"
