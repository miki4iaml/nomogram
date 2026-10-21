# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for composed formulations: catalog entries built from others."""

from collections.abc import Mapping
from typing import Any

import numpy as np
import pytest
import sympy

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.comparison import Composition, compose
from nomogram.inversion import invert
from nomogram.model import Basis, Formulation, Variable
from nomogram.relations import report
from nomogram.units import Q_

CATALOG = catalog()

PARTS = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[constants.g1]
identifier = "g"
value = 1.5
unit = "UNITLESS"
description = "A constant"
reference = "src"

[constants.g2]
identifier = "g"
value = 2.0
unit = "UNITLESS"
description = "Another value of it"
reference = "src"

[formulations.outer]
label = "Outer"
expression = "k * e"
fixed_units = false
output = { identifier = "y", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [
  { identifier = "k", kind = "DimensionlessRatio", unit = "UNITLESS", description = "factor" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "pressure" },
]
domains = [{ bounds = { e = [0.0, 1000.0] } }, { bounds = { k = [0.5, 2.0] } }]

[formulations.pressure]
label = "Pressure"
expression = "a * exp(b * t)"
fixed_units = true
output = { identifier = "e_s", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 6.0, b = 0.07 }
domains = [{ bounds = { t = [-100.0, 100.0] } }]

[formulations.factor]
label = "Factor"
expression = "1 + c * t"
fixed_units = true
output = { identifier = "f", kind = "DimensionlessRatio", unit = "UNITLESS", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { c = 1e-3 }
"""

BOTH = """
[formulations.both]
label = "Both"
composition = { outer = "outer", inner = { k = "factor", e = "pressure" } }
citations = [{ reference = "src", domains = [{ bounds = { t = [-40.0, 50.0] } }] }]
"""

HALF = """
[formulations.half]
label = "Half"
composition = { outer = "outer", inner = { e = "pressure" } }
"""


def test_a_composition_substitutes_the_expressions() -> None:
    both = load_catalog([PARTS, BOTH]).formulations["both"]
    assert both.expression == "(1 + c * t) * (a * exp(b * t))"
    symbols = {s.name: s for s in both.sympy_expression.free_symbols}
    a, b, c, t = (symbols[n] for n in "abct")
    assert (
        sympy.simplify(both.sympy_expression - (1 + c * t) * a * sympy.exp(b * t)) == 0
    )
    assert [v.identifier for v in both.inputs] == ["t"]
    assert [c.identifier for c in both.coefficients] == ["c", "a", "b"]
    assert both.fixed_units
    assert both.output.kind == "VapourPressure"
    assert both.derivation is not None
    assert (both.derivation.source, both.derivation.method) == ("outer", "composition")
    assert dict(both.derivation.parts) == {"k": "factor", "e": "pressure"}
    assert both.coefficient_units["c"].unit == "1 / delta_degree_Celsius"


def test_a_composition_evaluates_as_the_chain() -> None:
    built = load_catalog([PARTS, BOTH])
    f = built.formulations
    chain = compose(f["outer"], {"k": f["factor"], "e": f["pressure"]})
    t = Q_(np.linspace(-40.0, 50.0, 19), "degC")
    expected = chain.evaluate(t=t).to("hPa").magnitude
    assert f["both"].evaluate(t=t).to("hPa").magnitude == pytest.approx(expected)
    outside = f["both"].evaluate(t=Q_(np.array([-50.0, 60.0]), "degC"))
    assert np.isnan(outside.magnitude).all()


def test_physical_domains_travel_with_their_inputs() -> None:
    both = load_catalog([PARTS, BOTH]).formulations["both"]
    assert [dict(d.bounds) for d in both.physical_domains] == [{"t": (-100.0, 100.0)}]
    half = load_catalog([PARTS, HALF]).formulations["half"]
    assert [v.identifier for v in half.inputs] == ["k", "t"]
    assert [dict(d.bounds) for d in half.physical_domains] == [
        {"k": (0.5, 2.0)},
        {"t": (-100.0, 100.0)},
    ]


def test_a_composition_may_use_another_one_written_after_it() -> None:
    chain = """
[formulations.chain]
label = "Chain"
composition = { outer = "outer", inner = { e = "half" } }
"""
    f = load_catalog([PARTS, chain, HALF]).formulations
    assert list(f)[-2:] == ["chain", "half"]
    assert [v.identifier for v in f["chain"].inputs] == ["k", "t"]
    k, t = Q_(1.5, ""), Q_(20.0, "degC")
    assert f["chain"].evaluate(k=k, t=t).magnitude == pytest.approx(
        1.5 * f["half"].evaluate(k=k, t=t).magnitude
    )


def test_bind_renames_an_input_of_an_inner_formulation() -> None:
    theta = """
[formulations.factor_theta]
label = "Factor of theta"
expression = "1 + c * theta"
fixed_units = true
output = { identifier = "f", kind = "DimensionlessRatio", unit = "UNITLESS", description = "out" }
inputs = [{ identifier = "theta", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { c = 2e-3 }

[formulations.bound]
label = "Bound"
composition = { outer = "outer", inner = { k = "factor_theta", e = "pressure" }, bind = { theta = "t" } }
"""
    bound = load_catalog([PARTS, theta]).formulations["bound"]
    assert bound.expression == "(1 + c * t) * (a * exp(b * t))"
    assert [v.identifier for v in bound.inputs] == ["t"]


def test_a_quantity_equation_keeps_its_unit_in_a_fixed_composition() -> None:
    pascal = """
[formulations.outer_pa]
label = "Outer in pascals"
expression = "k * e"
fixed_units = false
output = { identifier = "y", kind = "VapourPressure", unit = "PA", description = "out" }
inputs = [
  { identifier = "k", kind = "DimensionlessRatio", unit = "UNITLESS", description = "factor" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "pressure" },
]

[formulations.scaled]
label = "Scaled"
composition = { outer = "outer_pa", inner = { e = "pressure" } }
"""
    f = load_catalog([PARTS, pascal]).formulations
    assert f["scaled"].expression == "100.0 * (k * (a * exp(b * t)))"
    k, t = Q_(1.5, ""), Q_(20.0, "degC")
    chain = compose(f["outer_pa"], {"e": f["pressure"]})
    assert f["scaled"].evaluate(k=k, t=t).to("Pa").magnitude == pytest.approx(
        chain.evaluate(k=k, t=t).to("Pa").magnitude
    )


def test_a_part_reached_twice_is_one_part() -> None:
    # The ratio feeds the outer formulation directly and through the factor:
    # its coefficient q is one coefficient, as in Dickson et al. (2007).
    twice = """
[formulations.ratio]
label = "Ratio"
expression = "q * t"
fixed_units = true
output = { identifier = "r", kind = "DimensionlessRatio", unit = "UNITLESS", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { q = 0.01 }

[formulations.of_ratio]
label = "Of the ratio"
expression = "1 + s * r"
fixed_units = true
output = { identifier = "f", kind = "DimensionlessRatio", unit = "UNITLESS", description = "out" }
inputs = [{ identifier = "r", kind = "DimensionlessRatio", unit = "UNITLESS", description = "in" }]
coefficients = { s = 0.5 }

[formulations.of_t]
label = "Of t"
composition = { outer = "of_ratio", inner = { r = "ratio" } }

[formulations.outer_two]
label = "Outer of two"
expression = "f * r * e"
fixed_units = false
output = { identifier = "y", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [
  { identifier = "f", kind = "DimensionlessRatio", unit = "UNITLESS", description = "f" },
  { identifier = "r", kind = "DimensionlessRatio", unit = "UNITLESS", description = "r" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" },
]

[formulations.twice]
label = "Twice"
composition = { outer = "outer_two", inner = { f = "of_t", r = "ratio", e = "pressure" } }
"""
    built = load_catalog([PARTS, twice]).formulations
    found = built["twice"]
    assert sorted(c.identifier for c in found.coefficients) == ["a", "b", "q", "s"]
    t = Q_(10.0, "degC")
    r = built["ratio"].evaluate(t=t)
    chain = (
        built["of_ratio"].evaluate(r=r).magnitude
        * r.magnitude
        * built["pressure"].evaluate(t=t).magnitude
    )
    assert found.evaluate(t=t).magnitude == pytest.approx(chain)


def test_parts_may_share_a_constant() -> None:
    shared = """
[formulations.outer_g]
label = "Outer with g"
expression = "g * k * e"
fixed_units = false
constants = ["g1"]
output = { identifier = "y", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [
  { identifier = "k", kind = "DimensionlessRatio", unit = "UNITLESS", description = "factor" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "pressure" },
]

[formulations.factor_g{n}]
label = "Factor with g"
expression = "g + c * t"
fixed_units = true
constants = ["g{n}"]
output = { identifier = "f", kind = "DimensionlessRatio", unit = "UNITLESS", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { c = 1e-3 }

[formulations.with_g]
label = "With g"
composition = { outer = "outer_g", inner = { k = "factor_g{n}" } }
"""
    with_g = load_catalog([PARTS, shared.replace("{n}", "1")]).formulations["with_g"]
    assert [k.key for k in with_g.constants] == ["g1"]
    with pytest.raises(CatalogError, match="constant g is g1 in one part and g2"):
        load_catalog([PARTS, shared.replace("{n}", "2")])


COMPOSED = """
[formulations.x]
label = "X"
composition = {composition}
{extra}
"""

PRESSURE_PA = """
[formulations.pressure_pa]
label = "Pressure in pascals"
expression = "a * exp(b * t)"
fixed_units = true
output = { identifier = "e_s", kind = "VapourPressure", unit = "PA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 600.0, b = 0.07 }

[formulations.factor_kelvin]
label = "Factor of a thermodynamic temperature"
expression = "u * t"
fixed_units = true
output = { identifier = "f", kind = "DimensionlessRatio", unit = "UNITLESS", description = "out" }
inputs = [{ identifier = "t", kind = "ThermodynamicTemperature", unit = "K", description = "in" }]
coefficients = { u = 0.004 }

[formulations.factor_a]
label = "Factor with a coefficient a"
expression = "1 + a * t"
fixed_units = true
output = { identifier = "f", kind = "DimensionlessRatio", unit = "UNITLESS", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 1e-3 }
"""

BOTH_PARTS = '{ outer = "outer", inner = { k = "factor", e = "pressure" } }'


@pytest.mark.parametrize(
    ("composition", "extra", "message"),
    [
        (BOTH_PARTS, 'expression = "k"', "takes expression from its parts"),
        ('"outer"', "", "composition: expected a table"),
        (
            '{ outer = "nope", inner = { e = "pressure" } }',
            "",
            "unknown formulation 'nope'",
        ),
        ('{ outer = "outer", inner = {} }', "", "expected a table of input identifier"),
        (
            '{ outer = "outer", inner = { e = "nope" } }',
            "",
            "unknown formulation 'nope'",
        ),
        (
            '{ outer = "outer", inner = { z = "pressure" } }',
            "",
            "outer has no input 'z'",
        ),
        (
            '{ outer = "outer", inner = { k = "pressure" } }',
            "",
            "pressure computes VapourPressure, but k is DimensionlessRatio",
        ),
        (
            '{ outer = "outer", inner = { e = "pressure_pa" } }',
            "",
            "pressure_pa gives PA, but e is in HectoPA",
        ),
        (
            '{ outer = "outer", inner = { e = "pressure" }, bind = { zz = "t" } }',
            "",
            "'zz' is not an input of an inner formulation",
        ),
        (
            '{ outer = "outer", inner = { e = "pressure" }, bind = { t = "e" } }',
            "",
            "'e' is computed by pressure",
        ),
        (
            '{ outer = "outer", inner = { k = "factor_kelvin", e = "pressure" } }',
            "",
            "input t of pressure differs in kind, unit or scale",
        ),
        (
            '{ outer = "outer", inner = { k = "factor_a", e = "pressure" } }',
            "",
            "coefficient a in both factor_a and pressure",
        ),
        (
            BOTH_PARTS,
            'output = { identifier = "w", kind = "Pressure", unit = "HectoPA", description = "w" }',
            "Pressure is not a specialization of VapourPressure",
        ),
        (
            BOTH_PARTS,
            'output = { identifier = "w", kind = "VapourPressure", unit = "PA", description = "w" }',
            "the unit is that of outer's output, HectoPA",
        ),
        (BOTH_PARTS, 'note = 1\nunknown = "x"', "unknown keys: unknown"),
    ],
)
def test_invalid_compositions_are_refused(
    composition: str, extra: str, message: str
) -> None:
    document = COMPOSED.format(composition=composition, extra=extra)
    with pytest.raises(CatalogError, match=message):
        load_catalog([PARTS, PRESSURE_PA, document])


def test_a_cycle_of_compositions_is_refused() -> None:
    cycle = """
[formulations.p]
label = "P"
composition = { outer = "q", inner = { e = "pressure" } }

[formulations.q]
label = "Q"
composition = { outer = "outer", inner = { e = "p" } }
"""
    with pytest.raises(CatalogError, match="compositions form a cycle: p -> q -> p"):
        load_catalog([PARTS, cycle])


def test_a_composition_identical_to_a_written_formulation_is_refused() -> None:
    written = """
[formulations.written]
label = "Written"
expression = "(1 + c * t) * a * exp(b * t)"
fixed_units = true
output = { identifier = "y", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 6.0, b = 0.07, c = 1e-3 }
"""
    with pytest.raises(CatalogError, match="identical to formulations"):
        load_catalog([PARTS, written, BOTH])


def test_parts_come_from_the_family_or_its_requires() -> None:
    base = '[catalog]\nname = "base"\nformat = 2\n' + PARTS
    user = '[catalog]\nname = "user"\nformat = 2\n{requires}\n' + HALF
    with pytest.raises(CatalogError, match=r"half uses formulations\.outer"):
        load_catalog([base, user.replace("{requires}", "")])
    built = load_catalog([base, user.replace("{requires}", 'requires = ["base"]')])
    assert built.formulations["half"].family == "user"


def test_the_legend_says_what_a_formulation_is_composed_of() -> None:
    both = load_catalog([PARTS, BOTH]).formulations["both"]
    assert "Composed of factor (k) and pressure (e) in outer." in both.render().markdown
    assert (
        "Composed of"
        not in load_catalog([PARTS]).formulations["pressure"].render().markdown
    )


def test_a_composition_can_be_inverted() -> None:
    both = load_catalog([PARTS, BOTH]).formulations["both"]
    inverse = invert(
        both,
        "t",
        output=Variable("t", "CelsiusTemperature", "DEG_C", "Celsius temperature"),
        input=Variable("y", "VapourPressure", "HectoPA", "Vapour pressure"),
        method="numerical",
    )
    y = both.evaluate(t=Q_(20.0, "degC"))
    assert inverse.evaluate(y=y).to("degC").magnitude == pytest.approx(20.0)


# --- ITU-R P.453, equation 9 ------------------------------------------


@pytest.mark.parametrize(
    ("key", "factor", "pure", "bounds"),
    [
        ("itu_r_p453_es_water", "itu_r_p453_ef_water", "buck1996", (-40.0, 50.0)),
        ("itu_r_p453_es_ice", "itu_r_p453_ef_ice", "buck1996_ice", (-80.0, 0.0)),
    ],
)
def test_itu_r_p453_equation_9_is_the_enhancement_factor_times_buck_1996(
    key: str, factor: str, pure: str, bounds: tuple[float, float]
) -> None:
    f = CATALOG.formulations
    es = f[key]
    assert es.derivation is not None
    assert dict(es.derivation.parts) == {"EF": factor, "e_s": pure}
    assert [v.identifier for v in es.inputs] == ["p", "t"]
    assert es.citations[0].reference == "itu_r_p453_14"
    assert es.citations[0].equation == "9"
    assert dict(es.citations[0].domains[0].bounds) == {"t": bounds}
    t = Q_(np.linspace(*bounds, 13), "degC")
    p = Q_(1013.25, "hPa")
    chain = compose(
        f["saturation_vapour_pressure_in_moist_air"], {"EF": f[factor], "e_s": f[pure]}
    )
    assert es.evaluate(p=p, t=t).magnitude == pytest.approx(
        chain.evaluate(p=p, t=t).magnitude
    )


def test_itu_r_p453_enhancement_factor_by_hand() -> None:
    # EF_water = 1 + 1e-4 [7.2 + P (0.0320 + 5.9e-6 t^2)], P.453-14 eq. 9.
    ef = CATALOG.formulations["itu_r_p453_ef_water"]
    value = ef.evaluate(p=Q_(1000.0, "hPa"), t=Q_(10.0, "degC")).magnitude
    assert value == pytest.approx(1 + 1e-4 * (7.2 + 1000.0 * (0.0320 + 5.9e-6 * 100.0)))
    kind = CATALOG.kinds["EnhancementFactor"]
    assert kind.specialization_of == "DimensionlessRatio"


def test_itu_r_p453_notation() -> None:
    es = CATALOG.formulations["itu_r_p453_es_water"]
    latex = es.latex(es.citations[0].notation)
    assert latex.startswith("e_s = a \\times")
    assert "P \\times" in latex


# --- Validity domains: never more permissive than the chain -----------

DOMAINS = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[formulations.outer]
label = "Outer"
expression = "k * e"
fixed_units = false
output = { identifier = "y", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [
  { identifier = "k", kind = "DimensionlessRatio", unit = "UNITLESS", description = "factor" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "pressure" },
]
domains = [{ bounds = { e = [0.0, 100.0] } }]
{outer_citations}

[formulations.pressure]
label = "Pressure"
expression = "a * exp(b * t)"
fixed_units = true
output = { identifier = "e_s", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 6.0, b = 0.07 }
domains = [{ bounds = { t = [-100.0, 100.0] } }]
citations = [{ reference = "src", domains = [{ bounds = { t = [-40.0, 50.0] } }] }]

[formulations.factor]
label = "Factor"
expression = "1 + c * t"
fixed_units = true
output = { identifier = "f", kind = "DimensionlessRatio", unit = "UNITLESS", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { c = 1e-3 }
citations = [{ reference = "src", domains = [{ bounds = { t = [-20.0, 80.0] } }] }]

[formulations.half]
label = "Half"
composition = { outer = "outer", inner = { e = "pressure" } }

[formulations.nested]
label = "Nested"
composition = { outer = "outer", inner = { k = "factor", e = "half" } }
"""

BOTH_DOMAINS = """
[formulations.both]
label = "Both"
composition = { outer = "outer", inner = { k = "factor", e = "pressure" } }
"""

OWN = """
[formulations.own]
label = "With a domain of its own"
composition = { outer = "outer", inner = { k = "factor", e = "pressure" } }
citations = [
  { reference = "src", equation = "1" },
  { reference = "src", equation = "2", domains = [{ bounds = { t = [-60.0, 60.0] } }] },
]
"""

GRID = Q_(np.arange(-110.0, 110.5, 0.5), "degC")


def valid(values: Any) -> tuple[float, float]:
    kept = GRID.magnitude[~np.isnan(np.asarray(values.magnitude))]
    return float(kept.min()), float(kept.max())


def domains(extra: str, outer_citations: str = "") -> Mapping[str, Formulation]:
    document = DOMAINS.replace("{outer_citations}", outer_citations)
    return load_catalog([document, extra]).formulations


@pytest.mark.parametrize(
    ("basis", "expected"),
    [("stated", (-20.0, 50.0)), ("all", (-20.0, 40.0)), ("physical", (-100.0, 40.0))],
)
def test_without_a_domain_of_its_own_a_composition_is_the_chain(
    basis: Basis, expected: tuple[float, float]
) -> None:
    # Stated: [-40, 50] and [-20, 80]; physical: t in [-100, 100] and
    # e = 6 exp(0.07 t) <= 100 hPa, that is t <= 40.19 degC.
    f = domains(BOTH_DOMAINS)
    chain = compose(f["outer"], {"k": f["factor"], "e": f["pressure"]})
    half = compose(f["outer"], {"e": f["pressure"]})
    nested_chain = compose(f["outer"], {"k": f["factor"], "e": half})
    cases: list[tuple[Formulation, Composition, dict[str, Any]]] = [
        (f["both"], chain, {"t": GRID}),
        (f["nested"], nested_chain, {"k": Q_(1.0, ""), "t": GRID}),
    ]
    for composed, reference, inputs in cases:
        assert valid(composed.evaluate(basis=basis, **inputs)) == expected
        assert valid(reference.evaluate(basis=basis, **inputs)) == expected


@pytest.mark.parametrize(
    ("basis", "expected"),
    [("stated", (-60.0, 60.0)), ("all", (-60.0, 40.0)), ("physical", (-100.0, 40.0))],
)
def test_a_domain_of_its_own_replaces_the_stated_domains_of_the_parts(
    basis: Basis, expected: tuple[float, float]
) -> None:
    own = domains(OWN)["own"]
    assert valid(own.evaluate(basis=basis, t=GRID)) == expected


OWN_K = """
[formulations.own_k]
label = "Factor only, with a domain of its own"
composition = { outer = "outer", inner = { k = "factor" } }
citations = [{ reference = "src", domains = [{ bounds = { t = [-10.0, 60.0] } }] }]
"""


def test_the_report_points_out_a_domain_beyond_those_of_the_parts() -> None:
    outer_citations = (
        'citations = [{ reference = "src", domains = '
        "[{ bounds = { e = [0.0, 90.0], k = [0.5, 2.0] } }] }]"
    )
    document = DOMAINS.replace("{outer_citations}", outer_citations)
    built = load_catalog([document, OWN, OWN_K])
    own, own_k, nested = (
        report(built, [key], budget=100) for key in ("own", "own_k", "nested")
    )
    assert (
        "stated domain beyond that of factor on t: [-60, 60] against [-20, 80]" in own
    )
    assert (
        "stated domain beyond that of pressure on t: [-60, 60] against [-40, 50]" in own
    )
    assert "domain stated for outer on e, a computed value, replaced" in own
    assert "domain stated for outer on k, a computed value, replaced" in own_k
    assert "beyond that of factor" not in own_k
    assert (
        "stated domain beyond that of outer on e: [-inf, inf] against [0, 90]" in own_k
    )
    assert "domain" not in nested
