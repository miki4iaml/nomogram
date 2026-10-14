# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.units`."""

import numpy as np
import pint
import pytest

from nomogram.units import Q_, ScaleType, convert, is_offset_unit, ureg


def test_celsius_point_converts_with_the_offset() -> None:
    assert convert(Q_(20, "degC"), "K").magnitude == pytest.approx(293.15)


def test_temperature_difference_converts_without_offset() -> None:
    assert convert(Q_(5, "delta_degC"), "K").magnitude == pytest.approx(5)


def test_difference_of_two_points_is_a_difference() -> None:
    difference: pint.Quantity = Q_(20, "degC") - Q_(5, "degC")
    assert not is_offset_unit(difference.units)
    assert convert(difference, "K").magnitude == pytest.approx(15)


def test_adding_two_temperature_points_is_refused() -> None:
    with pytest.raises(pint.errors.OffsetUnitCalculusError):
        _ = Q_(20, "degC") + Q_(5, "degC")


@pytest.mark.parametrize(
    ("unit", "offset"),
    [
        ("degC", True),
        ("degF", True),
        ("K", False),
        ("delta_degC", False),
        ("hPa", False),
    ],
)
def test_is_offset_unit(unit: str, offset: bool) -> None:
    assert is_offset_unit(unit) is offset


def test_convert_accepts_numpy_arrays() -> None:
    result = convert(Q_(np.array([0.0, 20.0]), "degC"), "K")
    assert result.magnitude == pytest.approx([273.15, 293.15])


def test_convert_accepts_quantities_from_another_registry() -> None:
    other = pint.UnitRegistry()
    result = convert(other.Quantity(1013.25, "hPa"), "Pa")
    assert result._REGISTRY is ureg
    assert result.magnitude == pytest.approx(101325)


def test_convert_rejects_incompatible_dimensions() -> None:
    with pytest.raises(pint.errors.DimensionalityError):
        convert(Q_(1, "hPa"), "K")


def test_convert_rejects_bare_numbers() -> None:
    with pytest.raises(TypeError, match="pint quantity"):
        convert(20.0, "K")


@pytest.mark.parametrize(
    ("value", "unit", "target", "expected"),
    [
        (50, "percent", "dimensionless", 0.5),  # relative humidity as a ratio
        (1013.25, "hPa", "Pa", 101325),
        (0.017290, "kg/m^3", "g/m^3", 17.290),  # absolute humidity
        (32, "degF", "degC", 0.0),  # Fahrenheit point
        (212, "degF", "degC", 100.0),
        (9, "delta_degF", "delta_degC", 5.0),  # Fahrenheit difference
    ],
)
def test_conversions_of_the_humidity_use_case(
    value: float, unit: str, target: str, expected: float
) -> None:
    result = convert(Q_(value, unit), target)
    assert result.magnitude == pytest.approx(expected, abs=1e-9)


def test_pint_does_not_tell_kelvin_points_from_differences() -> None:
    # Known pint limit, pinned so that a change in pint does not go
    # unnoticed: kelvin values are always added, whether they are points
    # (thermodynamic temperatures) or differences. Telling them apart is
    # the job of nomogram's quantity kinds.
    total: pint.Quantity = Q_(300, "K") + Q_(290, "K")
    assert total.magnitude == pytest.approx(590)


def test_scale_types() -> None:
    assert {s.value for s in ScaleType} == {"ratio", "interval"}
