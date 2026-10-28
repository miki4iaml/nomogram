# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.dimensions`: units of coefficients.

Three levels: the whole catalog, edge cases written for the purpose, and
formulas generated at random. Local propagation and linear algebra must
always agree.
"""

import dataclasses
import math
import random
from fractions import Fraction

import pytest

from nomogram.catalog import catalog, load_catalog
from nomogram.dimensions import (
    DimensionError,
    _dimension,
    _linear,
    _propagate,
    _setup,
    infer_units,
    unit_text,
)
from nomogram.inversion import dew_point
from nomogram.model import Coefficient, Formulation, Variable
from nomogram.units import Q_, ureg

CATALOG = catalog()
WITH_COEFFICIENTS = [f for f in CATALOG.formulations.values() if f.coefficients]

#: Coefficients read as numerical values inside a logarithm: hidden, their
#: declared unit cannot come back (a pure number is as consistent).
NUMERICAL_VALUES = {("goff_gratch1946", "e_st"), ("goff_gratch1946_ice", "e_i0")}
#: Units declared because the expression does not determine them (the 10^3
#: of 10^3 - 1.005 S fixes the unit of 31.998; in 1 - a S / S_0, S_0 is 35
#: per mille, not the pure number 35): hidden, they cannot come back.
NEEDED = {
    ("dickson2007_total_molality", "S_1"),
    ("dickson2007_osmotic_coefficient_of_salinity", "S_1"),
    ("dickson2007_vapour_pressure", "S_1"),
    ("coare36_salinity_factor", "S_0"),
}


def make(
    expression: str,
    coefficients: dict[str, str | None],
    *,
    output: tuple[str, str] = ("e", "HectoPA"),
    inputs: tuple[tuple[str, str], ...] = (("t", "DEG_C"),),
    fixed_units: bool = True,
) -> Formulation:
    """A formulation written for a test, outside the catalog."""
    return Formulation(
        key="test",
        label="Test",
        output=Variable(output[0], "Unknown", output[1], "output"),
        inputs=tuple(Variable(i, "Unknown", u, "input") for i, u in inputs),
        coefficients=tuple(
            Coefficient(name, 1.5, unit, None) for name, unit in coefficients.items()
        ),
        constants=(),
        expression=expression,
        fixed_units=fixed_units,
        physical_domains=(),
        citations=(),
        note=None,
        matches=(),
    )


def propagated(formulation: Formulation) -> dict[str, dict[str, Fraction]]:
    """Dimensions found by local propagation alone."""
    context, constraints, _ = _setup(formulation)
    _propagate(context, constraints)
    return {
        name: _dimension(context.units[name])
        for name in context.unknown
        if name in context.units
    }


def assert_methods_agree(formulation: Formulation) -> None:
    linear = _linear(formulation)
    for name, dimension in propagated(formulation).items():
        assert linear[name] == dimension, (formulation.key, name)


# --- Level 1: the catalog -----------------------------------------------


@pytest.mark.parametrize("formulation", WITH_COEFFICIENTS, ids=lambda f: f.key)
def test_every_coefficient_of_the_catalog_has_a_unit(formulation: Formulation) -> None:
    units = infer_units(formulation)
    assert all(u.unit is not None for u in units.values())
    assert_methods_agree(formulation)
    # Propagation suffices for the whole catalog.
    assert set(propagated(formulation)) == {
        name for name, u in units.items() if u.origin == "inferred"
    }


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("sonntag1990_magnus", {"A": "", "B": "°C", "C": "hPa"}),
        ("buck1996", {"A": "", "B": "°C", "C": "hPa", "D": "°C"}),
        ("sonntag1990", {"a0": "K", "a1": "", "a2": "K⁻¹", "a3": "K⁻²", "a4": ""}),
        ("murphy_koop2005_ice", {"c0": "", "c1": "K", "c2": "", "c3": "K⁻¹"}),
        ("iapws_r14_08_sublimation", {"a1": "", "b1": "", "T_t": "K", "p_t": "Pa"}),
    ],
)
def test_units_found_for_known_forms(key: str, expected: dict[str, str]) -> None:
    units = CATALOG.formulations[key].coefficient_units
    assert {name: unit_text(units[name].unit) for name in expected} == expected


PI = """
[formulations.f]
label = "With pi"
expression = "a * pi * t"
fixed_units = true
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 2.0 }
"""


@pytest.mark.parametrize(
    ("unit", "text"),
    [
        # Products as the SI Brochure writes them: never two solidi.
        ("g * K / hPa / m ** 3", "g·K·hPa⁻¹·m⁻³"),
        ("1 / delta_degC ** 2 / hPa", "°C⁻²·hPa⁻¹"),
        # An exponent that is not whole, after a caret.
        ("mmHg / permille ** 1.5", "mmHg·‰^-1.5"),
        ("K ** -0.5", "K^-0.5"),
        # A unit of the catalog keeps its symbol.
        ("J / (kg * K)", "J/(kg·K)"),
    ],
)
def test_units_are_written_as_products(unit: str, text: str) -> None:
    assert unit_text(ureg.Unit(unit)) == text


def test_pi_is_a_pure_number_in_unit_inference() -> None:
    f = load_catalog([PI]).formulations["f"]
    assert unit_text(f.coefficient_units["a"].unit) == "hPa·°C⁻¹"
    assert f.evaluate(t=Q_(1, "degC")).to("hPa").magnitude == pytest.approx(2 * math.pi)


def test_a_composition_keeps_the_units_of_its_parts() -> None:
    # The molality and the osmotic coefficient are intermediate quantities
    # of Dickson et al. (2007): their units fix 31.998, 0.018 and the
    # coefficients of the osmotic coefficient, none of them declared.
    units = CATALOG.formulations["dickson2007_vapour_pressure"].coefficient_units
    assert {name: unit_text(units[name].unit) for name in ("c", "k", "c_0")} == {
        "c": "mol/kg",
        "k": "kg/mol",
        "c_0": "",
    }
    assert units["c"].origin == "inferred"
    assert units["c"].reason is not None
    assert "dickson2007_total_molality" in units["c"].reason


def test_units_satisfied_only_together_leave_the_coefficients_open() -> None:
    # hPa and Pa are distinct factors in a numerical value equation: no
    # unit makes A B P and A B p alike, so none is written.
    found = infer_units(
        make(
            "A * B * P + A * B * p",
            {"A": None, "B": None},
            output=("e", "HectoPA"),
            inputs=(("P", "HectoPA"), ("p", "PA")),
        )
    )
    assert (found["A"].unit, found["B"].unit) == (None, None)


def test_magnus_reasons_point_to_the_constraint() -> None:
    units = CATALOG.formulations["sonntag1990_magnus"].coefficient_units
    assert units["B"].reason == "B + t"
    assert units["B"].origin == "inferred"
    assert units["C"].reason is not None
    assert units["C"].reason.startswith("e_s = ")


@pytest.mark.parametrize("formulation", WITH_COEFFICIENTS, ids=lambda f: f.key)
def test_hidden_declared_units_come_back(formulation: Formulation) -> None:
    for index, coefficient in enumerate(formulation.coefficients):
        if coefficient.unit is None or (formulation.key, coefficient.identifier) in (
            NUMERICAL_VALUES | NEEDED
        ):
            continue
        hidden = list(formulation.coefficients)
        hidden[index] = dataclasses.replace(coefficient, unit=None)
        found = infer_units(
            dataclasses.replace(formulation, coefficients=tuple(hidden))
        )
        declared = formulation.coefficient_units[coefficient.identifier].unit
        assert found[coefficient.identifier].origin == "inferred"
        assert _dimension(found[coefficient.identifier].unit) == _dimension(declared)


def test_a_logarithm_reads_a_hidden_unit_as_a_numerical_value() -> None:
    gg = CATALOG.formulations["goff_gratch1946"]
    hidden = tuple(
        dataclasses.replace(c, unit=None) if c.identifier == "e_st" else c
        for c in gg.coefficients
    )
    found = infer_units(dataclasses.replace(gg, coefficients=hidden))
    assert found["e_st"].unit == ureg.dimensionless


@pytest.mark.parametrize("key", ["sonntag1990_magnus", "buck1981", "murray1967"])
def test_derived_formulations_get_units_too(key: str) -> None:
    inverse = dew_point(CATALOG.formulations[key])
    assert isinstance(inverse, Formulation)
    units = infer_units(inverse)
    assert unit_text(units["C"].unit) == "hPa"
    assert all(u.unit is not None for u in units.values())


# --- Level 2: edge cases ------------------------------------------------


def test_product_of_unknowns_stays_undetermined() -> None:
    formulation = make("A * B * t", {"A": None, "B": None})
    units = infer_units(formulation)
    assert {u.origin for u in units.values()} == {None}
    assert _linear(formulation) == {"A": None, "B": None}


def test_simultaneous_constraints_are_left_to_linear_algebra() -> None:
    # A*B and A*t/B are both pressures: A^2 t is a pressure squared.
    formulation = make("A * B + A * t / B", {"A": None, "B": None})
    assert propagated(formulation) == {}
    units = infer_units(formulation)
    assert units["A"].reason == "several constraints together"
    pressure = _dimension(ureg.Unit("hPa"))
    assert _dimension(units["A"].unit) == {
        **pressure,
        "[temperature]": Fraction(-1, 2),
    }
    assert _dimension(units["B"].unit) == {"[temperature]": Fraction(1, 2)}


def test_linear_algebra_keeps_the_units_a_numerical_value_equation_uses() -> None:
    # The value of A holds for hPa and degrees Celsius, not for Pa and K.
    fixed = infer_units(make("A * B + A * t / B", {"A": None, "B": None}))
    assert fixed["A"].unit == ureg.Unit("hPa") / ureg.Unit("delta_degC") ** 0.5
    assert fixed["B"].unit == ureg.Unit("delta_degC") ** 0.5
    # A quantity equation is free of units: SI base units serve.
    quantity = infer_units(
        make("A * B + A * t / B", {"A": None, "B": None}, fixed_units=False)
    )
    assert quantity["A"].unit == ureg.Unit("kg / m / s ** 2 / K ** 0.5")


def test_a_unit_the_written_units_do_not_fix_stays_undetermined() -> None:
    def formulation(fixed: bool) -> Formulation:
        return make(
            "1 - a * S / S_0",
            {"a": None, "S_0": None},
            output=("f", "UNITLESS"),
            inputs=(("S", "PERMILLE"),),
            fixed_units=fixed,
        )

    # Dimensionally both are pure numbers, but S_0 may be 35 per mille or
    # 0.035: with fixed units, a declaration is needed.
    assert {u.unit for u in infer_units(formulation(True)).values()} == {None}
    assert {u.origin for u in infer_units(formulation(True)).values()} == {None}
    assert all(
        u.unit == ureg.dimensionless for u in infer_units(formulation(False)).values()
    )


def test_roots_and_fractional_powers() -> None:
    units = infer_units(make("C * sqrt(t) + D * t ** 1.5", {"C": None, "D": None}))
    assert _dimension(units["C"].unit) == {
        **_dimension(ureg.Unit("hPa")),
        "[temperature]": Fraction(-1, 2),
    }
    assert _dimension(units["D"].unit)["[temperature]"] == Fraction(-3, 2)


def test_exponential_of_a_logarithm() -> None:
    units = infer_units(make("exp(A * ln(t / B))", {"A": None, "B": None}))
    assert unit_text(units["B"].unit) == "°C"
    assert units["A"].unit == ureg.dimensionless


def test_conflict_is_located() -> None:
    formulation = make(
        "C * exp(A * t / (B + t))", {"A": None, "B": "HectoPA", "C": None}
    )
    with pytest.raises(DimensionError, match=r"in B \+ t: .*hPa.*°C"):
        infer_units(formulation)


def test_contradiction_found_by_linear_algebra_only() -> None:
    # A*B is a pressure, and so is A*B*t: impossible, t is a temperature.
    formulation = make("A * B + A * B * t", {"A": None, "B": None})
    with pytest.raises(DimensionError, match="contradict"):
        infer_units(formulation)


def test_numerical_values_only_for_fixed_units() -> None:
    def formulation(fixed: bool) -> Formulation:
        return make(
            "a * ln(T)",
            {"a": None},
            output=("q", "UNITLESS"),
            inputs=(("T", "K"),),
            fixed_units=fixed,
        )

    assert infer_units(formulation(True))["a"].unit == ureg.dimensionless
    with pytest.raises(DimensionError, match="pure number is required"):
        infer_units(formulation(False))


@pytest.mark.parametrize(
    ("unit", "text"),
    [
        (None, ""),
        ("dimensionless", ""),
        ("delta_degC", "°C"),
        ("hPa", "hPa"),
        ("1/K", "K⁻¹"),
        ("1/K**2", "K⁻²"),
        ("1/hPa", "hPa⁻¹"),
    ],
)
def test_unit_text(unit: str | None, text: str) -> None:
    assert unit_text(None if unit is None else ureg.Unit(unit)) == text


# --- Level 3: formulas generated at random ------------------------------

VARIABLES = {"t": "delta_degC", "T": "K", "p": "Pa"}


class Generator:
    """Random consistent formulas, with the true unit of each coefficient."""

    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)
        self.truth: dict[str, object] = {}

    def coefficient(self, unit: object) -> str:
        name = f"c{len(self.truth)}"
        self.truth[name] = unit
        return name

    def expression(self, unit: object, depth: int) -> str:
        if depth == 0:
            choice = self.random.choice(["leaf", "variable"])
        else:
            choice = self.random.choices(
                ["leaf", "variable", "sum", "product", "power", "exponential"],
                weights=[1, 1, 3, 2, 2, 2],
            )[0]
        if choice == "leaf":
            return self.coefficient(unit)
        name = self.random.choice(sorted(VARIABLES))
        variable = ureg.Unit(VARIABLES[name])
        if choice == "variable":
            return f"{self.coefficient(unit / variable)} * {name}"
        if choice == "sum":
            return f"({self.expression(unit, depth - 1)} + {self.expression(unit, depth - 1)})"
        if choice == "product":
            # Two subexpressions sharing the unit: their unknowns are linked.
            left = self.expression(variable, depth - 1)
            return f"({left}) * ({self.expression(unit / variable, depth - 1)})"
        if choice == "power":
            power = self.random.choice([2, -1, 0.5])
            inner = self.expression(unit / variable**power, depth - 1)
            return f"{name} ** {power} * ({inner})"
        pure = self.expression(ureg.dimensionless, depth - 1)
        return f"{self.coefficient(unit)} * exp({pure})"


@pytest.mark.parametrize("seed", range(100))
def test_random_formulas_both_methods_agree_and_find_the_truth(seed: int) -> None:
    generator = Generator(seed)
    expression = generator.expression(ureg.Unit("hPa"), depth=4)
    names = sorted(generator.truth)
    formulation = make(
        expression,
        dict.fromkeys(names),
        inputs=(("t", "DEG_C"), ("T", "K"), ("p", "PA")),
    )
    used = {s.name for s in formulation.sympy_expression.free_symbols}
    if set(names) - used:
        pytest.skip("SymPy simplified a coefficient away")
    assert_methods_agree(formulation)
    linear = _linear(formulation)
    units = infer_units(formulation)
    for name in names:
        if linear[name] is not None:
            assert linear[name] == _dimension(generator.truth[name]), (expression, name)
            assert units[name].origin == "inferred"
