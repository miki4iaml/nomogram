# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the atmospheric thermodynamics of Bechtold (2015): humidity
variables, virtual and potential temperatures, saturation."""

from typing import Any

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
    }
