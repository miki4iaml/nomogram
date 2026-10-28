# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the atmosphere family: vertical coordinates and their kinds."""

import pytest

from nomogram.catalog import catalog
from nomogram.comparison import feeds
from nomogram.model import ConstantNature
from nomogram.units import ScaleType

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


def test_the_standard_acceleration_of_free_fall() -> None:
    g_n = CATALOG.constants["g_n_cgpm1901"]
    assert g_n.value == 9.80665
    assert g_n.unit == "M-PER-SEC2"
    assert g_n.nature is ConstantNature.CONVENTIONAL
