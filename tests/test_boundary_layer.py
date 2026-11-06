# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The surface layer of the ECMWF IFS (Part IV, section 3.2): Monin-Obukhov
similarity, roughness lengths, transfer coefficients."""

import math
from typing import Any

import numpy as np
import pytest
import sympy

from nomogram.catalog import catalog
from nomogram.expression import to_latex
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
ONE = "dimensionless"


def zeta(*values: float) -> object:
    return Q_(np.array(values), ONE)


@pytest.mark.parametrize(
    ("gradient", "profile"),
    [
        (
            "ecmwf_ifs_gradient_function_momentum_unstable",
            "ecmwf_ifs_profile_function_momentum_unstable",
        ),
        (
            "ecmwf_ifs_gradient_function_heat_unstable",
            "ecmwf_ifs_profile_function_heat_unstable",
        ),
    ],
)
def test_paulson_integrates_the_gradient_functions(gradient: str, profile: str) -> None:
    # Phi = 1 - zeta dPsi/dzeta (section 3.2), proved symbolically.
    phi, psi = F[gradient].sympy_expression, F[profile].sympy_expression
    (z,) = psi.free_symbols
    assert (
        sympy.simplify(1 - z * sympy.diff(psi, z) - phi.subs(phi.free_symbols.pop(), z))
        == 0
    )


def test_the_profile_functions_by_hand() -> None:
    # Unstable, zeta = -0.5: x = 9^(1/4) = sqrt(3).
    x = math.sqrt(3)
    psi_m = math.pi / 2 - 2 * math.atan(x) + math.log((1 + x) ** 2 * (1 + x**2) / 8)
    values = F["ecmwf_ifs_profile_function_momentum"].evaluate(zeta=zeta(-0.5, 0.5))
    a, b, c, d = 1, 2 / 3, 5, 0.35
    stable = -b * (0.5 - c / d) * math.exp(-d * 0.5) - a * 0.5 - b * c / d
    assert values.magnitude == pytest.approx([psi_m, stable], rel=1e-12)
    heat = F["ecmwf_ifs_profile_function_heat"].evaluate(zeta=zeta(-0.5))
    assert heat.magnitude == pytest.approx([2 * math.log(2)], rel=1e-12)


@pytest.mark.parametrize(
    "key", ["ecmwf_ifs_profile_function_momentum", "ecmwf_ifs_profile_function_heat"]
)
def test_the_branches_of_the_profile_functions_meet_at_neutral(key: str) -> None:
    values = F[key].evaluate(zeta=zeta(-1e-9, 0.0, 1e-9)).magnitude
    assert values == pytest.approx([0.0, 0.0, 0.0], abs=1e-7)


def test_the_profile_function_is_written_with_the_arctangent() -> None:
    latex = to_latex(F["ecmwf_ifs_profile_function_momentum_unstable"].sympy_expression)
    assert r"\arctan" in latex


def test_the_transfer_coefficients_are_logarithmic_at_neutral() -> None:
    z_n, z_0m, z_0h = Q_(10.0, "m"), Q_(1e-3, "m"), Q_(1e-4, "m")
    neutral = Q_(0.0, ONE)
    c_m = F["ecmwf_ifs_transfer_coefficient_momentum"].evaluate(
        z_n=z_n, z_0M=z_0m, zeta_n=neutral, zeta_0M=neutral
    )
    log_m = math.log((10.0 + 1e-3) / 1e-3)
    assert c_m.magnitude == pytest.approx((0.4 / log_m) ** 2, rel=1e-12)
    c_h = F["ecmwf_ifs_transfer_coefficient_heat"].evaluate(
        z_n=z_n, z_0M=z_0m, z_0H=z_0h, zeta_n=neutral, zeta_0M=neutral, zeta_0H=neutral
    )
    log_h = math.log((10.0 + 1e-3) / 1e-4)
    assert c_h.magnitude == pytest.approx(0.4**2 / (log_m * log_h), rel=1e-12)


def test_the_transfer_coefficient_calls_the_profile_function_twice() -> None:
    # Unstable surface layer, L = -50 m: the profile function at both heights.
    z_n, z_0m, length = 10.0, 1e-3, -50.0
    zeta_n, zeta_0 = (z_n + z_0m) / length, z_0m / length
    psi = F["ecmwf_ifs_profile_function_momentum"]
    psi_n, psi_0 = psi.evaluate(zeta=zeta(zeta_n, zeta_0)).magnitude
    c_m = F["ecmwf_ifs_transfer_coefficient_momentum"].evaluate(
        z_n=Q_(z_n, "m"),
        z_0M=Q_(z_0m, "m"),
        zeta_n=Q_(zeta_n, ONE),
        zeta_0M=Q_(zeta_0, ONE),
    )
    expected = 0.4**2 / (math.log((z_n + z_0m) / z_0m) - psi_n + psi_0) ** 2
    assert c_m.magnitude == pytest.approx(expected, rel=1e-12)
    # Unstable: more mixing than at neutral.
    assert expected > (0.4 / math.log((z_n + z_0m) / z_0m)) ** 2


def test_the_friction_velocity_from_the_transfer_coefficient() -> None:
    u_s = F["ecmwf_ifs_friction_velocity"].evaluate(
        C_M=Q_(1.444e-3, ONE), U_n=Q_(10.0, "m/s")
    )
    assert u_s.to("m/s").magnitude == pytest.approx(0.38, rel=1e-12)


def test_the_obukhov_length_from_the_surface_layer_scales() -> None:
    u_s, s_s, q_s, t_n = 0.3, -0.5, -1e-5, 290.0
    length = F["ecmwf_ifs_obukhov_length"].evaluate(
        u_s=Q_(u_s, "m/s"), s_s=Q_(s_s, "J/kg"), q_s=Q_(q_s, "kg/kg"), T_n=Q_(t_n, "K")
    )
    epsilon = 461.5250 / 287.0597 - 1
    q_0v = u_s * s_s / 1004.7090 + epsilon * t_n * u_s * q_s
    expected = -(u_s**3) / (0.4 * 9.80665 / t_n * q_0v)
    assert length.to("m").magnitude == pytest.approx(expected, rel=1e-12)
    # Downward fluxes of heat and moisture: a stable layer, L > 0.
    assert expected > 0


def test_the_bulk_richardson_numbers_agree_on_one_state() -> None:
    # A stable layer: the two forms of the IFS, from the virtual potential
    # temperature (3.26) and from dry static energy and humidity (3.27).
    g, c_p, z_n, u_n = 9.80665, 1004.7090, 10.0, 5.0
    t_surf, t_n, q = 285.0, 287.0, 0.008
    s_surf, s_n = c_p * t_surf, c_p * t_n + g * z_n
    epsilon = 461.5250 / 287.0597 - 1
    theta_v = (s_n + s_surf - g * z_n) / (2 * c_p) * (1 + epsilon * q)
    from_theta = F["ecmwf_ifs_bulk_richardson_number"].evaluate(
        theta_v=Q_(theta_v, "K"),
        z_n=Q_(z_n, "m"),
        theta_vn=Q_(s_n / c_p * (1 + epsilon * q), "K"),
        theta_vsurf=Q_(s_surf / c_p * (1 + epsilon * q), "K"),
        U_n=Q_(u_n, "m/s"),
    )
    from_s = F["ecmwf_ifs_bulk_richardson_number_dry_static_energy"].evaluate(
        z_n=Q_(z_n, "m"),
        U_n=Q_(u_n, "m/s"),
        s_n=Q_(s_n, "J/kg"),
        s_surf=Q_(s_surf, "J/kg"),
        q_n=Q_(q, "kg/kg"),
        q_surf=Q_(q, "kg/kg"),
    )
    assert from_theta.magnitude > 0
    assert from_s.magnitude == pytest.approx(from_theta.magnitude, rel=1e-2)


def test_the_roughness_lengths_over_sea() -> None:
    u_s = Q_(0.3, "m/s")
    z_0m = F["ecmwf_ifs_roughness_length_momentum_sea"].evaluate(u_s=u_s)
    expected = 0.11 * 1.5e-5 / 0.3 + 0.018 * 0.3**2 / 9.80665
    assert z_0m.to("m").magnitude == pytest.approx(expected, rel=1e-12)
    z_0h = F["ecmwf_ifs_roughness_length_heat_sea"].evaluate(u_s=u_s)
    z_0q = F["ecmwf_ifs_roughness_length_humidity_sea"].evaluate(u_s=u_s)
    assert z_0h.to("m").magnitude == pytest.approx(0.40 * 1.5e-5 / 0.3, rel=1e-12)
    assert z_0q.to("m").magnitude == pytest.approx(0.62 * 1.5e-5 / 0.3, rel=1e-12)


def test_the_roughness_length_over_sea_ice_is_the_max_of_the_ifs() -> None:
    c_i = np.linspace(0.0, 1.0, 1001)
    z_0m = F["ecmwf_ifs_roughness_length_momentum_sea_ice"].evaluate(c_i=Q_(c_i, ONE))
    written = np.maximum(
        1e-3, 0.93e-3 * (1 - c_i) + 6.05e-3 * np.exp(-17 * (c_i - 0.5) ** 2)
    )
    assert z_0m.to("m").magnitude == pytest.approx(written, rel=1e-12)


def test_the_surface_layer_is_found_by_search() -> None:
    assert (
        "formulations.ecmwf_ifs_obukhov_length"
        in CATALOG.search(kind="ObukhovLength").refs
    )
    paulson = set(CATALOG.used_by("references.paulson1970").refs)
    assert "formulations.ecmwf_ifs_profile_function_momentum_unstable" in paulson
    term = CATALOG.search("drag coefficient").refs
    assert "trade_terms.drag_coefficient" in term
    assert CATALOG.families["boundary-layer"].requires == ("atmosphere",)


def test_the_surface_layer_is_linked_to_wikidata() -> None:
    from nomogram.semantics import MatchRelation

    entity = "http://www.wikidata.org/entity/"

    def wikidata(entry: object) -> tuple[str, MatchRelation]:
        matches = entry.matches  # type: ignore[attr-defined]
        (link,) = [m for m in matches if m.target.startswith(entity)]
        return link.target.removeprefix(entity), link.relation

    # The Monin-Obukhov length of Wikidata is the atmosphere's: narrower than
    # the kind, which is any fluid's.
    assert wikidata(CATALOG.kinds["ObukhovLength"]) == (
        "Q3110303",
        MatchRelation.NARROW,
    )
    assert wikidata(CATALOG.kinds["FrictionVelocity"]) == (
        "Q1695787",
        MatchRelation.EXACT,
    )
    assert wikidata(CATALOG.references["hogstrom1988"]) == (
        "Q60638164",
        MatchRelation.EXACT,
    )


def test_the_dry_static_energy_at_2_m_at_neutral_and_very_stable() -> None:
    f = F["ecmwf_ifs_dry_static_energy_2m"]
    s_surf, s_n, z_n, z_0ma, z_0h = 288000.0, 288500.0, 10.0, 0.1, 0.01
    lengths: dict[str, Any] = {
        "s_surf": Q_(s_surf, "J/kg"),
        "s_n": Q_(s_n, "J/kg"),
        "z_n": Q_(z_n, "m"),
        "z_0ma": Q_(z_0ma, "m"),
        "z_0H": Q_(z_0h, "m"),
    }
    neutral = Q_(0.0, ONE)
    s_2 = f.evaluate(**lengths, zeta_2=neutral, zeta_n=neutral, zeta_0H=neutral)
    beta = math.log((2 + z_0ma) / z_0h) / math.log((z_n + z_0ma) / z_0h)
    assert s_2.magnitude == pytest.approx(s_surf + (s_n - s_surf) * beta, rel=1e-12)
    # Very stable: f_2m tends to 1, and the interpolation factor to 0.75.
    far = f.evaluate(
        **lengths, zeta_2=Q_(1e9, ONE), zeta_n=Q_(1e9, ONE), zeta_0H=Q_(1e7, ONE)
    )
    assert far.magnitude == pytest.approx(s_surf + 0.75 * (s_n - s_surf), rel=1e-6)


def test_the_wind_at_10_m_is_the_wind_at_a_blending_height_of_10_m() -> None:
    zeta_10 = Q_(-0.2, ONE)
    f_10 = F["ecmwf_ifs_wind_speed_10m"].evaluate(
        F_blend=Q_(6.0, "m/s"),
        z_blend=Q_(10.0, "m"),
        z_0=Q_(0.03, "m"),
        zeta_10=zeta_10,
        zeta_blend=zeta_10,
        zeta_0=Q_(-0.0006, ONE),
    )
    assert f_10.to("m/s").magnitude == pytest.approx(6.0, rel=1e-12)


def test_the_friction_velocity_of_the_diagnostics_agrees_with_the_drag() -> None:
    # 3.108 against 3.29 with C_M of 3.16, at the same heights.
    z_b, z_0, zeta_b, zeta_0 = 40.0, 0.03, (40.0 + 0.03) / -100.0, 0.03 / -100.0
    u_s = F["ecmwf_ifs_friction_velocity_blending_height"].evaluate(
        F_blend=Q_(8.0, "m/s"),
        z_blend=Q_(z_b, "m"),
        z_0=Q_(z_0, "m"),
        zeta_blend=Q_(zeta_b, ONE),
        zeta_0=Q_(zeta_0, ONE),
    )
    c_m = F["ecmwf_ifs_transfer_coefficient_momentum"].evaluate(
        z_n=Q_(z_b, "m"),
        z_0M=Q_(z_0, "m"),
        zeta_n=Q_(zeta_b, ONE),
        zeta_0M=Q_(zeta_0, ONE),
    )
    from_drag = F["ecmwf_ifs_friction_velocity"].evaluate(C_M=c_m, U_n=Q_(8.0, "m/s"))
    assert u_s.to("m/s").magnitude == pytest.approx(
        from_drag.to("m/s").magnitude, rel=1e-12
    )


def test_the_visibility_of_clean_air_is_100_km() -> None:
    beta = -math.log(0.02) / 1e5
    v = F["ecmwf_ifs_visibility"].evaluate(beta_tot=Q_(beta, "1/m"))
    assert v.to("km").magnitude == pytest.approx(100.0, rel=1e-12)
    assert CATALOG.kinds["Visibility"].cf_standard_names == ("visibility_in_air",)


@pytest.mark.parametrize(
    "key",
    [
        "ecmwf_ifs_profile_function_momentum_stable",
        "ecmwf_ifs_profile_function_heat_stable",
    ],
)
def test_the_stable_profile_functions_carry_the_constants_of_beljaars_and_holtslag(
    key: str,
) -> None:
    # The IFS attributes the form to Holtslag and De Bruin (1988), modified;
    # a = 1 and b = 2/3 are those of Beljaars and Holtslag (1991), where
    # Holtslag and De Bruin have 0.7 and 0.75 (Andreas 2002, eq. 3.4, 3.5).
    formulation = F[key]
    coefficients = {c.identifier: c.value for c in formulation.coefficients}
    assert coefficients["a"] == 1.0
    assert coefficients["b"] == pytest.approx(2 / 3)
    assert "beljaars_holtslag1991" in formulation.references
    assert f"formulations.{key}" in CATALOG.search("Beljaars").refs
    assert CATALOG.references["andreas2002"].status.value == "verified"
