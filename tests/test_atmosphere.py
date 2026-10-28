# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the atmosphere family: vertical coordinates and their kinds."""

from typing import Any

import pytest

from nomogram.catalog import catalog
from nomogram.comparison import feeds
from nomogram.model import ConstantNature
from nomogram.units import Q_, ScaleType

CATALOG = catalog()


@pytest.mark.parametrize(
    ("output", "input"),
    [
        ("SurfaceAltitude", "Altitude"),
        # A pressure altitude is a geopotential height of the standard
        # atmosphere.
        ("PressureAltitude", "GeopotentialHeight"),
        ("SeaLevelPressure", "Pressure"),
        ("LapseRate", "TemperatureGradient"),
    ],
)
def test_a_kind_feeds_the_inputs_of_its_ancestors(output: str, input: str) -> None:
    assert feeds(output, input)


@pytest.mark.parametrize(
    ("output", "input"),
    [
        # 25 m apart at 8 km (WMO-No. 8, table 12.10).
        ("GeopotentialHeight", "Altitude"),
        ("PressureAltitude", "Altitude"),
        # Tens of metres apart: the geoid height.
        ("EllipsoidalHeight", "Altitude"),
        # Opposite signs.
        ("LapseRate", "VerticalTemperatureGradient"),
        ("VerticalTemperatureGradient", "LapseRate"),
        # The QNH goes through the standard atmosphere, not the actual one.
        ("AltimeterSetting", "SeaLevelPressure"),
    ],
)
def test_vertical_kinds_never_mix(output: str, input: str) -> None:
    assert not feeds(output, input)


def test_kinds_of_vertical_coordinates() -> None:
    kinds = CATALOG.kinds
    height = kinds["GeopotentialHeight"]
    assert height.specialization_of == "Length"
    assert height.scale_type is ScaleType.INTERVAL
    assert height.cf_standard_names == ("geopotential_height",)
    assert set(height.applicable_units) == {"M", "KiloM", "FT"}
    geopotential = kinds["Geopotential"]
    assert "M2-PER-SEC2" in geopotential.applicable_units
    assert kinds["LapseRate"].cf_standard_names == ("air_temperature_lapse_rate",)
    assert not kinds["VerticalTemperatureGradient"].cf_standard_names


def test_a_trade_term_tells_which_geopotential_is_meant() -> None:
    # WMO writes the geopotential of upper-air observations in standard
    # geopotential metres: CF's geopotential height.
    meanings = CATALOG.trade_terms["geopotential"].meanings
    assert {m.kind for m in meanings} == {"Geopotential", "GeopotentialHeight"}
    flight_level = CATALOG.trade_terms["flight_level"].meanings[0]
    assert flight_level.kind == "PressureAltitude"
    assert flight_level.sources == ("sera2012",)


def test_search_reaches_vertical_coordinates() -> None:
    found = CATALOG.search("geopotential_height", section="kinds").refs
    assert "kinds.GeopotentialHeight" in found
    assert "kinds.GeopotentialHeight" in CATALOG.search("Q12432978").refs
    terms = CATALOG.search("pressure", "altitude").refs
    assert {"kinds.PressureAltitude", "trade_terms.pressure_altitude"} <= set(terms)
    assert "kinds.LapseRate" in CATALOG.search(family="atmosphere").refs
    assert "trade_terms.elevation" in CATALOG.used_by("references.wmo2024").refs


FORMULATIONS = CATALOG.formulations


def test_geopotential_height_from_the_geopotential() -> None:
    definition = FORMULATIONS["geopotential_height_definition"]
    value = definition.evaluate(Phi=Q_(98066.5, "m**2/s**2"))
    assert value.to("m").magnitude == pytest.approx(10000.0)


def test_conversions_differ_by_their_earth_radius() -> None:
    # ITU-R P.835: 84.852 km' correspond to 86 km (Annex 1, 1.1).
    p835 = FORMULATIONS["itu_r_p835_geopotential_height"]
    assert p835.evaluate(z=Q_(86, "km")).magnitude == pytest.approx(84.852, abs=5e-4)
    back = FORMULATIONS["itu_r_p835_geometric_altitude"]
    assert back.evaluate(Z=Q_(84.852, "km")).magnitude == pytest.approx(86, abs=5e-4)
    # The spherical Earth of the IFS, a larger radius: a smaller correction.
    era5 = FORMULATIONS["era5_geometric_altitude"]
    p835_back = back.evaluate(Z=Q_(10, "km")).to("m").magnitude
    era5_back = era5.evaluate(Z=Q_(10, "km")).to("m").magnitude
    assert 15 < era5_back - 10000 < p835_back - 10000 < 16


def test_wmo_geopotential_height_of_a_gps_radiosonde() -> None:
    # WMO-No. 8, 12.5.5.2: 30 km of geometric height give 29.7785 km at the
    # Equator and 29.932 km at 80 degrees north.
    wgs84 = FORMULATIONS["wmo_geopotential_height_wgs84"]
    equator = wgs84.evaluate(z=Q_(30, "km"), phi=Q_(0, "deg"))
    north = wgs84.evaluate(z=Q_(30, "km"), phi=Q_(80, "deg"))
    assert equator.magnitude == pytest.approx(29.7785, abs=5e-5)
    assert north.magnitude == pytest.approx(29.932, abs=1e-3)


def test_normal_gravity_at_the_latitude() -> None:
    # Surface gravity is greatest at the poles, 9.83218 m s-2 (12.5.5.2).
    wgs84 = FORMULATIONS["wmo_normal_gravity_wgs84"]
    assert wgs84.evaluate(phi=Q_(90, "deg")).magnitude == pytest.approx(
        9.83218, abs=1e-5
    )
    smithsonian = FORMULATIONS["wmo_normal_gravity_smithsonian"]
    assert smithsonian.evaluate(phi=Q_(45, "deg")).magnitude == pytest.approx(9.80616)
    assert "sin" in wgs84.latex()


def test_pressure_through_the_layers_of_the_standard_atmosphere() -> None:
    # U.S. Standard Atmosphere 1976: P_1 = 22 632.06 Pa at 11 km' (a layer
    # of -6.5 K/km' from 101 325 Pa and 288.15 K), P_2 = 5 474.889 Pa at
    # 20 km' (an isothermal layer at 216.65 K).
    gradient = FORMULATIONS["ussa1976_pressure_layer_gradient"]
    p_1 = gradient.evaluate(
        P_b=Q_(101325, "Pa"),
        T_b=Q_(288.15, "K"),
        L=Q_(-6.5, "K/km"),
        H=Q_(11, "km"),
        H_b=Q_(0, "km"),
    )
    assert p_1.to("Pa").magnitude == pytest.approx(22632.06, abs=0.01)
    isothermal = FORMULATIONS["ussa1976_pressure_layer_isothermal"]
    p_2 = isothermal.evaluate(
        P_b=p_1, T_b=Q_(216.65, "K"), H=Q_(20, "km"), H_b=Q_(11, "km")
    )
    assert p_2.to("Pa").magnitude == pytest.approx(5474.889, abs=0.01)


def test_the_thickness_of_a_layer_by_wmo_and_by_the_ifs() -> None:
    # 1000 to 500 hPa at a mean virtual temperature of 255 K: the IFS gives
    # the geopotential, WMO the pressure; their gas constants of dry air
    # differ by 3 x 10^-5.
    ifs = FORMULATIONS["ecmwf_ifs_hypsometric_geopotential"]
    phi = ifs.evaluate(
        Phi_1=Q_(0, "m**2/s**2"),
        p_1=Q_(1000, "hPa"),
        p_2=Q_(500, "hPa"),
        T_v=Q_(255, "K"),
    )
    thickness = FORMULATIONS["geopotential_height_definition"].evaluate(Phi=phi)
    assert thickness.to("m").magnitude == pytest.approx(5173.9, abs=0.1)
    wmo = FORMULATIONS["wmo_hypsometric_pressure"]
    p_2 = wmo.evaluate(p_1=Q_(1000, "hPa"), dZ=thickness, T_v=Q_(255, "K"))
    assert p_2.to("hPa").magnitude == pytest.approx(500, rel=1e-4)


def test_the_two_forms_of_the_reduction_to_sea_level() -> None:
    # Equations 3.1 and 3.2 of WMO-No. 8: the same formula for the source,
    # 6.4 x 10^-4 apart in the exponent.
    station: dict[str, Any] = {
        "p_s": Q_(950, "hPa"),
        "H_p": Q_(500, "m"),
        "T_s": Q_(288.15, "K"),
        "e_s": Q_(10, "hPa"),
    }
    exponential = FORMULATIONS["wmo_sea_level_pressure"].evaluate(**station)
    decimal = FORMULATIONS["wmo_sea_level_pressure_log10"].evaluate(**station)
    assert exponential.magnitude == pytest.approx(1007.44, abs=0.01)
    assert 0.03 < exponential.magnitude - decimal.magnitude < 0.05


def test_the_dry_adiabatic_gradient() -> None:
    # Bechtold (2015), equation 38: a decrease of 0.98 K per 100 m.
    gradient = FORMULATIONS["bechtold2015_dry_adiabatic_gradient"].evaluate()
    assert gradient.to("K/km").magnitude == pytest.approx(-9.76, abs=0.01)


def test_the_standard_acceleration_of_free_fall() -> None:
    g_n = CATALOG.constants["g_n_cgpm1901"]
    assert g_n.value == 9.80665
    assert g_n.unit == "M-PER-SEC2"
    assert g_n.nature is ConstantNature.CONVENTIONAL
