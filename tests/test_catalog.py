# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.catalog`: bundled content and validation."""

import datetime

import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.model import ReferenceStatus, UnitBasis
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
citations = [{ reference = "src" }]
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
        (replace('reference = "src"', 'reference = "nope"'), "unknown reference"),
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
{extra}bounds = {{ {name} = [{low}, {high}] }}
"""


@pytest.mark.parametrize(
    ("extra", "name", "low", "high", "message"),
    [
        ("", "x", 0, 1, "'x' is not an input"),
        ("", "t", 1, 0, "empty interval"),
        # A domain stated by a source belongs to its citation.
        ('basis = "stated"\n', "t", 0, 1, "unknown keys: basis"),
    ],
)
def test_invalid_domains_are_refused(
    extra: str, name: str, low: float, high: float, message: str
) -> None:
    domain = DOMAIN.format(extra=extra, name=name, low=low, high=high)
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


@pytest.mark.parametrize(
    ("expression", "coefficients", "message"),
    [
        ("a * b * t", "{ a = 2.0, b = 3.0 }", "does not determine the unit of a, b"),
        (
            "c * exp(a * t / (b + t))",
            (
                '{ a = 1.0, b = { value = 2.0, unit = "HectoPA", unit_basis = "added", '
                'note = "x" }, c = 3.0 }'
            ),
            r"units contradict the expression, in b \+ t",
        ),
    ],
)
def test_every_coefficient_needs_a_unit_declared_or_inferred(
    expression: str, coefficients: str, message: str
) -> None:
    document = replace('expression = "a * t"', f'expression = "{expression}"').replace(
        "coefficients = { a = 2.0 }", f"coefficients = {coefficients}"
    )
    with pytest.raises(CatalogError, match=message):
        load_catalog([document])


NOTATION = """
[notations.n]
label = "A notation"
symbols = {{ e = '{symbol}' }}
"""


def test_notation_symbols_stay_within_the_common_latex_subset() -> None:
    accepted = load_catalog([VALID + NOTATION.format(symbol=r"E_{\mathrm{w}}")])
    assert accepted.notations["n"].symbols["e"] == r"E_{\mathrm{w}}"
    with pytest.raises(CatalogError, match=r"notations.n.symbols.e: .*\\textrm"):
        load_catalog([VALID + NOTATION.format(symbol=r"E_{\textrm{w}}")])


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


def test_a_local_kind_may_declare_an_interval_scale() -> None:
    document = KIND.format(name="Modified", parent="DimensionlessRatio")
    kind = load_catalog([document + 'scale_type = "interval"\n']).kinds["Modified"]
    assert kind.scale_type.value == "interval"
    assert kind.delta is False
    assert load_catalog([document]).kinds["Modified"].scale_type.value == "ratio"
    with pytest.raises(CatalogError, match="is not one of"):
        load_catalog([document + 'scale_type = "ordinal"\n'])


def test_table_expected() -> None:
    with pytest.raises(CatalogError, match="expected a table"):
        load_catalog(["[formulations]\nf = 1\n"])


def test_coefficient_with_unit_and_note() -> None:
    document = replace(
        "coefficients = { a = 2.0 }",
        'coefficients = { a = { value = 2.0, unit = "K", unit_basis = "added", '
        'note = "difference" } }',
    ).replace('expression = "a * t"', 'expression = "t * exp(a / t)"')
    coefficient = load_catalog([document]).formulations["f"].coefficients[0]
    assert (coefficient.value, coefficient.unit, coefficient.note) == (
        2.0,
        "K",
        "difference",
    )
    assert coefficient.unit_basis is UnitBasis.ADDED


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ('{ value = 2.0, unit = "K" }', 'needs unit_basis: "added" \\(with a note\\)'),
        ('{ value = 2.0, unit = "K", unit_basis = "stated" }', "goes in its citation"),
        (
            '{ value = 2.0, unit = "K", unit_basis = "added" }',
            "added unit needs a note",
        ),
        ('{ value = 2.0, unit_basis = "stated" }', "unit_basis without a unit"),
        ('{ value = 2.0, unit = "K", unit_basis = "guessed" }', "is not one of"),
    ],
)
def test_declared_units_say_where_they_come_from(table: str, message: str) -> None:
    document = replace(
        "coefficients = { a = 2.0 }", f"coefficients = {{ a = {table} }}"
    )
    document = document.replace('expression = "a * t"', 'expression = "t * exp(a / t)"')
    with pytest.raises(CatalogError, match=message):
        load_catalog([document])


def test_catalog_declares_only_units_inference_cannot_give() -> None:
    origins = {
        (f.key, name): unit.origin
        for f in CATALOG.formulations.values()
        for name, unit in f.coefficient_units.items()
        if unit.origin != "inferred"
    }
    assert origins == {
        ("iapws_sr1_86", "T_c"): "stated",
        ("iapws_sr1_86", "p_c"): "stated",
        ("iapws_r14_08_sublimation", "T_t"): "stated",
        ("iapws_r14_08_sublimation", "p_t"): "stated",
        ("goff_gratch1946", "e_st"): "added",
        ("goff_gratch1946_ice", "e_i0"): "added",
    }


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
    bundled_text = (
        files("nomogram") / "data" / "catalog" / "water-vapour.toml"
    ).read_text(encoding="utf-8")
    bundled = tomllib.loads(bundled_text)["formulations"]["alduchov_eskridge1996"]
    for key, value in example.items():
        assert bundled[key] == value, key
