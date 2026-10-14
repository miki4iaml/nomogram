# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.catalog`: bundled content and validation."""

import datetime

import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.model import ReferenceStatus
from nomogram.semantics import MatchRelation

CATALOG = catalog()

VALID = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[formulations.f]
label = "Test formulation"
expression = "a * t"
fixed_units = true
references = ["src"]
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 2.0 }
"""


def test_catalog_is_read_once() -> None:
    assert catalog() is CATALOG


def test_kind_defined_by_nomogram() -> None:
    kind = CATALOG.kinds["SaturationVapourPressureOverWater"]
    assert kind.origin == "nomogram"
    assert kind.iri is None
    assert kind.specialization_of == "VapourPressure"
    assert kind.applicable_units == CATALOG.kinds["VapourPressure"].applicable_units
    assert kind.matches[0].relation is MatchRelation.BROAD
    assert CATALOG.kinds["VapourPressure"].origin == "qudt"


def test_formulations_are_grouped_by_computed_kind() -> None:
    keys = [f.key for f in CATALOG.formulations_of("SaturationVapourPressureOverWater")]
    assert set(keys) == {
        "iapws_sr1_86",
        "sonntag1990",
        "sonntag1990_magnus",
        "alduchov_eskridge1996",
        "tetens1930",
        "buck1981",
        "buck1981_magnus",
        "hyland_wexler1983",
        "bolton1980",
        "murray1967",
        "buck1996",
        "goff_gratch1946",
        "goff1957",
    }


def test_references_carry_their_verification_status() -> None:
    assert CATALOG.references["iapws95"].status is ReferenceStatus.VERIFIED
    assert CATALOG.references["sonntag1990"].status is ReferenceStatus.TO_CONFIRM
    assert CATALOG.references["sonntag1990"].note


def test_constant_and_its_source() -> None:
    r_v = CATALOG.constants["R_v_iapws95"]
    assert (r_v.identifier, r_v.value, r_v.unit) == ("R_v", 461.51805, "J-PER-KiloGM-K")
    assert r_v.reference == "iapws95"
    assert r_v.matches[0].verified == datetime.date(2026, 10, 14)


def test_trade_term_points_to_unambiguous_kinds() -> None:
    term = CATALOG.trade_terms["absolute_humidity"]
    assert [m.kind for m in term.meanings] == [
        "MassConcentrationOfWaterVapour",
        "MassRatioOfWaterVapourToDryGas",
    ]
    assert term.meanings[0].sources == ("ams_glossary",)


def test_minimal_valid_document() -> None:
    loaded = load_catalog([VALID])
    formulation = loaded.formulations["f"]
    assert formulation.coefficients[0].unit is None
    assert loaded.formulations_of("VapourPressure") == (formulation,)


def test_documents_are_merged() -> None:
    other = '[references.other]\nauthors = "B"\ntitle = "T"\nstatus = "verified"\n'
    assert set(load_catalog([VALID, other]).references) == {"src", "other"}


def replace(old: str, new: str) -> str:
    assert old in VALID
    return VALID.replace(old, new)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("a = [", "invalid TOML"),
        ("[nothing.x]\n", "unknown sections: nothing"),
        (replace('status = "verified"', 'status = "maybe"'), "is not one of"),
        (
            replace('label = "Test formulation"', 'surplus = "x"'),
            "unknown keys: surplus",
        ),
        (replace('label = "Test formulation"\n', ""), "missing keys: label"),
        (
            replace('expression = "a * t"', 'expression = "a * t * b"'),
            "undeclared name",
        ),
        (
            replace('expression = "a * t"', 'expression = "t"'),
            "declared but not used: a",
        ),
        (replace('references = ["src"]', 'references = ["nope"]'), "unknown reference"),
        (replace('unit = "HectoPA"', 'unit = "NOPE"'), "unknown unit"),
        (
            replace('unit = "DEG_C"', 'unit = "K"'),
            "K does not apply to CelsiusTemperature",
        ),
        (replace('kind = "VapourPressure"', 'kind = "Nope"'), "unknown kind"),
        (replace('identifier = "e"', 'identifier = "t"'), "declared twice: t"),
        (
            replace("[formulations.f]", "[formulations.f]\nconstants = ['c']"),
            "unknown constant",
        ),
        (replace('label = "Test formulation"', "label = 1\n[x]"), "unknown sections"),
    ],
)
def test_invalid_documents_are_refused(document: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([document])


def test_entry_defined_twice_is_refused() -> None:
    with pytest.raises(CatalogError, match="defined twice: src"):
        load_catalog(
            [
                VALID,
                '[references.src]\nauthors = "B"\ntitle = "T"\nstatus = "verified"\n',
            ]
        )


DOMAIN = """
[[formulations.f.domains]]
basis = "{basis}"
bounds = {{ {name} = [{low}, {high}] }}
"""


@pytest.mark.parametrize(
    ("basis", "name", "low", "high", "message"),
    [
        ("stated", "x", 0, 1, "'x' is not an input"),
        ("stated", "t", 1, 0, "empty interval"),
        ("guessed", "t", 0, 1, "is not one of physical, stated"),
    ],
)
def test_invalid_domains_are_refused(
    basis: str, name: str, low: float, high: float, message: str
) -> None:
    domain = DOMAIN.format(basis=basis, name=name, low=low, high=high)
    with pytest.raises(CatalogError, match=message):
        load_catalog([VALID + domain])


QUANTITY = """
[constants.k]
identifier = "k"
value = 2.0
unit = "J-PER-KiloGM-K"
description = "constant"
reference = "src"

[formulations.q]
label = "Quantity equation"
expression = "e / (k * T)"
fixed_units = false
output = {{ identifier = "rho", kind = "MassConcentrationOfWaterVapour", unit = "{unit}", description = "out" }}
inputs = [
  {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "in" }},
  {{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "in" }},
]
constants = ["k"]
"""


def test_quantity_equation_gets_its_unit_factor() -> None:
    loaded = load_catalog([VALID + QUANTITY.format(unit="GM-PER-M3")])
    # hPa / (J kg-1 K-1 * K) = 100 kg/m3 = 100 000 g/m3.
    assert loaded.formulations["q"].output_factor == pytest.approx(1e5)


def test_dimensionally_inconsistent_equation_is_refused() -> None:
    document = VALID + QUANTITY.format(unit="GM-PER-M3").replace(
        'expression = "e / (k * T)"', 'expression = "e / (k * T * T)"'
    )
    with pytest.raises(CatalogError, match="not dimensionally homogeneous"):
        load_catalog([document])


def test_bad_matches_are_refused() -> None:
    bad_date = replace(
        'status = "verified"',
        'status = "verified"\nmatches = [{ target = "x", relation = "exact", verified = "today" }]',
    )
    with pytest.raises(CatalogError, match="expected a date"):
        load_catalog([bad_date])
    bad_relation = bad_date.replace('"today"', "2026-10-14").replace(
        '"exact"', '"same"'
    )
    with pytest.raises(CatalogError, match="is not one of exact"):
        load_catalog([bad_relation])


KIND = """
[kinds.{name}]
label = "Local kind"
specialization_of = "{parent}"
"""


@pytest.mark.parametrize(
    ("name", "parent", "message"),
    [
        ("VapourPressure", "Pressure", "already a QUDT kind"),
        ("Local", "Nope", "unknown kind 'Nope'"),
    ],
)
def test_invalid_kinds_are_refused(name: str, parent: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([KIND.format(name=name, parent=parent)])


def test_table_expected() -> None:
    with pytest.raises(CatalogError, match="expected a table"):
        load_catalog(["[formulations]\nf = 1\n"])


def test_coefficient_with_unit_and_note() -> None:
    document = replace(
        "coefficients = { a = 2.0 }",
        'coefficients = { a = { value = 2.0, unit = "K", note = "difference" } }',
    )
    coefficient = load_catalog([document]).formulations["f"].coefficients[0]
    assert (coefficient.value, coefficient.unit, coefficient.note) == (
        2.0,
        "K",
        "difference",
    )


def test_coefficient_table_without_unit() -> None:
    document = replace(
        "coefficients = { a = 2.0 }", "coefficients = { a = { value = 2.0 } }"
    )
    assert load_catalog([document]).formulations["f"].coefficients[0].unit is None


def test_catalog_guide_example_matches_the_catalog() -> None:
    import re
    import tomllib
    from importlib.resources import files
    from pathlib import Path

    guide = Path(__file__).parents[1] / "docs" / "catalog.md"
    block = re.search(
        r"```toml\n(.*?)```", guide.read_text(encoding="utf-8"), re.DOTALL
    )
    assert block is not None
    example = tomllib.loads(block.group(1))["formulations"]["alduchov_eskridge1996"]
    bundled_text = (files("nomogram") / "data" / "catalog" / "humidity.toml").read_text(
        encoding="utf-8"
    )
    bundled = tomllib.loads(bundled_text)["formulations"]["alduchov_eskridge1996"]
    for key, value in example.items():
        assert bundled[key] == value, key
