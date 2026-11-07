# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The explicit formulas of the NPS evaporation duct model.

Fairall et al. (1978, NPS61-78-005) and Frederickson et al. (1994,
NPS-MR-94-003): the gradient functions of stability, the two-term radio
refractivity, the linear mixing ratio, the Monin-Obukhov length from the
profile scales and the vertical gradient of refractivity.
"""

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.comparison import feeds
from nomogram.semantics import semantic_catalog
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
ONE = "dimensionless"


def value(key: str, **inputs: object) -> np.ndarray:
    return np.asarray(F[key].evaluate(**inputs).magnitude)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("key", "zeta", "expected"),
    [
        # Points where the unstable forms are exact: 16^(-1/4), 8^(-1/3), 4^(-1/2).
        ("fairall1978_gradient_function_momentum_unstable", -1.0, 0.5),
        ("fairall1978_gradient_function_heat_unstable", -7 / 19, 0.5),
        ("frederickson1994_gradient_function_scalar", -3 / 16, 0.5),
        ("fairall1978_gradient_function_momentum_stable", 0.5, 3.35),
        ("fairall1978_gradient_function_heat_stable", 0.5, 4.2),
        ("frederickson1994_gradient_function_scalar", 0.5, 4.5),
        ("frederickson1994_gradient_function_scalar", 0.0, 1.0),
    ],
)
def test_gradient_functions_at_exact_points(
    key: str, zeta: float, expected: float
) -> None:
    assert float(value(key, zeta=Q_(zeta, ONE))) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("quantity", ["momentum", "heat"])
def test_the_branches_of_fairall_meet_at_neutral(quantity: str) -> None:
    key = f"fairall1978_gradient_function_{quantity}"
    zeta = np.array([-2.0, -0.5, -1e-12, 0.0, 1e-12, 0.5, 2.0])
    both = value(key, zeta=Q_(zeta, ONE))
    unstable = value(f"{key}_unstable", zeta=Q_(zeta[:3], ONE))
    stable = value(f"{key}_stable", zeta=Q_(zeta[3:], ONE))
    np.testing.assert_allclose(both, np.concatenate([unstable, stable]), rtol=1e-12)
    np.testing.assert_allclose(both[2:5], 1.0, rtol=1e-9)


def test_the_unstable_piece_of_frederickson_is_that_of_the_ifs() -> None:
    # The expressions compared, beyond the domain Dyer and Hicks state.
    zeta = Q_(np.linspace(-5.0, -0.01, 9), ONE)
    np.testing.assert_allclose(
        value("frederickson1994_gradient_function_scalar", zeta=zeta),
        value("ecmwf_ifs_gradient_function_heat_unstable", zeta=zeta, outside="ignore"),
        rtol=1e-12,
    )


def test_the_two_term_refractivity_is_close_to_that_of_itu_r_p453() -> None:
    # Fairall - P.453 = e/T (5.6 - 2000/T): a few tenths of an N-unit at most.
    t = Q_(np.array([253.15, 273.15, 288.15, 303.15]), "K")
    e = Q_(np.array([1.0, 6.0, 17.0, 42.0]), "hPa")
    p = Q_(1013.25, "hPa")
    fairall = value("fairall1978_radio_refractivity", P=p, e=e, T=t)
    itu = value("itu_r_p453_refractivity_total_pressure", P=p, e=e, T=t)
    assert float(fairall[2]) == pytest.approx(
        77.6 * 1013.25 / 288.15 + 3.73e5 * 17 / 288.15**2, rel=1e-12
    )
    assert np.all(np.abs(fairall - itu) < 0.3)


def test_the_linear_mixing_ratio_is_the_exact_one_near_995_hpa_of_dry_air() -> None:
    e = Q_(10.0, "hPa")
    linear = F["fairall1978_mixing_ratio"].evaluate(e=e)
    assert linear.to("g/kg").magnitude == pytest.approx(6.25, rel=1e-12)
    exact = F["mixing_ratio_from_vapour_pressure"].evaluate(e=e, p=Q_(1005.2, "hPa"))
    assert exact.to("g/kg").magnitude == pytest.approx(6.25, rel=1e-3)


def test_the_obukhov_lengths_of_fairall_and_frederickson_agree_at_295_k() -> None:
    # 0.18 q_* (g/kg) equals 0.61 T q_* (kg/kg) at T = 0.18/0.61 x 1000 K;
    # the two lengths then differ only by their von Karman constants.
    t = Q_(180 / 0.61, "K")
    u_s, t_s = Q_(0.3, "m/s"), Q_(0.1, "K")
    fairall = F["fairall1978_obukhov_length"].evaluate(
        T=t, u_s=u_s, T_s=t_s, q_s=Q_(-0.2, "g/kg"), g=Q_(9.8, "m/s^2")
    )
    frederickson = F["frederickson1994_obukhov_length"].evaluate(
        T=t, u_s=u_s, T_s=t_s, q_s=Q_(-0.2e-3, "kg/kg")
    )
    expected = t.magnitude * 0.09 / (0.35 * 9.8 * (0.1 - 0.18 * 0.2))
    assert fairall.to("m").magnitude == pytest.approx(expected, rel=1e-12)
    assert frederickson.to("m").magnitude == pytest.approx(
        expected * 0.35 / 0.4, rel=1e-12
    )
    assert fairall.magnitude > 0  # T_* > 0: stable, in the profile convention


def test_the_gradient_reaches_the_critical_one_at_the_neutral_duct_height() -> None:
    # Equation 25 at phi_T = 1 gives Z_* = -(7.2 q_* - 1.3 T_*)/(alpha_T kappa 0.125),
    # where equation 24 gives the critical gradient -0.157 m-1 (equation 3).
    q_s, t_s = -0.2, 0.05
    height = -(7.2 * q_s - 1.3 * t_s) / (1.35 * 0.35 * 0.125)
    gradient = F["fairall1978_vertical_refractivity_gradient"].evaluate(
        Phi_H=Q_(1.0, ONE), z=Q_(height, "m"), q_s=Q_(q_s, "g/kg"), T_s=Q_(t_s, "K")
    )
    assert gradient.to("ppm/m").magnitude == pytest.approx(-0.157, rel=1e-12)
    assert gradient.to("1/km").magnitude == pytest.approx(-0.157e-3, rel=1e-12)


def test_n_units_per_metre_are_declared_by_nomogram() -> None:
    unit = semantic_catalog().units["PPM-PER-M"]
    assert unit.iri is None  # absent from QUDT 3.5.3
    assert unit.multiplier == 1e-6
    kind = semantic_catalog().quantity_kinds["InverseLength"]
    assert "PPM-PER-M" in kind.applicable_units


def test_the_profile_scales_feed_no_look_alike() -> None:
    profile = (
        "SurfaceLayerProfileScaleOfPotentialTemperature",
        "SurfaceLayerProfileScaleOfTemperature",
        "SurfaceLayerProfileScaleOfMixingRatio",
        "SurfaceLayerProfileScaleOfSpecificHumidity",
    )
    for kind in profile:
        others = [k for k in profile if k != kind]
        others += ["SurfaceLayerScaleOfSpecificHumidity"]  # the IFS's, by the flux
        for other in others:
            assert not feeds(kind, other)
            assert not feeds(other, kind)
    assert feeds("VerticalRadioRefractivityGradient", "InverseLength")
    assert not feeds("VerticalRadioRefractivityGradient", "RadioRefractivity")


def test_the_nps_formulas_are_found_by_search() -> None:
    assert "formulations.fairall1978_radio_refractivity" in set(
        CATALOG.search("Fairall").refs
    )
    refractivities = {f.key for f in CATALOG.formulations_of("RadioRefractivity")}
    assert {
        "fairall1978_radio_refractivity",
        "itu_r_p453_refractivity_total_pressure",
    } <= refractivities
    heat = {f.key for f in CATALOG.formulations_of("GradientFunctionForHeat")}
    assert {
        "fairall1978_gradient_function_heat",
        "frederickson1994_gradient_function_scalar",
        "ecmwf_ifs_gradient_function_heat_unstable",
    } <= heat
    assert set(CATALOG.used_by("references.businger1971").refs) == {
        "formulations.fairall1978_gradient_function_momentum_unstable",
        "formulations.fairall1978_gradient_function_momentum_stable",
        "formulations.businger1971_keyps",
        "formulations.businger1971_gradient_function_heat_unstable",
    }
    assert "formulations.frederickson1994_gradient_function_scalar" in set(
        CATALOG.used_by("references.frederickson1994_nps").refs
    )
    lengths = {f.key for f in CATALOG.formulations_of("ObukhovLength")}
    assert {
        "fairall1978_obukhov_length",
        "frederickson1994_obukhov_length",
    } <= lengths
    assert [
        f.key for f in CATALOG.formulations_of("VerticalRadioRefractivityGradient")
    ] == ["fairall1978_vertical_refractivity_gradient"]
    assert "formulations.fairall1978_vertical_refractivity_gradient" in set(
        CATALOG.search("refractivity gradient").refs
    )
