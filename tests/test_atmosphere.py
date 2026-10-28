# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the atmosphere family: vertical coordinates and their kinds."""

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


def test_the_standard_acceleration_of_free_fall() -> None:
    g_n = CATALOG.constants["g_n_cgpm1901"]
    assert g_n.value == 9.80665
    assert g_n.unit == "M-PER-SEC2"
    assert g_n.nature is ConstantNature.CONVENTIONAL
