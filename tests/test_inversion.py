# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.inversion`: dew point by symbolic or numerical inversion."""

import math
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import catalog, load_catalog
from nomogram.comparison import compose
from nomogram.inversion import InversionError, NumericalInverse, dew_point, invert
from nomogram.model import Formulation, OutOfDomainError, ValidityWarning, Variable
from nomogram.units import Q_

CATALOG = catalog()
FORMULATIONS = CATALOG.formulations
SATURATION = CATALOG.formulations_of("SaturationVapourPressureOverWater")
MAGNUS = (
    "sonntag1990_magnus",
    "alduchov_eskridge1996",
    "buck1981_magnus",
    "bolton1980",
)
NUMERICAL = (
    "iapws_sr1_86",
    "sonntag1990",
    "hyland_wexler1983",
    "goff_gratch1946",
    "goff1957",
)


@pytest.mark.parametrize("key", MAGNUS)
def test_magnus_forms_invert_to_the_classical_dew_point_formula(key: str) -> None:
    inverse = dew_point(FORMULATIONS[key])
    assert isinstance(inverse, Formulation)
    assert inverse.expression == "B*ln(e/C)/(A - ln(e/C))"
    assert inverse.derivation is not None
    assert inverse.derivation.method == "symbolic inversion"
    assert inverse.derivation.source == key
    assert inverse.output.kind == "DewPointTemperature"
    assert inverse.references == FORMULATIONS[key].references


@pytest.mark.parametrize("key", NUMERICAL)
def test_formulations_without_closed_form_invert_numerically(key: str) -> None:
    inverse = dew_point(FORMULATIONS[key])
    assert isinstance(inverse, NumericalInverse)
    assert inverse.derivation.method == "numerical inversion"


@pytest.mark.parametrize("formulation", SATURATION, ids=lambda f: f.key)
def test_round_trip_through_the_dew_point(formulation: Formulation) -> None:
    temperatures = Q_(np.array([0.5, 20.0, 40.0]), "degC")
    arguments: dict[str, Any] = {formulation.inputs[0].identifier: temperatures}
    vapour = formulation.evaluate(outside="ignore", **arguments)
    back = dew_point(formulation).evaluate(e=vapour, outside="ignore")
    assert back.to("degC").magnitude == pytest.approx([0.5, 20.0, 40.0], abs=1e-6)


def test_iapws_inverse_reproduces_table_1_of_the_release() -> None:
    # 101325 Pa at 373.1243 K (IAPWS SR1-86(1992), Table 1).
    inverse = dew_point(FORMULATIONS["iapws_sr1_86"])
    result = inverse.evaluate(e=Q_(101325, "Pa")).to("K").magnitude
    assert result == pytest.approx(373.1243, abs=1e-4)


def test_buck_picks_the_right_branch_of_its_quadratic_solution() -> None:
    inverse = dew_point(FORMULATIONS["buck1981"])
    assert isinstance(inverse, Formulation)
    assert "sqrt(" in inverse.expression
    vapour = FORMULATIONS["buck1981"].evaluate(t=Q_(25, "degC"))
    assert inverse.evaluate(e=vapour).magnitude == pytest.approx(25.0, abs=1e-6)


def test_kelvin_formulation_gets_an_explicit_celsius_offset() -> None:
    inverse = dew_point(FORMULATIONS["murray1967"])
    assert isinstance(inverse, Formulation)
    offset = next(c for c in inverse.coefficients if c.identifier == "T_celsius_zero")
    assert offset.value == 273.15
    assert "SI Brochure" in (offset.note or "")


def test_validity_domain_is_carried_through_the_function() -> None:
    source = FORMULATIONS["alduchov_eskridge1996"]
    inverse = dew_point(source)
    assert isinstance(inverse, Formulation)
    low, high = inverse.domains[0].bounds["e"]
    ends = source.evaluate(t=Q_(np.array([-40.0, 50.0]), "degC")).magnitude
    assert (low, high) == pytest.approx(tuple(ends))
    assert "Carried by inversion" in (inverse.domains[0].criterion or "")
    assert math.isnan(inverse.evaluate(e=Q_(200, "hPa")).magnitude)


def test_scale_of_the_source_is_kept_and_undone() -> None:
    bolton = FORMULATIONS["bolton1980"]  # IPTS-68, inferred from the date
    inverse = dew_point(bolton)
    assert inverse.output.temperature_scale is bolton.inputs[0].temperature_scale
    numerical = dew_point(bolton, method="numerical")
    vapour = bolton.evaluate(t=Q_(20, "degC"))
    for candidate in (inverse, numerical):
        assert candidate.evaluate(e=vapour).magnitude == pytest.approx(20.0, abs=1e-6)
    # Without conversion, the IPTS-68 temperature comes out (0.005 K higher).
    raw = numerical.evaluate(e=vapour, scale="ignore").magnitude
    assert raw == pytest.approx(20.005, abs=1e-6)


def test_dew_point_from_temperature_and_relative_humidity() -> None:
    source = FORMULATIONS["alduchov_eskridge1996"]
    vapour = compose(
        FORMULATIONS["vapour_pressure_from_relative_humidity"], {"e_s": source}
    )
    dew = compose(dew_point(source), {"e": vapour})
    assert [v.identifier for v in dew.inputs] == ["RH", "t"]
    saturated = dew.evaluate(RH=Q_(100, "percent"), t=Q_(20, "degC"))
    assert saturated.magnitude == pytest.approx(20.0, abs=1e-9)
    half = dew.evaluate(RH=Q_(50, "percent"), t=Q_(20, "degC"))
    assert 9.2 < half.magnitude < 9.3


def test_numerical_inverse_outside_policies() -> None:
    inverse = dew_point(FORMULATIONS["iapws_sr1_86"])
    below = Q_(np.array([500.0, 2000.0]), "Pa")  # 500 Pa is below the triple point
    assert np.isnan(inverse.evaluate(e=below).magnitude[0])
    beyond = dew_point(FORMULATIONS["goff_gratch1946"], search=(200.0, 400.0))
    high = Q_(1100.0, "hPa")  # above 102 degC, outside the stated domain
    with pytest.raises(OutOfDomainError):
        beyond.evaluate(e=high, outside="raise")
    with pytest.warns(ValidityWarning):
        beyond.evaluate(e=high, outside="warn")
    assert not math.isnan(beyond.evaluate(e=high, outside="ignore").magnitude)
    assert math.isnan(beyond.evaluate(e=high).magnitude)
    with pytest.raises(TypeError, match="expected the input e"):
        inverse.evaluate(T=high)


DECREASING = """
[formulations.down]
label = "Decreasing test formulation"
expression = "a - b * t"
fixed_units = true
output = { identifier = "p", kind = "VapourPressure", unit = "PA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 1000.0, b = 10.0 }

[[formulations.down.domains]]
basis = "stated"
bounds = { t = [0.0, 50.0] }

[[formulations.down.domains]]
basis = "physical"
bounds = {}

[formulations.unsolvable]
label = "SymPy finds no algorithm"
expression = "exp(t) + t ** 2"
fixed_units = true
output = { identifier = "p", kind = "VapourPressure", unit = "PA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]

[[formulations.unsolvable.domains]]
basis = "stated"
bounds = { t = [0.5, 3.0] }

[formulations.square]
label = "Square, positive branch only"
expression = "t ** 2"
fixed_units = true
output = { identifier = "p", kind = "VapourPressure", unit = "PA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]

[[formulations.square.domains]]
basis = "stated"
bounds = { t = [-5.0, -1.0] }

[formulations.lambert]
label = "Needs the Lambert W function"
expression = "t * exp(t)"
fixed_units = true
output = { identifier = "p", kind = "VapourPressure", unit = "PA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]

[[formulations.lambert.domains]]
basis = "stated"
bounds = { t = [0.5, 3.0] }
"""
TESTS = load_catalog([DECREASING]).formulations
TEMPERATURE = Variable("t", "CelsiusTemperature", "DEG_C", "temperature")
PRESSURE = Variable("p", "VapourPressure", "PA", "pressure")


def test_decreasing_function_inverts_numerically() -> None:
    inverse = invert(
        TESTS["down"], "t", output=TEMPERATURE, input=PRESSURE, method="numerical"
    )
    assert inverse.evaluate(p=Q_(700.0, "Pa")).magnitude == pytest.approx(
        30.0, abs=1e-9
    )
    assert inverse.key == "down_inverse"
    assert inverse.label.startswith("Inverse of:")


@pytest.mark.parametrize("key", ["square", "lambert", "unsolvable"])
def test_no_usable_closed_form_falls_back_or_refuses(key: str) -> None:
    # x ** 2 on negative x: the solution found is the positive branch;
    # t * exp(t): the closed form needs a function outside the syntax.
    with pytest.raises(InversionError, match="no closed form"):
        invert(TESTS[key], "t", output=TEMPERATURE, input=PRESSURE, method="symbolic")
    fallback = invert(TESTS[key], "t", output=TEMPERATURE, input=PRESSURE)
    assert isinstance(fallback, NumericalInverse)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"formulation": "mass_concentration_ideal_gas"},
            "only formulations of one input",
        ),
        ({"solve_for": "T"}, "has no input 'T'"),
        ({"input_unit": "PA"}, "must keep the unit"),
        ({"output_unit": "K"}, "K does not apply to DewPointTemperature"),
        ({"output_unit": "DEG_F"}, "cannot express a result solved in DEG_C in DEG_F"),
        (
            {"output_kind": "TemperatureDifference", "output_unit": "K"},
            "temperature differences",
        ),
    ],
)
def test_invalid_inversions_are_refused(kwargs: dict[str, str], message: str) -> None:
    formulation = FORMULATIONS[kwargs.get("formulation", "sonntag1990_magnus")]
    output = Variable(
        "t_d",
        kwargs.get("output_kind", "DewPointTemperature"),
        kwargs.get("output_unit", "DEG_C"),
        "x",
    )
    vapour = Variable("e", "VapourPressure", kwargs.get("input_unit", "HectoPA"), "e")
    with pytest.raises(InversionError, match=message):
        invert(formulation, kwargs.get("solve_for", "t"), output=output, input=vapour)


def test_forced_symbolic_without_closed_form_is_refused() -> None:
    with pytest.raises(InversionError, match="no closed form"):
        dew_point(FORMULATIONS["sonntag1990"], method="symbolic")


def test_numerical_inversion_needs_a_search_interval() -> None:
    output = Variable("T_d", "ThermodynamicTemperature", "K", "x")
    vapour = Variable("e", "VapourPressure", "PA", "e")
    with pytest.raises(InversionError, match="give a search interval"):
        invert(FORMULATIONS["hyland_wexler1983"], "T", output=output, input=vapour)


def test_symbolic_inversion_into_kelvin() -> None:
    output = Variable("T_d", "ThermodynamicTemperature", "K", "Dew point, in kelvin")
    vapour = Variable("e", "VapourPressure", "HectoPA", "e")
    inverse = invert(
        FORMULATIONS["alduchov_eskridge1996"], "t", output=output, input=vapour
    )
    assert isinstance(inverse, Formulation)
    saturated = FORMULATIONS["alduchov_eskridge1996"].evaluate(t=Q_(20, "degC"))
    assert inverse.evaluate(e=saturated).magnitude == pytest.approx(293.15, abs=1e-9)


def test_numerical_inverse_composes() -> None:
    source = FORMULATIONS["iapws_sr1_86"]
    vapour = compose(
        FORMULATIONS["vapour_pressure_from_relative_humidity"], {"e_s": source}
    )
    dew = compose(dew_point(source), {"e": vapour})
    assert [v.identifier for v in dew.inputs] == ["RH", "T"]
    result = dew.evaluate(RH=Q_(100, "percent"), T=Q_(20, "degC"))
    assert result.magnitude == pytest.approx(20.0, abs=1e-6)


def test_its90_back_conversion_is_the_identity() -> None:
    its90 = CATALOG.temperature_scales["its90"]
    assert its90.to_its90([12.3]).tolist() == [12.3]


def test_only_domains_bounding_the_unknown_are_carried() -> None:
    inverse = invert(TESTS["down"], "t", output=TEMPERATURE, input=PRESSURE)
    assert isinstance(inverse, Formulation)
    assert inverse.expression == "(a - p)/b"
    assert [d.bounds for d in inverse.domains] == [{"p": (500.0, 1000.0)}]


@pytest.mark.parametrize("formulation", SATURATION, ids=lambda f: f.key)
def test_forward_of_the_inverse_gives_back_the_vapour_pressure(
    formulation: Formulation,
) -> None:
    # f(f^-1(e)) = e, on vapour pressures of ordinary air.
    arguments: dict[str, Any] = {
        formulation.inputs[0].identifier: Q_(np.array([2.0, 10.0, 30.0]), "degC")
    }
    vapour = formulation.evaluate(outside="ignore", **arguments).to("hPa")
    grid = Q_(np.linspace(vapour.magnitude[0], vapour.magnitude[-1], 9), "hPa")
    dew = dew_point(formulation).evaluate(e=grid, outside="ignore")
    again = formulation.evaluate(
        outside="ignore", **{formulation.inputs[0].identifier: dew}
    )
    assert again.to("hPa").magnitude == pytest.approx(grid.magnitude, rel=1e-9)
