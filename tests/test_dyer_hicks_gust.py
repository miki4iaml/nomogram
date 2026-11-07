# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The gradient functions of Dyer and Hicks (1970), the GUST relations of
Long (1984), and the gradient Richardson number."""

import warnings

import numpy as np
import pytest
import sympy

from nomogram.catalog import catalog
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
ONE = "dimensionless"

# Dyer and Hicks (1970), Table 1 (p. 718): -z/L, Phi_M, Phi_H = Phi_W,
# Phi_H / Phi_M^2, measured at Hay and Gurley.
DYER_HICKS = np.array(
    [
        (0.01, 0.99, 0.95, 0.97),
        (0.02, 0.97, 0.89, 0.95),
        (0.05, 0.90, 0.76, 0.94),
        (0.1, 0.81, 0.62, 0.95),
        (0.2, 0.69, 0.48, 1.02),
        (0.5, 0.55, 0.32, 1.05),
        (1.0, 0.47, 0.23, 1.03),
    ]
)

# Long (1984), Table 1 (p. 10): eta, phi_m, phi_h, roots of the GUST relations.
LONG = np.array(
    [
        (0.001, 0.99975, 0.99950),
        (0.005, 0.99875, 0.99752),
        (0.01, 0.99751, 0.99506),
        (0.05, 0.98773, 0.97645),
        (0.10, 0.97591, 0.95540),
        (0.50, 0.89498, 0.83929),
        (1.0, 0.81917, 0.75488),
        (2.5, 0.68002, 0.62477),
        (5.0, 0.56432, 0.52517),
        (10.0, 0.45729, 0.43310),
        (25.0, 0.34046, 0.32917),
        (50.0, 0.27095, 0.26494),
        (100.0, 0.21529, 0.21216),
        (500.0, 0.12598, 0.12533),
        (1000.0, 0.099997, 0.099667),
        (5000.0, 0.058480, 0.058414),
    ]
)


def value(key: str, **inputs: object) -> np.ndarray:
    return np.asarray(F[key].evaluate(**inputs).magnitude)  # type: ignore[arg-type]


# --- Dyer and Hicks (1970) ---------------------------------------------------


def test_the_forms_approximate_table_1_to_within_a_few_per_cent() -> None:
    zeta = Q_(-DYER_HICKS[:, 0], ONE)
    momentum = value("ecmwf_ifs_gradient_function_momentum_unstable", zeta=zeta)
    heat = value("ecmwf_ifs_gradient_function_heat_unstable", zeta=zeta)
    departures = [
        100 * (momentum - DYER_HICKS[:, 1]) / DYER_HICKS[:, 1],
        100 * (heat - DYER_HICKS[:, 2]) / DYER_HICKS[:, 2],
    ]
    # From -4.07 % (Phi_M at -0.05) to +5.45 % (Phi_H at -1.0).
    assert min(d.min() for d in departures) == pytest.approx(-4.07, abs=0.01)
    assert max(d.max() for d in departures) == pytest.approx(5.45, abs=0.01)
    # Ri = z/L Phi_H / Phi_M^2 departs from z/L by 6 per cent at most (p. 718).
    assert np.abs(DYER_HICKS[:, 3] - 1).max() == pytest.approx(0.06)


def test_their_stated_domain_bounds_the_forms_by_default() -> None:
    zeta = Q_([-2.0, -0.5, -0.005], ONE)
    with pytest.warns(UserWarning, match="2 value"):
        warned = value(
            "ecmwf_ifs_gradient_function_heat_unstable", zeta=zeta, outside="warn"
        )
    np.testing.assert_allclose(warned, (1 + 16 * np.array([2.0, 0.5, 0.005])) ** -0.5)
    bounded = value("ecmwf_ifs_gradient_function_heat_unstable", zeta=zeta)
    assert np.isnan(bounded[[0, 2]]).all()
    assert bounded[1] == pytest.approx(1 / 3)
    domains = [
        dict(d.bounds)
        for c in F["ecmwf_ifs_gradient_function_momentum_unstable"].citations
        if c.reference == "dyer_hicks1970"
        for d in c.domains
    ]
    assert domains == [{"zeta": (-1.0, -0.01)}]


def test_the_gradient_richardson_number_equals_z_over_l() -> None:
    identity = F["dyer_hicks1970_gradient_richardson_number"]
    ri = value(
        "dyer_hicks1970_gradient_richardson_number",
        zeta=Q_(-0.5, ONE),
        Phi_M=Q_(0.55, ONE),
        Phi_H=Q_(0.32, ONE),
    )
    assert float(ri) == pytest.approx(-0.5 * 0.32 / 0.55**2)
    assert identity.nature is not None
    assert identity.nature.value == "identity"
    # With the two forms, exactly z/L: SymPy reduces it, nomogram evaluates it.
    composed = F["dyer_hicks1970_richardson_number_unstable"]
    assert composed.sympy_expression == sympy.Symbol("zeta", real=True)
    zeta = np.linspace(-1.0, -0.01, 7)
    np.testing.assert_allclose(
        value("dyer_hicks1970_richardson_number_unstable", zeta=Q_(zeta, ONE)),
        zeta,
        rtol=1e-15,
    )
    assert not composed.derived


# --- Businger et al. (1971), equation 12, and Carl et al. (1973) --------------


def test_the_normalized_heat_function_of_businger_and_the_form_of_carl() -> None:
    heat = value("businger1971_gradient_function_heat_unstable", zeta=Q_(-1.0, ONE))
    assert float(heat) == pytest.approx(10**-0.5)
    # Carl et al. tend to the free-convection limit (-16 z/L)^(-1/3).
    zeta = Q_(-1e6, ONE)
    carl = value("carl1973_gradient_function_momentum_unstable", zeta=zeta)
    assert float(carl) == pytest.approx(16e6 ** (-1 / 3), rel=1e-7)
    cited = {
        c.reference for c in F["carl1973_gradient_function_momentum_unstable"].citations
    }
    assert cited == {"long1984", "carl1973"}
    assert CATALOG.references["carl1973"].status.value == "to-confirm"


# --- Long (1984), the GUST relations -------------------------------------------


@pytest.mark.parametrize(
    ("key", "column"), [("long1984_gust_momentum", 1), ("long1984_gust_heat", 2)]
)
def test_the_gust_relations_reproduce_the_table_of_long(key: str, column: int) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        roots = value(key, eta=Q_(LONG[:, 0], ONE))
    np.testing.assert_allclose(roots, LONG[:, column], atol=6e-6, rtol=0)
    assert F[key].implicit


def test_the_gust_quartic_is_keyps_and_tends_to_its_limits() -> None:
    zeta = np.linspace(-5.0, -0.01, 50)
    gust = value("long1984_gust_momentum", eta=Q_(-9 * zeta, ONE))
    keyps = value("businger1971_keyps", zeta=Q_(zeta, ONE))
    np.testing.assert_allclose(gust, keyps, rtol=1e-12)
    # Weak instability: (1 + eta)^(-1/4) and (1 + eta)^(-1/2) (2.4), to O(eta^2).
    small = Q_(1e-4, ONE)
    m = float(value("long1984_gust_momentum", eta=small))
    h = float(value("long1984_gust_heat", eta=small))
    assert m == pytest.approx((1 + 1e-4) ** -0.25, abs=1e-8)
    assert h == pytest.approx((1 + 1e-4) ** -0.5, abs=1e-8)
    # Strong instability: eta^(-1/3) for both (p. 9).
    large = Q_(1e9, ONE)
    for key in ("long1984_gust_momentum", "long1984_gust_heat"):
        assert float(value(key, eta=large)) == pytest.approx(1e-3, rel=1e-3)


def test_the_new_entries_are_found_and_typed() -> None:
    gust = {f.key for f in CATALOG.search(keyword="GUST").formulations}
    assert gust == {"long1984_gust_momentum", "long1984_gust_heat"}
    stated = {f.key for f in CATALOG.search(source="dyer_hicks1970").formulations}
    assert stated == {
        "ecmwf_ifs_gradient_function_momentum_unstable",
        "ecmwf_ifs_gradient_function_heat_unstable",
        "dyer_hicks1970_gradient_richardson_number",
        "dyer_hicks1970_richardson_number_unstable",
    }
    assert set(CATALOG.used_by("references.long1984").refs) >= {
        "formulations.fairall1978_gradient_function_momentum_unstable",
        "formulations.businger1971_gradient_function_heat_unstable",
        "formulations.carl1973_gradient_function_momentum_unstable",
        "formulations.long1984_gust_momentum",
        "formulations.long1984_gust_heat",
    }
    for kind in ("GradientRichardsonNumber", "ScaledStabilityParameter"):
        assert CATALOG.kinds[kind].specialization_of == "DimensionlessRatio"
    richardson = {f.key for f in CATALOG.formulations_of("GradientRichardsonNumber")}
    assert richardson == {
        "dyer_hicks1970_gradient_richardson_number",
        "dyer_hicks1970_richardson_number_unstable",
    }
