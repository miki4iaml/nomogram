# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.model`, on the bundled catalog."""

import dataclasses
import math

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.model import DomainBasis, OutOfDomainError, ValidityWarning
from nomogram.units import Q_

CATALOG = catalog()
SONNTAG = CATALOG.formulations["sonntag1990_magnus"]
IDEAL_GAS = CATALOG.formulations["mass_concentration_ideal_gas"]
SONNTAG_20C_HPA = 6.112 * math.exp(17.62 * 20 / (243.12 + 20))


@pytest.mark.parametrize(
    "temperature",
    [Q_(20, "degC"), Q_(293.15, "K"), Q_(68, "degF")],
)
def test_inputs_are_converted_to_the_unit_and_scale_of_the_formula(
    temperature: object,
) -> None:
    result = SONNTAG.evaluate(t=temperature)
    assert str(result.units) == "hectopascal"
    assert result.magnitude == pytest.approx(SONNTAG_20C_HPA)


def test_coefficients_are_never_converted() -> None:
    assert [c.value for c in SONNTAG.coefficients] == [17.62, 243.12, 6.112]
    assert SONNTAG.fixed_units
    assert SONNTAG.output_factor == 1.0


def test_evaluation_is_vectorised_and_nan_outside_the_stated_domain() -> None:
    result = SONNTAG.evaluate(t=Q_(np.array([-50.0, 0.0, 20.0, 100.0]), "degC"))
    assert np.isnan(result.magnitude[[0, 3]]).all()
    assert result.magnitude[1] == pytest.approx(6.112)


def test_outside_can_warn_and_compute() -> None:
    with pytest.warns(ValidityWarning, match="1 value"):
        result = SONNTAG.evaluate(t=Q_(100, "degC"), outside="warn")
    # Magnus overestimates by 2 to 3 % at 100 degC (IAPWS: 1014.18 hPa).
    assert 1.02 < result.magnitude / 1014.18 < 1.03


def test_outside_can_raise() -> None:
    with pytest.raises(OutOfDomainError, match="outside its stated domain"):
        SONNTAG.evaluate(t=Q_(-50, "degC"), outside="raise")


def test_outside_can_be_ignored_for_comparisons() -> None:
    result = SONNTAG.evaluate(t=Q_(-50, "degC"), outside="ignore")
    assert not math.isnan(result.magnitude)


def test_basis_selects_the_domains() -> None:
    # No physical domain is declared for Sonntag: nothing is masked.
    result = SONNTAG.evaluate(t=Q_(-50, "degC"), basis="physical")
    assert not math.isnan(result.magnitude)
    assert math.isnan(SONNTAG.evaluate(t=Q_(-50, "degC"), basis="all").magnitude)
    assert SONNTAG.domains[0].basis is DomainBasis.STATED


def test_quantity_equation_reproduces_the_iapws_value() -> None:
    # Saturation at 20 degC: e_s = 23.392 hPa (IAPWS) gives 17.290 g/m3.
    result = IDEAL_GAS.evaluate(
        RH=Q_(100, "percent"), e_s=Q_(23.392, "hPa"), T=Q_(20, "degC")
    )
    assert result.to("g/m^3").magnitude == pytest.approx(17.290, abs=0.001)
    assert not IDEAL_GAS.fixed_units


def test_missing_or_unexpected_inputs_are_reported() -> None:
    with pytest.raises(TypeError, match="missing inputs: t; unexpected: T"):
        SONNTAG.evaluate(T=Q_(20, "degC"))


def test_latex_in_a_notation() -> None:
    wmo = CATALOG.notations["wmo"]
    assert SONNTAG.latex(wmo).startswith(r"e_{\mathrm{w}} = C \times \exp\left(")
    assert SONNTAG.latex().startswith(r"e_{\mathrm{s}} = ")


def test_formulations_are_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        SONNTAG.label = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        SONNTAG.domains[0].bounds["t"] = (0.0, 1.0)  # type: ignore[index]
