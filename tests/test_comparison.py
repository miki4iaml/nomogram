# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.comparison`: matching rules and validation."""

import dataclasses
import math

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.comparison import compare, compose, same_state
from nomogram.units import Q_

FORMULATIONS = catalog().formulations
IAPWS = FORMULATIONS["iapws_sr1_86"]
SONNTAG = FORMULATIONS["sonntag1990_magnus"]
IDEAL_GAS = FORMULATIONS["mass_concentration_ideal_gas"]


def test_temperature_points_share_a_state_but_not_differences() -> None:
    assert same_state("CelsiusTemperature", "ThermodynamicTemperature")
    assert same_state("VapourPressure", "VapourPressure")
    assert not same_state("CelsiusTemperature", "TemperatureDifference")
    # The dew point is a temperature, but not the temperature of the air.
    assert not same_state("CelsiusTemperature", "DewPointTemperature")
    assert not same_state("VapourPressure", "SaturationVapourPressureOverWater")


def test_compare_needs_one_matching_value_per_input() -> None:
    with pytest.raises(ValueError, match="found: none"):
        compare([SONNTAG], IAPWS, {"RelativeHumidity": Q_(1, "")})
    both = {
        "CelsiusTemperature": Q_(20, "degC"),
        "ThermodynamicTemperature": Q_(293.15, "K"),
    }
    with pytest.raises(
        ValueError, match="found: CelsiusTemperature, ThermodynamicTemperature"
    ):
        compare([SONNTAG], IAPWS, both)


def test_compare_refuses_another_kind() -> None:
    with pytest.raises(ValueError, match="computes MassConcentrationOfWaterVapour"):
        compare([IDEAL_GAS], IAPWS, {"ThermodynamicTemperature": Q_(20, "degC")})


def test_values_are_expressed_in_the_reference_unit() -> None:
    comparison = compare([SONNTAG], IAPWS, {"ThermodynamicTemperature": Q_(20, "degC")})
    assert str(comparison.values["sonntag1990_magnus"].units) == "pascal"
    assert comparison.reference == "iapws_sr1_86"
    with pytest.raises(dataclasses.FrozenInstanceError):
        comparison.reference = "x"  # type: ignore[misc]


def test_max_abs_deviation_ignores_nan_and_reports_all_nan() -> None:
    grid = Q_(np.array([-50.0, 20.0]), "degC")
    comparison = compare([SONNTAG], IAPWS, {"CelsiusTemperature": grid})
    worst = comparison.max_abs_deviation()
    assert worst["sonntag1990_magnus"] == pytest.approx(0.0028, abs=0.0001)
    outside = compare([SONNTAG], IAPWS, {"CelsiusTemperature": Q_(-50, "degC")})
    assert math.isnan(outside.max_abs_deviation()["sonntag1990_magnus"])


def test_comparison_records_the_scale_mode() -> None:
    # Weiss and Price fitted T on IPTS-48 and S on PSS-78.
    weiss = FORMULATIONS["weiss_price1980_vapour_pressure"]
    t = Q_(np.array([10.0, 20.0]), "degC")
    # Reference Salinity in g/kg; taken as given, Practical Salinity, a number.
    reference = {"ThermodynamicTemperature": t, "SeaWaterSalinity": Q_(35.0, "g/kg")}
    as_given = {"ThermodynamicTemperature": t, "SeaWaterSalinity": Q_(35.0)}
    converted = compare([weiss], weiss, reference)
    ignored = compare([weiss], weiss, as_given, scale="ignore")
    assert converted.scale == "convert"
    assert ignored.scale == "ignore"
    # Taken on its own scales, the formulation gives other numbers.
    assert not np.allclose(
        converted.values[weiss.key].magnitude,
        ignored.values[weiss.key].magnitude,
        rtol=1e-6,
    )


def test_composition_inputs_and_key() -> None:
    ha = compose(IDEAL_GAS, {"e_s": SONNTAG}, bind={"t": "T"})
    assert ha.key == "mass_concentration_ideal_gas[e_s=sonntag1990_magnus]"
    assert [v.identifier for v in ha.inputs] == ["RH", "T"]
    assert ha.output.kind == "MassConcentrationOfWaterVapour"
    unbound = compose(IDEAL_GAS, {"e_s": SONNTAG})
    assert [v.identifier for v in unbound.inputs] == ["RH", "T", "t"]
    result = unbound.evaluate(RH=Q_(1, ""), T=Q_(20, "degC"), t=Q_(20, "degC"))
    assert result.to("g/m^3").magnitude == pytest.approx(17.241, abs=0.001)


@pytest.mark.parametrize(
    ("inner", "bind", "message"),
    [
        ({"x": "sonntag1990_magnus"}, {}, "has no input 'x'"),
        ({"RH": "sonntag1990_magnus"}, {}, "but RH is RelativeHumidity"),
        ({"e_s": "sonntag1990_magnus"}, {"t": "RH"}, "cannot bind t"),
        ({"e_s": "sonntag1990_magnus"}, {"nope": "T"}, "cannot bind 'nope'"),
        ({"e_s": "sonntag1990_magnus"}, {"t": "e_s"}, "cannot bind 't' to 'e_s'"),
    ],
)
def test_invalid_compositions_are_refused(
    inner: dict[str, str], bind: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        compose(IDEAL_GAS, {k: FORMULATIONS[v] for k, v in inner.items()}, bind)


def test_a_specialized_kind_feeds_its_parent_never_the_reverse() -> None:
    from nomogram.comparison import feeds

    assert feeds("SaturationVapourPressureOverWater", "VapourPressure")
    assert feeds("VapourPressure", "VapourPressure")
    assert not feeds("VapourPressure", "SaturationVapourPressureOverWater")
    assert not feeds("Unknown", "VapourPressure")
    vapour = FORMULATIONS["vapour_pressure_from_relative_humidity"]
    with pytest.raises(ValueError, match="computes VapourPressure"):
        compose(IDEAL_GAS, {"e_s": vapour})
