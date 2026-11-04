# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the atmospheric thermodynamics of Bechtold (2015): humidity
variables, virtual and potential temperatures, saturation."""

import math
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.relations import verify
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
EPSILON = 0.622
KAPPA = 287.06 / 1004.7


def value(key: str, unit: str, **inputs: Any) -> float:
    return float(F[key].evaluate(**inputs).to(unit).magnitude)


# --- Humidity variables -----------------------------------------------------------


def test_specific_humidity_and_mixing_ratio_convert_both_ways() -> None:
    q = value("specific_humidity_from_mixing_ratio", "kg/kg", r=Q_(0.02, "kg/kg"))
    assert q == pytest.approx(0.02 / 1.02)
    r = value("mixing_ratio_from_specific_humidity", "kg/kg", q=Q_(q, "kg/kg"))
    assert r == pytest.approx(0.02)


def test_the_forms_from_vapour_pressure_agree_with_the_conversion() -> None:
    e, p = Q_(2000, "Pa"), Q_(100000, "Pa")
    q = value("bechtold2015_specific_humidity_from_vapour_pressure", "kg/kg", e=e, p=p)
    r = value("bechtold2015_mixing_ratio_from_vapour_pressure", "kg/kg", e=e, p=p)
    assert r == pytest.approx(EPSILON * 2000 / 98000)
    assert q == pytest.approx(r / (1 + r))


# --- Virtual temperature ----------------------------------------------------------


def test_moisture_warms_the_virtual_temperature_by_about_one_kelvin() -> None:
    # Section 7: at 300 K and q = 5 g/kg, "virtually about 1 K warmer".
    found = value(
        "bechtold2015_virtual_temperature", "K", T=Q_(300, "K"), q=Q_(5, "g/kg")
    )
    assert found - 300 == pytest.approx(300 * 0.005 * (1 - EPSILON) / EPSILON)
    assert 0.9 < found - 300 < 1.0


def test_the_definition_gives_back_the_virtual_temperature() -> None:
    t_v = value(
        "bechtold2015_virtual_temperature", "K", T=Q_(290, "K"), q=Q_(0.01, "kg/kg")
    )
    density = Q_(100000 / (287.06 * t_v), "kg/m^3")
    found = value(
        "bechtold2015_virtual_temperature_definition",
        "K",
        p=Q_(100000, "Pa"),
        rho=density,
    )
    assert found == pytest.approx(t_v)


def test_the_three_forms_of_equation_25_agree() -> None:
    T, q = Q_(290, "K"), 0.015
    exact = value("bechtold2015_virtual_temperature", "K", T=T, q=Q_(q, "kg/kg"))
    mixing = value(
        "bechtold2015_virtual_temperature_mixing_ratio",
        "K",
        T=T,
        r=Q_(q / (1 - q), "kg/kg"),
    )
    rounded = value(
        "bechtold2015_virtual_temperature_rounded", "K", T=T, q=Q_(q, "kg/kg")
    )
    assert mixing == pytest.approx(exact)
    assert rounded == pytest.approx(exact, rel=1e-5)


# --- Potential temperatures -------------------------------------------------------


def test_the_potential_temperature_is_the_temperature_at_1000_hpa() -> None:
    at_reference = value(
        "bechtold2015_potential_temperature", "K", T=Q_(280, "K"), p=Q_(1000, "hPa")
    )
    assert at_reference == pytest.approx(280)
    aloft = value(
        "bechtold2015_potential_temperature", "K", T=Q_(250, "K"), p=Q_(500, "hPa")
    )
    assert aloft == pytest.approx(250 * 2**KAPPA)
    assert KAPPA == pytest.approx(2 / 7, rel=1e-5)


def test_the_virtual_potential_temperature_is_that_of_the_virtual_temperature() -> None:
    # Equation 36 is printed with p / p_0: the catalog writes p_0 / p, as
    # in equation 28, so that it exceeds T_v above the 1000 hPa level.
    p = Q_(700, "hPa")
    found = value(
        "bechtold2015_virtual_potential_temperature", "K", T_v=Q_(270, "K"), p=p
    )
    dry = value("bechtold2015_potential_temperature", "K", T=Q_(270, "K"), p=p)
    assert found == pytest.approx(dry)
    assert found > 270


def test_without_water_the_moist_potential_temperatures_are_the_dry_one() -> None:
    T, p, dry_air = Q_(285, "K"), Q_(850, "hPa"), Q_(0, "kg/kg")
    dry = value("bechtold2015_potential_temperature", "K", T=T, p=p)
    moist = value(
        "bechtold2015_potential_temperature_moist_air", "K", T=T, p=p, r=dry_air
    )
    equivalent = value(
        "bechtold2015_equivalent_potential_temperature",
        "K",
        T=T,
        p=p,
        r=dry_air,
        r_w=dry_air,
        L_v=Q_(2.5008e6, "J/kg"),
    )
    assert moist == pytest.approx(dry)
    assert equivalent == pytest.approx(dry)


def test_condensing_the_vapour_warms_the_equivalent_potential_temperature() -> None:
    T, p, r = Q_(290, "K"), Q_(900, "hPa"), Q_(0.012, "kg/kg")
    moist = value("bechtold2015_potential_temperature_moist_air", "K", T=T, p=p, r=r)
    equivalent = value(
        "bechtold2015_equivalent_potential_temperature",
        "K",
        T=T,
        p=p,
        r=r,
        r_w=r,
        L_v=Q_(2.5008e6, "J/kg"),
    )
    # L_v r / c_p is about 30 K.
    assert 25 < equivalent - moist < 40


# --- Saturation -------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "bechtold2015_saturation_vapour_pressure_constant_latent_heat",
        "bechtold2015_magnus_water",
    ],
)
def test_at_the_triple_point_the_saturation_pressure_is_p_vs0(key: str) -> None:
    assert value(key, "hPa", T=Q_(273.16, "K")) == pytest.approx(6.112)


def test_equation_54_boils_at_99_39_degc_under_1013_hpa() -> None:
    # The notes write 99.5 degC (p. 10).
    def pressure(celsius: float) -> float:
        return value("bechtold2015_magnus_water", "hPa", T=Q_(celsius + 273.15, "K"))

    assert pressure(99.38) < 1013 < pressure(99.40)


# --- Relations --------------------------------------------------------------------


def test_the_two_forms_of_equation_25_are_proven_equivalent() -> None:
    relation = CATALOG.relations["bechtold2015_virtual_temperature_two_forms"]
    assert relation.citation == "bechtold2015"
    assert verify(relation, CATALOG).status == "proven"


def test_0_608_is_the_exact_coefficient_to_the_printed_precision() -> None:
    found = verify(
        CATALOG.relations["bechtold2015_virtual_temperature_rounding"], CATALOG
    )
    assert found.status == "held"
    assert found.detail is not None
    assert "equivalent to the printed precision" in found.detail
    assert "a factor of T cannot be told from a coefficient" in found.detail


@pytest.mark.parametrize(
    ("key", "factor", "ratio"),
    [
        (
            "bechtold2015_ashrae2017_mixing_ratio",
            0.622 / 0.621945,
            "(0.622 / 0.621945)",
        ),
        ("bechtold2015_buck1981_magnus", 6.112 / 6.1121, "(6.112 / 6.1121)"),
        # The e_0 of the IFS in Pa, Bechtold's C in hPa.
        (
            "bechtold2015_ecmwf_ifs_water",
            6.112 / 6.1121,
            "(6.112 / 611.21, PA brought into HectoPA)",
        ),
        (
            "bechtold2015_ecmwf_ifs_ice",
            6.112 / 6.1121,
            "(6.112 / 611.21, PA brought into HectoPA)",
        ),
    ],
)
def test_bechtold_rounds_a_coefficient(key: str, factor: float, ratio: str) -> None:
    found = verify(CATALOG.relations[key], CATALOG)
    assert found.status == "proven"
    assert found.value == pytest.approx(factor)
    assert found.detail is not None
    assert ratio in found.detail


def test_the_new_kinds_find_their_formulations() -> None:
    found = CATALOG.search(kind="PotentialTemperature").refs
    assert "formulations.bechtold2015_potential_temperature" in found
    assert "formulations.bechtold2015_potential_temperature_moist_air" in found
    assert "formulations.bechtold2015_equivalent_potential_temperature" in found
    assert {f.key for f in CATALOG.formulations_of("VirtualTemperature")} == {
        "bechtold2015_virtual_temperature_definition",
        "bechtold2015_virtual_temperature",
        "bechtold2015_virtual_temperature_mixing_ratio",
        "bechtold2015_virtual_temperature_rounded",
        "metpy171_virtual_temperature",
        "ecmwf_ifs_virtual_temperature",
    }


def test_the_lifting_condensation_level_of_the_ifs() -> None:
    # Davies-Jones (1983) as the IFS writes it (6.74), by hand, with T_0 =
    # 273.16 K: 20 degC and a dew point of 10 degC give 7.81 degC; Bolton
    # (1980, eq. 15) gives 280.93 K, 0.03 K below.
    t_d, t = 283.15, 293.15
    t_lcl = F["ecmwf_ifs_lcl_temperature"].evaluate(T_d=Q_(t_d, "K"), T=Q_(t, "K"))
    by_hand = t_d - (0.212 + 1.571e-3 * (t_d - 273.16) - 4.36e-4 * (t - 273.16)) * (
        t - t_d
    )
    assert t_lcl.to("K").magnitude == pytest.approx(by_hand, rel=1e-12)
    bolton = 1 / (1 / (t_d - 56) + math.log(t / t_d) / 800) + 56
    assert t_lcl.to("K").magnitude == pytest.approx(bolton, abs=0.05)
    # The reference pressure cancels when theta is computed with it.
    kappa = 287.0597 / 1004.7090
    pressures = []
    for p_0 in (1000.0, 1013.25):
        theta = t * (p_0 / 950.0) ** kappa
        p_lcl = F["ecmwf_ifs_lcl_pressure"].evaluate(
            T_LCL=t_lcl, theta=Q_(theta, "K"), p_0=Q_(p_0, "hPa")
        )
        pressures.append(p_lcl.to("hPa").magnitude)
    expected = 950.0 * (t_lcl.to("K").magnitude / t) ** (1 / kappa)
    assert pressures == pytest.approx([expected, expected], rel=1e-12)
    composed = F["ecmwf_ifs_lcl_pressure_dew_point"].evaluate(
        T_d=Q_(t_d, "K"),
        T=Q_(t, "K"),
        theta=Q_(t * (1000.0 / 950.0) ** kappa, "K"),
        p_0=Q_(1000.0, "hPa"),
    )
    assert composed.to("hPa").magnitude == pytest.approx(expected, rel=1e-12)


def test_murphy_and_koop_over_water_meets_ice_and_iapws() -> None:
    # Both forms of Murphy and Koop (2005) meet at the triple point, as
    # IAPWS does; above freezing the form over water follows IAPWS.
    triple = Q_(273.16, "K")
    water = F["murphy_koop2005_water"].evaluate(T=triple).to("Pa").magnitude
    ice = F["murphy_koop2005_ice"].evaluate(T=triple).to("Pa").magnitude
    assert water == pytest.approx(611.657, abs=0.001)
    assert ice == pytest.approx(water, rel=1e-5)
    t = Q_(np.linspace(273.16, 330.0, 50), "K")
    mk = F["murphy_koop2005_water"].evaluate(T=t).to("Pa").magnitude
    iapws = F["iapws_sr1_86"].evaluate(T=t).to("Pa").magnitude
    assert np.max(np.abs(mk / iapws - 1)) < 2e-4


def test_metpy_over_ice_and_its_choice_of_phase() -> None:
    # _saturation_vapor_pressure_solid of MetPy 1.7.1, by hand, at -20 degC.
    r_v, c_pv, c_i, l_v, l_f, t_0, e_0 = (
        461.52312,
        1860.0780,
        2090.0,
        2.50084e6,
        3.337e5,
        273.16,
        6.112,
    )
    t = 253.15
    l_s0 = l_v + l_f
    by_hand = (
        e_0
        * (t_0 / t) ** ((c_i - c_pv) / r_v)
        * math.exp((l_s0 / t_0 - (l_s0 - (c_i - c_pv) * (t - t_0)) / t) / r_v)
    )
    ice = F["metpy171_saturation_vapour_pressure_ice"].evaluate(T=Q_(t, "K"))
    assert ice.to("hPa").magnitude == pytest.approx(by_hand, rel=1e-9)
    # phase='auto': over ice up to the triple point, over water above.
    temperatures = Q_(np.array([263.15, 273.16, 273.17, 283.15]), "K")
    auto = F["metpy171_saturation_vapour_pressure_auto"].evaluate(T=temperatures)
    over_ice = F["metpy171_saturation_vapour_pressure_ice"].evaluate(T=temperatures)
    over_water = F["metpy171_saturation_vapour_pressure"].evaluate(T=temperatures)
    expected = np.where(
        temperatures.magnitude > 273.16, over_water.magnitude, over_ice.magnitude
    )
    assert auto.to("hPa").magnitude == pytest.approx(expected, rel=1e-12)


def test_the_mixed_phase_of_the_ifs() -> None:
    # 7.101 and 12.16: ice below 250.16 K, water from 273.16 K, weighted
    # by ((T - 250.16)/23)^2 in between (0.25 halfway).
    t = Q_(np.array([240.0, 250.16, 261.66, 273.16, 280.0]), "K")
    alpha = F["ecmwf_ifs_mixed_phase_fraction"].evaluate(T=t).magnitude
    assert alpha == pytest.approx([0.0, 0.0, 0.25, 1.0, 1.0], abs=1e-12)
    mixed = F["ecmwf_ifs_saturation_mixed_phase"].evaluate(T=t).to("Pa").magnitude
    water = F["ecmwf_ifs_saturation_water"].evaluate(T=t).to("Pa").magnitude
    ice = F["ecmwf_ifs_saturation_ice"].evaluate(T=t).to("Pa").magnitude
    assert mixed == pytest.approx(alpha * water + (1 - alpha) * ice, rel=1e-12)
    # Continuous at both thresholds.
    for edge in (250.16, 273.16):
        around = Q_(np.array([edge - 1e-6, edge + 1e-6]), "K")
        values = F["ecmwf_ifs_saturation_mixed_phase"].evaluate(T=around).magnitude
        assert values[0] == pytest.approx(values[1], rel=1e-6)


def test_the_water_and_ice_pairs_are_found_by_search() -> None:
    found = set(CATALOG.search(keyword="mixed phase", section="formulations").refs)
    assert {
        "formulations.ecmwf_ifs_saturation_mixed_phase",
        "formulations.metpy171_saturation_vapour_pressure_auto",
    } <= found
    used = set(CATALOG.used_by("references.alduchov_eskridge1996").refs)
    assert "formulations.ecmwf_ifs_saturation_ice" in used
