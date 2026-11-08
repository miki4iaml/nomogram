# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Flux-profile relations of the surface layer: COARE 3.6 and Large and
Yeager (2004)."""

import math
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
K = 0.4

# Five cases of the test data of COARE 3.6 (NOAA-PSL/COARE-algorithm, commit
# bd1cac8, MIT License): test_36_data.txt and
# test_36_output_withnowavesinput_withwarmlayer.txt, from the most to the
# least unstable (zu/L from -3.99 to -0.049); zu = 18 m, zt = zq = 17 m.
# Columns: u, t (degC), lat, tsg (degC); usr, tsr, zo, zot, L, dT_skinx,
# U10, U10N, T10 (degC), gust, dT_warm_to_skin.
CASES = [
    (
        2.2824139328,
        25.880649368,
        13.140463,
        27.634228,
        8.1609266881e-02,
        -6.2451899344e-02,
        2.0556293319e-05,
        1.6e-04,
        -4.5117798246,
        3.4628996273e-01,
        2.2475394412,
        2.5604312371,
        25.966077054,
        6.8005654437e-01,
        1.1290406571e-01,
        -2.7603780149e-04,
    ),
    (
        6.1413362339,
        26.170475991,
        13.901053,
        26.936519,
        1.9471059850e-01,
        -1.2199070471e-02,
        2.9957621054e-05,
        1.1779341418e-04,
        -54.502994786,
        2.7055851044e-01,
        5.9486801857,
        6.1504319746,
        26.246014642,
        7.0631642747e-01,
        0.0,
        -2.2458510765e-04,
    ),
    (
        7.4387688286,
        25.434405962,
        14.846116,
        26.270934,
        2.4272686868e-01,
        -1.6065287278e-02,
        5.2128891816e-05,
        6.7238969864e-05,
        -92.710366163,
        2.1453453360e-01,
        7.1728717464,
        7.3455095626,
        25.514557502,
        7.3781392546e-01,
        1.2196704257e-02,
        -1.7800174802e-04,
    ),
    (
        9.8295755593,
        25.147984538,
        14.842304,
        26.228159,
        3.4443302938e-01,
        -2.1660600297e-02,
        1.4172088211e-04,
        2.5405204932e-05,
        -162.11549510,
        2.1689795434e-01,
        9.4177243703,
        9.5759820496,
        25.235439349,
        8.6898008383e-01,
        0.0,
        -1.8750770177e-04,
    ),
    (
        12.781127627,
        25.335928151,
        15.579628,
        26.187875,
        4.8312082690e-01,
        -1.3774924943e-02,
        3.8131657450e-04,
        9.7717819392e-06,
        -367.54986608,
        2.0122954205e-01,
        12.146716866,
        12.256515322,
        25.418842135,
        9.2743851353e-01,
        0.0,
        -1.9035097465e-04,
    ),
]
(
    u,
    t,
    lat,
    tsg,
    usr,
    tsr,
    zo,
    zot,
    obukhov,
    dt_skin,
    u10,
    u10n,
    t10,
    gust,
    warm,
    qsr,
) = (np.array(column) for column in zip(*CASES, strict=True))
Z_U, Z_T = 18.0, 17.0


def grv(latitude: np.ndarray) -> np.ndarray:
    """The gravity at a latitude, as COARE 3.6 computes it (grv)."""
    x = np.sin(np.radians(latitude))
    series = (
        1 + 0.0052790414 * x**2 + 2.32718e-05 * x**4 + 1.262e-07 * x**6 + 7e-10 * x**8
    )
    return 9.7803267715 * series


G = Q_(grv(lat), "m/s**2")
S = Q_(np.sqrt(u**2 + gust**2), "m/s")
U = Q_(u, "m/s")
L = Q_(obukhov, "m")


def value(key: str, **inputs: Any) -> np.ndarray:
    result = F[key].evaluate(outside="ignore", **inputs)
    return np.asarray(result.magnitude)


# --- COARE 3.6 against its test data ---------------------------------------------


def test_coare_friction_velocity_and_temperature_scale() -> None:
    found = value(
        "coare36_friction_velocity",
        S=S,
        z_u=Q_(Z_U, "m"),
        z_0M=Q_(zo, "m"),
        L=L,
    )
    np.testing.assert_allclose(found, usr, rtol=1e-9)
    # The skin: the sea temperature with the warm layer, less the cool skin.
    skin = tsg + warm - dt_skin
    scale = value(
        "coare36_temperature_scale",
        T_surf=Q_(skin + 273.15, "K"),
        T=Q_(t + 273.15, "K"),
        z_t=Q_(Z_T, "m"),
        z_0T=Q_(zot, "m"),
        L=L,
        g=G,
    )
    np.testing.assert_allclose(scale, tsr, rtol=1e-7)


def test_coare_obukhov_length() -> None:
    # The code takes ta = t + 273.16.
    found = value(
        "coare36_obukhov_length",
        T=Q_(t + 273.16, "K"),
        u_s=Q_(usr, "m/s"),
        T_s=Q_(tsr, "K"),
        q_s=Q_(qsr, "kg/kg"),
        g=G,
    )
    np.testing.assert_allclose(found, obukhov, rtol=1e-7)


def test_coare_values_at_10_m() -> None:
    wind = value(
        "coare36_wind_speed_at_height",
        U=U,
        S=S,
        u_s=Q_(usr, "m/s"),
        z_u=Q_(Z_U, "m"),
        z_r=Q_(10.0, "m"),
        L=L,
    )
    np.testing.assert_allclose(wind, u10, rtol=1e-9)
    temperature = value(
        "coare36_temperature_at_height",
        T=Q_(t + 273.15, "K"),
        T_s=Q_(tsr, "K"),
        z_t=Q_(Z_T, "m"),
        z_r=Q_(10.0, "m"),
        L=L,
        g=G,
    )
    np.testing.assert_allclose(temperature - 273.15, t10, atol=1e-8)
    neutral = value(
        "coare36_equivalent_neutral_wind_10m",
        u_s=Q_(usr, "m/s"),
        U=U,
        S=S,
        z_0M=Q_(zo, "m"),
    )
    np.testing.assert_allclose(neutral, u10n, rtol=1e-9)


def test_coare_humidity_at_its_own_height_and_its_scale() -> None:
    q = Q_(np.full(5, 0.016), "kg/kg")
    same = value(
        "coare36_specific_humidity_at_height",
        q=q,
        q_s=Q_(qsr, "kg/kg"),
        z_q=Q_(Z_T, "m"),
        z_t=Q_(Z_T, "m"),
        z_r=Q_(Z_T, "m"),
        L=L,
    )
    np.testing.assert_allclose(same, 0.016, rtol=1e-12)
    # Over an evaporating sea, the air is drier below 10 m... than at 17 m:
    # q decreases with height when q_* < 0.
    lower = value(
        "coare36_specific_humidity_at_height",
        q=q,
        q_s=Q_(qsr, "kg/kg"),
        z_q=Q_(Z_T, "m"),
        z_t=Q_(Z_T, "m"),
        z_r=Q_(10.0, "m"),
        L=L,
    )
    assert np.all(lower > 0.016)
    # The scale from the difference gives back q_* for that difference.
    scale = value(
        "coare36_humidity_scale",
        q_surf=Q_(np.full(5, 0.0204), "kg/kg"),
        q=q,
        z_q=Q_(Z_T, "m"),
        z_0Q=Q_(zot, "m"),
        L=L,
    )
    assert np.all(scale < 0)


# --- Large and Yeager (2004) ------------------------------------------------------


def test_large_yeager_profile_functions() -> None:
    zeta = Q_(np.array([-2.0, -0.3, -0.01]), "")
    for mine, ifs in (
        (
            "large_yeager2004_profile_function_momentum",
            "ecmwf_ifs_profile_function_momentum_unstable",
        ),
        (
            "large_yeager2004_profile_function_heat",
            "ecmwf_ifs_profile_function_heat_unstable",
        ),
    ):
        # Paulson in unstable conditions, as the IFS writes it.
        np.testing.assert_allclose(
            value(mine, zeta=zeta), value(ifs, zeta=zeta), rtol=1e-12
        )
        stable = value(mine, zeta=Q_(np.array([0.0, 0.5, 2.0]), ""))
        np.testing.assert_allclose(stable, [0.0, -2.5, -10.0], atol=1e-15)


def test_large_yeager_shifts_reduce_to_identities() -> None:
    neutral = Q_(0.0, "")
    c_dn, c_hn = Q_(1.2e-3, ""), Q_(1.1e-3, "")
    ten = Q_(10.0, "m")
    # At 10 m and neutral, the coefficients are the neutral ones...
    c_d = value(
        "large_yeager2004_drag_coefficient_at_height",
        C_DN=c_dn,
        z_u=ten,
        zeta_u=neutral,
    )
    assert float(c_d) == pytest.approx(1.2e-3, rel=1e-12)
    c_h = value(
        "large_yeager2004_transfer_coefficient_heat_at_height",
        C_HN=c_hn,
        C_DN=c_dn,
        C_D=Q_(float(c_d), ""),
        z_u=ten,
        zeta_u=neutral,
    )
    assert float(c_h) == pytest.approx(1.1e-3, rel=1e-12)
    # ...and the wind at 10 m is the neutral wind at 10 m.
    wind = value(
        "large_yeager2004_neutral_wind_10m",
        U=Q_(7.0, "m/s"),
        C_DN=c_dn,
        z_u=ten,
        zeta_u=neutral,
    )
    assert float(wind) == pytest.approx(7.0, rel=1e-12)
    # A temperature measured at the height of the wind stays as it is.
    theta = value(
        "large_yeager2004_potential_temperature_at_wind_height",
        theta=Q_(290.0, "K"),
        T_s=Q_(-0.02, "K"),
        z_theta=ten,
        z_u=ten,
        zeta_u=Q_(-0.1, ""),
        zeta_theta=Q_(-0.1, ""),
    )
    assert float(theta) == pytest.approx(290.0, rel=1e-12)
    # Unstable: the drag at 20 m exceeds the neutral drag at 10 m less than
    # the neutral profile alone would make it fall.
    unstable = value(
        "large_yeager2004_drag_coefficient_at_height",
        C_DN=c_dn,
        z_u=Q_(20.0, "m"),
        zeta_u=Q_(-0.5, ""),
    )
    neutral_20 = value(
        "large_yeager2004_drag_coefficient_at_height",
        C_DN=c_dn,
        z_u=Q_(20.0, "m"),
        zeta_u=neutral,
    )
    assert float(unstable) > float(neutral_20)


def test_large_yeager_stability_is_that_of_coare_without_humidity() -> None:
    # Without water vapour, zeta = kappa g z t*/(u*^2 theta_v), which is
    # z/L with the Obukhov length of COARE when theta_v is the temperature.
    common = {"u_s": Q_(0.3, "m/s"), "T_s": Q_(0.05, "K"), "g": Q_(9.81, "m/s**2")}
    zeta = value(
        "large_yeager2004_stability_parameter",
        z=Q_(10.0, "m"),
        theta_v=Q_(290.0, "K"),
        q_s=Q_(0.0, "kg/kg"),
        q=Q_(0.0, "kg/kg"),
        **common,
    )
    length = value(
        "coare36_obukhov_length", T=Q_(290.0, "K"), q_s=Q_(0.0, "kg/kg"), **common
    )
    assert float(zeta) == pytest.approx(10.0 / float(length), rel=1e-12)


def test_large_yeager_scales_close_the_kinematic_fluxes() -> None:
    c_d, c_h = Q_(1.3e-3, ""), Q_(1.2e-3, "")
    du = Q_(8.0, "m/s")
    u_star = value("ecmwf_ifs_friction_velocity", C_M=c_d, U_n=du)
    t_star = value(
        "large_yeager2004_temperature_scale",
        C_H=c_h,
        C_D=c_d,
        theta=Q_(288.0, "K"),
        T_surf=Q_(290.0, "K"),
    )
    # u* t* = C_H |dU| (theta - SST), the kinematic heat flux (4c).
    assert float(u_star * t_star) == pytest.approx(1.2e-3 * 8.0 * -2.0, rel=1e-12)


def test_the_alternatives_are_found_together() -> None:
    friction = {f.key for f in CATALOG.formulations_of("FrictionVelocity")}
    assert {"coare36_friction_velocity", "ecmwf_ifs_friction_velocity"} <= friction
    cited = {c.reference for c in F["ecmwf_ifs_friction_velocity"].citations}
    assert "large_yeager2004" in cited
    scales = {
        f.key
        for f in CATALOG.formulations_of(
            "SurfaceLayerProfileScaleOfPotentialTemperature"
        )
    }
    assert {"coare36_temperature_scale", "large_yeager2004_temperature_scale"} <= scales
    neutral = {f.key for f in CATALOG.formulations_of("EquivalentNeutralWindSpeed")}
    assert {
        "coare36_equivalent_neutral_wind_10m",
        "large_yeager2004_neutral_wind_10m",
    } <= neutral
    assert math.isfinite(K)


# --- Relations with the profile function as an input -------------------------------


def test_fairall_scale_and_profile_are_inverse() -> None:
    # Equation 16 gives the scale from the difference, 11 the value back.
    lengths = {"z": Q_(10.0, "m"), "z_0H": Q_(1e-4, "m")}
    psi = Q_(np.array([0.8, 0.0, -2.0]), "")
    theta_0, theta = Q_(300.0, "K"), Q_(298.5, "K")
    scale = value(
        "fairall1978_potential_temperature_scale",
        theta=theta,
        theta_0=theta_0,
        Psi_H=psi,
        **lengths,
    )
    back = value(
        "fairall1978_potential_temperature_profile",
        theta_0=theta_0,
        T_s=Q_(scale, "K"),
        Psi_H=psi,
        **lengths,
    )
    np.testing.assert_allclose(back, 298.5, rtol=1e-12)
    u_star = value(
        "fairall1978_friction_velocity",
        U=Q_(7.0, "m/s"),
        U_0=Q_(0.0, "m/s"),
        z=Q_(10.0, "m"),
        z_0M=Q_(1e-4, "m"),
        Psi_M=psi,
    )
    wind = value(
        "fairall1978_wind_profile",
        U_0=Q_(0.0, "m/s"),
        u_s=Q_(u_star, "m/s"),
        z=Q_(10.0, "m"),
        z_0M=Q_(1e-4, "m"),
        Psi_M=psi,
    )
    np.testing.assert_allclose(wind, 7.0, rtol=1e-12)
    r_star = value(
        "fairall1978_mixing_ratio_scale",
        r=Q_(15.0, "g/kg"),
        r_0=Q_(22.0, "g/kg"),
        z=Q_(10.0, "m"),
        z_0Q=Q_(1e-4, "m"),
        Psi_H=psi,
    )
    mixing = value(
        "fairall1978_mixing_ratio_profile",
        r_0=Q_(22.0, "g/kg"),
        r_s=Q_(r_star, "g/kg"),
        z=Q_(10.0, "m"),
        z_0Q=Q_(1e-4, "m"),
        Psi_H=psi,
    )
    np.testing.assert_allclose(mixing, 15.0, rtol=1e-12)
    # Over an evaporating sea, the mixing ratio decreases with height.
    assert np.all(r_star < 0)


def test_fairall_and_frederickson_differ_by_their_constants() -> None:
    # The same form, k = 0.4 for Frederickson, alpha kappa = 1.35 x 0.35 for
    # the scales of Fairall, kappa = 0.35 for his friction velocity.
    wind = {"U": Q_(7.0, "m/s"), "U_0": Q_(0.0, "m/s"), "z": Q_(10.0, "m")}
    common = {"z_0M": Q_(1e-4, "m"), "Psi_M": Q_(0.3, "")}
    fairall = value("fairall1978_friction_velocity", **wind, **common)
    frederickson = value("frederickson1994_friction_velocity", **wind, **common)
    assert float(fairall / frederickson) == pytest.approx(0.35 / 0.4, rel=1e-12)
    humidity = {"z": Q_(10.0, "m"), "z_0Q": Q_(1e-4, "m"), "Psi_H": Q_(0.3, "")}
    q_star = value(
        "frederickson1994_humidity_scale",
        q=Q_(0.015, "kg/kg"),
        q_0=Q_(0.022, "kg/kg"),
        **humidity,
    )
    r_star = value(
        "fairall1978_mixing_ratio_scale",
        r=Q_(15.0, "g/kg"),
        r_0=Q_(22.0, "g/kg"),
        **humidity,
    )
    assert float(r_star / (q_star * 1000)) == pytest.approx(
        1.35 * 0.35 / 0.4, rel=1e-12
    )


def test_businger_profiles_are_logarithmic_at_neutral() -> None:
    neutral = Q_(0.0, "")
    wind = value(
        "businger1985_wind_profile",
        u_s=Q_(0.3, "m/s"),
        z=Q_(10.0, "m"),
        z_0M=Q_(1e-4, "m"),
        Psi_M=neutral,
    )
    assert float(wind) == pytest.approx(0.3 / 0.4 * math.log(1e5), rel=1e-12)
    rise = value(
        "businger1985_potential_temperature_profile",
        T_s=Q_(0.05, "K"),
        z=Q_(10.0, "m"),
        z_0M=Q_(1e-4, "m"),
        Psi_H=neutral,
    )
    assert float(rise) == pytest.approx(0.05 / 0.4 * math.log(1e5), rel=1e-12)
    # The wind of Businger gives back the friction velocity of Frederickson.
    u_star = value(
        "frederickson1994_friction_velocity",
        U=Q_(float(wind), "m/s"),
        U_0=Q_(0.0, "m/s"),
        z=Q_(10.0, "m"),
        z_0M=Q_(1e-4, "m"),
        Psi_M=neutral,
    )
    assert float(u_star) == pytest.approx(0.3, rel=1e-12)


def test_the_generic_alternatives_are_found_together() -> None:
    friction = {f.key for f in CATALOG.formulations_of("FrictionVelocity")}
    assert {
        "fairall1978_friction_velocity",
        "frederickson1994_friction_velocity",
        "coare36_friction_velocity",
    } <= friction
    assert F["fairall1978_friction_velocity"].family == "evaporation-duct"
    assert F["businger1985_wind_profile"].family == "boundary-layer"


# --- COARE 3.6 in stable conditions, from its code -----------------------------------

# Three stable cases (air warmer than the sea, zu/L = 1.45, 0.53, 0.086),
# computed by running the code of COARE 3.6 (commit bd1cac8, MIT License)
# on: u = 4, 8, 12 m/s at zu = 18 m; ts = 15 degC; t = ts + 1.5, 3, 2 degC at
# zt = zq = 17 m; rh = 85 %; P = 1015 hPa; lat = 45 deg; no shortwave, 350 W/m2
# of longwave; zi = 600 m; Ss = 35. Its test data hold no stable case.
STABLE_U = np.array([4.0, 8.0, 12.0])
STABLE_T = 15.0 + np.array([1.5, 3.0, 2.0])
STABLE = {
    "usr": [8.1431175969e-02, 2.0328575138e-01, 4.1123988124e-01],
    "tsr": [4.1012278196e-02, 8.8366303201e-02, 6.0602824368e-02],
    "qsr": [-8.4990662981e-06, 1.5268838629e-05, -3.4204571420e-06],
    "zo": [1.9576704175e-05, 3.2917280022e-05, 2.3849905281e-04],
    "zot": [1.6000000000e-04, 1.0299809242e-04, 1.4837566586e-05],
    "L": [1.2393560378e01, 3.3680142907e01, 2.0851331646e02],
    "dT_skinx": [1.2044009284e-01, 1.2471414605e-02, 9.6161380596e-03],
    "U10": [3.4160218168e00, 7.1585830408e00, 1.1195494636e01],
    "U10N": [2.6724401729e00, 6.4137440870e00, 1.0941296455e01],
    "T10": [1.6289424719e01, 1.7743530193e01, 1.6962926773e01],
}
STABLE_GUST = 0.2  # the gustiness of the code where the buoyancy flux is negative


def test_coare_in_stable_conditions() -> None:
    expected = {k: np.array(v) for k, v in STABLE.items()}
    s = Q_(np.sqrt(STABLE_U**2 + STABLE_GUST**2), "m/s")
    length = Q_(expected["L"], "m")
    g = Q_(grv(np.full(3, 45.0)), "m/s**2")
    found = value(
        "coare36_friction_velocity",
        S=s,
        z_u=Q_(Z_U, "m"),
        z_0M=Q_(expected["zo"], "m"),
        L=length,
    )
    np.testing.assert_allclose(found, expected["usr"], rtol=1e-8)
    scale = value(
        "coare36_temperature_scale",
        T_surf=Q_(15.0 - expected["dT_skinx"] + 273.15, "K"),
        T=Q_(STABLE_T + 273.15, "K"),
        z_t=Q_(Z_T, "m"),
        z_0T=Q_(expected["zot"], "m"),
        L=length,
        g=g,
    )
    np.testing.assert_allclose(scale, expected["tsr"], rtol=1e-6)
    obukhov_length = value(
        "coare36_obukhov_length",
        T=Q_(STABLE_T + 273.16, "K"),
        u_s=Q_(expected["usr"], "m/s"),
        T_s=Q_(expected["tsr"], "K"),
        q_s=Q_(expected["qsr"], "kg/kg"),
        g=g,
    )
    # The code computes L at the start of an iteration from the scales of the
    # one before: in stable conditions, it lags them by about 1e-5.
    np.testing.assert_allclose(obukhov_length, expected["L"], rtol=2e-5)
    wind = value(
        "coare36_wind_speed_at_height",
        U=Q_(STABLE_U, "m/s"),
        S=s,
        u_s=Q_(expected["usr"], "m/s"),
        z_u=Q_(Z_U, "m"),
        z_r=Q_(10.0, "m"),
        L=length,
    )
    np.testing.assert_allclose(wind, expected["U10"], rtol=1e-8)
    temperature = value(
        "coare36_temperature_at_height",
        T=Q_(STABLE_T + 273.15, "K"),
        T_s=Q_(expected["tsr"], "K"),
        z_t=Q_(Z_T, "m"),
        z_r=Q_(10.0, "m"),
        L=length,
        g=g,
    )
    np.testing.assert_allclose(temperature - 273.15, expected["T10"], atol=1e-7)
    neutral = value(
        "coare36_equivalent_neutral_wind_10m",
        u_s=Q_(expected["usr"], "m/s"),
        U=Q_(STABLE_U, "m/s"),
        S=s,
        z_0M=Q_(expected["zo"], "m"),
    )
    np.testing.assert_allclose(neutral, expected["U10N"], rtol=1e-7)
