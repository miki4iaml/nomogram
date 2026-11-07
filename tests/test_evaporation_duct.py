# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The evaporation duct height of the Paulus-Jeske model (NOSC TD 1596, 1989).

The 37 test cases of its Table 2 are computed again by chaining the
formulations of the catalog, step by step, as section 3.0 orders them.
Table 2 never reaches the stable height of step 4 (b) nor the limited one
of step 4 (c): the test for T_a - T_s > -1 replaces every stable case by
one at T_a = T_s - 1. The continuity of the pieces and the identity of
4 (b) and 4 (c) check those only for consistency.
"""

import math

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.comparison import feeds
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
ONE = "dimensionless"

#: Table 2: air and sea temperatures (degC), relative humidity (%), wind
#: speed (knots) and evaporation duct height (m), to within 0.1 m.
TABLE_2 = [
    (0, 15, 10, 1, 3.9), (0, 15, 10, 20, 16.8), (0, 15, 75, 1, 2.8),
    (0, 15, 75, 20, 12.3), (0, 15, 100, 1, 2.4), (0, 15, 100, 20, 10.4),
    (0, 16, 10, 1, 4.0), (0, 16, 10, 20, 17.3), (0, 16, 75, 1, 3.0),
    (0, 16, 75, 20, 13.0), (0, 16, 100, 1, 2.6), (0, 16, 100, 20, 11.2),
    (15, 15, 10, 1, 8.7), (15, 15, 10, 20, 37.0), (15, 15, 75, 1, 3.6),
    (15, 15, 75, 20, 13.9), (15, 15, 100, 1, 0.0), (15, 15, 100, 20, 0.0),
    (15, 16, 10, 1, 9.1), (15, 16, 10, 20, 38.8), (15, 16, 75, 0, 0.0),
    (15, 16, 75, 1, 3.8), (15, 16, 75, 20, 14.6), (15, 16, 100, 1, 0.9),
    (15, 16, 100, 20, 2.6),
    (30, 15, 10, 1, 8.7), (30, 15, 10, 20, 37.0), (30, 15, 75, 1, 3.6),
    (30, 15, 75, 20, 13.9), (30, 15, 100, 1, 0.0), (30, 15, 100, 20, 0.0),
    (30, 16, 10, 1, 9.1), (30, 16, 10, 20, 38.8), (30, 16, 75, 1, 3.8),
    (30, 16, 75, 20, 14.6), (30, 16, 100, 1, 0.0), (30, 16, 100, 20, 0.0),
]  # fmt: skip

Z_1 = 6.0  # m, the reference height (step 6)


def value(key: str, **inputs: object) -> float:
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(F[key].evaluate(**inputs).magnitude)  # type: ignore[arg-type]


def saturation(t_k: float) -> float:
    """Step 3, in hPa."""
    return value("paulus1989_saturation_vapour_pressure", T=Q_(t_k, "K"))


def potential_refractivity(t_k: float, e: float) -> float:
    """Step 3, N_A or N_S."""
    return value("paulus1989_potential_refractivity", T=Q_(t_k, "K"), e=Q_(e, "hPa"))


def duct_height(u: float, t_ak: float, t_sk: float, e: float, e_0: float) -> float:
    """Steps 2 to 5, temperatures in kelvin, vapour pressures in hPa."""
    ri_b = value(
        "paulus1989_bulk_richardson_number",
        T_a=Q_(t_ak, "K"),
        T_s=Q_(t_sk, "K"),
        u=Q_(max(u, 1.0), "knot"),  # the floor of the FORTRAN listing
    )
    ri_b = min(ri_b, 1.0)  # step 2
    delta_n = value(
        "paulus1989_potential_refractivity_difference",
        N_A=Q_(potential_refractivity(t_ak, e), "ppm"),
        N_S=Q_(potential_refractivity(t_sk, e_0), "ppm"),
    )
    length = value("paulus1989_obukhov_length", Ri_b=Q_(ri_b, ONE))
    common = {"Delta_N_p": Q_(delta_n, "ppm"), "L": Q_(length, "m")}
    if ri_b < 0:  # step 5
        psi = value("paulus1989_profile_function", zeta=Q_(Z_1 / length, ONE))
        delta = value(
            "paulus1989_evaporation_duct_height_unstable",
            Psi_H=Q_(psi, ONE),
            **common,
        )
        return 0.0 if math.isnan(delta) or delta_n >= 0 else delta
    delta = value("paulus1989_evaporation_duct_height_stable", **common)  # step 4
    if delta < 0 or delta / length > 1:
        delta = value(
            "paulus1989_evaporation_duct_height_limited", Delta_N_p=common["Delta_N_p"]
        )
    return delta


def paulus_jeske(t_a: float, t_s: float, rh: float, u: float) -> float:
    """The six steps of section 3.0, with the test of p. 7."""
    if u < 0.01:  # step 1
        return 0.0
    t_ak, t_sk = t_a + 273.2, t_s + 273.2  # step 1, as the source converts
    e_0 = saturation(t_sk)
    if t_a - t_s > -1:  # p. 7: computed for T_a = T_s and T_a = T_s - 1
        at_sea = duct_height(u, t_sk, t_sk, rh / 100 * e_0, e_0)
        t_1 = t_sk - 1
        below = duct_height(u, t_1, t_sk, rh / 100 * saturation(t_1), e_0)
        if at_sea > below:
            return min(below, 40.0)
    return min(duct_height(u, t_ak, t_sk, rh / 100 * saturation(t_ak), e_0), 40.0)


@pytest.mark.parametrize(("t_a", "t_s", "rh", "u", "expected"), TABLE_2)
def test_the_37_test_cases_of_table_2(
    t_a: float, t_s: float, rh: float, u: float, expected: float
) -> None:
    assert paulus_jeske(t_a, t_s, rh, u) == pytest.approx(expected, abs=0.05 + 1e-9)


def test_table_2_has_37_cases() -> None:
    assert len(TABLE_2) == 37


def test_the_pieces_of_the_fits_meet() -> None:
    # Straight-line fits printed to two or three digits: the pieces meet
    # within 2 %, which a transcription error would not.
    for bound in (-3.75, -0.12, 0.14):
        below = value("paulus1989_profile_coefficient", Ri_b=Q_(bound, ONE))
        above = value("paulus1989_profile_coefficient", Ri_b=Q_(bound + 1e-9, ONE))
        assert above == pytest.approx(below, rel=0.02)
    for bound in (-0.01, -0.026, -0.1, -1.0, -2.2):
        at = value("paulus1989_profile_function", zeta=Q_(bound, ONE))
        beyond = value("paulus1989_profile_function", zeta=Q_(bound - 1e-9, ONE))
        assert beyond == pytest.approx(at, rel=0.01)


def test_the_limited_height_is_the_stable_one_at_delta_over_l_equal_to_one() -> None:
    delta_n = Q_(-10.0, "ppm")
    delta = value("paulus1989_evaporation_duct_height_limited", Delta_N_p=delta_n)
    stable = value(
        "paulus1989_evaporation_duct_height_stable",
        Delta_N_p=delta_n,
        L=Q_(delta, "m"),
    )
    assert stable == pytest.approx(delta, rel=1e-12)


def test_no_duct_without_a_negative_refractivity_difference() -> None:
    delta = value(
        "paulus1989_evaporation_duct_height_stable",
        Delta_N_p=Q_(2.0, "ppm"),
        L=Q_(50.0, "m"),
    )
    assert delta == 0.0


def test_the_kinds_of_jeske_feed_no_look_alike() -> None:
    assert feeds("EvaporationDuctHeight", "Height")
    assert not feeds(
        "BulkRichardsonNumberOverProfileCoefficient", "BulkRichardsonNumber"
    )
    assert not feeds(
        "BulkRichardsonNumber", "BulkRichardsonNumberOverProfileCoefficient"
    )
    assert not feeds("PotentialRadioRefractivity", "RadioRefractivity")
    assert not feeds(
        "PotentialRadioRefractivityDifference", "PotentialRadioRefractivity"
    )


def test_the_evaporation_duct_is_found_by_search() -> None:
    found = set(CATALOG.search("evaporation duct").refs)
    for branch in ("stable", "limited", "unstable"):
        assert f"formulations.paulus1989_evaporation_duct_height_{branch}" in found
    heights = CATALOG.formulations_of("EvaporationDuctHeight")
    assert {f.key for f in heights} >= {
        "paulus1989_evaporation_duct_height_stable",
        "paulus1989_evaporation_duct_height_limited",
        "paulus1989_evaporation_duct_height_unstable",
    }
    assert (
        "trade_terms.bulk_richardson_number"
        in CATALOG.search("bulk Richardson number").refs
    )
    meanings = CATALOG.trade_terms["bulk_richardson_number"].meanings
    assert {m.kind for m in meanings} == {
        "BulkRichardsonNumber",
        "BulkRichardsonNumberOverProfileCoefficient",
    }
    assert set(CATALOG.used_by("references.paulus1989_td1596").refs) >= {
        "formulations.paulus1989_bulk_richardson_number",
        "formulations.paulus1989_profile_function",
    }
    assert CATALOG.families["evaporation-duct"].requires == ("boundary-layer", "radio")
