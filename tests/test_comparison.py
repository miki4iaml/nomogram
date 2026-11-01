# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.comparison`: matching rules and validation."""

import dataclasses
import math
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.comparison import compare, compose, partial, same_state
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


def test_a_difference_never_feeds_a_temperature_point() -> None:
    from nomogram.comparison import feeds

    # QUDT makes a temperature difference a temperature; not nomogram.
    assert not feeds("TemperatureDifference", "Temperature")
    assert feeds("DewPointTemperature", "Temperature")
    assert feeds("TemperatureDifference", "TemperatureDifference")


def test_points_of_an_interval_scale_deviate_in_kelvins() -> None:
    # Two WMO dew points about 0.004 K apart, around 0 degC: in degC the
    # relative deviation would blow up there and change sign.
    e = Q_(np.linspace(5.0, 8.0, 7), "hPa")
    inputs = {
        "VapourPressure": e,
        "Pressure": Q_(1013.25, "hPa"),
        "EnhancementFactor": Q_(1.0044, ""),
    }
    reference = FORMULATIONS["wmo_dew_point_moist_air"]
    comparison = compare([FORMULATIONS["wmo_dew_point"]], reference, inputs)
    values = comparison.values
    kelvin = {k: v.to("K").magnitude for k, v in values.items()}
    expected = kelvin["wmo_dew_point"] / kelvin["wmo_dew_point_moist_air"] - 1
    found = comparison.relative_deviations["wmo_dew_point"]
    assert found == pytest.approx(expected)
    assert np.abs(found).max() < 1e-4
    assert str(values["wmo_dew_point"].units) == "degree_Celsius"


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
    assert ha.label is None
    named = compose(IDEAL_GAS, {"e_s": SONNTAG}, bind={"t": "T"}, label="HA, Sonntag")
    assert named.label == "HA, Sonntag"
    assert partial(named, RH=Q_(1, "")).label == "HA, Sonntag"
    assert partial(ha, RH=Q_(1, "")).label == ha.key


def test_fixed_levels_let_interpolation_schemes_compare_along_the_pressure() -> None:
    levels: dict[str, Any] = {
        "p_1": Q_(850, "hPa"),
        "p_2": Q_(500, "hPa"),
        "T_1": Q_(278, "K"),
        "T_2": Q_(252, "K"),
    }
    in_ln_p = partial(FORMULATIONS["log_pressure_interpolation_temperature"], **levels)
    in_p = partial(FORMULATIONS["pressure_interpolation_temperature"], **levels)
    assert [v.identifier for v in in_ln_p.inputs] == ["p"]
    assert in_ln_p.key == (
        "log_pressure_interpolation_temperature"
        "(p_1=850 hPa, p_2=500 hPa, T_1=278 K, T_2=252 K)"
    )
    assert in_ln_p.label == FORMULATIONS["log_pressure_interpolation_temperature"].label
    assert (
        in_ln_p.citations
        == FORMULATIONS["log_pressure_interpolation_temperature"].citations
    )
    assert in_ln_p.output.kind == "ThermodynamicTemperature"
    pressures = Q_(np.array([850.0, 700.0, 500.0]), "hPa")
    table = compare([in_p], in_ln_p, {"Pressure": pressures})
    values = table.values[in_p.key].to("K").magnitude
    assert values == pytest.approx([278.0, 278.0 - 26.0 * 150 / 350, 252.0])
    # The levels are the same: the schemes meet there.
    deviation = table.relative_deviations[in_p.key]
    assert deviation[[0, 2]] == pytest.approx([0.0, 0.0])
    # Named, it shows its own label rather than a citation.
    named = partial(in_ln_p.formulation, label="T in ln p", **levels)
    assert (named.label, named.citations) == ("T in ln p", ())
    with pytest.raises(ValueError, match="has no input q"):
        partial(FORMULATIONS["log_pressure_interpolation_temperature"], q=Q_(1, ""))
    # Rebuilt, it keeps what it was: named or not.
    rebuilt = dataclasses.replace(in_ln_p, values={**levels, "T_2": Q_(250, "K")})
    assert (rebuilt.named, rebuilt.citations) == (False, in_ln_p.citations)
    assert dataclasses.replace(named, values=levels).named


def test_one_value_never_feeds_several_inputs() -> None:
    # p, p_1 and p_2 are pressures: one value for all three would put the
    # target on the levels.
    scheme = FORMULATIONS["log_pressure_interpolation_temperature"]
    temperatures: dict[str, Any] = {"T_1": Q_(278, "K"), "T_2": Q_(252, "K")}
    with pytest.raises(ValueError, match="would feed p, p_1, p_2.*partial"):
        compare(
            [scheme],
            partial(scheme, **temperatures),
            {"Pressure": Q_([850.0, 700.0], "hPa")},
        )


@pytest.mark.parametrize("value", [850, Q_(850, "K")])
def test_partial_needs_a_quantity_of_the_input_dimension(value: Any) -> None:
    scheme = FORMULATIONS["log_pressure_interpolation_temperature"]
    with pytest.raises(ValueError, match="p_1 needs a quantity convertible to HectoPA"):
        partial(scheme, p_1=value)


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


def test_a_temperature_feeds_one_in_the_other_unit_and_a_dew_point_a_temperature() -> (
    None
):
    from nomogram.inversion import dew_point

    # The ISO standard atmosphere gives kelvins; Tetens takes degrees Celsius.
    profile = compose(
        FORMULATIONS["tetens1930"], {"t": FORMULATIONS["iso2533_temperature"]}
    )
    at_sea_level = profile.evaluate(H=Q_(0.0, "km"))
    direct = FORMULATIONS["tetens1930"].evaluate(t=Q_(15.0, "degC"))
    assert at_sea_level.magnitude == pytest.approx(direct.magnitude)
    # A dew point is the temperature at which the saturation vapour
    # pressure is evaluated: through the inverse, the round trip is exact.
    back = compose(SONNTAG, {"t": dew_point(SONNTAG)})
    assert back.evaluate(e=Q_(12.0, "hPa")).to("hPa").magnitude == pytest.approx(12.0)
    # A difference never feeds a point, nor a pressure a temperature.
    with pytest.raises(ValueError, match="but t is CelsiusTemperature"):
        compose(SONNTAG, {"t": FORMULATIONS["sonntag1990_magnus"]})
