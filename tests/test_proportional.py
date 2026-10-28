# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for proportionalities and relations computed by nomogram."""

import dataclasses
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
    # C exp(a t) and C' exp(a t), C' = C exp(0.01 a): a shift of t by
    # 0.01 K, a Celsius origin written 273.16 K, gives the factor exactly.
    loaded = with_catalog(
        SOURCE
        + exponential("f", 6.0)
        + exponential("g", 6.00420147)
        + relation("f", "g")
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "proven"
    assert found.detail is not None
    assert "the ratio of C of f to C of g" in found.detail
    assert "equal to it with a shift of t (-0.01)" in found.detail
    assert "may come from the scale of t" in found.detail


def test_a_shift_beyond_the_catalog_scales_is_no_matter_of_scale() -> None:
    # 6.0 and 6.3: a shift of t by 0.7 degC, which no scale gives.
    loaded = with_catalog(
        SOURCE + exponential("f", 6.0) + exponential("g", 6.3) + relation("f", "g")
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "proven"
    assert found.value == pytest.approx(6.0 / 6.3)
    assert found.detail is not None
    assert found.detail.endswith(
        "no shift nor factor of t within what the catalog's scales give makes "
        "them as close: not a matter of scale"
    )


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
    assert (
        "no shift of T within what the catalog's scales give makes them as close"
        in found.detail
    )
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


# --- Printed precision ---------------------------------------------------------------


def test_the_printed_precision_is_read_in_any_notation() -> None:
    from nomogram.model import ConstantNature
    from nomogram.relations import _constant_step, _printed_step

    assert _printed_step(5.9e-6) == pytest.approx(5e-8)
    assert _printed_step(0.0001) == pytest.approx(5e-5)
    assert _printed_step(6.112) == pytest.approx(5e-4)
    # An integral value is read without its trailing zeros.
    assert _printed_step(72.0) == 0.5
    assert _printed_step(2.501e6) == 500
    t_0 = CATALOG.constants["T_0_ecmwf_ifs"]
    assert _constant_step(t_0) == pytest.approx(5e-3)
    exact = dataclasses.replace(t_0, nature=ConstantNature.EXACT)
    assert _constant_step(exact) == 0
    printed = dataclasses.replace(t_0, printed="273.1600")
    assert _constant_step(printed) == pytest.approx(5e-5)


def test_a_small_coefficient_does_not_hide_a_large_variation() -> None:
    # b t^2 with b = 1e-5 makes the ratio vary by a factor of 2.5 over the
    # bounds; its rounding, 5e-7, explains nothing of it.
    f = (
        exponential("f", 6.0, a=0.06)
        .replace('"C * exp(a * t)"', '"C * exp(a * t + b * t ** 2)"')
        .replace("a = 0.06 }", "a = 0.06, b = 1e-05 }")
    )
    loaded = load_catalog(
        [SOURCE + f + exponential("g", 6.0, a=0.06) + relation("f", "g")]
    )
    assert verify(loaded.relations["r"], loaded).status == "refuted"


def test_a_coefficient_explains_only_a_variation_it_can_take_away() -> None:
    # The ratio varies along p, which the rounding of a (0.005, along t)
    # cannot follow, and which b explains only for half of it.
    two = """
[formulations.f]
label = "f"
expression = "C * exp(a * t + b * p)"
fixed_units = true
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }
inputs = [
  { identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" },
  { identifier = "p", kind = "Pressure", unit = "HectoPA", description = "p" },
]
coefficients = { C = 6.0, a = 0.07, b = 0.001 }

[[formulations.f.citations]]
reference = "src"
"""
    bounds = relation("f", "g").replace(
        "bounds = { t = [-40.0, 50.0] }",
        "bounds = { t = [-40.0, 50.0], p = [0.0, 100.0] }",
    )
    loaded = load_catalog([SOURCE + two + exponential("g", 6.0) + bounds])
    assert verify(loaded.relations["r"], loaded).status == "refuted"


def test_two_equal_coefficients_explain_no_factor() -> None:
    f = exponential("f", 7.2, a=0.0700001)
    g = exponential("g", 7.2, a=0.07000012)
    loaded = load_catalog([SOURCE + f + g + relation("f", "g")])
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "held"
    assert found.detail is not None
    assert "the median of the sampled ratio" in found.detail
    assert "(7.2 / 7.2)" not in found.detail


def test_negative_outputs_are_compared_by_their_ratio() -> None:
    def negative(key: str, a: float) -> str:
        return exponential(key, 6.0, a=a).replace(
            '"C * exp(a * t)"', '"-C * exp(a * t)"'
        )

    loaded = load_catalog(
        [
            SOURCE
            + negative("f", 0.0700001)
            + negative("g", 0.07000012)
            + relation("f", "g")
        ]
    )
    assert verify(loaded.relations["r"], loaded).status == "held"


def test_a_ratio_that_changes_sign_is_refuted() -> None:
    # (t + 0.07) / (t + 10) is negative from -10 to -0.07 degC.
    f = exponential("f", 2.0).replace('"C * exp(a * t)"', '"C * (t + a)"')
    g = exponential("g", 2.0, a=10.0).replace('"C * exp(a * t)"', '"C * (t + a)"')
    loaded = load_catalog([SOURCE + f + g + relation("f", "g")])
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "refuted"
    assert "the ratio changes sign" in found.method


@pytest.mark.parametrize(
    ("bounds", "status", "share"),
    [
        # The square root of a negative t is not real: part of the samples,
        # or all.
        ("t = [-40.0, 50.0]", "held", "% of the samples only"),
        ("t = [-40.0, -1.0]", "unverified", "0 % of the samples only"),
    ],
)
def test_samples_where_a_side_is_not_finite_are_left_aside(
    bounds: str, status: str, share: str
) -> None:
    # Two writings of sqrt(t) that SymPy does not cancel for a real t.
    f = exponential("f", 6.0, a=0.0700001).replace(
        '"C * exp(a * t)"', '"C * sqrt(t) * exp(a * t)"'
    )
    g = exponential("g", 6.0, a=0.07000012).replace(
        '"C * exp(a * t)"', '"C * sqrt(t ** 3) / t * exp(a * t)"'
    )
    document = relation("f", "g").replace("t = [-40.0, 50.0]", bounds)
    loaded = load_catalog([SOURCE + f + g + document])
    found = verify(loaded.relations["r"], loaded)
    assert found.status == status
    assert share in found.method


def test_an_exact_constant_hides_no_rounding() -> None:
    exact = """
[constants.k]
identifier = "k"
value = 1.380649
unit = "UNITLESS"
description = "an exact constant"
reference = "src"
nature = "exact"
"""
    f = (
        exponential("f", 6.0, a=0.0700001)
        .replace('"C * exp(a * t)"', '"C * k * exp(a * t)"')
        .replace("a = 0.0700001 }", 'a = 0.0700001 }\nconstants = ["k"]')
    )
    g = exponential("g", 6.0, a=0.07000012)
    loaded = load_catalog([SOURCE + exact + f + g + relation("f", "g")])
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "held"
    assert found.detail is not None
    assert "k of f" not in found.detail


def test_a_ratio_constant_without_coefficients_is_held() -> None:
    # sqrt(t^2) / t is 1 for t > 0, which SymPy does not conclude for a
    # real t.
    def plain(key: str, expression: str) -> str:
        return (
            exponential(key, 1.0)
            .replace('"C * exp(a * t)"', f'"{expression}"')
            .replace("coefficients = { C = 1.0, a = 0.07 }\n", "")
        )

    document = relation("f", "g").replace("t = [-40.0, 50.0]", "t = [1.0, 50.0]")
    loaded = load_catalog(
        [SOURCE + plain("f", "sqrt(t ** 2)") + plain("g", "t") + document]
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "held"
    assert found.detail is not None
    assert "within the precision of the computation" in found.detail


def test_a_salinity_is_moved_only_as_far_as_its_scales_go() -> None:
    # Knudsen and Cox salinities convert; PSS-78, a number, holds no value
    # in g/kg; Absolute Salinity does not convert. None gives 6.0 / 6.3.
    def salinity(key: str, c: float) -> str:
        return (
            exponential(key, c)
            .replace('"C * exp(a * t)"', '"C * exp(a * S)"')
            .replace(
                'identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C"',
                'identifier = "S", kind = "SeaWaterSalinity", unit = "GM-PER-KiloGM"',
            )
        )

    document = relation("f", "g").replace("t = [-40.0, 50.0]", "S = [30.0, 40.0]")
    loaded = with_catalog(SOURCE + salinity("f", 6.0) + salinity("g", 6.3) + document)
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "proven"
    assert found.detail is not None
    assert found.detail.endswith(
        "no shift nor factor of S within what the catalog's scales give makes "
        "them as close: not a matter of scale"
    )


def test_a_scale_whose_table_misses_the_bounds_moves_nothing() -> None:
    # The table of "old" starts at 0 degC: below, only the 0.01 K of a
    # Celsius origin written 273.16 K is tried.
    scales = """
[scales.ref]
label = "Reference scale"
kinds = ["CelsiusTemperature"]

[scales.old]
label = "Old scale"
kinds = ["CelsiusTemperature"]
reference_scale = "ref"
unit = "DEG_C"
differences = [[0.0, 0.0], [400.0, 0.1]]
"""
    document = relation("f", "g").replace("t = [-40.0, 50.0]", "t = [-40.0, -1.0]")
    loaded = load_catalog(
        [SOURCE + scales + exponential("f", 6.0) + exponential("g", 6.3) + document]
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.detail is not None
    assert found.detail.endswith("not a matter of scale")


# --- Fingerprints ------------------------------------------------------------------


def test_the_signature_follows_the_units_of_coefficients() -> None:
    from nomogram.relations import signature

    ifs = CATALOG.formulations["ecmwf_ifs_saturation_water"]
    coefficients = tuple(
        dataclasses.replace(c, unit="HectoPA") if c.identifier == "e_0" else c
        for c in ifs.coefficients
    )
    assert signature(ifs) != signature(
        dataclasses.replace(ifs, coefficients=coefficients)
    )


def test_the_fingerprint_follows_names_and_the_scales_of_the_catalog() -> None:
    from nomogram.relations import fingerprint

    document = (
        SOURCE + exponential("f", 6.0) + exponential("g", 6.3) + relation("f", "g")
    )
    renamed = document.replace(
        '"C * exp(a * t)"\nfixed_units = true\noutput = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }\ninputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]\ncoefficients = { C = 6.0',
        '"K * exp(a * t)"\nfixed_units = true\noutput = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }\ninputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]\ncoefficients = { K = 6.0',
        1,
    )
    assert renamed != document
    prints = set()
    for loaded in (
        load_catalog([document]),
        load_catalog([renamed]),
        with_catalog(document),
    ):
        prints.add(fingerprint(loaded.relations["r"], loaded))
    assert len(prints) == 3


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


def test_points_of_an_interval_scale_have_no_ratio() -> None:
    def dew_point(key: str, c: float) -> str:
        return exponential(key, c).replace(
            'kind = "VapourPressure", unit = "HectoPA"',
            'kind = "DewPointTemperature", unit = "DEG_C"',
        )

    with pytest.raises(CatalogError, match="ratio of points of an interval scale"):
        load_catalog(
            [SOURCE + dew_point("f", 6.0) + dew_point("g", 6.3) + relation("f", "g")]
        )


def test_a_factor_names_coefficients_brought_into_the_subject_unit() -> None:
    pascals = exponential("p", 611.0).replace('unit = "HectoPA"', 'unit = "PA"')
    loaded = load_catalog(
        [SOURCE + pascals + exponential("g", 6.3) + relation("p", "g")]
    )
    found = verify(loaded.relations["r"], loaded)
    assert found.status == "proven"
    assert found.value == pytest.approx(611.0 / 630.0)
    assert found.detail is not None
    assert "the ratio of C of p to C of g (611.0 / 6.3, HectoPA brought into PA)" in (
        found.detail
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
    with pytest.raises(CatalogError, match="no factor converts these units"):
        load_catalog([SOURCE + kelvin + exponential("g", 6.3) + renamed])
