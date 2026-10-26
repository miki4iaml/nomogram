# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for proportionalities and relations computed by nomogram."""

from importlib.resources import files

import pytest

from nomogram.catalog import Catalog, CatalogError, catalog, load_catalog, main
from nomogram.model import RelationKind
from nomogram.relations import verify

CATALOG = catalog()
MURRAY = CATALOG.relations["murray1967_tetens1930"]

SOURCE = """
[references.src]
authors = "A."
title = "T"
status = "verified"
"""


def exponential(key: str, c: float, a: float = 0.07) -> str:
    """A pure exponential of a Celsius temperature, written for a test."""
    return f"""
[formulations.{key}]
label = "{key}"
expression = "C * exp(a * t)"
fixed_units = true
output = {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }}
inputs = [{{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }}]
coefficients = {{ C = {c}, a = {a} }}

[[formulations.{key}.citations]]
reference = "src"
"""


def with_catalog(*documents: str) -> Catalog:
    """The bundled catalog, its scales among others, with documents for a test."""
    bundled = sorted(
        (
            f
            for f in files("nomogram.data.catalog").iterdir()
            if f.name.endswith(".toml")
        ),
        key=lambda f: f.name,
    )
    return load_catalog([*(f.read_text(encoding="utf-8") for f in bundled), *documents])


def relation(subject: str, other: str, extra: str = "") -> str:
    return f"""
[relations.r]
kind = "proportional"
subject = "{subject}"
object = "{other}"
bounds = {{ t = [-40.0, 50.0] }}
{extra}
"""


# --- Murray and Tetens --------------------------------------------------------------


def test_murray_is_tetens_to_the_printed_precision() -> None:
    assert MURRAY.computed
    assert MURRAY.citation is None
    found = verify(MURRAY, CATALOG)
    assert found.status == "held"
    assert found.value == pytest.approx(6.1078 / 6.11, rel=1e-7)
    assert found.detail is not None
    detail = found.detail
    assert "the ratio of C of murray1967 to C of tetens1930 (6.1078 / 6.11)" in detail
    assert "rounding of A of murray1967 (17.269388)" in detail
    assert "equivalent to the printed precision" in detail
    assert "rounding of C of tetens1930 (6.11)" in detail
    assert "not a matter of scale" in detail


def test_a_computed_relation_is_found_and_linked() -> None:
    found = CATALOG.search("computed by nomogram", section="relations")
    assert "relations.murray1967_tetens1930" in found.refs
    assert (
        "relations.murray1967_tetens1930"
        in CATALOG.used_by("formulations.tetens1930").refs
    )


def test_the_verdicts_command_gives_the_factor(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["verify"]) == 0
    assert "murray1967_tetens1930: held factor 0.99963993" in capsys.readouterr().out


# --- Strict proportionality and scale ---------------------------------------------


def test_an_equivalence_is_a_proportionality() -> None:
    assert RelationKind.EQUIVALENT.broader is RelationKind.PROPORTIONAL
    assert RelationKind.PROPORTIONAL.broader is None
    assert RelationKind.APPROXIMATES.broader is None


def test_a_strict_proportionality_may_be_a_matter_of_scale() -> None:
    # C exp(a t) and C' exp(a t): a shift of t gives the factor exactly.
    loaded = with_catalog(
        SOURCE + exponential("f", 6.0) + exponential("g", 6.3) + relation("f", "g")
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "proven"
    assert found.value == pytest.approx(6.0 / 6.3)
    assert found.detail is not None
    assert "the ratio of C of f to C of g" in found.detail
    assert "with a shift of t" in found.detail
    assert "may come from the scale of t" in found.detail


def test_a_factor_of_an_input_the_object_is_proportional_to_tells_nothing() -> None:
    # C T and C' T: a factor of T is a factor of the result, any one.
    def linear(key: str, c: float) -> str:
        return f"""
[formulations.{key}]
label = "{key}"
expression = "C * T"
fixed_units = true
output = {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }}
inputs = [{{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "T" }}]
coefficients = {{ C = {c} }}

[[formulations.{key}.citations]]
reference = "src"
"""

    loaded = with_catalog(
        SOURCE
        + linear("f", 2.0)
        + linear("g", 2.1)
        + relation("f", "g").replace("t = [-40.0, 50.0]", "T = [233.15, 323.15]")
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "proven"
    assert found.detail is not None
    assert "no shift of T makes them as close" in found.detail
    assert "a factor of T cannot be told from a coefficient" in found.detail
    assert "may come from the scale" not in found.detail


def test_without_a_scaled_input_scale_is_not_examined() -> None:
    loaded = load_catalog(
        [SOURCE + exponential("f", 6.0) + exponential("g", 6.3) + relation("f", "g")]
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.detail is not None
    assert found.detail.endswith("no input with a conventional scale")


def test_held_but_not_equal_to_the_printed_precision() -> None:
    # The exponents differ within the rounding of the first; the constants
    # differ far beyond their rounding.
    f = exponential("f", 6.000001, a=0.0700001)
    g = exponential("g", 6.300001, a=0.07000012)
    loaded = load_catalog([SOURCE + f + g + relation("f", "g")])
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "held"
    assert found.detail is not None
    assert "rounding of a of f (0.0700001)" in found.detail
    assert "equivalent to the printed precision" not in found.detail


def test_a_factor_that_is_no_ratio_of_coefficients() -> None:
    g = exponential("g", 2.5).replace('"C * exp(a * t)"', '"C * 2 * exp(a * t)"')
    loaded = load_catalog([SOURCE + exponential("f", 6.0) + g + relation("f", "g")])
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "proven"
    assert found.value == pytest.approx(1.2)
    assert found.detail is not None
    assert "the ratio of" not in found.detail


@pytest.mark.parametrize(
    ("scale", "expected"), [("", "unverified"), ('scale = "ignore"', "proven")]
)
def test_formulations_on_different_scales(scale: str, expected: str) -> None:
    on_ipts68 = exponential("g", 6.3).replace(
        'description = "t" }]',
        'description = "t", scale = "ipts68", scale_basis = "inferred-from-date" }]',
    )
    loaded = with_catalog(
        SOURCE + exponential("f", 6.0) + on_ipts68 + relation("f", "g", scale)
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.status == expected
    if expected == "proven":
        assert "scales ignored" in found.method


def test_a_ratio_that_varies_is_refuted() -> None:
    loaded = load_catalog(
        [
            SOURCE
            + exponential("f", 6.0)
            + exponential("g", 6.0, a=0.08)
            + relation("f", "g")
        ]
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "refuted"
    assert found.value is None
    assert set(found.at) == {"t"}


# --- What the catalog refuses ------------------------------------------------------


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (
            relation("f", "g").replace('kind = "proportional"', 'kind = "approximates"')
            + "accuracy = 1.0\n",
            "an approximation states its source",
        ),
        (
            relation("f", "g").replace("bounds = { t = [-40.0, 50.0] }", ""),
            "checked on a domain",
        ),
        (relation("f", "g", "accuracy = 1.0"), "only for an approximation"),
    ],
)
def test_what_a_proportionality_cannot_be(document: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog(
            [SOURCE + exponential("f", 6.0) + exponential("g", 6.3) + document]
        )


def test_a_given_expression_may_convert_a_unit_but_not_rename_it() -> None:
    kelvin = (
        exponential("k", 6.0)
        .replace(
            'identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C"',
            'identifier = "T", kind = "ThermodynamicTemperature", unit = "K"',
        )
        .replace("a * t", "a * (T - 273.15)")
    )
    converted = relation("k", "g", 'given = { t = "T - 273.15" }').replace(
        "bounds = { t = [-40.0, 50.0] }", "bounds = { T = [233.15, 323.15] }"
    )
    loaded = load_catalog([SOURCE + kelvin + exponential("g", 6.3) + converted])
    assert verify(loaded.relations["r"], loaded).status == "proven"
    renamed = converted.replace('"T - 273.15"', '"T"')
    with pytest.raises(CatalogError, match="needs the same units"):
        load_catalog([SOURCE + kelvin + exponential("g", 6.3) + renamed])
