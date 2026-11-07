# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Stability functions of the surface layer: SHEBA, Cheng and Brutsaert,
Holtslag and De Bruin, Beljaars and Holtslag, Webb, Businger (1985),
COARE 3.6, and the relations between z/L and the Richardson numbers."""

import math

import numpy as np
import pytest
import sympy

from nomogram.catalog import catalog
from nomogram.expression import compile_numeric
from nomogram.model import Formulation
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
ONE = "dimensionless"
STABLE = np.linspace(0.01, 1.9, 40)
UNSTABLE = np.linspace(-1.9, -0.01, 40)


def value(key: str, outside: str = "nan", **inputs: object) -> np.ndarray:
    quantities = {k: Q_(v, ONE) for k, v in inputs.items()}
    result = F[key].evaluate(outside=outside, **quantities)  # type: ignore[arg-type]
    return np.asarray(result.magnitude)


def slope(formulation: Formulation, zeta: np.ndarray) -> np.ndarray:
    """dPsi/dzeta, symbolically, at the values of zeta."""
    expr = formulation.sympy_expression
    derivative = sympy.diff(expr, sympy.Symbol("zeta", real=True))
    function = compile_numeric(derivative, formulation.names)
    fixed = [c.value for c in formulation.coefficients]
    fixed += [k.value for k in formulation.constants]
    return np.asarray(function(zeta, *fixed), dtype=float)


# --- Gradient and profile functions form pairs: Phi = 1 - zeta dPsi/dzeta ----


@pytest.mark.parametrize(
    ("gradient", "profile", "zeta"),
    [
        (
            "grachev2007_gradient_function_momentum_stable",
            "grachev2007_profile_function_momentum_stable",
            STABLE,
        ),
        (
            "grachev2007_gradient_function_heat_stable",
            "grachev2007_profile_function_heat_stable",
            STABLE,
        ),
        (
            "cheng_brutsaert2005_gradient_function_momentum_stable",
            "cheng_brutsaert2005_profile_function_momentum_stable",
            STABLE,
        ),
        (
            "cheng_brutsaert2005_gradient_function_heat_stable",
            "cheng_brutsaert2005_profile_function_heat_stable",
            STABLE,
        ),
        (
            "holtslag_debruin1988_gradient_function_momentum_stable",
            "coare36_profile_function_momentum_stable",
            STABLE,
        ),
        (
            "beljaars_holtslag1991_gradient_function_momentum_stable",
            "ecmwf_ifs_profile_function_momentum_stable",
            STABLE,
        ),
        (
            "beljaars_holtslag1991_gradient_function_heat_stable",
            "ecmwf_ifs_profile_function_heat_stable",
            STABLE,
        ),
        (
            "fairall1978_gradient_function_momentum_stable",
            "businger1985_profile_function_momentum_stable",
            STABLE,
        ),
        (
            "businger1985_gradient_function_heat_stable",
            "businger1985_profile_function_heat_stable",
            STABLE,
        ),
        (
            "ecmwf_ifs_gradient_function_momentum_unstable",
            "ecmwf_ifs_profile_function_momentum_unstable",
            UNSTABLE,
        ),
    ],
)
def test_each_gradient_function_is_the_derivative_of_its_profile_function(
    gradient: str, profile: str, zeta: np.ndarray
) -> None:
    phi = value(gradient, outside="ignore", zeta=zeta)
    np.testing.assert_allclose(phi, 1 - zeta * slope(F[profile], zeta), rtol=1e-10)


# --- SHEBA (Grachev et al. 2007) ----------------------------------------------


def test_sheba_limits_and_its_domain_stated_on_the_bulk_richardson_number() -> None:
    small = 1e-7
    momentum = value("grachev2007_gradient_function_momentum_stable", zeta=[0.0, small])
    heat = value("grachev2007_gradient_function_heat_stable", zeta=[0.0, small])
    # 1 in neutral conditions, of slope a_m = a_h = 5 (p. 329).
    np.testing.assert_allclose([momentum[0], heat[0]], 1.0)
    assert (momentum[1] - 1) / small == pytest.approx(5.0, rel=1e-5)
    assert (heat[1] - 1) / small == pytest.approx(5.0, rel=1e-5)
    # 6.5 zeta^(1/3) and 1 + b_h = 6 as zeta grows (p. 329).
    large = 1e9
    far = value("grachev2007_gradient_function_momentum_stable", zeta=large)
    assert float(far) / (6.5 * large ** (1 / 3)) == pytest.approx(1.0, rel=1e-3)
    assert float(
        value("grachev2007_gradient_function_heat_stable", zeta=large)
    ) == pytest.approx(6.0, rel=1e-6)
    for key in (
        "grachev2007_gradient_function_momentum_stable",
        "grachev2007_profile_function_heat_stable",
    ):
        f = F[key]
        assert not any(c.domains for c in f.citations)
        assert any("RiB" in a.text for a in f.assumptions)


# --- Cheng and Brutsaert (2005) -----------------------------------------------


def test_cheng_brutsaert_limits_and_fitted_ranges() -> None:
    # Psi_m about -4.23 - 6.1 ln(zeta) for large zeta (p. 534), phi_m about 7.
    zeta = 1e4
    psi = value(
        "cheng_brutsaert2005_profile_function_momentum_stable",
        outside="ignore",
        zeta=zeta,
    )
    assert float(psi) == pytest.approx(
        -6.1 * math.log(2) - 6.1 * math.log(zeta), abs=1e-6
    )
    phi = value(
        "cheng_brutsaert2005_gradient_function_momentum_stable",
        outside="ignore",
        zeta=zeta,
    )
    assert float(phi) == pytest.approx(7.1, rel=1e-3)
    # Fitted up to zeta = 5 for momentum, 2 for heat: NaN beyond, by default.
    momentum = value(
        "cheng_brutsaert2005_gradient_function_momentum_stable", zeta=[4.0, 6.0]
    )
    heat = value("cheng_brutsaert2005_gradient_function_heat_stable", zeta=[1.5, 3.0])
    assert not math.isnan(momentum[0])
    assert math.isnan(momentum[1])
    assert not math.isnan(heat[0])
    assert math.isnan(heat[1])


# --- Holtslag and De Bruin, Webb, Businger (1985) -------------------------------


def test_the_log_linear_forms_and_their_stated_range() -> None:
    zeta = np.array([0.1, 0.4])
    np.testing.assert_allclose(
        value("holtslag_debruin1988_gradient_function_momentum_stable", zeta=zeta),
        value("holtslag_debruin1988_gradient_function_heat_stable", zeta=zeta),
    )
    webb = value("webb1970_gradient_function_heat_stable", zeta=[0.4, 1.0])
    ifs = value("ecmwf_ifs_gradient_function_momentum_stable", zeta=[0.4, 1.0])
    # Fairly consistent with most data for 0 < z/L < 0.5 (Beljaars 1992).
    assert webb[0] == pytest.approx(3.0)
    assert ifs[0] == pytest.approx(3.0)
    assert math.isnan(webb[1])
    assert math.isnan(ifs[1])
    assert value(
        "ecmwf_ifs_gradient_function_momentum_stable", outside="ignore", zeta=1.0
    ) == pytest.approx(6.0)


def test_the_richardson_numbers_of_businger_and_of_dyer_and_hicks() -> None:
    # Equation 38 is the identity of Dyer and Hicks with 1 + 4.7 zeta for both.
    zeta = STABLE
    phi = 1 + 4.7 * zeta
    identity = value(
        "dyer_hicks1970_gradient_richardson_number", zeta=zeta, Phi_M=phi, Phi_H=phi
    )
    np.testing.assert_allclose(
        value("businger1985_gradient_richardson_number_stable", zeta=zeta),
        identity,
        rtol=1e-14,
    )
    # With Ri = zeta (equation 37), Fleagle and Businger give Dyer and Hicks.
    zeta = np.linspace(-1.0, -0.01, 9)
    np.testing.assert_allclose(
        value("fleagle_businger1980_gradient_function_momentum_unstable", Ri=zeta),
        value("ecmwf_ifs_gradient_function_momentum_unstable", zeta=zeta),
        rtol=1e-14,
    )


def test_kramm_gives_back_zeta_from_the_richardson_number() -> None:
    # Ri at zeta = 2: 0.182 by Webb's form (4.4), 0.188 by Businger's (4.11).
    webb = 2 / (1 + 5 * 2)
    businger = 2 / (1 + 4.7 * 2) * (1 - 0.26 / (1 + 4.7 * 2))
    assert round(webb, 3) == 0.182
    assert businger == pytest.approx(0.1875)  # printed 0.188
    assert float(value("kramm2013_stability_parameter_webb", Ri=webb)) == pytest.approx(
        2.0, rel=1e-12
    )
    assert float(
        value("kramm2013_stability_parameter_businger", Ri=businger)
    ) == pytest.approx(2.0, rel=1e-12)
    beyond = value("kramm2013_stability_parameter_businger", Ri=[0.21, 0.25])
    assert not math.isnan(beyond[0])
    assert math.isnan(beyond[1])
    assert math.isnan(float(value("kramm2013_stability_parameter_webb", Ri=0.25)))


# --- COARE 3.6 -------------------------------------------------------------------


def test_coare_blends_its_forms_and_steps_at_neutral() -> None:
    near = value("coare36_profile_function_heat", zeta=[-1e-9, 0.0])
    assert near[0] == pytest.approx(0.0, abs=1e-8)
    # The rounded constants of the stable heat function: -0.0045 at zeta = 0.
    assert near[1] == pytest.approx(-(1 - 0.6667 * 14.28 + 8.525), rel=1e-12)
    assert near[1] == pytest.approx(-0.0045, abs=1e-4)
    momentum = value("coare36_profile_function_momentum", zeta=[-1e-9, 0.0])
    np.testing.assert_allclose(momentum, 0.0, atol=1e-8)
    # Convective for large -zeta: the weight zeta^2/(1 + zeta^2) tends to 1.
    zeta = -1e4
    convective = value("coare36_profile_function_momentum_unstable", zeta=zeta)
    y = (1 - 10.15 * zeta) ** 0.3333
    expected = (
        1.5 * math.log((1 + y + y**2) / 3)
        - math.sqrt(3) * math.atan((1 + 2 * y) / math.sqrt(3))
        + math.pi / math.sqrt(3)
    )
    assert float(convective) == pytest.approx(expected, rel=1e-6)


# --- Bulk Richardson number of the lowest level (Beljaars 1992) --------------------


def test_the_bulk_richardson_number_from_z_over_l() -> None:
    def psi(key: str, zeta: float) -> float:
        return float(value(key, zeta=zeta))

    z_1, z_0m, z_0h = 10.0, 1e-4, 1e-5
    for zeta in (-0.5, 0.1):
        expected = (
            zeta
            * (math.log(z_1 / z_0h + 1) - psi("ecmwf_ifs_profile_function_heat", zeta))
            / (
                math.log(z_1 / z_0m + 1)
                - psi("ecmwf_ifs_profile_function_momentum", zeta)
            )
            ** 2
        )
        result = F["beljaars1992_bulk_richardson_number_lowest_level"].evaluate(
            zeta_1=Q_(zeta, ONE),
            z_1=Q_(z_1, "m"),
            z_0M=Q_(z_0m, "m"),
            z_0H=Q_(z_0h, "m"),
        )
        assert result.magnitude == pytest.approx(expected, rel=1e-12)


# --- Search ----------------------------------------------------------------------


def test_the_new_entries_are_found() -> None:
    sheba = {f.key for f in CATALOG.search(keyword="SHEBA").formulations}
    assert sheba == {
        "grachev2007_gradient_function_momentum_stable",
        "grachev2007_gradient_function_heat_stable",
        "grachev2007_profile_function_momentum_stable",
        "grachev2007_profile_function_heat_stable",
    }
    coare = {
        f.key
        for f in CATALOG.search(
            keyword="COARE", kind="ProfileFunctionForHeat"
        ).formulations
    }
    assert coare == {
        "coare36_profile_function_heat_unstable",
        "coare36_profile_function_heat_stable",
        "coare36_profile_function_heat",
    }
    stability = {f.key for f in CATALOG.formulations_of("StabilityParameter")}
    assert {
        "kramm2013_stability_parameter_webb",
        "kramm2013_stability_parameter_businger",
    } <= stability
    cited = {f.key for f in CATALOG.search(source="beljaars1992").formulations}
    assert {
        "ecmwf_ifs_gradient_function_momentum_stable",
        "webb1970_gradient_function_heat_stable",
        "beljaars1992_bulk_richardson_number_lowest_level",
    } <= cited
