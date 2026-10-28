# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the end of WMO-No. 8, Annex 4.B: frost point, relative
humidity with respect to ice from it, and the Assmann psychrometer."""

import math
from typing import Any

import pytest

from nomogram.catalog import catalog
from nomogram.comparison import compose, feeds
from nomogram.relations import verify
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


def test_a_psychrometer_reading_is_no_thermodynamic_bulb_temperature() -> None:
    # WMO-No. 8, 4.3.1.7: the reading of most instruments is not the
    # thermodynamic wet-bulb temperature of Annex 4.A.
    for reading, thermodynamic in (
        ("PsychrometerWetBulbTemperature", "WetBulbTemperature"),
        ("PsychrometerIceBulbTemperature", "IceBulbTemperature"),
    ):
        assert not feeds(reading, thermodynamic)
        assert not feeds(thermodynamic, reading)
        assert feeds(reading, "Temperature")
    kinds = {
        key: next(v.kind for v in F[key].inputs if "Bulb" in v.kind)
        for key in (
            "wmo_psychrometer_water",
            "wmo_psychrometric_formula_ice",
            "metpy171_psychrometric_vapour_pressure",
            "wmo_wet_bulb_ideal_gas",
            "wmo_ice_bulb_ideal_gas",
            "ashrae2017_mixing_ratio_from_wet_bulb",
        )
    }
    assert kinds == {
        "wmo_psychrometer_water": "PsychrometerWetBulbTemperature",
        "wmo_psychrometric_formula_ice": "PsychrometerIceBulbTemperature",
        "metpy171_psychrometric_vapour_pressure": "PsychrometerWetBulbTemperature",
        "wmo_wet_bulb_ideal_gas": "WetBulbTemperature",
        "wmo_ice_bulb_ideal_gas": "IceBulbTemperature",
        "ashrae2017_mixing_ratio_from_wet_bulb": "WetBulbTemperature",
    }


def test_a_relative_humidity_over_ice_feeds_no_relative_humidity() -> None:
    # WMO-No. 8 evaluates the relative humidity over water, even below
    # 0 degC (4.A, para. 17); QUDT defines it so.
    assert not feeds("RelativeHumidityWithRespectToIce", "RelativeHumidity")
    assert feeds("RelativeHumidityWithRespectToIce", "RelativePartialPressure")
    assert feeds("RelativeHumidity", "RelativePartialPressure")
    with pytest.raises(ValueError, match="RelativeHumidityWithRespectToIce"):
        compose(
            F["vapour_pressure_from_relative_humidity"],
            {"RH": F["wmo_relative_humidity_ice"]},
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


# --- ASHRAE (via PsychroLib) and MetPy ------------------------------------------


def test_ashrae_equation_33_is_wmo_4a19_solved_for_the_mixing_ratio() -> None:
    # With c_pa = 1.006, c_pv = 1.86 kJ/(kg K) and L_v(t_w) = 2501 - 2.326 t_w
    # kJ/kg, the air temperature of 4.A.19 gives back the dry bulb.
    t, t_w, w_s = 30.0, 15.0, 0.010647455293969347
    w = F["ashrae2017_mixing_ratio_from_wet_bulb"].evaluate(
        t=Q_(t, "degC"), t_w=Q_(t_w, "degC"), W_s=Q_(w_s, "kg/kg")
    )
    air = F["wmo_wet_bulb_ideal_gas"].evaluate(
        T_w=Q_(t_w + 273.15, "K"),
        r=w,
        r_w=Q_(w_s, "kg/kg"),
        L_v=Q_((2501 - 2.326 * t_w) * 1e3, "J/kg"),
        c_pa=Q_(1006.0, "J/(kg*K)"),
        c_pv=Q_(1860.0, "J/(kg*K)"),
    )
    assert air.to("degC").magnitude == pytest.approx(t)


def test_ashrae_at_saturation_the_mixing_ratio_is_its_saturation_value() -> None:
    t = Q_(12.0, "degC")
    w = F["ashrae2017_mixing_ratio_from_wet_bulb"].evaluate(
        t=t, t_w=t, W_s=Q_(0.0088, "kg/kg")
    )
    assert w.magnitude == pytest.approx(0.0088)


def test_metpy_reproduces_its_doctests() -> None:
    e_s = F["metpy171_saturation_vapour_pressure"].evaluate(T=Q_(298.15, "K"))
    assert e_s.to("hPa").magnitude == pytest.approx(31.623456, rel=1e-7)
    e = F["metpy171_psychrometric_vapour_pressure"].evaluate(
        p=Q_(958, "hPa"), T=Q_(298.15, "K"), T_w=Q_(285.15, "K")
    )
    assert e.to("Pa").magnitude == pytest.approx(627.52, abs=0.005)


# --- Saturation of the ECMWF IFS -------------------------------------------------


@pytest.mark.parametrize("kelvin", [233.15, 273.16, 303.15])
def test_the_ifs_saturation_over_water_is_buck_1981_in_kelvins(kelvin: float) -> None:
    ifs = F["ecmwf_ifs_saturation_water"].evaluate(T=Q_(kelvin, "K")).to("hPa")
    buck = (
        F["buck1981_magnus"]
        .evaluate(t=Q_(kelvin - 273.16, "degC"), scale="ignore")
        .to("hPa")
    )
    assert ifs.magnitude == pytest.approx(buck.magnitude, rel=1e-12)


def test_the_ifs_saturation_over_water_is_proven_buck_1981() -> None:
    # Proven on the expressions brought into the same units: Pa and hPa.
    relation = CATALOG.relations["ecmwf_ifs_buck1981_magnus"]
    assert relation.computed
    assert verify(relation, CATALOG).status == "proven"
