# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Formulations derived by differentiation (nomogram.differentiation)."""

import numpy as np
import pytest
from bundled_catalog import with_families

from nomogram.catalog import Catalog, CatalogError, load_catalog
from nomogram.differentiation import derivative
from nomogram.expression import LATEX_COMMANDS, latex_commands
from nomogram.model import Variable
from nomogram.similarity import DerivationError
from nomogram.units import Q_

SOURCES = """
[references.src]
authors = "A."
title = "T"
status = "verified"

[formulations.profile]
label = "Quadratic temperature profile"
expression = "T_0 + a * H + b * H ** 2"
fixed_units = true
output = { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "Temperature" }
inputs = [ { identifier = "H", kind = "GeopotentialHeight", unit = "M", description = "Geopotential height" } ]
coefficients = { T_0 = 288.15, a = -0.0065, b = 1e-7 }

[[formulations.profile.citations]]
reference = "src"

[[formulations.profile.citations.domains]]
bounds = { H = [0.0, 20000.0] }
criterion = "0 to 20 km, as stated."

[formulations.layers]
label = "Two layers"
expression = "piecewise((T_0 + a * H, H <= 11000), (T_1, 11000 < H))"
fixed_units = true
output = { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "Temperature" }
inputs = [ { identifier = "H", kind = "GeopotentialHeight", unit = "M", description = "Geopotential height" } ]
coefficients = { T_0 = 288.15, a = -0.0065, T_1 = 216.65 }

[formulations.profile_in_km]
label = "Linear profile, height in kilometres"
expression = "T_0 + a * H"
fixed_units = true
output = { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "Temperature" }
inputs = [ { identifier = "H", kind = "GeopotentialHeight", unit = "KiloM", description = "Geopotential height" } ]
coefficients = { T_0 = 288.15, a = -6.5 }

[formulations.parabola]
label = "Parabola"
expression = "c * x ** 2"
fixed_units = true
output = { identifier = "z", kind = "Height", unit = "M", description = "Height" }
inputs = [ { identifier = "x", kind = "Length", unit = "M", description = "Distance" } ]
coefficients = { c = 0.25 }
"""

GRADIENT = """
[formulations.profile_gradient]
label = "Gradient of the profile"
derivative = { of = "profile", with_respect_to = "H" }
output = { identifier = "dT", kind = "TemperatureGradient", unit = "K-PER-M", description = "dT/dH" }

[formulations.parabola_curvature]
label = "Second derivative of the parabola"
derivative = { of = "parabola", with_respect_to = "x", order = 2 }
output = { identifier = "k", kind = "InverseLength", unit = "PER-M", description = "d2z/dx2" }

[formulations.layers_gradient]
label = "Gradient of the layers"
derivative = { of = "layers", with_respect_to = "H" }
output = { identifier = "dT", kind = "TemperatureGradient", unit = "K-PER-M", description = "dT/dH" }

[formulations.height_of_gradient]
label = "Height where the gradient takes a value"
expression = "dT(H=H) == g"
calls = { dT = "profile_gradient" }
fixed_units = true
output = { identifier = "H", kind = "GeopotentialHeight", unit = "M", description = "Geopotential height" }
inputs = [ { identifier = "g", kind = "TemperatureGradient", unit = "K-PER-M", description = "Gradient" } ]
"""

GRADIENT_OUTPUT = Variable("dT", "TemperatureGradient", "K-PER-M", "dT/dH")


def catalog_with(*documents: str) -> Catalog:
    return load_catalog([SOURCES, *documents])


CATALOG = catalog_with(GRADIENT)


def test_a_derivative_entry_differentiates_its_source() -> None:
    gradient = CATALOG.formulations["profile_gradient"]
    assert gradient.expression == "2*H*b + a"
    # The coefficients and constants its expression still uses, by name.
    assert [c.identifier for c in gradient.coefficients] == ["a", "b"]
    assert [v.identifier for v in gradient.inputs] == ["H"]
    assert gradient.derived
    assert gradient.derivation is not None
    assert gradient.derivation.method == "differentiation"
    assert gradient.derivation.source == "profile"
    assert (gradient.derivation.with_respect_to, gradient.derivation.order) == ("H", 1)
    assert gradient.note == "Derived by nomogram from profile: dT/dH."
    value = gradient.evaluate(H=Q_(1000, "m")).to("K/m").magnitude
    assert value == pytest.approx(-0.0065 + 2e-7 * 1000, rel=1e-12)


def test_a_derivative_keeps_the_domains_of_its_source() -> None:
    gradient = CATALOG.formulations["profile_gradient"]
    values = gradient.evaluate(H=Q_([10_000, 30_000], "m")).to("K/m").magnitude
    assert values[0] == pytest.approx(-0.0045)
    assert np.isnan(values[1])  # beyond the 20 km its source states


def test_a_formulation_by_pieces_is_differentiated_piece_by_piece() -> None:
    gradient = CATALOG.formulations["layers_gradient"]
    assert gradient.expression.startswith("piecewise((a, H <= 11000")
    values = gradient.evaluate(H=Q_([5000, 15_000], "m")).to("K/m").magnitude
    assert values.tolist() == pytest.approx([-0.0065, 0.0])
    # The branch 0 has every dimension: a keeps the unit inferred in its
    # source, K/m, not that of a pure number.
    unit = gradient.coefficient_units["a"]
    assert (f"{unit.unit:~}", unit.origin) == ("K / m", "inferred")


def test_a_derivative_of_order_two() -> None:
    curvature = CATALOG.formulations["parabola_curvature"]
    assert curvature.expression == "2*c"
    assert curvature.derivation is not None
    assert curvature.derivation.order == 2
    assert curvature.note == "Derived by nomogram from parabola: d^2 z/dx^2."
    # Its inputs stay those of its source, though the expression lost x.
    assert [v.identifier for v in curvature.inputs] == ["x"]
    assert curvature.evaluate(x=Q_(3, "m")).to("1/m").magnitude == pytest.approx(0.5)
    # Of order 2, K/m would be the wrong dimension: K/m2.
    with pytest.raises(DerivationError, match="a dimension K-PER-M does not have"):
        derivative(CATALOG.formulations["profile"], "H", GRADIENT_OUTPUT, order=2)


def test_an_implicit_equation_calls_a_derivative() -> None:
    height = CATALOG.formulations["height_of_gradient"]
    found = height.evaluate(g=Q_(-0.0045, "K/m")).to("m").magnitude
    assert found == pytest.approx((-0.0045 + 0.0065) / 2e-7, rel=1e-9)


def test_the_derivative_of_a_layer_of_the_iso_atmosphere_is_its_gradient() -> None:
    layer = with_families(("atmosphere",)).formulations["iso2533_temperature_layer"]
    output = Variable("dT", "VerticalTemperatureGradient", "K-PER-M", "dT/dH")
    gradient = derivative(layer, "H", output)
    assert gradient.expression == "beta"
    assert [v.identifier for v in gradient.inputs] == ["T_b", "beta", "H", "H_b"]
    assert gradient.key == "iso2533_temperature_layer_derivative_H"
    value = gradient.evaluate(
        T_b=Q_(288.15, "K"),
        beta=Q_(-0.0065, "K/m"),
        H=Q_(3000, "m"),
        H_b=Q_(0, "m"),
    )
    assert value.to("K/m").magnitude == pytest.approx(-0.0065)


def test_a_derivative_is_found_by_its_provenance_and_from_its_source() -> None:
    derived = set(CATALOG.search(provenance="derived").refs)
    assert "formulations.profile_gradient" in derived
    using = {e.key for e in CATALOG.used_by("formulations.profile")}
    assert "profile_gradient" in using
    used = {e.key for e in CATALOG.uses("formulations.profile_gradient")}
    assert "profile" in used


def test_a_derivative_is_shown_with_its_source() -> None:
    rendering = CATALOG.formulations["profile_gradient"].render()
    assert "Derivative of profile with respect to H." in rendering.markdown
    assert latex_commands(rendering.latex) <= LATEX_COMMANDS
    second = CATALOG.formulations["parabola_curvature"].render()
    assert "Derivative of order 2 of parabola with respect to x." in second.markdown


@pytest.mark.parametrize(
    ("key", "with_respect_to", "output", "order", "message"),
    [
        ("height_of_gradient", "g", GRADIENT_OUTPUT, 1, "implicit equation"),
        ("profile", "z", GRADIENT_OUTPUT, 1, "no input 'z'"),
        ("profile", "H", GRADIENT_OUTPUT, 0, "whole number of 1 or more"),
        ("profile", "H", GRADIENT_OUTPUT, True, "whole number of 1 or more"),
        (
            "profile",
            "H",
            Variable("dT", "ThermodynamicTemperature", "K", "x"),
            1,
            "a dimension K does not have",
        ),
        # In fixed units, a height in km gives K/km: never converted to K/m.
        ("profile_in_km", "H", GRADIENT_OUTPUT, 1, "holds only in its units"),
    ],
)
def test_derivative_refuses(
    key: str, with_respect_to: str, output: Variable, order: int, message: str
) -> None:
    with pytest.raises(DerivationError, match=message):
        derivative(CATALOG.formulations[key], with_respect_to, output, order=order)


def test_a_piecewise_definition_inside_an_expression_is_not_differentiated() -> None:
    document = """
[formulations.nested]
label = "Nested"
expression = "2 * piecewise((T_0 + a * H, H <= 11000), (T_0, 11000 < H))"
fixed_units = true
output = { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "T" }
inputs = [ { identifier = "H", kind = "GeopotentialHeight", unit = "M", description = "H" } ]
coefficients = { T_0 = 144.0, a = -0.003 }
"""
    nested = load_catalog([document]).formulations["nested"]
    with pytest.raises(DerivationError, match="inside an expression"):
        derivative(nested, "H", GRADIENT_OUTPUT)


ENTRY = """
[formulations.g]
label = "G"
{extra}
derivative = {derivative}
output = {{ identifier = "dT", kind = "TemperatureGradient", unit = "K-PER-M", description = "x" }}
"""


@pytest.mark.parametrize(
    ("derivative_table", "extra", "message"),
    [
        (
            '{ of = "profile", with_respect_to = "H" }',
            'expression = "a"',
            "a derivative takes expression from its source",
        ),
        ('{ of = "nope", with_respect_to = "H" }', "", "unknown formulation 'nope'"),
        (
            '{ of = "profile", with_respect_to = 1 }',
            "",
            "expected the identifier of an input",
        ),
        (
            '{ of = "profile", with_respect_to = "H", order = 0 }',
            "",
            r"formulations\.g\.derivative: profile: the order",
        ),
        (
            '{ of = "profile", with_respect_to = "H", step = 1 }',
            "",
            "unknown keys: step",
        ),
    ],
)
def test_invalid_derivative_entries_are_refused(
    derivative_table: str, extra: str, message: str
) -> None:
    document = ENTRY.format(extra=extra, derivative=derivative_table)
    with pytest.raises(CatalogError, match=message):
        catalog_with(document)


def test_a_derivative_entry_may_cite_a_source_that_prints_it() -> None:
    document = """
[formulations.cited_gradient]
label = "Gradient of the profile, as a source prints it"
derivative = { of = "profile", with_respect_to = "H" }
output = { identifier = "dT", kind = "TemperatureGradient", unit = "K-PER-M", description = "dT/dH" }
note = "Printed by the source."
keywords = ["gradient"]

[[formulations.cited_gradient.citations]]
reference = "src"
"""
    cited = catalog_with(document).formulations["cited_gradient"]
    assert not cited.derived
    assert cited.note == "Printed by the source."
    assert cited.keywords == ("gradient",)
    assert [c.reference for c in cited.citations] == ["src"]
