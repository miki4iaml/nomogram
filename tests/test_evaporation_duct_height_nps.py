# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The evaporation duct heights of Fairall et al. (1978) and Frederickson
et al. (1994): implicit equations whose unknown reaches the gradient
function, at z*/L.

Table II-C of Fairall et al. (appendix C) is the oracle; the identities
say what each check proves: the transcription of equation 25 from
equation 24, and the ducting criterion dM/dz = 0 with the modified
refractivity of ITU-R P.453.
"""

import itertools
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.model import Formulation, RootWarning
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
FAIRALL = F["fairall1978_evaporation_duct_height"]
FREDERICKSON = F["frederickson1994_evaporation_duct_height"]
ONE = "dimensionless"
#: The height of Z/L in table II-C (p. 23).
Z = 10.0

#: First line of rows of table II-C, the bulk method: Z/L, T_* (K), q_*
#: (g/kg), Z_* (m), read on the images of pages C-11 and C-23. Each Z_* was
#: checked against the minimum frequency trapped of its row, about
#: 360/Z_*^1.5 (equation 29), where a digit was hard to read (rows 19 to 21).
TABLE_II_C = {
    16: (-9.65e-2, -0.02, -0.24, 17.5),
    17: (-1.04e-1, -0.02, -0.24, 17.3),
    18: (-9.95e-2, -0.02, -0.23, 16.9),
    19: (-8.36e-2, -0.02, -0.22, 17.3),
    20: (-8.26e-2, -0.02, -0.22, 16.9),
    21: (-6.95e-2, -0.02, -0.19, 15.6),
    22: (-6.34e-2, -0.02, -0.18, 15.3),
    23: (-5.48e-2, -0.02, -0.17, 15.1),
    24: (-5.07e-2, -0.02, -0.16, 14.2),
    25: (-4.43e-2, -0.02, -0.15, 13.8),
    26: (-4.24e-2, -0.02, -0.14, 12.8),
    27: (-3.62e-2, -0.01, -0.13, 12.8),
    28: (-3.94e-2, -0.01, -0.13, 12.6),
    29: (-3.98e-2, -0.01, -0.13, 12.3),
    30: (-3.64e-2, -0.01, -0.13, 12.5),
    31: (-3.47e-2, -0.01, -0.12, 11.7),
    246: (-4.98e-2, -0.06, -0.24, 19.8),
    247: (-5.75e-2, -0.06, -0.26, 20.5),
    248: (-3.81e-2, -0.06, -0.25, 21.2),
    249: (-3.43e-1, -0.07, -0.28, 14.9),
    250: (-5.47e-2, -0.07, -0.25, 20.1),
    251: (-3.77e-2, -0.07, -0.24, 20.5),
    252: (-3.68e-2, -0.06, -0.23, 20.2),
    253: (-7.11e-2, -0.08, -0.23, 17.6),
    254: (-5.21e-1, -0.13, -0.28, 12.9),
    255: (-5.64e-1, -0.10, -0.24, 11.6),
}

#: Second line of rows 246 to 253 (profile T_*, q_*), p. C-23: no duct,
#: Z_* printed 0.0, which nomogram gives as NaN.
NO_DUCT = [
    (3.86e-2, 0.06, 0.10),
    (2.81e-2, 0.04, 0.07),
    (8.68e-3, 0.01, 0.09),
    (2.11e-2, 0.03, 0.09),
    (1.33e-2, 0.02, 0.13),
    (1.43e-2, -0.01, 0.17),
]


def height(formulation: Formulation, q_s: Any, t_s: Any, length: Any) -> np.ndarray:
    result = formulation.evaluate(
        q_s=Q_(q_s, "g/kg"), T_s=Q_(t_s, "K"), L=Q_(length, "m")
    )
    return np.asarray(result.to("m").magnitude)


def test_table_ii_c_within_the_rounding_of_its_inputs() -> None:
    # T_* and q_* are printed to 0.01, Z/L to three digits, Z_* to 0.1 m: the
    # heights computed at the corners of the box of the inputs bound the
    # printed one, each row about a metre wide at most (q_* to 0.01 g/kg).
    xi, t_s, q_s, printed = (
        np.array(c) for c in zip(*TABLE_II_C.values(), strict=True)
    )
    half = 0.005 * 10.0 ** np.floor(np.log10(np.abs(xi)))
    corners = np.array(
        [
            height(FAIRALL, q_s + dq * 0.005, t_s + dt * 0.005, Z / (xi + dx * half))
            for dx, dt, dq in itertools.product((-1, 1), repeat=3)
        ]
    )
    low, high = corners.min(axis=0), corners.max(axis=0)
    rows = list(TABLE_II_C)
    outside = [
        r
        for r, lo, hi, p in zip(rows, low, high, printed, strict=True)
        if not (lo <= p + 0.05 and p - 0.05 <= hi)
    ]
    assert not outside
    assert np.all(high - low < 1.1)


def test_no_duct_in_table_ii_c_is_no_root() -> None:
    xi, t_s, q_s = (np.array(c) for c in zip(*NO_DUCT, strict=True))
    assert np.all(7.2 * q_s - 1.3 * t_s > 0)  # equation 26 says no ducting
    with pytest.warns(RootWarning, match="6 with no root"):
        found = height(FAIRALL, q_s, t_s, Z / xi)
    assert np.all(np.isnan(found))


def test_equation_25_is_equation_24_at_the_critical_gradient() -> None:
    # This checks the transcription of equation 25 from equation 24 only:
    # the gradient of N with phi_T(Z_*/L) is -0.157 m-1 at every root.
    q_s = np.array([-0.24, -0.13, -0.28, -0.20])
    t_s = np.array([-0.02, -0.01, -0.13, 0.03])
    length = np.array([-103.6, -276.2, -19.2, 400.0])
    found = height(FAIRALL, q_s, t_s, length)
    phi = F["fairall1978_gradient_function_heat"].evaluate(zeta=Q_(found / length, ONE))
    gradient = F["fairall1978_vertical_refractivity_gradient"].evaluate(
        Phi_H=phi, z=Q_(found, "m"), q_s=Q_(q_s, "g/kg"), T_s=Q_(t_s, "K")
    )
    np.testing.assert_allclose(gradient.to("ppm/m").magnitude, -0.157, rtol=1e-12)


def test_the_modified_refractivity_of_itu_is_at_its_minimum_at_the_duct_height() -> (
    None
):
    # dM/dz = dN/dz + dM/dh at constant N, with M = N + 157 h, h in km (ITU-R
    # P.453, equation 17): zero at Z_* because both sources take 157 for
    # 10^6/a, an Earth of radius about 6370 km.
    q_s, t_s, length = -0.24, -0.02, -103.6
    found = float(height(FAIRALL, q_s, t_s, length))
    phi = F["fairall1978_gradient_function_heat"].evaluate(zeta=Q_(found / length, ONE))
    d_n = F["fairall1978_vertical_refractivity_gradient"].evaluate(
        Phi_H=phi, z=Q_(found, "m"), q_s=Q_(q_s, "g/kg"), T_s=Q_(t_s, "K")
    )
    m = F["itu_r_p453_modified_refractivity"]
    n = Q_(350.0, "ppm")
    d_m = (m.evaluate(N=n, h=Q_(1.0, "km")) - m.evaluate(N=n, h=Q_(0.0, "km"))) / Q_(
        1.0, "km"
    )
    assert (d_n + d_m).to("ppm/m").magnitude == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize(
    ("formulation", "factor", "slope"),
    [(FAIRALL, 1.35 * 0.35 * 0.125, 6.4), (FREDERICKSON, 0.4 * 0.125, 7.0)],
)
def test_stable_heights_in_closed_form(
    formulation: Formulation, factor: float, slope: float
) -> None:
    # Stable, phi = 1 + slope Z/L: Z_* = A / (1 - slope A / L), positive for
    # L > slope A, with A the neutral height.
    q_s, t_s = -0.2, 0.02
    neutral = -(7.2 * q_s - 1.3 * t_s) / factor
    length = np.array([1e6, 1000.0, 300.0, 2 * slope * neutral])
    found = height(formulation, q_s, t_s, length)
    np.testing.assert_allclose(
        found, neutral / (1 - slope * neutral / length), rtol=1e-12
    )


def test_neutral_heights_of_fairall_and_frederickson() -> None:
    # Frederickson et al. drop alpha_T and take k = 0.4: their neutral height
    # is alpha_T kappa / k = 1.18 times that of Fairall et al.
    fairall = height(FAIRALL, -0.2, -0.02, 1e9)
    frederickson = height(FREDERICKSON, -0.2, -0.02, 1e9)
    assert frederickson / fairall == pytest.approx(1.35 * 0.35 / 0.4, rel=1e-6)


def test_the_duct_heights_are_found_by_search() -> None:
    heights = {f.key for f in CATALOG.formulations_of("EvaporationDuctHeight")}
    assert {
        "fairall1978_evaporation_duct_height",
        "frederickson1994_evaporation_duct_height",
    } <= heights
    users = set(CATALOG.used_by("formulations.fairall1978_gradient_function_heat").refs)
    assert "formulations.fairall1978_evaporation_duct_height" in users
    implicit = set(CATALOG.search(implicit=True, kind="EvaporationDuctHeight").refs)
    assert "formulations.frederickson1994_evaporation_duct_height" in implicit
