# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the end of WMO-No. 8, Annex 4.B: frost point, relative
humidity with respect to ice from it, and the Assmann psychrometer."""

import math
from typing import Any

import pytest

from nomogram.catalog import catalog
from nomogram.comparison import feeds
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
P = Q_(1000, "hPa")


def enhancement(hectopascal: float) -> float:
    """WMO-No. 8, 4.B.5."""
    return 1.0016 + 3.15e-6 * hectopascal - 0.074 / hectopascal


def magnus(celsius: float, a: float, b: float) -> float:
    """WMO-No. 8, 4.B.1 (water) or 4.B.3 (ice), in hPa."""
    return 6.112 * math.exp(a * celsius / (b + celsius))


@pytest.mark.parametrize("celsius", [-60.0, -40.0, -20.0, -1.0])
def test_the_frost_point_inverts_the_saturation_pressure_over_ice(
    celsius: float,
) -> None:
    e = F["wmo_es_ice_moist_air"].evaluate(p=P, t=Q_(celsius, "degC"))
    found = F["wmo_frost_point_moist_air"].evaluate(e=e, p=P)
    assert found.to("degC").magnitude == pytest.approx(celsius)


def test_relative_humidity_over_ice_from_the_frost_point() -> None:
    f = F["relative_humidity_ice_from_frost_point"]
    assert f.derived
    assert not f.citations
    t = Q_(-20, "degC")
    assert f.evaluate(t_f=t, t=t, p=P).magnitude == pytest.approx(100)
    found = f.evaluate(t_f=Q_(-25, "degC"), t=t, p=P).magnitude
    expected = 100 * magnus(-25, 22.46, 272.62) / magnus(-20, 22.46, 272.62)
    assert found == pytest.approx(expected)
    # The enhancement factor cancels: the value does not depend on p.
    aloft = f.evaluate(t_f=Q_(-25, "degC"), t=t, p=Q_(500, "hPa")).magnitude
    assert aloft == pytest.approx(found)


def test_the_assmann_psychrometer_with_a_wet_bulb() -> None:
    f = F["wmo_psychrometer_water"]
    p = Q_(1013.25, "hPa")
    same = f.evaluate(t=Q_(20, "degC"), t_w=Q_(20, "degC"), p=p)
    saturated = F["wmo_es_water_moist_air"].evaluate(t=Q_(20, "degC"), p=p)
    assert same.magnitude == pytest.approx(saturated.magnitude)
    found = f.evaluate(t=Q_(20, "degC"), t_w=Q_(15, "degC"), p=p).magnitude
    expected = enhancement(1013.25) * magnus(15, 17.62, 243.12) - 6.53e-4 * (
        1 + 0.000944 * 15
    ) * 1013.25 * (20 - 15)
    assert found == pytest.approx(expected)
    assert f.conditions is not None
    assert f.conditions.startswith("An Assmann aspirated psychrometer")


def test_the_assmann_psychrometer_with_an_ice_bulb() -> None:
    found = F["wmo_psychrometer_ice"].evaluate(
        t=Q_(-5, "degC"), t_i=Q_(-8, "degC"), p=P
    )
    expected = enhancement(1000) * magnus(-8, 22.46, 272.62) - 5.75e-4 * 1000 * 3
    assert found.magnitude == pytest.approx(expected)


def test_a_frost_point_is_a_temperature_but_not_a_dew_point() -> None:
    assert feeds("FrostPointTemperature", "Temperature")
    assert not feeds("FrostPointTemperature", "DewPointTemperature")
    assert not feeds("IceBulbTemperature", "WetBulbTemperature")
    assert CATALOG.kinds["WetBulbTemperature"].cf_standard_names == (
        "wet_bulb_temperature",
    )


@pytest.mark.parametrize(
    ("kind", "applies"),
    [
        ("FrostPointTemperature", True),
        ("IceBulbTemperature", True),
        ("WetBulbTemperature", True),
        ("VirtualTemperature", True),
        ("DewPointTemperature", True),
        ("TemperatureDifference", False),
        ("Pressure", False),
    ],
)
def test_a_temperature_scale_applies_to_every_temperature(
    kind: str, applies: bool
) -> None:
    its90 = CATALOG.scales["its90"]
    assert its90.applies_to(kind, CATALOG.kinds) is applies
    assert its90.applies_to("Unknown", CATALOG.kinds) is False


# --- General psychrometric formulae and thermodynamic bulbs (WMO-No. 8) -----------


def test_the_general_formula_with_the_assmann_coefficient_is_4b8() -> None:
    p, t, t_w = Q_(1013.25, "hPa"), Q_(20, "degC"), Q_(15, "degC")
    e_ws = F["wmo_es_water_moist_air"].evaluate(t=t_w, p=p)
    a = Q_(6.53e-4 * (1 + 0.000944 * 15), "1/K")
    general = F["wmo_psychrometric_formula_water"].evaluate(
        e_ws=e_ws, A=a, p=p, t=t, t_w=t_w
    )
    assmann = F["wmo_psychrometer_water"].evaluate(t=t, t_w=t_w, p=p)
    assert general.magnitude == pytest.approx(assmann.magnitude)


def test_the_general_formula_over_ice_with_the_assmann_coefficient_is_4b9() -> None:
    t, t_i = Q_(-5, "degC"), Q_(-8, "degC")
    e_is = F["wmo_es_ice_moist_air"].evaluate(t=t_i, p=P)
    general = F["wmo_psychrometric_formula_ice"].evaluate(
        e_is=e_is, A=Q_(5.75e-4, "1/K"), p=P, t=t, t_i=t_i
    )
    assmann = F["wmo_psychrometer_ice"].evaluate(t=t, t_i=t_i, p=P)
    assert general.magnitude == pytest.approx(assmann.magnitude)
    assert CATALOG.kinds["PsychrometerCoefficient"].specialization_of == (
        "InverseTemperature"
    )


@pytest.mark.parametrize(
    ("key", "bulb", "saturation", "latent"),
    [
        ("wmo_wet_bulb_ideal_gas", "T_w", "r_w", "L_v"),
        ("wmo_ice_bulb_ideal_gas", "T_i", "r_i", "L_s"),
    ],
)
def test_the_air_temperature_from_a_thermodynamic_bulb(
    key: str, bulb: str, saturation: str, latent: str
) -> None:
    f = F[key]
    common: dict[str, Any] = {
        bulb: Q_(270.0, "K"),
        saturation: Q_(0.004, "kg/kg"),
        latent: Q_(2.5e6, "J/kg"),
        "c_pa": Q_(1005.0, "J/(kg*K)"),
        "c_pv": Q_(1846.0, "J/(kg*K)"),
    }
    # Saturated air is at its bulb temperature.
    saturated = f.evaluate(r=Q_(0.004, "kg/kg"), **common)
    assert saturated.to("K").magnitude == pytest.approx(270.0)
    drier = f.evaluate(r=Q_(0.002, "kg/kg"), **common).to("K").magnitude
    assert drier == pytest.approx(270 + 0.002 * 2.5e6 / (1005 + 0.002 * 1846))
    assert f.citations[0].assumptions
