# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Reference case: saturation vapour pressure and absolute humidity of air.

Expected values come from published sources, never from the formulas
under test: IAPWS SR1-86(1992) Table 1, and the deviations and accuracy
claims of Alduchov and Eskridge (1996, Tables II and III).
"""

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.comparison import compare, compose
from nomogram.model import Outside
from nomogram.units import Q_

CATALOG = catalog()
FORMULATIONS = CATALOG.formulations
IAPWS = FORMULATIONS["iapws_sr1_86"]
SATURATION = CATALOG.formulations_of("SaturationVapourPressureOverWater")
IDEAL_GAS = FORMULATIONS["mass_concentration_ideal_gas"]


@pytest.mark.parametrize(
    ("kelvin", "pascal"),
    [(273.16, 611.657), (373.1243, 0.101325e6), (647.096, 22.064e6)],
)
def test_iapws_reproduces_table_1_of_the_release(kelvin: float, pascal: float) -> None:
    # Table 1 gives six significant figures.
    result = IAPWS.evaluate(T=Q_(kelvin, "K")).to("Pa").magnitude
    assert result == pytest.approx(pascal, rel=1e-6)


@pytest.mark.parametrize(
    ("celsius", "hectopascal"),
    [(20.0, 23.392), (40.0, 73.851), (100.0, 1014.18)],
)
def test_iapws_at_usual_temperatures(celsius: float, hectopascal: float) -> None:
    # At 100 degC the saturation pressure is 1014.18 hPa, not 1013.25.
    result = IAPWS.evaluate(T=Q_(celsius, "degC")).to("hPa").magnitude
    assert result == pytest.approx(hectopascal, abs=0.001 if celsius < 100 else 0.01)


def test_zero_celsius_is_just_below_the_iapws_domain() -> None:
    # 0 degC = 273.15 K < 273.16 K, the triple point: NaN unless asked.
    assert np.isnan(IAPWS.evaluate(T=Q_(0, "degC")).magnitude)
    value = IAPWS.evaluate(T=Q_(0, "degC"), outside="ignore").to("hPa").magnitude
    assert value == pytest.approx(6.1121, abs=1e-4)


def test_every_formulation_stays_close_to_iapws_between_0_and_40_celsius() -> None:
    grid = Q_(np.linspace(0.01, 40.0, 41), "degC")
    comparison = compare(SATURATION, IAPWS, {"ThermodynamicTemperature": grid})
    worst = comparison.max_abs_deviation()
    # Alduchov and Eskridge (1996, Table III) give at most 3.214 % (Tetens)
    # against three basic formulations over -40..50 degC; above 0 degC all
    # stay well within 0.5 % of IAPWS.
    assert max(worst.values()) < 0.005
    assert worst["iapws_sr1_86"] == 0.0


def test_sonntag_magnus_deviation_at_20_celsius() -> None:
    comparison = compare(
        [FORMULATIONS["sonntag1990_magnus"]],
        IAPWS,
        {"CelsiusTemperature": Q_(20, "degC")},
    )
    deviation = comparison.relative_deviations["sonntag1990_magnus"]
    assert float(deviation) == pytest.approx(-0.0028, abs=0.0001)


def test_magnus_forms_overestimate_at_100_celsius_outside_their_domain() -> None:
    magnus = [FORMULATIONS[k] for k in ("sonntag1990_magnus", "alduchov_eskridge1996")]
    nan = compare(magnus, IAPWS, {"CelsiusTemperature": Q_(100, "degC")})
    assert np.isnan(nan.relative_deviations["alduchov_eskridge1996"])
    computed = compare(
        magnus, IAPWS, {"CelsiusTemperature": Q_(100, "degC")}, outside="ignore"
    )
    for key in ("sonntag1990_magnus", "alduchov_eskridge1996"):
        assert 0.02 < float(computed.relative_deviations[key]) < 0.03


def test_aekr_stated_domain_and_criterion() -> None:
    aekr = FORMULATIONS["alduchov_eskridge1996"]
    domain = aekr.domains[0]
    assert domain.bounds["t"] == (-40.0, 50.0)
    assert "0.384 %" in (domain.criterion or "")
    assert np.isnan(aekr.evaluate(t=Q_(-45, "degC")).magnitude)


@pytest.mark.parametrize(
    ("key", "uncertainty"), [("sonntag1990_magnus", "0.6 %"), ("wmo2008_ice", "1 %")]
)
def test_the_wmo_guide_states_no_uncertainty_for_its_magnus_forms(
    key: str, uncertainty: str
) -> None:
    # WMO-No. 8 (2024), Annex 4.B gives ranges, no uncertainty; the WMO
    # ET-QTC training unit states one, and is cited for it on its own.
    citations = {c.reference: c for c in FORMULATIONS[key].citations}
    guide = citations["wmo2024"].domains[0].criterion or ""
    training = citations["wmo_etqtc2025"].domains[0].criterion or ""
    assert "No uncertainty stated" in guide
    assert "%" not in guide
    assert f"up to {uncertainty} (k = 2)" in training


def test_the_wmo_magnus_form_over_ice_keeps_to_its_stated_domain() -> None:
    ice = FORMULATIONS["wmo2008_ice"]
    assert np.isnan(ice.evaluate(t=Q_(5, "degC")).magnitude)
    assert np.isnan(ice.evaluate(t=Q_(-70, "degC")).magnitude)
    hectopascal = ice.evaluate(t=Q_(-10, "degC")).to("hPa").magnitude
    assert hectopascal == pytest.approx(2.5988, abs=1e-4)


def test_the_wmo_training_unit_is_linked_to_both_magnus_forms() -> None:
    linked = {entry.key for entry in CATALOG.used_by("references.wmo_etqtc2025")}
    assert linked == {"sonntag1990_magnus", "wmo2008_ice"}
    assert [entry.key for entry in CATALOG.used_by("notations.wmo")] == [
        "sonntag1990_magnus"
    ]


@pytest.mark.parametrize(
    ("celsius", "grams", "outside"),
    [(0.0, 4.848, "ignore"), (20.0, 17.290, "nan"), (40.0, 51.099, "nan")],
)
def test_absolute_humidity_at_saturation_from_iapws(
    celsius: float, grams: float, outside: Outside
) -> None:
    ha = compose(IDEAL_GAS, {"e_s": IAPWS})
    result = ha.evaluate(RH=Q_(100, "percent"), T=Q_(celsius, "degC"), outside=outside)
    assert result.to("g/m^3").magnitude == pytest.approx(grams, abs=0.001)


def test_absolute_humidity_compared_across_vapour_pressure_formulations() -> None:
    compositions = [
        compose(IDEAL_GAS, {"e_s": f}, bind={f.inputs[0].identifier: "T"})
        for f in SATURATION
    ]
    reference = next(c for c in compositions if c.key.endswith("[e_s=iapws_sr1_86]"))
    comparison = compare(
        compositions,
        reference,
        {
            "RelativeHumidity": Q_(np.array([0.5, 1.0]), "dimensionless"),
            "ThermodynamicTemperature": Q_(20, "degC"),
        },
    )
    assert len(comparison.values) == len(SATURATION)
    # HA is proportional to e_s: same relative deviations as e_s itself.
    sonntag = comparison.relative_deviations[
        "mass_concentration_ideal_gas[e_s=sonntag1990_magnus]"
    ]
    assert sonntag == pytest.approx([-0.0028, -0.0028], abs=0.0001)


def test_murray_is_referred_to_the_triple_point() -> None:
    # Offset 273.16 K, not 273.15 K: the constant C is the value there.
    murray = FORMULATIONS["murray1967"]
    assert murray.evaluate(T=Q_(273.16, "K")).magnitude == pytest.approx(6.1078)


def test_goff_gratch_is_referred_to_the_steam_point() -> None:
    goff_gratch = FORMULATIONS["goff_gratch1946"]
    result = goff_gratch.evaluate(T=Q_(373.16, "K")).magnitude
    assert result == pytest.approx(1013.246)
    # Range -50 to 102 degC (Gibbins 1990, as quoted by Vömel).
    assert np.isnan(goff_gratch.evaluate(T=Q_(-60, "degC")).magnitude)


def test_conflicting_attributions_are_recorded() -> None:
    assert "Sonntag (1994)" in (FORMULATIONS["sonntag1990"].note or "")
    assert "GG46" in (FORMULATIONS["goff1957"].note or "")


MIXING_RATIO = FORMULATIONS["mixing_ratio_from_vapour_pressure"]
SPECIFIC_HUMIDITY = FORMULATIONS["specific_humidity_from_mixing_ratio"]


def test_mixing_ratio_reproduces_psychrolib() -> None:
    # PsychroLib (tests, commit 3066345): 25 degC, standard pressure at 500 m.
    result = MIXING_RATIO.evaluate(e=Q_(3169.7, "Pa"), p=Q_(95461, "Pa"))
    assert result.magnitude == pytest.approx(0.0213603998047487, rel=1e-9)


@pytest.mark.parametrize(
    ("celsius", "ashrae", "tolerance"),
    # Saturation humidity ratio at 101325 Pa, ASHRAE Handbook -
    # Fundamentals (2017), ch. 1, Table 2, with the tolerances PsychroLib
    # applies to the same values. The ideal gas formula stays 0.4 to
    # 0.6 % below: the table likely includes non-ideal effects.
    [(5.0, 0.005425, 0.005), (25.0, 0.020173, 0.005), (50.0, 0.086863, 0.01)],
)
def test_saturation_mixing_ratio_against_ashrae_table(
    celsius: float, ashrae: float, tolerance: float
) -> None:
    saturated = compose(MIXING_RATIO, {"e": IAPWS})
    result = saturated.evaluate(T=Q_(celsius, "degC"), p=Q_(101325, "Pa"))
    assert result.magnitude == pytest.approx(ashrae, rel=tolerance)
    assert result.magnitude < ashrae


def test_specific_humidity_from_mixing_ratio() -> None:
    saturated = compose(MIXING_RATIO, {"e": IAPWS})
    specific = compose(SPECIFIC_HUMIDITY, {"r": saturated})
    assert [v.identifier for v in specific.inputs] == ["p", "T"]
    result = specific.evaluate(T=Q_(25, "degC"), p=Q_(101325, "Pa"))
    assert result.magnitude == pytest.approx(0.020173 / 1.020173, rel=0.005)


def test_mixing_ratio_from_temperature_humidity_and_pressure() -> None:
    vapour = compose(
        FORMULATIONS["vapour_pressure_from_relative_humidity"], {"e_s": IAPWS}
    )
    mixing = compose(MIXING_RATIO, {"e": vapour})
    assert {v.identifier for v in mixing.inputs} == {"RH", "T", "p"}
    dry = mixing.evaluate(RH=Q_(0, "percent"), T=Q_(20, "degC"), p=Q_(1013.25, "hPa"))
    assert dry.magnitude == 0.0


def test_epsilon_values_follow_their_sources() -> None:
    constants = CATALOG.constants
    # ECMWF IFS CY49R1, Part IV, section 12.5: R_d / R_v.
    assert constants["epsilon_ecmwf_ifs"].value == pytest.approx(
        287.0597 / 461.5250, abs=1e-7
    )
    # MetPy 1.7.1: M_w / M_d.
    assert constants["epsilon_metpy"].value == pytest.approx(
        18.015268 / 28.96546, abs=1e-7
    )
    assert constants["epsilon_ashrae2017"].value == 0.621945
    values = [c.value for k, c in constants.items() if k.startswith("epsilon_")]
    assert max(values) / min(values) - 1 < 1e-4


# --- Saturation over ice ----------------------------------------------------

ICE = CATALOG.formulations_of("SaturationVapourPressureOverIce")
IAPWS_ICE = FORMULATIONS["iapws_r14_08_sublimation"]


def test_iapws_ice_reproduces_table_3_of_the_release() -> None:
    # IAPWS R14-08(2011), Table 3: 8.94735e-6 MPa at 230 K.
    result = IAPWS_ICE.evaluate(T=Q_(230.0, "K")).to("MPa").magnitude
    assert result == pytest.approx(8.94735e-6, rel=1e-6)


def test_iapws_ice_domain_follows_the_release() -> None:
    inside = IAPWS_ICE.evaluate(T=Q_(np.array([50.0, 273.16]), "K")).magnitude
    assert not np.isnan(inside).any()
    outside = IAPWS_ICE.evaluate(T=Q_(np.array([49.0, 273.17]), "K")).magnitude
    assert np.isnan(outside).all()


def test_ice_and_water_meet_at_the_triple_point() -> None:
    triple = Q_(273.16, "K")
    ice = IAPWS_ICE.evaluate(T=triple).to("Pa").magnitude
    water = IAPWS.evaluate(T=triple).to("Pa").magnitude
    assert ice == 611.657
    assert water == pytest.approx(ice, rel=1e-6)


def test_supercooled_water_holds_more_vapour_than_ice() -> None:
    cold = Q_(np.array([-40.0, -20.0, -5.0]), "degC")
    ice = IAPWS_ICE.evaluate(T=cold)
    water = IAPWS.evaluate(T=cold, outside="ignore")
    ratio = (water / ice).to("").magnitude
    assert (ratio > 1).all()
    assert np.all(np.diff(ratio) < 0)  # the gap closes towards 0 degC


def test_ice_formulations_against_iapws() -> None:
    grid = Q_(np.array([-80.0, -40.0, -20.0, -1.0]), "degC")
    comparison = compare(
        ICE, IAPWS_ICE, {"ThermodynamicTemperature": grid}, outside="ignore"
    )
    deviations = comparison.relative_deviations
    # Down to -40 degC, all but two stay within 0.2 % of IAPWS.
    rough = {"murray1967_ice", "marti_mauersberger1993"}
    for key, values in deviations.items():
        if key not in rough:
            assert np.abs(values[1:]).max() < 0.002, key
    # Goff-Gratch, long the reference over ice, sits 0.15 to 0.27 % below.
    assert -0.0027 < deviations["goff_gratch1946_ice"].min()
    assert deviations["goff_gratch1946_ice"].max() < -0.0015
    # Murray's Magnus-Tetens form departs by about 11 % at -80 degC.
    assert deviations["murray1967_ice"][0] == pytest.approx(-0.11, abs=0.002)
    assert deviations["murray1967_ice"][1] == pytest.approx(-0.019, abs=0.001)


def test_hyland_wexler_over_ice_behaves_as_its90() -> None:
    hyland = FORMULATIONS["hyland_wexler1983_ice"]
    assert hyland.inputs[0].scale_basis is not None
    assert hyland.inputs[0].scale_basis.value == "inferred-from-numbers"
    grid = Q_(np.array([-80.0, -60.0, -40.0, -20.0, -1.0]), "degC")
    comparison = compare([hyland], IAPWS_ICE, {"ThermodynamicTemperature": grid})
    assert comparison.max_abs_deviation()["hyland_wexler1983_ice"] < 0.00033
