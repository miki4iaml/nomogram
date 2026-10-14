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
