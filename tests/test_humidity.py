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
from nomogram.inversion import dew_point
from nomogram.model import Outside
from nomogram.semantics import MatchRelation
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
    # the fitted ones stay well within 0.5 % of IAPWS. Integrated with a
    # constant latent heat, Clausius-Clapeyron departs by 4 % at 40 degC.
    for key in (
        "bechtold2015_saturation_vapour_pressure_constant_latent_heat",
        "ambaum2020_constant_latent_heat",
    ):
        assert 0.03 < worst.pop(key) < 0.05, key
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


#: Wikidata items of formulations, checked on 2026-10-24 (Bechtold's on
#: 2026-10-26): the Goff-Gratch item covers the equations over water and
#: over ice, the Buck item the group of his correlations, which Bechtold
#: restates; the Tetens item is the equation over water, and the
#: Clausius-Clapeyron item the relation that Bechtold integrates.
FORMULATION_ITEMS = {
    "bechtold2015_magnus_water": ("Q4787919", MatchRelation.BROAD),
    "bechtold2015_saturation_vapour_pressure_constant_latent_heat": (
        "Q745416",
        MatchRelation.BROAD,
    ),
    "goff_gratch1946": ("Q3433288", MatchRelation.BROAD),
    "goff_gratch1946_ice": ("Q3433288", MatchRelation.BROAD),
    "buck1981_magnus": ("Q4787919", MatchRelation.BROAD),
    "buck1981": ("Q4787919", MatchRelation.BROAD),
    "buck1981_ice": ("Q4787919", MatchRelation.BROAD),
    "buck1996": ("Q4787919", MatchRelation.BROAD),
    "buck1996_ice": ("Q4787919", MatchRelation.BROAD),
    "tetens1930": ("Q28231917", MatchRelation.CLOSE),
}


def test_formulations_link_to_their_wikidata_items() -> None:
    for key, (item, relation) in FORMULATION_ITEMS.items():
        (match,) = CATALOG.formulations[key].matches
        assert match.target == f"http://www.wikidata.org/entity/{item}", key
        assert match.relation is relation, key
    found = {e.key for e in CATALOG.search("Q4787919", section="formulations")}
    assert found == {k for k, (q, _) in FORMULATION_ITEMS.items() if q == "Q4787919"}


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
    # ECMWF IFS CY49R1, Part IV: printed in section 7.5.2 (p. 136), defined
    # as R_d / R_v from section 12.5.
    ifs = constants["epsilon_ecmwf_ifs"]
    assert (ifs.value, ifs.definition) == (0.621981, "R_d / R_v")
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


PSYCHROLIB = FORMULATIONS["psychrolib_saturation_pressure"]


def test_psychrolib_switches_from_ice_to_water_at_the_triple_point() -> None:
    ice = FORMULATIONS["hyland_wexler1983_ice"]
    water = FORMULATIONS["hyland_wexler1983"]
    triple, freezing = Q_(273.16, "K"), Q_(273.15, "K")
    # The branches meet at the triple point (611.657 Pa); at 0 degC, where
    # ASHRAE switches, they leave a step of 0.06 Pa (the note says so).
    assert water.evaluate(T=triple).magnitude == pytest.approx(
        ice.evaluate(T=triple).magnitude, rel=1e-8
    )
    step = water.evaluate(T=freezing).magnitude - ice.evaluate(T=freezing).magnitude
    assert round(step, 2) == 0.06
    assert "step of 0.06 Pa" in (PSYCHROLIB.note or "")
    below, above = PSYCHROLIB.evaluate(T=Q_([273.15, 273.17], "K")).magnitude
    assert below == ice.evaluate(T=freezing).magnitude
    assert above == water.evaluate(T=Q_(273.17, "K")).magnitude
    # PsychroLib refuses temperatures outside -100 to 200 degC.
    assert np.isnan(PSYCHROLIB.evaluate(T=Q_([-101.0, 201.0], "degC")).magnitude).all()


@pytest.mark.parametrize(
    ("celsius", "pascals", "rel", "abs_"),
    # ASHRAE Handbook - Fundamentals (2017), chapter 1, table 3, as the
    # tests of PsychroLib give it: within 300 ppm, except at -60 degC.
    [
        (-60.0, 1.08, None, 0.01),
        (-20.0, 103.24, 3e-4, None),
        (-5.0, 401.74, 3e-4, None),
        (5.0, 872.6, 3e-4, None),
        (25.0, 3169.7, 3e-4, None),
        (50.0, 12351.3, 3e-4, None),
        (100.0, 101418.0, 3e-4, None),
        (150.0, 476101.4, 3e-4, None),
    ],
)
def test_psychrolib_against_the_ashrae_table(
    celsius: float, pascals: float, rel: float | None, abs_: float | None
) -> None:
    found = PSYCHROLIB.evaluate(T=Q_(celsius, "degC")).magnitude
    assert found == pytest.approx(pascals, rel=rel, abs=abs_)


def test_a_dew_point_from_psychrolib_converges_at_the_triple_point() -> None:
    # Continuous at the switch: the inverse finds the temperature back.
    frost_dew = dew_point(PSYCHROLIB)
    t = Q_([-10.0, 0.0, 0.01, 0.02, 10.0], "degC")
    back = frost_dew.evaluate(e=PSYCHROLIB.evaluate(T=t)).to("degC").magnitude
    assert back == pytest.approx(t.magnitude, abs=1e-6)


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
    # Down to -40 degC, all but four stay within 0.2 % of IAPWS.
    rough = {"murray1967_ice", "marti_mauersberger1993"}
    low = {"ecmwf_ifs_saturation_ice", "bechtold2015_magnus_ice"}
    for key, values in deviations.items():
        if key not in rough | low:
            assert np.abs(values[1:]).max() < 0.002, key
    # The Magnus form of the IFS sits 0.08 to 0.21 % below, down to -40 degC.
    for key in low:
        assert -0.0022 < deviations[key][1:].min()
        assert deviations[key][1:].max() < -0.0008
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


# --- WMO-No. 8 (2024), Annex 4.B --------------------------------------------

WMO_F = FORMULATIONS["wmo_enhancement_factor"]
WMO_ES_WATER = FORMULATIONS["wmo_es_water_moist_air"]
WMO_ES_ICE = FORMULATIONS["wmo_es_ice_moist_air"]


def test_wmo_enhancement_factor_stays_within_the_stated_effect_of_pressure() -> None:
    # Note to Annex 4.B: the pressure dependence of f is 0 % to +0.6 %, the
    # formula being meant for pressures around 1000 hPa.
    f = WMO_F.evaluate(p=Q_(np.linspace(500.0, 1100.0, 61), "hPa")).magnitude
    assert np.all(f > 1.0)
    assert np.all(f < 1.006)


@pytest.mark.parametrize(
    ("moist", "pure", "celsius"),
    [
        ("wmo_es_water_moist_air", "sonntag1990_magnus", [-40.0, 0.0, 20.0, 50.0]),
        ("wmo_es_ice_moist_air", "wmo2008_ice", [-60.0, -30.0, -5.0]),
    ],
)
def test_wmo_saturation_in_moist_air_is_f_times_the_pure_phase(
    moist: str, pure: str, celsius: list[float]
) -> None:
    # Equations 4.B.2 and 4.B.4: e'(p, t) = f(p) e(t).
    t, p = Q_(np.array(celsius), "degC"), Q_(850.0, "hPa")
    expected = (
        WMO_F.evaluate(p=p).magnitude * FORMULATIONS[pure].evaluate(t=t).magnitude
    )
    assert FORMULATIONS[moist].evaluate(p=p, t=t).magnitude == pytest.approx(expected)


@pytest.mark.parametrize("hectopascal", [700.0, 1013.25])
def test_wmo_dew_point_inverts_the_saturation_in_moist_air(hectopascal: float) -> None:
    # Equation 4.B.6 is 4.B.2 solved for the temperature.
    t, p = Q_(np.linspace(-40.0, 50.0, 10), "degC"), Q_(hectopascal, "hPa")
    e = WMO_ES_WATER.evaluate(p=p, t=t)
    dew = FORMULATIONS["wmo_dew_point_moist_air"].evaluate(e=e, p=p)
    assert dew.to("degC").magnitude == pytest.approx(t.magnitude, abs=1e-9)


def test_wmo_relative_humidity_is_the_ratio_to_saturation_in_percent() -> None:
    # Equation 4.B.10: U = 100 e'/e'_w(p, t).
    saturation = WMO_ES_WATER.evaluate(p=Q_(1000.0, "hPa"), t=Q_(20.0, "degC"))
    humidity = FORMULATIONS["wmo_relative_humidity"]
    assert humidity.evaluate(e=saturation, e_ws=saturation).to("percent").magnitude == (
        pytest.approx(100.0)
    )
    half = humidity.evaluate(e=saturation / 2, e_ws=saturation)
    assert half.to("percent").magnitude == pytest.approx(50.0)


def test_the_wmo_dew_point_is_found_by_its_kind() -> None:
    found = {f.key for f in CATALOG.search(kind="DewPointTemperature").formulations}
    assert {"wmo_dew_point", "wmo_dew_point_moist_air"} <= found
