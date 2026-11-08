# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Neutral transfer coefficients of the sea surface and the stability
factors of Louis et al. (1982)."""

import math

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
K = 0.4


def evaluate(key: str, outside: str = "nan", **inputs: object) -> np.ndarray:
    result = F[key].evaluate(outside=outside, **inputs)  # type: ignore[arg-type]
    return np.asarray(result.magnitude)


def speed(*values: float) -> object:
    return Q_(np.array(values), "m/s")


def length(value: float) -> object:
    return Q_(value, "m")


def fixed_point(u: float, roughness: object, height: float = 10.0) -> float:
    """C_DN of a neutral logarithmic profile, iterated as the codes do."""
    c = 1e-3
    for _ in range(200):
        u_s = u * math.sqrt(c)
        c = (K / math.log(height / roughness(u, u_s))) ** 2  # type: ignore[operator]
    return c


# --- Large and Yeager (2004), equations 6a to 6d -----------------------------------


def test_large_yeager_coefficients_at_their_printed_values() -> None:
    c_dn = evaluate("large_yeager2004_neutral_drag_coefficient", U_10N=speed(2, 10))
    np.testing.assert_allclose(
        c_dn, [(1.35 + 0.142 + 2 / 13.09) / 1000, (0.27 + 0.142 + 10 / 13.09) / 1000]
    )
    # The values Bonino et al. (2022, figure 1) plot for NCAR: 1.65e-3 and 1.175e-3.
    np.testing.assert_allclose(c_dn, [1.65e-3, 1.175e-3], rtol=0.005)
    c = Q_(c_dn[1], "")
    c_en = evaluate("large_yeager2004_neutral_transfer_coefficient_humidity", C_DN=c)
    assert float(c_en) == pytest.approx(34.6e-3 * math.sqrt(c_dn[1]))
    c_hn = evaluate(
        "large_yeager2004_neutral_transfer_coefficient_heat",
        C_DN=c,
        zeta=Q_(np.array([0.5, -0.5]), ""),
    )
    np.testing.assert_allclose(c_hn, np.array([18.0, 32.7]) * 1e-3 * math.sqrt(c_dn[1]))


# --- Logarithmic profiles: Beljaars (1992) and COARE 3.6 ---------------------------


def test_beljaars_and_coare_neutral_coefficients() -> None:
    z_1, z_0m, z_0h = length(10.0), length(1e-4), length(3.4e-5)
    c_mn = float(evaluate("beljaars1992_neutral_drag_coefficient", z_1=z_1, z_0M=z_0m))
    assert c_mn == pytest.approx((K / math.log(1e5)) ** 2)
    c_dn = float(evaluate("coare36_neutral_drag_coefficient", z_0M=z_0m))
    assert c_dn == pytest.approx(c_mn, rel=1e-12)
    beljaars = float(
        evaluate("beljaars1992_neutral_transfer_coefficient_heat", z_1=z_1, z_0H=z_0h)
    )
    coare = float(
        evaluate("coare36_neutral_transfer_coefficient_heat", z_0M=z_0m, z_0T=z_0h)
    )
    assert beljaars == pytest.approx((K / math.log(10 / 3.4e-5)) ** 2)
    # The product form of COARE, that of the captions of Beljaars' figures 18
    # and 19, is larger by 9.4 % here (note of equation 108).
    assert coare / beljaars - 1 == pytest.approx(0.094, abs=5e-4)
    humidity = float(
        evaluate("coare36_neutral_transfer_coefficient_humidity", z_0M=z_0m, z_0Q=z_0h)
    )
    assert humidity == pytest.approx(coare, rel=1e-12)
    q = float(
        evaluate(
            "beljaars1992_neutral_transfer_coefficient_humidity", z_1=z_1, z_0Q=z_0h
        )
    )
    assert q == pytest.approx(beljaars, rel=1e-12)


# --- Edson et al. (2013) and Hersbach (2011) -----------------------------------------


def test_edson_high_wind_relations_agree_and_keep_their_range() -> None:
    u_s = evaluate("edson2013_friction_velocity_high_wind", U_10N=speed(5.0, 10.0))
    assert math.isnan(u_s[0])
    assert u_s[1] == pytest.approx(0.34)
    c = evaluate(
        "edson2013_neutral_drag_coefficient_high_wind", U_10N=speed(5.0, 10.0, 1e6)
    )
    assert math.isnan(c[0])
    assert c[1] == pytest.approx((u_s[1] / 10.0) ** 2)
    # The asymptote, C_m^2, about 3.8e-3 (p. 1603).
    assert c[2] == pytest.approx(0.062**2, rel=2e-5)
    drag = float(
        evaluate(
            "businger1985_drag_coefficient", u_s=Q_(u_s[1], "m/s"), U=Q_(10.0, "m/s")
        )
    )
    assert drag == pytest.approx(c[1])


def test_hersbach_neutral_drag_coefficient() -> None:
    c = float(evaluate("hersbach2011_neutral_drag_coefficient", U_10N=Q_(10.0, "m/s")))
    assert c == pytest.approx((1.03e-3 + 0.04e-3 * 10**1.48) / 10**0.21)


# --- The fixed points of COARE 3.6 and of the IFS ------------------------------------


def coare_roughness(
    u: float, u_s: float, nu: float = 1.47e-5, g: float = 9.81
) -> float:
    alpha = 0.0017 * min(u, 19.0) - 0.005
    return alpha * u_s**2 / g + 0.11 * nu / u_s


# A RootWarning fails the test: the physical domain leaves one root.
@pytest.mark.filterwarnings("error")
def test_coare36_fixed_point_is_the_root_of_the_implicit_equation() -> None:
    winds = (2.0, 5.0, 10.0, 18.0, 25.0)
    c = evaluate(
        "coare36_neutral_drag_coefficient_from_wind",
        U_10N=speed(*winds),
        nu=Q_(1.47e-5, "m**2/s"),
        g=Q_(9.81, "m/s**2"),
    )
    expected = [fixed_point(u, coare_roughness) for u in winds]
    np.testing.assert_allclose(c, expected, rtol=1e-9)
    # Bonino et al. (2022, figure 1) plot 0.97e-3, 1.32e-3 and about 2.76e-3 for
    # COARE at 2, 10 and 25 m/s.
    np.testing.assert_allclose(c[[0, 2, 4]], [0.97e-3, 1.32e-3, 2.76e-3], rtol=0.02)


@pytest.mark.filterwarnings("error")
def test_ifs_fixed_point_and_its_physical_domain() -> None:
    def ifs_roughness(u: float, u_s: float) -> float:
        return 0.11 * 1.5e-5 / u_s + 0.018 * u_s**2 / 9.80665

    def ifs_fixed_point(u: float) -> float:
        c = 1e-3
        for _ in range(200):
            z_0 = ifs_roughness(u, u * math.sqrt(c))
            c = (K / math.log((10 + z_0) / z_0)) ** 2
        return c

    winds = (2.0, 10.0, 25.0)
    c = evaluate("ecmwf_ifs_neutral_drag_coefficient_from_wind", U_10N=speed(*winds))
    np.testing.assert_allclose(c, [ifs_fixed_point(u) for u in winds], rtol=1e-9)
    # Within the physical domain, C_DN <= kappa^2/4.
    assert np.all(c <= K**2 / 4)
    # Bonino et al. (2022, figure 1) plot 1.005e-3, 1.445e-3 and 2.375e-3
    # for ECMWF at 2, 10 and 25 m/s.
    np.testing.assert_allclose(c, [1.005e-3, 1.445e-3, 2.375e-3], rtol=0.005)


# --- Louis et al. (1982), as Beljaars (1992) quotes them ------------------------------


def test_louis_stability_factors() -> None:
    ri = Q_(np.array([-0.1, 0.0, 0.1]), "")
    z_1, z_0m = length(10.0), length(0.1)
    f_m = evaluate("louis1982_stability_factor_momentum", Ri_b=ri, z_1=z_1, z_0M=z_0m)
    f_h = evaluate("louis1982_stability_factor_heat", Ri_b=ri, z_1=z_1, z_0M=z_0m)
    c_h = 75 * K**2 * math.sqrt(101) / math.log(101) ** 2
    np.testing.assert_allclose(
        f_m,
        [1 + 1.0 / (1 + c_h * math.sqrt(0.1)), 1.0, 1 / (1 + 1.0 / math.sqrt(1.5))],
    )
    np.testing.assert_allclose(
        f_h,
        [1 + 1.5 / (1 + c_h * math.sqrt(0.1)), 1.0, 1 / (1 + 1.5 * math.sqrt(1.5))],
    )


# --- Search ---------------------------------------------------------------------------


def test_neutral_coefficients_are_found_together() -> None:
    keys = {
        f.key
        for f in CATALOG.formulations_of("NeutralSurfaceDragCoefficientForMomentum")
    }
    assert {
        "large_yeager2004_neutral_drag_coefficient",
        "beljaars1992_neutral_drag_coefficient",
        "coare36_neutral_drag_coefficient",
        "coare36_neutral_drag_coefficient_from_wind",
        "ecmwf_ifs_neutral_drag_coefficient_from_wind",
        "edson2013_neutral_drag_coefficient_high_wind",
        "hersbach2011_neutral_drag_coefficient",
    } <= keys
    found = {f.key for f in CATALOG.search(keyword="Louis").formulations}
    assert {
        "louis1982_stability_factor_momentum",
        "louis1982_stability_factor_heat",
    } <= found
