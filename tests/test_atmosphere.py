# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the atmosphere family: vertical coordinates and their kinds."""

import math
from pathlib import Path
from typing import Any

import numpy as np
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
        ("SeaLevelPressure", "Pressure"),
        ("LapseRate", "TemperatureGradient"),
    ],
)
def test_a_kind_feeds_the_inputs_of_its_ancestors(output: str, input: str) -> None:
    assert feeds(output, input)


@pytest.mark.parametrize(
    ("output", "input"),
    [
        # Apart by gravity: 25 m at 8 km at 22°N (WMO-No. 8, table 12.10).
        ("GeopotentialHeight", "Altitude"),
        # A geopotential height of the standard atmosphere, not of the
        # actual one; siblings, as in QUDT.
        ("PressureAltitude", "GeopotentialHeight"),
        ("PressureAltitude", "Altitude"),
        # Aviation's altitude and height are altimetric (SERA, GM1).
        ("AltimetricAltitude", "Altitude"),
        ("AltimetricHeight", "Height"),
        ("AltimetricAltitude", "PressureAltitude"),
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


def test_the_altitude_of_aviation_is_altimetric() -> None:
    # SERA's guidance material: "altimetric rather than geometric".
    for term, kind, geometric in [
        ("altitude", "AltimetricAltitude", "Altitude"),
        ("height", "AltimetricHeight", "Height"),
    ]:
        kinds = {m.community: m.kind for m in CATALOG.trade_terms[term].meanings}
        assert kinds == {"aviation (ICAO, SERA)": kind, "CF, meteorology": geometric}
        assert CATALOG.kinds[kind].specialization_of == "Length"


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


def test_the_reference_atmosphere_of_itu_r_p835() -> None:
    heights = Q_([0.0, 11.0, 20.0, 84.852], "km")
    temperature = FORMULATIONS["itu_r_p835_temperature"].evaluate(H=heights)
    assert temperature.magnitude == pytest.approx([288.15, 216.65, 216.65, 186.946])
    pressure = FORMULATIONS["itu_r_p835_pressure"]
    assert pressure.evaluate(H=Q_(0.0, "km")).magnitude == pytest.approx(1013.25)
    # The source's layers meet with small jumps: 3a ends at 226.3206 hPa,
    # 3b starts at 226.3226 hPa.
    end = pressure.evaluate(H=Q_(11.0, "km")).magnitude
    start = pressure.evaluate(H=Q_(11.000001, "km")).magnitude
    assert end == pytest.approx(226.3206, abs=1e-4)
    assert 0 < (start - end) / end < 2e-5


def test_a_layer_of_p835_is_the_general_form_of_the_us_standard_atmosphere() -> None:
    # 3a with k = 34.1632 against 33a with the constants of 1976
    # (g0' M0 / R* = 34.163195 K/km').
    p835 = FORMULATIONS["itu_r_p835_pressure"].evaluate(H=Q_(5.0, "km"))
    ussa = FORMULATIONS["ussa1976_pressure_layer_gradient"].evaluate(
        P_b=Q_(1013.25, "hPa"),
        T_b=Q_(288.15, "K"),
        L=Q_(-6.5, "K/km"),
        H=Q_(5.0, "km"),
        H_b=Q_(0.0, "km"),
    )
    assert p835.to("hPa").magnitude == pytest.approx(ussa.to("hPa").magnitude, rel=1e-6)


def test_pressure_altitude_by_inversion_and_from_the_nws() -> None:
    from nomogram.inversion import invert
    from nomogram.model import Variable

    altitude = invert(
        FORMULATIONS["itu_r_p835_pressure"],
        "H",
        output=Variable("H_p", "PressureAltitude", "KiloM", "Pressure altitude"),
        input=Variable("P", "Pressure", "HectoPA", "Pressure"),
    )
    p835 = altitude.evaluate(P=Q_(500, "hPa")).to("m").magnitude
    nws = FORMULATIONS["nws_pressure_altitude"].evaluate(P=Q_(500, "hPa"))
    assert p835 == pytest.approx(5574.44, abs=0.01)
    assert p835 - nws.to("m").magnitude == pytest.approx(2.33, abs=0.01)


def test_interpolation_schemes_on_the_reference_atmosphere() -> None:
    # Between 850 and 500 hPa of the ITU-R reference atmosphere, a layer of
    # constant gradient: linear in height is exact, linear in ln p is
    # 0.31 K too warm at 700 hPa, linear in p (FULL-POS, ECMWF option)
    # 1.36 K too cold; the height linear in ln p is 48 m too low, exact only
    # for an isothermal layer.
    from nomogram.inversion import invert
    from nomogram.model import Variable

    height = invert(
        FORMULATIONS["itu_r_p835_pressure"],
        "H",
        output=Variable("H", "GeopotentialHeight", "KiloM", "Geopotential height"),
        input=Variable("P", "Pressure", "HectoPA", "Pressure"),
    )
    temperature = FORMULATIONS["itu_r_p835_temperature"]
    levels = {p: height.evaluate(P=Q_(p, "hPa")).to("m") for p in (850, 700, 500)}
    t = {p: temperature.evaluate(H=h) for p, h in levels.items()}
    pressures: dict[str, Any] = {
        "p": Q_(700, "hPa"),
        "p_1": Q_(850, "hPa"),
        "p_2": Q_(500, "hPa"),
    }
    two_levels: dict[str, Any] = {"T_1": t[850], "T_2": t[500]}
    truth = t[700].magnitude
    in_ln_p = FORMULATIONS["log_pressure_interpolation_temperature"]
    in_p = FORMULATIONS["pressure_interpolation_temperature"]
    in_z = FORMULATIONS["height_interpolation_temperature"]
    assert in_ln_p.evaluate(**pressures, **two_levels).magnitude - truth == (
        pytest.approx(0.31, abs=0.01)
    )
    assert in_p.evaluate(**pressures, **two_levels).magnitude - truth == (
        pytest.approx(-1.36, abs=0.01)
    )
    # The layers are linear in the geopotential height; the scheme takes
    # geometric altitudes, a few metres above it here: 4 mK.
    geometric = FORMULATIONS["itu_r_p835_geometric_altitude"]
    z = {p: geometric.evaluate(Z=h).to("m") for p, h in levels.items()}
    at_z = in_z.evaluate(z=z[700], z_1=z[850], z_2=z[500], **two_levels)
    assert at_z.magnitude - truth == pytest.approx(0.0041, abs=5e-5)
    z_in_ln_p = FORMULATIONS["log_pressure_interpolation_geopotential_height"].evaluate(
        **pressures, Z_1=levels[850], Z_2=levels[500]
    )
    assert (z_in_ln_p - levels[700]).magnitude == pytest.approx(-48.4, abs=0.1)


def test_fullpos_below_the_surface() -> None:
    # The surface temperature through the standard gradient, 2000 Pa below
    # the model level: about 180 m, 1.17 K warmer.
    surface = FORMULATIONS["fullpos_surface_temperature"].evaluate(
        T_L=Q_(285, "K"), p_s=Q_(95000, "Pa"), p_L=Q_(93000, "Pa")
    )
    assert surface.magnitude == pytest.approx(286.166, abs=1e-3)
    # FULL-POS (ECMWF) and WMO reduce to sea level through the same gradient
    # of 0.0065 K/m: 0.0014 hPa apart for a dry station at 500 m.
    fullpos = FORMULATIONS["fullpos_mean_sea_level_pressure"].evaluate(
        p_s=Q_(950, "hPa"),
        Phi_s=Q_(500 * 9.80665, "m**2/s**2"),
        T_s=Q_(288.15, "K"),
    )
    wmo = FORMULATIONS["wmo_sea_level_pressure"].evaluate(
        p_s=Q_(950, "hPa"), H_p=Q_(500, "m"), T_s=Q_(288.15, "K"), e_s=Q_(0, "hPa")
    )
    assert fullpos.to("hPa").magnitude == pytest.approx(1007.683, abs=1e-3)
    assert abs(fullpos.to("hPa").magnitude - wmo.magnitude) < 0.002


def test_ecmwf_extrapolation_below_the_surface() -> None:
    # A surface at 850 hPa, 280 K and 1400 m; the 1000 hPa level lies
    # below it: warmer, and lower. The third-order expansions of ECMWF and
    # FULL-POS stay within about 10^-5 K and 1 cm of the exact forms.
    below: dict[str, Any] = {
        "p": Q_(1000, "hPa"),
        "p_s": Q_(850, "hPa"),
        "T_s": Q_(280, "K"),
    }
    expanded = FORMULATIONS["ecmwf_temperature_below_ground"].evaluate(**below)
    exact = FORMULATIONS["ecmwf_temperature_below_ground_exact"].evaluate(**below)
    assert expanded.magnitude == pytest.approx(288.793, abs=1e-3)
    assert abs(expanded.magnitude - exact.magnitude) < 1.1e-5
    surface = Q_(1400 * 9.80665, "m**2/s**2")
    height = FORMULATIONS["geopotential_height_definition"]
    phi = FORMULATIONS["ecmwf_geopotential_below_ground"].evaluate(
        **below, Phi_s=surface
    )
    phi_exact = FORMULATIONS["ecmwf_geopotential_below_ground_exact"].evaluate(
        **below, Phi_s=surface
    )
    z = height.evaluate(Phi=phi).to("m").magnitude
    assert z == pytest.approx(47.16, abs=0.01)
    assert abs(z - height.evaluate(Phi=phi_exact).to("m").magnitude) < 0.01
    station: dict[str, Any] = {
        "p_s": Q_(850, "hPa"),
        "Phi_s": surface,
        "T_s": Q_(280, "K"),
    }
    approx = FORMULATIONS["fullpos_mean_sea_level_pressure"].evaluate(**station)
    msl = FORMULATIONS["ecmwf_mean_sea_level_pressure_exact"].evaluate(**station)
    assert abs((approx - msl).to("hPa").magnitude) < 0.01


def test_the_water_vapour_of_the_reference_atmosphere() -> None:
    # P.835 equation 6: 7.5 g/m3 at the ground, a scale height of 2 km;
    # equation 8 above, the density of a mixing ratio of 2 x 10^-6.
    density = FORMULATIONS["itu_r_p835_water_vapour_density"]
    rho = density.evaluate(z=Q_([0.0, 2.0], "km")).magnitude
    assert rho == pytest.approx([7.5, 7.5 * math.exp(-1)])
    upper = FORMULATIONS["itu_r_p835_water_vapour_density_upper"].evaluate(
        P=Q_(100, "hPa"), T=Q_(216.7, "K")
    )
    assert upper.magnitude == pytest.approx(2e-4)


def test_relative_humidity_linear_in_pressure() -> None:
    # FULL-POS (3.2.5): halfway in pressure, halfway in relative humidity.
    rh = FORMULATIONS["pressure_interpolation_relative_humidity"].evaluate(
        p=Q_(675, "hPa"),
        p_1=Q_(850, "hPa"),
        p_2=Q_(500, "hPa"),
        RH_1=Q_(60, "percent"),
        RH_2=Q_(40, "percent"),
    )
    assert rh.magnitude == pytest.approx(50.0)


def test_a_temperature_in_kelvins_feeds_a_celsius_input() -> None:
    # A composition never inserts an offset: the definition t = T - T0 does.
    from nomogram.comparison import compose

    celsius = FORMULATIONS["celsius_temperature_definition"]
    assert celsius.evaluate(T=Q_(273.15, "K")).magnitude == pytest.approx(0.0)
    in_kelvins = compose(FORMULATIONS["wmo_es_water_moist_air"], {"t": celsius})
    direct = FORMULATIONS["wmo_es_water_moist_air"].evaluate(
        t=Q_(20, "degC"), p=Q_(1000, "hPa")
    )
    converted = in_kelvins.evaluate(T=Q_(293.15, "K"), p=Q_(1000, "hPa"))
    assert converted.magnitude == pytest.approx(direct.magnitude)


def _reference_state(height: Any, pressure: float) -> dict[str, Any]:
    """Temperature, specific humidity and dew point of P.835 at a pressure."""
    h = height.evaluate(P=Q_(pressure, "hPa"))
    t = FORMULATIONS["itu_r_p835_temperature"].evaluate(H=h)
    z = FORMULATIONS["itu_r_p835_geometric_altitude"].evaluate(Z=h)
    rho = FORMULATIONS["itu_r_p835_water_vapour_density"].evaluate(z=z)
    e = FORMULATIONS["itu_r_p453_vapour_pressure_from_density"].evaluate(rho=rho, T=t)
    r = FORMULATIONS["metpy171_mixing_ratio"].evaluate(e=e, p=Q_(pressure, "hPa"))
    q = FORMULATIONS["specific_humidity_from_mixing_ratio"].evaluate(r=r)
    t_d = FORMULATIONS["metpy171_dew_point"].evaluate(e=e)
    return {"T": t, "q": q, "T_d": t_d.to("K")}


def test_relative_humidity_between_two_levels_by_each_practice_of_metpy() -> None:
    # Between 850 and 500 hPa of the ITU-R reference atmosphere, at 700 hPa:
    # the dew point interpolated, by a Skew-T or a stability index, is
    # 2.4 to 2.7 points too humid; the specific humidity, in ln p or in the
    # potential temperature, 12 to 13 points, a chord above a decrease
    # close to exponential, which its logarithm in ln p follows.
    from nomogram.inversion import invert
    from nomogram.model import Variable

    height = invert(
        FORMULATIONS["itu_r_p835_pressure"],
        "H",
        output=Variable("H", "GeopotentialHeight", "KiloM", "Geopotential height"),
        input=Variable("P", "Pressure", "HectoPA", "Pressure"),
    )
    low, mid, high = (_reference_state(height, p) for p in (850, 700, 500))
    truth = FORMULATIONS["metpy171_relative_humidity_from_specific_humidity"].evaluate(
        q=mid["q"], p=Q_(700, "hPa"), T=mid["T"]
    )
    levels: dict[str, Any] = {
        "p": Q_(700, "hPa"),
        "p_1": Q_(850, "hPa"),
        "p_2": Q_(500, "hPa"),
        "T_1": low["T"],
        "T_2": high["T"],
    }
    dew = {"T_d_1": low["T_d"], "T_d_2": high["T_d"]}
    humid = {"q_1": low["q"], "q_2": high["q"]}
    routes = {
        "metpy171_relative_humidity_dew_point_log_pressure": (dew, 2.67),
        "metpy171_relative_humidity_dew_point_pressure": (dew, 2.43),
        "metpy171_relative_humidity_specific_humidity_log_pressure": (humid, 13.38),
        "metpy171_relative_humidity_isentropic": (humid, 12.20),
        "relative_humidity_log_specific_humidity_log_pressure": (humid, 0.03),
    }
    assert truth.to("percent").magnitude == pytest.approx(47.34, abs=0.01)
    for key, (values, error) in routes.items():
        rh = FORMULATIONS[key].evaluate(**levels, **values)
        assert (rh - truth).to("percent").magnitude == pytest.approx(error, abs=0.01), (
            key
        )


def test_a_variable_linear_in_the_potential_temperature_as_metpy_tests_it() -> None:
    # MetPy's test_isentropic_pressure_addition_args_interp: levels at 950
    # and 900 hPa, 292 and 290 K; at 297 K, a variable of 80 and 40 there
    # is 69.197. The specific humidities here carry its numbers.
    two_levels: dict[str, Any] = {
        "p": Q_(936.213, "hPa"),
        "p_1": Q_(950, "hPa"),
        "p_2": Q_(900, "hPa"),
        "T_1": Q_(292, "K"),
        "T_2": Q_(290, "K"),
    }
    q = FORMULATIONS["metpy171_isentropic_specific_humidity"].evaluate(
        **two_levels, q_1=Q_(80, "g/kg"), q_2=Q_(40, "g/kg")
    )
    assert q.to("g/kg").magnitude == pytest.approx(69.197, abs=2e-3)


def test_the_pressure_of_an_isentropic_level_by_the_methods_of_ziv_and_alpert() -> None:
    # The isentropic level of the ITU-R reference atmosphere at 700 hPa,
    # placed from its levels at 850 and 500 hPa: theta linear in p puts it
    # 24 hPa lower, the temperature linear in height, its own profile,
    # within 0.2 hPa (Bechtold's g of 9.81 against the 9.80665 of P.835);
    # the temperature linear in ln p, MetPy's by iteration, 8.4 hPa lower.
    from nomogram.inversion import invert
    from nomogram.model import Variable

    height = invert(
        FORMULATIONS["itu_r_p835_pressure"],
        "H",
        output=Variable("H", "GeopotentialHeight", "KiloM", "Geopotential height"),
        input=Variable("P", "Pressure", "HectoPA", "Pressure"),
    )
    theta = FORMULATIONS["bechtold2015_potential_temperature"]
    h, t, th = {}, {}, {}
    for p in (850, 700, 500):
        h[p] = height.evaluate(P=Q_(p, "hPa"))
        t[p] = FORMULATIONS["itu_r_p835_temperature"].evaluate(H=h[p])
        th[p] = theta.evaluate(T=t[p], p=Q_(p, "hPa"))
    levels: dict[str, Any] = {"p_1": Q_(850, "hPa"), "p_2": Q_(500, "hPa")}
    thetas = {"theta_1": th[850], "theta_2": th[500]}
    temperatures = {"T_1": t[850], "T_2": t[500]}
    methods = {
        "potential_temperature_interpolation_pressure": ({**levels, **thetas}, 723.99),
        "ziv_alpert1994_isentropic_pressure_exner": ({**levels, **thetas}, 708.62),
        "ziv_alpert1994_isentropic_pressure_constant_lapse_rate": (
            {"p_2": levels["p_2"], **temperatures, "Z_1": h[850], "Z_2": h[500]},
            699.85,
        ),
        "ziv_alpert1994_isentropic_pressure_temperature_exner": (
            {**levels, **temperatures},
            695.62,
        ),
    }
    for key, (values, expected) in methods.items():
        p = FORMULATIONS[key].evaluate(theta=th[700], **values)
        assert p.to("hPa").magnitude == pytest.approx(expected, abs=0.01), key
        if "p_1" in values:
            # At the potential temperature of the first level, its pressure.
            at_first = FORMULATIONS[key].evaluate(theta=th[850], **values)
            assert at_first.to("hPa").magnitude == pytest.approx(850.0), key
    # Method (c) has no closed form: the potential temperature of its
    # profile, against the pressure, is solved on a fine grid.
    grid = Q_(np.linspace(500.0, 850.0, 35001), "hPa")
    profile = FORMULATIONS["metpy171_potential_temperature_between_levels"].evaluate(
        p=grid, **levels, **temperatures
    )
    target = FORMULATIONS["metpy171_potential_temperature"].evaluate(
        T=t[700], p=Q_(700, "hPa")
    )
    # theta decreases as p increases: np.interp needs it increasing.
    solved = np.interp(target.magnitude, profile.magnitude[::-1], grid.magnitude[::-1])
    assert solved == pytest.approx(708.39, abs=0.02)


def test_the_pressure_altitude_of_the_iso_standard_atmosphere() -> None:
    # The printed hypsometrical tables of ISO 2533 Addendum 1, to the metre:
    # table 1 at 5.00, 5.10 and 5.20 hPa, table 2 at 1000, 1020, 1049 hPa.
    altitude = FORMULATIONS["iso2533_pressure_altitude"]
    printed = {
        5.00: 35776,
        5.10: 35638,
        5.20: 35502,
        1000.0: 111,
        1020.0: -56,
        1049.0: -293,
    }
    found = altitude.evaluate(p=Q_(list(printed), "hPa")).to("m").magnitude
    # Within a unit of the last digit printed (35 776.5 m printed 35 776).
    assert found == pytest.approx(list(printed.values()), abs=1.0)
    # Its layers meet: the pressures at their bounds come from its formulae.
    for bound in (226.32, 54.7487, 8.68016):
        below, above = altitude.evaluate(p=Q_([bound * (1 + 1e-9), bound], "hPa"))
        assert (above - below).to("m").magnitude == pytest.approx(0.0, abs=0.01)
    # The inversion of the ITU-R reference atmosphere, within 2 cm.
    assert altitude.evaluate(p=Q_(500, "hPa")).to("m").magnitude == pytest.approx(
        5574.44, abs=0.02
    )
    outside = altitude.evaluate(p=Q_([1.0, 1300.0], "hPa")).magnitude
    assert np.isnan(outside).all()


def test_the_dry_adiabatic_gradient() -> None:
    # Bechtold (2015), equation 38: a decrease of 0.98 K per 100 m.
    gradient = FORMULATIONS["bechtold2015_dry_adiabatic_gradient"].evaluate()
    assert gradient.to("K/km").magnitude == pytest.approx(-9.76, abs=0.01)


def test_the_standard_acceleration_of_free_fall() -> None:
    g_n = CATALOG.constants["g_n_cgpm1901"]
    assert g_n.value == 9.80665
    assert g_n.unit == "M-PER-SEC2"
    assert g_n.nature is ConstantNature.CONVENTIONAL


def test_the_lapse_rate_and_the_vertical_gradient_are_defined_from_each_other() -> None:
    lapse = CATALOG.formulations["lapse_rate_definition"]
    gradient = CATALOG.formulations["vertical_temperature_gradient_definition"]
    assert lapse.output.kind == gradient.inputs[0].kind == "LapseRate"
    assert gradient.output.kind == lapse.inputs[0].kind == "VerticalTemperatureGradient"
    cooling = Q_(-0.0065, "K/m")
    assert lapse.evaluate(dTdz=cooling).magnitude == pytest.approx(0.0065)
    back = gradient.evaluate(Gamma=lapse.evaluate(dTdz=cooling))
    assert back.magnitude == pytest.approx(-0.0065)


def test_the_dry_adiabatic_lapse_rate_comes_through_the_definition() -> None:
    # Bechtold prints dT/dz = -g/c_pd (equation 38); his lapse rate is g/c_pd.
    printed = CATALOG.formulations["bechtold2015_dry_adiabatic_gradient"]
    composed = CATALOG.formulations["bechtold2015_dry_adiabatic_lapse_rate"]
    assert printed.output.kind == "VerticalTemperatureGradient"
    assert composed.output.kind == "LapseRate"
    assert composed.derivation is not None
    assert composed.evaluate().magnitude == pytest.approx(-printed.evaluate().magnitude)
    assert composed.evaluate().magnitude == pytest.approx(0.0098, abs=1e-4)


LAYER = """
[catalog]
name = "mine"
format = 2
requires = ["atmosphere"]

[formulations."mine:layer"]
label = "Pressure in a layer, from its lapse rate"
composition = {{ outer = "ussa1976_pressure_layer_gradient", inner = {{ L = "{inner}" }} }}
"""


def test_a_lapse_rate_feeds_a_vertical_gradient_only_through_the_definition(
    tmp_path: Path,
) -> None:
    from nomogram.catalog import CatalogError

    path = tmp_path / "mine.toml"
    path.write_text(
        LAYER.format(inner="vertical_temperature_gradient_definition"), encoding="utf-8"
    )
    layer = catalog(extra=[path]).formulations["mine:layer"]
    gradient = CATALOG.formulations["ussa1976_pressure_layer_gradient"]
    common: dict[str, Any] = {
        "P_b": Q_(101325.0, "Pa"),
        "T_b": Q_(288.15, "K"),
        "H": Q_(5000.0, "m"),
        "H_b": Q_(0.0, "m"),
    }
    expected = gradient.evaluate(L=Q_(-0.0065, "K/m"), **common)
    found = layer.evaluate(Gamma=Q_(0.0065, "K/m"), **common)
    assert found.magnitude == pytest.approx(expected.magnitude)
    # A lapse rate straight into the gradient: siblings never feed each other.
    direct = tmp_path / "direct.toml"
    direct.write_text(
        LAYER.format(inner="bechtold2015_dry_adiabatic_lapse_rate"), encoding="utf-8"
    )
    with pytest.raises(CatalogError, match="computes LapseRate, but L is"):
        catalog(extra=[direct])


@pytest.mark.parametrize(
    ("key", "inputs", "printed"),
    [
        # ISO 2533, Table 3: the characteristics at mean sea level.
        ("iso2533_air_density", {"p": Q_(101325.0, "Pa"), "T": Q_(288.15, "K")}, 1.225),
        (
            "iso2533_pressure_scale_height",
            {"T": Q_(288.15, "K"), "g": Q_(9.80665, "m/s^2")},
            8434.5,
        ),
        ("iso2533_speed_of_sound", {"T": Q_(288.15, "K")}, 340.294),
        ("iso2533_dynamic_viscosity", {"T": Q_(288.15, "K")}, 17.894e-6),
        (
            "iso2533_kinematic_viscosity_of_air",
            {"p": Q_(101325.0, "Pa"), "T": Q_(288.15, "K")},
            14.607e-6,
        ),
        ("iso2533_thermal_conductivity", {"T": Q_(288.15, "K")}, 25.343e-3),
    ],
)
def test_the_iso_standard_atmosphere_gives_its_sea_level_characteristics(
    key: str, inputs: dict[str, Any], printed: float
) -> None:
    found = CATALOG.formulations[key].evaluate(**inputs)
    assert found.magnitude == pytest.approx(printed, rel=5e-5)


def test_the_acceleration_of_free_fall_decreases_with_altitude() -> None:
    gravity = CATALOG.formulations["iso2533_acceleration_of_free_fall"]
    assert gravity.evaluate(h=Q_(0.0, "m")).magnitude == pytest.approx(9.80665)
    # g_n (r / (r + h))^2 with r = 6 356 766 m.
    expected = 9.80665 * (6356766.0 / (6356766.0 + 11000.0)) ** 2
    assert gravity.evaluate(h=Q_(11.0, "km")).magnitude == pytest.approx(expected)


def test_the_iso_standard_cites_lambert_and_the_geopotential_altitude() -> None:
    lambert = CATALOG.formulations["wmo_normal_gravity_smithsonian"]
    assert "iso2533_1975" in {c.reference for c in lambert.citations}
    definition = CATALOG.formulations["geopotential_height_definition"]
    assert any(
        c.reference == "iso2533_1975" and c.equation == "6"
        for c in definition.citations
    )
    meaning = CATALOG.trade_terms["geopotential_altitude"].meanings[0]
    assert meaning.kind == "GeopotentialHeight"
    assert meaning.sources == ("iso2533_1975",)


def test_a_scale_height_is_a_length_but_no_vertical_coordinate() -> None:
    assert CATALOG.kinds["PressureScaleHeight"].specialization_of == "Length"
    assert feeds("PressureScaleHeight", "Length")
    assert not feeds("PressureScaleHeight", "GeopotentialHeight")
    assert not feeds("PressureScaleHeight", "Altitude")


@pytest.mark.parametrize(
    ("height", "printed"),
    # ISO 2533, Table 4; Addendum 2 extrapolates the troposphere to -5 km.
    [(-5.0, 320.65), (-2.0, 301.15), (0.0, 288.15), (11.0, 216.65), (47.0, 270.65)]
    + [(71.0, 214.65), (80.0, 196.65)],
)
def test_the_iso_temperature_follows_table_4(height: float, printed: float) -> None:
    temperature = CATALOG.formulations["iso2533_temperature"]
    found = temperature.evaluate(H=Q_(height, "km"), outside="raise")
    assert found.magnitude == pytest.approx(printed)


def test_the_iso_temperature_holds_where_one_of_its_sources_says() -> None:
    temperature = CATALOG.formulations["iso2533_temperature"]
    stated = {
        c.reference: d.bounds["H"] for c in temperature.citations for d in c.domains
    }
    assert stated == {"iso2533_1975": (-2.0, 80.0), "iso2533_add2_1997": (-5.0, 2.0)}
    assert math.isnan(temperature.evaluate(H=Q_(-6.0, "km")).magnitude)


def test_the_pressure_of_addendum_1_inverts_its_pressure_altitude() -> None:
    pressure = CATALOG.formulations["iso2533_pressure"]
    altitude = CATALOG.formulations["iso2533_pressure_altitude"]
    assert pressure.inputs[0].kind == altitude.output.kind == "PressureAltitude"
    assert pressure.evaluate(H_p=Q_(0.0, "m")).magnitude == pytest.approx(
        1013.25, abs=1e-3
    )
    heights = np.linspace(-1449.0, 46999.0, 2001)
    back = (
        altitude.evaluate(p=pressure.evaluate(H_p=Q_(heights, "m"))).to("m").magnitude
    )
    # Within the precision of the printed coefficients: a few millimetres.
    assert np.nanmax(np.abs(back - heights)) < 0.01
    assert not np.isnan(back).any()


def test_the_iso_pressure_of_a_layer_differs_from_the_us_one_by_its_gas_constant() -> (
    None
):
    iso = CATALOG.formulations["iso2533_pressure_layer_gradient"]
    us = CATALOG.formulations["ussa1976_pressure_layer_gradient"]
    base: dict[str, Any] = {
        "T_b": Q_(288.15, "K"),
        "H": Q_(11000.0, "m"),
        "H_b": Q_(0.0, "m"),
    }
    found = iso.evaluate(p_b=Q_(101325.0, "Pa"), beta=Q_(-0.0065, "K/m"), **base)
    reference = us.evaluate(P_b=Q_(101325.0, "Pa"), L=Q_(-0.0065, "K/m"), **base)
    # R = 287.052 87 against R*/M_0 = 287.053 01 J/(kg K).
    assert found.magnitude == pytest.approx(reference.magnitude, rel=2e-6)
    assert found.magnitude != pytest.approx(reference.magnitude, rel=1e-7)
    isothermal = CATALOG.formulations["iso2533_pressure_layer_isothermal"]
    top = isothermal.evaluate(
        p_b=found, T=Q_(216.65, "K"), H=Q_(20000.0, "m"), H_b=Q_(11000.0, "m")
    )
    assert top.to("hPa").magnitude == pytest.approx(54.7487, rel=1e-5)


def test_dry_and_moist_air_densities_never_feed_each_other() -> None:
    assert CATALOG.formulations["iso2533_air_density"].output.kind == "DensityOfDryAir"
    assert feeds("DensityOfDryAir", "Density")
    assert not feeds("DensityOfDryAir", "DensityOfMoistAir")
    assert not feeds("DensityOfMoistAir", "DensityOfDryAir")
