# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for expressions passed as arguments of the formulations called."""

import math

import numpy as np
import pytest
from bundled_catalog import bundled_documents
from matplotlib.mathtext import MathTextParser

from nomogram.catalog import Catalog, CatalogError, load_catalog
from nomogram.expression import LATEX_COMMANDS, latex_commands
from nomogram.inversion import invert
from nomogram.model import Formulation, Variable
from nomogram.units import Q_

SOURCE = """
[references.src]
authors = "A."
title = "T"
status = "verified"
"""

# A profile function of z/L, by pieces, with a domain its source states.
PSI = """
[formulations.psi]
label = "psi"
expression = "piecewise((2 * ln((1 + (1 - 16 * zeta) ** (1 / 2)) / 2), zeta < 0), (-5 * zeta, zeta >= 0))"
fixed_units = false
output = { identifier = "Psi", kind = "DimensionlessRatio", unit = "UNITLESS", description = "Psi" }
inputs = [{ identifier = "zeta", kind = "DimensionlessRatio", unit = "UNITLESS", description = "zeta" }]

[[formulations.psi.citations]]
reference = "src"

[[formulations.psi.citations.domains]]
bounds = { zeta = [-5, 1] }
"""

ROUGHNESS_AND_L = (
    '{ identifier = "z_0", kind = "Length", unit = "M", description = "z_0" }, '
    '{ identifier = "L", kind = "Length", unit = "M", description = "L" }'
)
LENGTHS = '{ identifier = "z", kind = "Length", unit = "M", description = "z" }, ' + (
    ROUGHNESS_AND_L
)


def profile(
    expression: str = "ln(z / z_0) - psi(zeta=z/L)",
    *,
    inputs: str = LENGTHS,
    extra: str = "",
    key: str = "prof",
    calls: str = '{ psi = "psi" }',
    fixed: bool = False,
) -> str:
    """A logarithmic profile with its stability correction, written for a test."""
    return f"""
[formulations.{key}]
label = "{key}"
expression = "{expression}"
calls = {calls}
fixed_units = {"true" if fixed else "false"}
output = {{ identifier = "F", kind = "DimensionlessRatio", unit = "UNITLESS", description = "F" }}
inputs = [{inputs}]
{extra}
[[formulations.{key}.citations]]
reference = "src"
"""


def load(*documents: str) -> Catalog:
    return load_catalog([SOURCE + PSI + "".join(documents)])


def _bundled() -> list[str]:
    """The core of the bundled catalog, which holds the temperature scales."""
    return bundled_documents("core")


def psi(zeta: float) -> float:
    if zeta < 0:
        return 2 * math.log((1 + math.sqrt(1 - 16 * zeta)) / 2)
    return -5 * zeta


Z, Z_0 = 10.0, 1e-4


def evaluate(
    f: Formulation, outside: str = "nan", **lengths: float | list[float]
) -> np.ndarray:
    values = {k: Q_(np.asarray(v, dtype=float), "m") for k, v in lengths.items()}
    result = f.evaluate(outside=outside, **values)  # type: ignore[arg-type]
    return np.asarray(result.magnitude)


# --- Values ---------------------------------------------------------------------


def test_an_expression_passed_to_a_call_gives_its_value() -> None:
    f = load(profile()).formulations["prof"]
    lengths = [-50.0, -10.0, 20.0, 100.0]
    values = evaluate(f, z=Z, z_0=Z_0, L=lengths)
    expected = [math.log(Z / Z_0) - psi(Z / L) for L in lengths]
    np.testing.assert_allclose(values, expected, rtol=1e-12)
    # Normalized as written by ast, substituted with its parentheses.
    (call,) = f.calls
    assert dict(call.arguments) == {"zeta": "z / L"}
    assert "16 * (z / L)" in f.expression
    # The condition of the formulation called bounds the expression passed.
    assert "z / L < 0" in f.expression


def test_the_domains_of_the_formulation_called_apply_to_the_value_passed() -> None:
    f = load(profile()).formulations["prof"]
    # z/L = 2 and -10 lie outside [-5, 1], stated for psi.
    values = evaluate(f, z=Z, z_0=Z_0, L=[5.0, -1.0, 20.0])
    assert math.isnan(values[0])
    assert math.isnan(values[1])
    assert values[2] == pytest.approx(math.log(Z / Z_0) - psi(0.5))
    ignored = evaluate(f, outside="ignore", z=Z, z_0=Z_0, L=5.0)
    assert float(ignored) == pytest.approx(math.log(Z / Z_0) - psi(2.0))
    with pytest.raises(ValueError, match="outside"):
        evaluate(f, outside="raise", z=Z, z_0=Z_0, L=5.0)


def test_an_argument_may_use_a_coefficient_of_the_caller() -> None:
    document = profile(
        "ln(z_r / z_0) - psi(zeta=z_r / L)",
        inputs=ROUGHNESS_AND_L,
        extra="coefficients = { z_r = 10 }",
        fixed=True,
    )
    f = load(document).formulations["prof"]
    # Its unit, a length, inferred through the input called.
    assert str(f.coefficient_units["z_r"].unit) == "meter"
    value = evaluate(f, z_0=Z_0, L=-20.0)
    assert float(value) == pytest.approx(math.log(Z / Z_0) - psi(-0.5))


def test_a_formulation_may_call_one_that_passes_an_expression() -> None:
    outer = f"""
[formulations.twice]
label = "twice"
expression = "2 * p(z=z, z_0=z_0, L=L)"
calls = {{ p = "prof" }}
fixed_units = false
output = {{ identifier = "G", kind = "DimensionlessRatio", unit = "UNITLESS", description = "G" }}
inputs = [{LENGTHS}]

[[formulations.twice.citations]]
reference = "src"
"""
    f = load(profile(), outer).formulations["twice"]
    values = evaluate(f, z=Z, z_0=Z_0, L=[-50.0, 5.0])
    assert values[0] == pytest.approx(2 * (math.log(Z / Z_0) - psi(-0.2)))
    # The domain of psi still applies, two calls down.
    assert math.isnan(values[1])


# --- Checks ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        # An input passed as such keeps the check of its kind.
        ("ln(z / z_0) - psi(zeta=z)", "z is Length, but psi takes zeta"),
        ("ln(z / z_0) - psi(zeta=z * L)", "but psi takes it in UNITLESS"),
        ("ln(z / z_0) - psi(zeta=z / M)", "an expression of the inputs"),
        ("ln(z / z_0) - psi(zeta=psi(zeta=z / L))", "takes no call"),
        ("ln(z / z_0) - psi(zeta=__import__)", "an expression of the inputs"),
        # A number alone would be folded into the expression called.
        ("ln(z / z_0 + 0 * L) - psi(zeta=0.1)", "is a number"),
        ("ln(z / z_0) - psi(zeta=piecewise((z / L, z > 1), (0, z <= 1)))", "condition"),
        ("ln(z / z_0) - psi(zeta=z / L + (z > L))", "condition"),
    ],
)
def test_malformed_expressions_passed_are_refused(
    expression: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load(profile(expression))


def test_an_expression_is_refused_toward_an_input_on_another_scale() -> None:
    called = """
[formulations.cel]
label = "cel"
expression = "2 * t"
fixed_units = true
output = { identifier = "y", kind = "CelsiusTemperature", unit = "DEG_C", description = "y" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]

[[formulations.cel.citations]]
reference = "src"
scales = { t = "ipts68" }
"""
    caller = """
[formulations.mean]
label = "mean"
expression = "c(t=(t_1 + t_2) / 2)"
calls = { c = "cel" }
fixed_units = true
output = { identifier = "y", kind = "CelsiusTemperature", unit = "DEG_C", description = "y" }
inputs = [
  { identifier = "t_1", kind = "CelsiusTemperature", unit = "DEG_C", description = "t_1" },
  { identifier = "t_2", kind = "CelsiusTemperature", unit = "DEG_C", description = "t_2" },
]

[[formulations.mean.citations]]
reference = "src"
"""
    with pytest.raises(CatalogError, match="on ipts68; pass it an input"):
        load_catalog([*_bundled(), SOURCE + called + caller])


# --- Display, search, inversion ---------------------------------------------------


def test_a_call_is_shown_with_the_expression_passed() -> None:
    f = load(profile()).formulations["prof"]
    rendering = f.render()
    assert r"\psi\left(\frac{z}{L}\right)" in rendering.latex
    assert latex_commands(rendering.latex) <= LATEX_COMMANDS
    MathTextParser("path").parse(rendering.mathtext)
    assert "Calls psi(zeta=z / L) with psi" in rendering.markdown


def test_a_formulation_passing_an_expression_is_linked_to_the_one_called() -> None:
    loaded = load(profile())
    assert "psi" in {e.key for e in loaded.uses("formulations.prof")}
    assert "prof" in {e.key for e in loaded.used_by("formulations.psi")}
    # Its inputs are its own: the kind of the input called is not one.
    f = loaded.formulations["prof"]
    assert {v.identifier for v in f.inputs} == {"z", "z_0", "L"}


def test_a_formulation_passing_an_expression_is_inverted_numerically() -> None:
    called = """
[formulations.g]
label = "g"
expression = "piecewise((x, x < 0), (2 * x, x >= 0))"
fixed_units = false
output = { identifier = "y", kind = "DimensionlessRatio", unit = "UNITLESS", description = "y" }
inputs = [{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }]

[[formulations.g.citations]]
reference = "src"

[[formulations.g.citations.domains]]
bounds = { x = [-10, 10] }
"""
    caller = """
[formulations.half]
label = "half"
expression = "g(x=u / 2)"
calls = { g = "g" }
fixed_units = false
output = { identifier = "v", kind = "DimensionlessRatio", unit = "UNITLESS", description = "v" }
inputs = [{ identifier = "u", kind = "DimensionlessRatio", unit = "UNITLESS", description = "u" }]

[[formulations.half.citations]]
reference = "src"
"""
    loaded = load_catalog([SOURCE + called + caller])
    output = Variable("u", "DimensionlessRatio", "UNITLESS", "u")
    given = Variable("v", "DimensionlessRatio", "UNITLESS", "v")
    inverse = invert(
        loaded.formulations["half"], "u", output=output, input=given, search=(-20, 20)
    )
    found = inverse.evaluate(v=Q_(np.array([-1.0, 1.0]), ""))
    np.testing.assert_allclose(np.asarray(found.magnitude), [-2.0, 1.0], rtol=1e-6)


# --- Units and scales of an expression passed --------------------------------------

LINE = """
[formulations.g]
label = "g"
expression = "2 * x"
fixed_units = {fixed}
output = {{ identifier = "y", kind = "Length", unit = "M", description = "y" }}
inputs = [{{ identifier = "x", kind = "Length", unit = "M", description = "x" }}]

[[formulations.g.citations]]
reference = "src"

[[formulations.g.citations.domains]]
bounds = {{ x = [0, 100] }}
"""


def line_caller(expression: str, inputs: str, *, fixed: bool = False) -> str:
    return f"""
[formulations.c]
label = "c"
expression = "{expression}"
calls = {{ g = "g" }}
fixed_units = {"true" if fixed else "false"}
output = {{ identifier = "y", kind = "Length", unit = "M", description = "y" }}
inputs = [{inputs}]

[[formulations.c.citations]]
reference = "src"
"""


KILOMETRES = (
    '{ identifier = "z_1", kind = "Length", unit = "KiloM", description = "z_1" }, '
    '{ identifier = "z_2", kind = "Length", unit = "KiloM", description = "z_2" }'
)
PRESSURES = (
    '{ identifier = "p", kind = "Pressure", unit = "PA", description = "p" }, '
    '{ identifier = "q", kind = "Pressure", unit = "PA", description = "q" }'
)


@pytest.mark.parametrize("fixed", [False, True])
def test_an_expression_passed_has_exactly_the_unit_it_feeds(fixed: bool) -> None:
    # A kilometre is no metre: the value is passed as a number.
    document = SOURCE + LINE.format(fixed=str(fixed).lower())
    with pytest.raises(CatalogError, match=r"z_1 \+ z_2 of g is in km, but g takes"):
        load_catalog(
            [document + line_caller("g(x=z_1 + z_2)", KILOMETRES, fixed=fixed)]
        )
    with pytest.raises(CatalogError, match="is in Pa, but g takes it in M"):
        load_catalog([document + line_caller("g(x=p + q)", PRESSURES, fixed=fixed)])


SATURATION = """
[formulations.e]
label = "e"
expression = "6.112 * exp(17.62 * t / (243.12 + t))"
fixed_units = true
output = { identifier = "e_s", kind = "VapourPressure", unit = "HectoPA", description = "e" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]

[[formulations.e.citations]]
reference = "src"
"""


def warm(expression: str, inputs: str) -> str:
    return f"""
[formulations.warm]
label = "warm"
expression = "{expression}"
calls = {{ e_s = "e" }}
fixed_units = true
output = {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }}
inputs = [{inputs}]

[[formulations.warm.citations]]
reference = "src"
"""


KELVINS = (
    '{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "T" }, '
    '{ identifier = "dT", kind = "TemperatureDifference", unit = "K", description = "dT" }'
)
PRESSURE = (
    '{ identifier = "p", kind = "Pressure", unit = "HectoPA", description = "p" }'
)
CELSIUS = (
    '{ identifier = "t_1", kind = "CelsiusTemperature", unit = "DEG_C", description = "t_1" }, '
    '{ identifier = "t_2", kind = "CelsiusTemperature", unit = "DEG_C", description = "t_2" }'
)


@pytest.mark.parametrize(
    ("expression", "inputs", "message"),
    [
        ("e_s(t=T + dT)", KELVINS, "is in K, but e takes it in DEG_C"),
        # Neither its kind nor its unit escapes the check.
        ("e_s(t=+p)", PRESSURE, "is in hPa, but e takes it in DEG_C"),
        ("e_s(t=(t_1 + t_2) / 2)", CELSIUS, "temperatures on an interval scale"),
    ],
)
def test_an_expression_feeds_degrees_celsius_with_degrees_celsius_only(
    expression: str, inputs: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([SOURCE + SATURATION + warm(expression, inputs)])


def on_scale(key: str, scale: str) -> str:
    return f"""
[formulations.{key}]
label = "{key}"
expression = "t"
fixed_units = true
output = {{ identifier = "y", kind = "CelsiusTemperature", unit = "DEG_C", description = "y" }}
inputs = [{{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }}]

[[formulations.{key}.citations]]
reference = "src"
scales = {{ t = "{scale}" }}
"""


def difference(expression: str) -> str:
    return f"""
[formulations.d]
label = "d"
expression = "{expression}"
calls = {{ a = "on_ipts68", b = "on_its90" }}
fixed_units = true
output = {{ identifier = "y", kind = "TemperatureDifference", unit = "K", description = "y" }}
inputs = [{{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }}]

[[formulations.d.citations]]
reference = "src"
"""


@pytest.mark.parametrize("expression", ["a(t=t) - b(t=t)", "a(t=t) - b(t=1 * t)"])
def test_an_input_written_in_an_expression_feeds_the_scale_of_the_input(
    expression: str,
) -> None:
    called = on_scale("on_ipts68", "ipts68") + on_scale("on_its90", "its90")
    with pytest.raises(CatalogError, match="feeds inputs on different scales"):
        load_catalog([*_bundled(), SOURCE + called + difference(expression)])


# --- The use the expressions are made for -----------------------------------------


def test_a_profile_between_two_heights_calls_its_function_twice() -> None:
    document = profile("ln(z / z_0) - psi(zeta=z / L) + psi(zeta=z_0 / L)")
    f = load(document).formulations["prof"]
    values = evaluate(f, z=Z, z_0=Z_0, L=[-50.0, 20.0, 5.0])
    expected = [math.log(Z / Z_0) - psi(Z / L) + psi(Z_0 / L) for L in (-50.0, 20.0)]
    np.testing.assert_allclose(values[:2], expected, rtol=1e-12)
    # z/L = 2 lies outside the domain of psi, z_0/L does not.
    assert math.isnan(values[2])
    # Two calls of one formulation, at two arguments.
    assert {p.computes for p in f.parts} == {"psi(zeta=z / L)", "psi(zeta=z_0 / L)"}


COMPOSED = """
[formulations.double]
label = "double"
expression = "2 * F"
fixed_units = false
output = { identifier = "G", kind = "DimensionlessRatio", unit = "UNITLESS", description = "G" }
inputs = [{ identifier = "F", kind = "DimensionlessRatio", unit = "UNITLESS", description = "F" }]

[[formulations.double.citations]]
reference = "src"

[formulations.both]
label = "both"
composition = { outer = "double", inner = { F = "prof" } }
output = { identifier = "G", kind = "DimensionlessRatio", unit = "UNITLESS", description = "G" }
"""


def test_a_composition_of_a_formulation_passing_an_expression() -> None:
    f = load(profile(), COMPOSED).formulations["both"]
    values = evaluate(f, z=Z, z_0=Z_0, L=[-50.0, 5.0])
    assert values[0] == pytest.approx(2 * (math.log(Z / Z_0) - psi(-0.2)))
    assert math.isnan(values[1])


def test_a_domain_stated_on_an_input_fed_by_an_expression_is_not_compared() -> None:
    from nomogram.relations import _beyond_parts

    domain = """
[[formulations.prof.citations.domains]]
bounds = { L = [-100, 100] }
"""
    f = load(profile() + domain).formulations["prof"]
    # psi states its domain on zeta, which z/L feeds: nothing to compare.
    assert _beyond_parts(f) == []


SUM = """
[formulations.h]
label = "h"
expression = "x + y"
fixed_units = false
output = { identifier = "s", kind = "Length", unit = "M", description = "s" }
inputs = [
  { identifier = "x", kind = "Length", unit = "M", description = "x" },
  { identifier = "y", kind = "Length", unit = "M", description = "y" },
]

[[formulations.h.citations]]
reference = "src"
"""


def test_a_call_may_pass_an_input_and_an_expression() -> None:
    lengths = (
        '{ identifier = "z", kind = "Length", unit = "M", description = "z" }, '
        '{ identifier = "z_0", kind = "Length", unit = "M", description = "z_0" }'
    )
    document = f"""
[formulations.k]
label = "k"
expression = "h(x=z, y=2 * z_0)"
calls = {{ h = "h" }}
fixed_units = false
output = {{ identifier = "s", kind = "Length", unit = "M", description = "s" }}
inputs = [{lengths}]

[[formulations.k.citations]]
reference = "src"
"""
    f = load_catalog([SOURCE + SUM + document]).formulations["k"]
    value = f.evaluate(z=Q_(10.0, "m"), z_0=Q_(1.0, "m"))
    assert float(value.magnitude) == pytest.approx(12.0)


def test_a_coefficient_of_contradictory_units_in_an_argument_is_refused() -> None:
    # ln wants z_r pure, the argument wants it in metres.
    document = profile(
        "ln(z_r) - psi(zeta=z_r / L)",
        inputs='{ identifier = "L", kind = "Length", unit = "M", description = "L" }',
        extra="coefficients = { z_r = 10 }",
        fixed=True,
    )
    with pytest.raises(CatalogError, match="units contradict"):
        load(document)


def test_a_scale_applies_only_to_the_inputs_of_its_kinds() -> None:
    mixed = (
        '{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }, '
        '{ identifier = "r", kind = "DimensionlessRatio", unit = "UNITLESS", description = "r" }'
    )
    called = on_scale("on_its90", "its90")
    document = f"""
[formulations.m]
label = "m"
expression = "b(t=t * r)"
calls = {{ b = "on_its90" }}
fixed_units = true
output = {{ identifier = "y", kind = "CelsiusTemperature", unit = "DEG_C", description = "y" }}
inputs = [{mixed}]

[[formulations.m.citations]]
reference = "src"
"""
    # r takes no temperature scale; t times r computes with degrees Celsius.
    with pytest.raises(CatalogError, match="temperatures on an interval scale"):
        load_catalog([*_bundled(), SOURCE + called + document])
