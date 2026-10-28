# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the saturation vapour pressures of Ambaum (2020)."""

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
R_V, T_0, L_0 = 461.52, 273.16, 2.501e6


def pascal(key: str, kelvin: object) -> np.ndarray:
    value = F[key].evaluate(T=Q_(kelvin, "K"), outside="ignore")
    return np.asarray(value.to("Pa").magnitude, dtype=float)


@pytest.mark.parametrize(
    "key", ["ambaum2020", "ambaum2020_constant_latent_heat", "ambaum2020_ice"]
)
def test_at_the_triple_point_the_pressure_is_e_0(key: str) -> None:
    assert pascal(key, T_0) == pytest.approx(611.655)


@pytest.mark.parametrize(
    ("key", "delta_c", "latent"),
    [
        ("ambaum2020", 2180.0, L_0),
        ("ambaum2020_constant_latent_heat", 0.0, L_0),
        ("ambaum2020_ice", 212.0, L_0 + 0.3334e6),
    ],
)
def test_the_equations_satisfy_clausius_clapeyron(
    key: str, delta_c: float, latent: float
) -> None:
    # d ln e / dT = L(T) / (R_v T^2), with L linear in temperature.
    kelvin = np.array([250.0, 270.0, 290.0, 310.0])
    step = 1e-3
    slope = (
        np.log(pascal(key, kelvin + step)) - np.log(pascal(key, kelvin - step))
    ) / (2 * step)
    expected = (latent - delta_c * (kelvin - T_0)) / (R_V * kelvin**2)
    assert slope == pytest.approx(expected, rel=1e-6)


def test_equation_13_stays_close_to_iapws() -> None:
    # Computed by nomogram: within 0.05 % from 0 to 80 degC, the fit range
    # of c_pl - c_pv = 2180 J kg-1 K-1 that Ambaum reports.
    kelvin = np.linspace(273.16, 353.15, 17)
    found = pascal("ambaum2020", kelvin) / pascal("iapws_sr1_86", kelvin)
    assert np.max(np.abs(found - 1)) < 5e-4


def test_equation_17_with_the_derived_latent_heat_stays_close_to_iapws() -> None:
    # L_s0 = L_0 + L_m0, which Ambaum does not print, is borne out against
    # the IAPWS sublimation curve: within 0.1 % from -40 to 0 degC.
    kelvin = np.linspace(233.15, 273.16, 9)
    found = pascal("ambaum2020_ice", kelvin) / pascal(
        "iapws_r14_08_sublimation", kelvin
    )
    assert np.max(np.abs(found - 1)) < 1e-3
    l_s0 = F["ambaum2020_ice"].coefficients
    assert next(c for c in l_s0 if c.identifier == "L_s0").note


def test_the_constant_latent_heat_departs_from_iapws_away_from_the_triple_point() -> (
    None
):
    found = pascal("ambaum2020_constant_latent_heat", 313.15) / pascal(
        "iapws_sr1_86", 313.15
    )
    assert 0.03 < found - 1 < 0.05
