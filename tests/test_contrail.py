# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Contrail formation from aircraft exhaust (family ``contrail``).

The oracles are the values Schumann (1996, 2000, 2012), Ponater et al.
(2002) and Gierens (2021) print. The exact threshold temperatures, which
the catalog solves as implicit equations, are also computed here by
bisection, independently of its search for roots: the slope of the
Sonntag form of Schumann (2012), A1, for the maximum threshold
temperature (Schumann 1996, equation 10), and A1 itself for the threshold
temperature (equation 11, on the root below the maximum threshold
temperature).
"""

from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from bundled_catalog import with_families

from nomogram.comparison import compose
from nomogram.model import RootWarning
from nomogram.units import Q_

CATALOG = with_families(("contrail",))
F = CATALOG.formulations

Array = npt.NDArray[np.float64]


def value(key: str, unit: str, outside: Any = "nan", **inputs: Any) -> Array:
    return np.asarray(
        F[key].evaluate(outside=outside, **inputs).to(unit).magnitude, dtype=float
    )


def slope(t: npt.ArrayLike) -> Array:
    key = "schumann2012_saturation_vapour_pressure_slope_liquid"
    return value(key, "Pa/K", T=Q_(t, "K"))


def p_liq(t: npt.ArrayLike) -> Array:
    return value("schumann2012_saturation_vapour_pressure_liquid", "Pa", T=Q_(t, "K"))


def bisect(residual: Callable[[Array], Array], low: Array, high: Array) -> Array:
    """The root of an increasing residual between low and high, elementwise."""
    for _ in range(64):
        middle = 0.5 * (low + high)
        above = residual(middle) > 0
        high = np.where(above, middle, high)
        low = np.where(above, low, middle)
    return np.asarray(0.5 * (low + high), dtype=float)


def exact_t_lm(g_values: npt.ArrayLike) -> Array:
    """Schumann (1996), equation 10: the slope of e_L equals G at T_LM."""
    g = np.asarray(g_values, dtype=float)
    return bisect(
        lambda t: slope(t) - g, np.full(g.shape, 150.0), np.full(g.shape, 320.0)
    )


def exact_t_lc(g_values: npt.ArrayLike, u_values: npt.ArrayLike) -> Array:
    """Schumann (1996), equation 11, below T_LM, where its residual increases."""
    g, u = np.broadcast_arrays(
        np.asarray(g_values, dtype=float), np.asarray(u_values, dtype=float)
    )
    t_lm = exact_t_lm(g)
    p_lm = p_liq(t_lm)
    return bisect(
        lambda t: t - (t_lm - (p_lm - u * p_liq(t)) / g),
        np.full(g.shape, 120.0),
        t_lm - 1e-9,
    )


def test_overall_propulsion_efficiency_of_the_b747_and_of_attas() -> None:
    key = "schumann1996_overall_propulsion_efficiency"
    # Table 2 of Schumann (1996): 31.1 kN, 247 m/s, 0.58 kg/s, 43 MJ/kg.
    b747 = value(
        key,
        "",
        F=Q_(31.1, "kN"),
        V=Q_(247, "m/s"),
        Q=Q_(43, "MJ/kg"),
        m_F=Q_(0.58, "kg/s"),
    )
    assert b747 == pytest.approx(0.30801, abs=5e-6)
    assert b747 == pytest.approx(0.308, abs=5e-4)  # as printed
    # ATTAS (p. 12): 6400 N, 115 m/s, 0.125 kg/s, "eta = 0.14 +/- 0.005".
    attas = value(
        key,
        "",
        F=Q_(6400, "N"),
        V=Q_(115, "m/s"),
        Q=Q_(43, "MJ/kg"),
        m_F=Q_(0.125, "kg/s"),
    )
    assert attas == pytest.approx(0.14, abs=0.005)


def test_an_efficiency_above_one_is_outside_its_kind() -> None:
    key = "schumann1996_overall_propulsion_efficiency"
    eta = value(
        key,
        "",
        F=Q_(100, "kN"),
        V=Q_(300, "m/s"),
        Q=Q_(43, "MJ/kg"),
        m_F=Q_(0.5, "kg/s"),
    )
    assert np.isnan(eta)  # 1.40: energy would not be conserved


def test_emission_indices_of_table_1() -> None:
    key = "schumann1996_emission_index_water_vapour"
    found = value(key, "kg/kg", m_H=Q_([0.14, 0.251, 1.0], "kg/kg"))
    assert found.tolist() == pytest.approx([1.25111, 2.24306, 8.93651], abs=5e-6)
    assert found.tolist() == pytest.approx([1.25, 2.24, 8.94], abs=5e-3)  # as printed


def test_slopes_of_the_mixing_line_of_table_3() -> None:
    key = "schumann1996_mixing_line_slope"
    common = {"c_p": Q_(1004, "J/(kg*K)"), "p": Q_(220, "hPa"), "eta": Q_(0.308, "")}
    fuels = {"kerosene": (1.25, 43), "methane": (2.24, 50), "hydrogen": (8.94, 120)}
    found = {
        name: float(value(key, "Pa/K", EI=Q_(ei, "kg/kg"), Q=Q_(q, "MJ/kg"), **common))
        for name, (ei, q) in fuels.items()
    }
    assert found["kerosene"] == pytest.approx(1.49, abs=5e-3)
    assert found["hydrogen"] == pytest.approx(3.82, abs=5e-3)
    # Table 3 prints 2.31 for methane; its Table 1 gives 2.299, which
    # departs from it by -0.5 %.
    assert found["methane"] == pytest.approx(2.2990, abs=5e-5)
    assert (found["methane"] - 2.31) / 2.31 == pytest.approx(-0.0048, abs=5e-4)


def test_contrail_factor_and_the_factors_of_peters() -> None:
    key = "schumann2000_contrail_factor"
    common = {
        "EI": Q_(1.25, "kg/kg"),
        "c_p": Q_(1004, "J/(kg*K)"),
        "Q": Q_(43, "MJ/kg"),
    }
    at_zero = float(value(key, "1/K", eta=Q_(0.0, ""), **common))
    assert at_zero * 1000 == pytest.approx(0.0292, abs=5e-5)  # g kg-1 K-1, as printed
    # The factors Peters suggested imply eta = 0.19, 0.27 and 0.40.
    implied = [1 - at_zero * 1000 / c for c in (0.036, 0.040, 0.049)]
    assert implied == pytest.approx([0.19, 0.27, 0.40], abs=5e-3)
    # C = G epsilon / p: the identity agrees with the slope of the mixing line.
    eta = Q_(0.308, "")
    g = value(
        "schumann1996_mixing_line_slope", "Pa/K", p=Q_(220, "hPa"), eta=eta, **common
    )
    from_slope = value(
        "schumann2000_contrail_factor_from_slope",
        "1/K",
        G=Q_(g, "Pa/K"),
        p=Q_(220, "hPa"),
    )
    assert from_slope == pytest.approx(value(key, "1/K", eta=eta, **common), rel=1e-12)


def test_maximum_threshold_temperatures_of_table_3() -> None:
    exact = exact_t_lm(np.array([1.49, 2.31, 3.82])) - 273.15
    assert exact.tolist() == pytest.approx([-42.9, -38.3, -32.7], abs=0.06)
    fit = value(
        "schumann1996_maximum_threshold_temperature_fit",
        "degC",
        G=Q_([1.49, 2.31, 3.82], "Pa/K"),
    )
    assert np.abs(fit - exact).max() < 0.05


def test_the_fit_of_schumann1996_departs_as_measured() -> None:
    g = np.geomspace(0.24, 23, 241)
    # At the very ends: geomspace may land a rounding beyond them.
    fit = value(
        "schumann1996_maximum_threshold_temperature_fit",
        "K",
        outside="ignore",
        G=Q_(g, "Pa/K"),
    )
    deviation = np.abs(fit - exact_t_lm(g))
    # 0.056 degC stated; 0.0755 K at G = 0.24 Pa/K, 0.0746 K at 23 Pa/K.
    assert deviation[0] == pytest.approx(0.0755, abs=5e-4)
    assert deviation[-1] == pytest.approx(0.0746, abs=5e-4)
    inner = (g >= 0.3) & (g <= 20)
    assert deviation[inner].max() < 0.043


def test_the_cubic_fit_of_gierens2021() -> None:
    key = "gierens2021_maximum_threshold_temperature_cubic"
    # "About 7.8 [Pa/K] at pa = 1000 hPa, implying a temperature threshold
    # of about -24 degC" (p. 10).
    assert value(key, "degC", G=Q_(7.8, "Pa/K")) == pytest.approx(-24.0, abs=0.5)
    g = np.geomspace(2, 200, 241)
    exact = exact_t_lm(g)
    inside = (exact >= 233) & (exact <= 293)
    assert (
        np.abs(value(key, "K", G=Q_(g[inside], "Pa/K")) - exact[inside]).max() < 0.033
    )


def test_gierens2021_switches_fits_at_two_pascals_per_kelvin() -> None:
    whole = F["gierens2021_maximum_threshold_temperature"]
    assert whole.derivation is not None
    assert whole.derivation.method == "branches"
    g = Q_([1.5, 2.5], "Pa/K")
    low = value("gierens2021_maximum_threshold_temperature_low", "K", G=g[:1])
    cubic = value("gierens2021_maximum_threshold_temperature_cubic", "K", G=g[1:])
    assert value(whole.key, "K", G=g).tolist() == pytest.approx([*low, *cubic])
    # The fits meet within 0.008 K at G = 2 Pa/K.
    at_two = Q_(2.0, "Pa/K")
    step = value(
        "gierens2021_maximum_threshold_temperature_cubic", "K", G=at_two
    ) - value("gierens2021_maximum_threshold_temperature_low", "K", G=at_two)
    assert step == pytest.approx(0.0081, abs=1e-4)


def threshold_fit(g_values: npt.ArrayLike, u_values: npt.ArrayLike) -> Array:
    g, u = np.broadcast_arrays(
        np.asarray(g_values, dtype=float), np.asarray(u_values, dtype=float)
    )
    return value(
        "schumann2012_threshold_temperature_fit",
        "K",
        T_LM=Q_(exact_t_lm(g), "K"),
        U=Q_(u, ""),
        G=Q_(g, "Pa/K"),
    )


def test_threshold_temperature_of_the_b747() -> None:
    # Table 3 of Schumann (1996): -50.6 degC for kerosene, U = 0.42.
    exact = exact_t_lc(1.49, 0.42) - 273.15
    assert exact == pytest.approx(-50.6, abs=0.06)
    assert threshold_fit(1.49, 0.42) - 273.15 == pytest.approx(exact, abs=0.13)


def test_the_fit_of_schumann2012_is_exact_at_both_ends_of_the_humidity() -> None:
    # Equation A7 at U = 0 and U = 1, where the correction is zero; it rises
    # steeply just below U = 1 (2e-4 K at U = 1 - 1e-12).
    # At U = 1 the root is double (the mixing line touches the curve): the
    # bisection finds it to about 1e-6 K only.
    g = np.array([0.5, 2.0, 10.0])
    for u in (0.0, 1.0):
        assert threshold_fit(g, u).tolist() == pytest.approx(
            exact_t_lc(g, u).tolist(), abs=1e-5
        )


def test_the_fit_of_schumann2012_departs_as_measured() -> None:
    # 0.13 K stated; the largest deviations lie near U = 0.9 at the ends of
    # the range of G, which Figure A2 (U up to 0.8) does not show.
    near_top = abs(threshold_fit(23.0, 0.89) - exact_t_lc(23.0, 0.89))
    assert near_top == pytest.approx(0.18, abs=0.01)
    near_bottom = abs(threshold_fit(0.24, 0.88) - exact_t_lc(0.24, 0.88))
    assert near_bottom == pytest.approx(0.14, abs=0.01)
    g, u = np.meshgrid(np.geomspace(1, 15, 6), np.linspace(0, 0.995, 21))
    assert np.abs(threshold_fit(g, u) - exact_t_lc(g, u)).max() < 0.125


def test_a_threshold_temperature_is_a_point_where_saturation_is_evaluated() -> None:
    # The maximum threshold temperature feeds the temperature of a
    # saturation vapour pressure: p_liq(T_LM), which the fit of Schumann
    # (2012) calls.
    at_threshold = compose(
        F["schumann2012_saturation_vapour_pressure_liquid"],
        {"T": F["schumann1996_maximum_threshold_temperature_fit"]},
    )
    t_lm = value(
        "schumann1996_maximum_threshold_temperature_fit", "K", G=Q_(1.49, "Pa/K")
    )
    found = at_threshold.evaluate(G=Q_(1.49, "Pa/K")).to("Pa").magnitude
    assert found == pytest.approx(float(p_liq(t_lm)), rel=1e-12)


def test_the_alternatives_of_the_maximum_threshold_temperature_are_found_together() -> (
    None
):
    found = {
        f.key for f in CATALOG.formulations_of("ContrailMaximumThresholdTemperature")
    }
    assert found == {
        "schumann1996_maximum_threshold_temperature_liquid",
        "schumann1996_maximum_threshold_temperature_fit",
        "gierens2021_maximum_threshold_temperature_low",
        "gierens2021_maximum_threshold_temperature_cubic",
        "gierens2021_maximum_threshold_temperature",
    }
    assert (
        "formulations.schumann1996_mixing_line_slope" in CATALOG.search("contrail").refs
    )
    # A provisional kind, found by the pull request adding it to QUDT.
    assert "kinds.MixingLineSlope" in CATALOG.search("1621").refs
    # "Contrail factor": C for Schumann (2000), G for Gierens (2021).
    meanings = CATALOG.trade_terms["contrail_factor"].meanings
    assert [m.kind for m in meanings] == ["ContrailFactor", "MixingLineSlope"]
    assert "trade_terms.contrail_factor" in CATALOG.search("contrail factor").refs


def test_the_slopes_of_saturation_are_derivatives_of_the_forms_in_pascals() -> None:
    for phase in ("liquid", "ice"):
        slope_entry = F[f"schumann2012_saturation_vapour_pressure_slope_{phase}"]
        assert slope_entry.derivation is not None
        assert (
            slope_entry.derivation.source
            == f"schumann2012_saturation_vapour_pressure_{phase}"
        )
    ice = value(
        "schumann2012_saturation_vapour_pressure_slope_ice", "Pa/K", T=Q_(230.0, "K")
    )
    liquid = slope(np.array(230.0))
    # Below the triple point, ice saturates at a lower pressure: at 230 K
    # its slope is smaller, about L_s p_i / (L_v p_w) = 1.13 x 0.62 = 0.71
    # times that over supercooled water, despite a larger latent heat.
    assert 0 < ice < liquid
    assert ice / liquid == pytest.approx(0.71, abs=0.01)
    # In fixed units, the coefficients keep the units inferred in the form
    # they derive from, where its exponential holds the pascals.
    units = F["schumann2012_saturation_vapour_pressure_slope_liquid"].coefficient_units
    assert {name: f"{u.unit:~}" for name, u in units.items()} == {
        "a0": "K",
        "a1": "",
        "a2": "1 / K",
        "a3": "1 / K ** 2",
        "a4": "",
    }
    assert units["a0"].reason == (
        "as in schumann2012_saturation_vapour_pressure_liquid, of which it is the derivative"
    )


TABLE_3 = Q_([1.49, 2.31, 3.82], "Pa/K")  # kerosene, methane, hydrogen
U_TABLE_2 = Q_(0.42, "")


def test_exact_threshold_temperatures_of_table_3() -> None:
    t_lm = F["schumann1996_maximum_threshold_temperature_liquid"].evaluate(G=TABLE_3)
    t_im = F["schumann1996_maximum_threshold_temperature_ice"].evaluate(G=TABLE_3)
    t_lc = F["schumann1996_threshold_temperature_liquid"].evaluate(
        T_LM=t_lm, U=U_TABLE_2, G=TABLE_3
    )
    t_ic = F["schumann1996_threshold_temperature_ice"].evaluate(
        T_IM=t_im, U=U_TABLE_2, G=TABLE_3
    )
    printed = {
        "T_LM": (t_lm, [-42.9, -38.3, -32.7]),
        "T_IM": (t_im, [-39.8, -35.5, -30.4]),
        "T_LC": (t_lc, [-50.6, -46.3, -41.2]),
        "T_IC": (t_ic, [-45.7, -41.8, -37.1]),
    }
    for found, values in printed.values():
        assert found.to("degC").magnitude.tolist() == pytest.approx(values, abs=0.06)
    # The search for roots agrees with the bisection.
    g = TABLE_3.magnitude
    assert t_lm.to("K").magnitude == pytest.approx(exact_t_lm(g), abs=1e-6)
    assert t_lc.to("K").magnitude == pytest.approx(exact_t_lc(g, 0.42), abs=1e-6)


def test_the_root_of_equation_11_above_t_lm_is_left_out() -> None:
    # Equation 11 has a second root above T_LM, about -21.65 degC for
    # kerosene, which no search reaches: the relative bound ends it at T_LM.
    g = TABLE_3.magnitude
    t_lm = exact_t_lm(g)
    p_lm = p_liq(t_lm)
    above = bisect(
        lambda t: -(t - (t_lm - (p_lm - 0.42 * p_liq(t)) / g)),
        t_lm + 1e-9,
        np.full(g.shape, 320.0),
    )
    assert (above - 273.15).tolist() == pytest.approx([-21.65, -15.96, -9.03], abs=0.01)
    found = F["schumann1996_threshold_temperature_liquid"].evaluate(
        T_LM=Q_(t_lm, "K"), U=U_TABLE_2, G=TABLE_3
    )
    assert (found.to("K").magnitude < t_lm).all()
    with pytest.warns(RootWarning, match="no root in the interval searched"):
        beyond = F["schumann1996_threshold_temperature_liquid"].evaluate(
            T_LM=Q_(t_lm[0], "K"), U=U_TABLE_2, G=TABLE_3[0], search=(260.0, 300.0)
        )
    assert np.isnan(beyond.magnitude)


def test_at_liquid_saturation_the_threshold_is_its_maximum() -> None:
    system = CATALOG.systems["schumann1996_threshold_temperature"]
    solution = system.evaluate(G=TABLE_3, U=Q_(1.0, ""))
    # The double root is taken on the end, or found where the members
    # cross within their rounding, about 1e-6 K below it.
    assert solution["T_LC"].to("K").magnitude == pytest.approx(
        solution["T_LM"].to("K").magnitude, abs=2e-6
    )


def test_the_threshold_temperature_of_attas() -> None:
    # Busen and Schumann (1995), as Schumann (1996) gives them (p. 12):
    # 302.3 hPa, EI = 1.21, Q = 43 MJ/kg, eta = 0.14: T_LC = -50.4 degC at
    # 34 %, -49.8 degC at 45 %, "about -51.8" for eta = 0.
    system = CATALOG.systems["schumann1996_threshold_temperature"]
    found = []
    for u, eta in ((0.34, 0.14), (0.45, 0.14), (0.34, 0.0)):
        g = F["schumann1996_mixing_line_slope"].evaluate(
            EI=Q_(1.21, "kg/kg"),
            c_p=Q_(1004, "J/(kg*K)"),
            p=Q_(302.3, "hPa"),
            Q=Q_(43, "MJ/kg"),
            eta=Q_(eta, ""),
        )
        found.append(
            float(system.evaluate(G=g, U=Q_(u, ""))["T_LC"].to("degC").magnitude)
        )
    assert found == pytest.approx([-50.4, -49.8, -51.8], abs=0.06)


def test_the_fit_of_the_maximum_over_ice_departs_as_measured() -> None:
    g = np.geomspace(0.15, 23, 241)
    exact = F["schumann1996_maximum_threshold_temperature_ice"].evaluate(
        G=Q_(g, "Pa/K")
    )
    fit = value(
        "schumann1996_maximum_threshold_temperature_ice_fit",
        "K",
        outside="ignore",
        G=Q_(g, "Pa/K"),
    )
    deviation = np.abs(fit - exact.to("K").magnitude)
    # 0.036 degC stated; 0.050 K at G = 0.15 Pa/K, the end of the range.
    assert deviation[0] == pytest.approx(0.0501, abs=5e-4)
    assert deviation[(g >= 0.3) & (g <= 20)].max() < 0.032


def test_the_threshold_over_ice_holds_below_ice_saturation_at_t_im() -> None:
    t_im = F["schumann1996_maximum_threshold_temperature_ice"].evaluate(G=TABLE_3[0])
    ratio = (
        F["schumann2012_saturation_vapour_pressure_ice"].evaluate(T=t_im)
        / F["schumann2012_saturation_vapour_pressure_liquid"].evaluate(T=t_im)
    ).to("")
    u = Q_(float(ratio.magnitude) + np.array([-0.05, 0.0, 0.05]), "")
    with pytest.warns(RootWarning, match="no root"):
        found = F["schumann1996_threshold_temperature_ice"].evaluate(
            T_IM=t_im, U=u, G=TABLE_3[0]
        )
    kelvins = found.to("K").magnitude
    assert kelvins[0] < t_im.to("K").magnitude
    # Just saturated with respect to ice at T_IM: the double root, T_IM.
    assert kelvins[1] == pytest.approx(t_im.to("K").magnitude, abs=1e-6)
    assert np.isnan(kelvins[2])  # supersaturated: no threshold


def test_the_critical_relative_humidity() -> None:
    key = "schumann2012_critical_relative_humidity"
    t_lm = F["schumann1996_maximum_threshold_temperature_liquid"].evaluate(G=TABLE_3[0])
    u = Q_(np.array([0.0, 0.2, 0.42, 0.8, 0.99, 1.0]), "")
    t_lc = F["schumann1996_threshold_temperature_liquid"].evaluate(
        T_LM=t_lm, U=u, G=TABLE_3[0]
    )
    # At the threshold temperature for U, the critical humidity is U.
    back = F[key].evaluate(T=t_lc, T_LM=t_lm, G=TABLE_3[0])
    assert back.magnitude == pytest.approx(u.magnitude, abs=1e-9)
    # Negative where dry air gives contrails; none above T_LM, as Ponater
    # et al. (2002) state, applied by default.
    found = F[key].evaluate(T=Q_([-59.0, -30.0], "degC"), T_LM=t_lm, G=TABLE_3[0])
    assert found.magnitude[0] == pytest.approx(-4.5026, abs=5e-4)
    assert np.isnan(found.magnitude[1])
    # Evaluated anyway, the formula gives there a number below 1, which is
    # no threshold.
    assert F[key].evaluate(
        T=Q_(-30.0, "degC"), T_LM=t_lm, G=TABLE_3[0], outside="ignore"
    ).magnitude == pytest.approx(0.652, abs=5e-4)


def test_the_systems_of_the_threshold_temperature() -> None:
    exact = CATALOG.systems["schumann1996_threshold_temperature"].evaluate(
        G=TABLE_3, U=U_TABLE_2
    )
    assert exact["T_LC"].to("degC").magnitude.tolist() == pytest.approx(
        [-50.641, -46.346, -41.175], abs=5e-4
    )
    ice = CATALOG.systems["schumann1996_threshold_temperature_ice"].evaluate(
        G=TABLE_3, U=U_TABLE_2
    )
    assert ice["T_IC"].to("degC").magnitude.tolist() == pytest.approx(
        [-45.7, -41.8, -37.1], abs=0.06
    )
    # The way of Schumann (2012), by the fits, within 0.13 K of it here.
    fit = CATALOG.systems["schumann2012_threshold_temperature"].evaluate(
        G=TABLE_3, U=U_TABLE_2
    )
    gap = fit["T_LC"].to("K").magnitude - exact["T_LC"].to("K").magnitude
    assert np.abs(gap).max() < 0.08


def appleman_saturation(t_celsius: npt.ArrayLike, p_hpa: float) -> Array:
    """The saturation mixing ratio over water in g/kg, as Appleman's tables
    imply it: Goff-Gratch, eps e / (p - e) with eps = 0.622."""
    e = value(
        "goff_gratch1946",
        "hPa",
        outside="ignore",
        T=Q_(np.asarray(t_celsius, dtype=float) + 273.15, "K"),
    )
    return np.asarray(1000 * 0.622 * e / (p_hpa - e), dtype=float)


APPLEMAN_T = np.array([-40.0, -50.0, -60.0, -70.0, -80.0])


def test_the_saturation_of_appleman_reproduces_table_1() -> None:
    # Table I: the moisture a saturated mixture needs per degree of
    # temperature rise to stay saturated, in g kg-1 per degree.
    table_1 = {
        (1000, 5): [0.0154, 0.0059, 0.0020, 0.0006, 0.0002],
        (1000, 40): [0.0926, 0.0436, 0.0192, 0.0078, 0.0029],
        (500, 5): [0.0308, 0.0117, 0.0040, 0.0013, 0.0004],
        (500, 40): [0.1864, 0.0875, 0.0384, 0.0156, 0.0058],
        (100, 5): [0.1544, 0.0587, 0.0201, 0.0062, 0.0017],
        (100, 40): [0.9822, 0.4466, 0.1935, 0.0778, 0.0291],
    }
    for (p, d_t), printed in table_1.items():
        required = (
            appleman_saturation(APPLEMAN_T + d_t, p)
            - appleman_saturation(APPLEMAN_T, p)
        ) / d_t
        # Within 1.2 % where the table prints two figures or more, within
        # its last figure below.
        assert required == pytest.approx(printed, rel=0.012, abs=1.2e-4)


def test_the_moisture_available_of_table_2() -> None:
    key = "appleman1953_available_moisture"
    table_2 = {
        (1000, 5): [0.0102, 0.0257, 0.0312, 0.0330, 0.0335],
        (1000, 40): [0.0307, 0.0326, 0.0333, 0.0335, 0.0336],
        (500, 5): [0.0, 0.0178, 0.0288, 0.0324, 0.0333],
        (500, 40): [0.0278, 0.0316, 0.0330, 0.0334, 0.0336],
        (100, 5): [0.0, 0.0, 0.0098, 0.0273, 0.0321],
        (100, 40): [0.0044, 0.0237, 0.0306, 0.0328, 0.0334],
    }
    for (p, d_t), printed in table_2.items():
        available = value(
            key,
            "g/kg/K",
            w_sw=Q_(appleman_saturation(APPLEMAN_T, p), "g/kg"),
            f_w=Q_(0.0, "percent"),
            dT=Q_(d_t, "K"),
        )
        positive = np.array(printed) > 0
        # The largest gap, 2.4e-4 at 100 hPa, -40 degC and Delta T = 40: the
        # saturation of Appleman's tables is not printed, Goff-Gratch with
        # 0.622 is an assumption, and its error grows at low pressure.
        assert available[positive] == pytest.approx(
            np.array(printed)[positive], abs=2.5e-4
        )
        # The table prints 0 where the formula gives less.
        assert (available[~positive] < 0).all()
    # Saturated air keeps the whole 0.0336 g kg-1 per degree.
    saturated = value(
        key,
        "g/kg/K",
        w_sw=Q_(0.5, "g/kg"),
        f_w=Q_(100.0, "percent"),
        dT=Q_(5.0, "K"),
    )
    assert saturated == pytest.approx(0.0336)


def test_the_critical_temperatures_of_figure_1() -> None:
    # The inset of Figure 1: P = 500 mb, Delta T = 5 degrees (N = 700).
    found = value(
        "appleman1953_critical_temperature_fixed_mixing",
        "degC",
        f_w=Q_([100, 95, 90, 80, 60, 40, 0], "percent"),
        p=Q_(500, "hPa"),
        dT=Q_(5, "K"),
    )
    printed = [-39.1, -40.0, -40.7, -41.9, -44.0, -45.6, -48.2]
    assert found.tolist() == pytest.approx(printed, abs=0.11)
    # Its scale is IPTS-48, inferred from the date: the result on ITS-90
    # differs from the formula as written by t90 - t48, +0.03 K here.
    as_written = value(
        "appleman1953_critical_temperature_fixed_mixing",
        "degC",
        scale="ignore",
        f_w=Q_(100, "percent"),
        p=Q_(500, "hPa"),
        dT=Q_(5, "K"),
    )
    assert found[0] - as_written == pytest.approx(0.03, abs=0.005)


def test_the_highest_critical_temperature_is_that_of_figure_4() -> None:
    # Figure 4, read to 0.3 K: the highest critical temperature over the
    # mixing ratios, for Delta T from 0.5 to 60 degrees as Appleman's
    # tables. Below -50 degC the Goff-Gratch equation over water stops,
    # and the default evaluation gives NaN: outside="ignore" goes on.
    d_t = Q_(np.geomspace(0.5, 60, 241), "K")
    read = {
        1000: [-39.35, -36.27, -32.95, -28.87],
        100: [-61.30, -58.87, -56.24, -53.08],
    }
    for p, values in read.items():
        highest = [
            float(
                np.nanmax(
                    value(
                        "appleman1953_critical_temperature_fixed_mixing",
                        "degC",
                        outside="ignore",
                        f_w=Q_(f_w, "percent"),
                        p=Q_(p, "hPa"),
                        dT=d_t,
                    )
                )
            )
            for f_w in (0, 60, 90, 100)
        ]
        assert highest == pytest.approx(values, abs=0.3)
    assert np.isnan(
        value(
            "appleman1953_critical_temperature_fixed_mixing",
            "degC",
            f_w=Q_(0, "percent"),
            p=Q_(100, "hPa"),
            dT=Q_(5, "K"),
        )
    )


def test_the_example_of_appleman() -> None:
    # p. 19: at 200 mb, 60 % and -60 degC, a trail forms where the
    # environment/exhaust ratio is 150:1, Delta T = 10 000 / (12 N 0.24).
    found = value(
        "appleman1953_critical_temperature_fixed_mixing",
        "degC",
        outside="ignore",
        f_w=Q_(60, "percent"),
        p=Q_(200, "hPa"),
        dT=Q_(10000 / (12 * 150 * 0.24), "K"),
    )
    assert found == pytest.approx(-60.0, abs=0.1)


def test_critical_and_threshold_temperatures_are_trade_terms() -> None:
    # Appleman's critical temperature, then the threshold temperature;
    # the threshold temperature of Schumann, T_LC, and of Gierens, T_LM.
    terms = CATALOG.trade_terms
    assert [m.kind for m in terms["critical_temperature"].meanings] == [
        "ContrailCriticalTemperatureAtFixedMixing",
        "ContrailThresholdTemperature",
    ]
    assert [m.kind for m in terms["threshold_temperature"].meanings] == [
        "ContrailThresholdTemperature",
        "ContrailMaximumThresholdTemperature",
    ]
    found = CATALOG.search("critical temperature").refs
    assert "trade_terms.critical_temperature" in found
    reached = CATALOG.uses("trade_terms.critical_temperature").refs
    assert "kinds.ContrailThresholdTemperature" in reached
