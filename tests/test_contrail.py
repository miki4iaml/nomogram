# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Contrail formation from aircraft exhaust (family ``contrail``).

The oracles are the values Schumann (1996, 2000, 2012) and Gierens
(2021) print. The exact threshold temperatures, solutions of implicit
equations not in the catalog yet, are computed here by bisection on the
formulations of the catalog: the slope of the Sonntag form of Schumann
(2012), A1, for the maximum threshold temperature (Schumann 1996,
equation 10), and A1 itself for the threshold temperature (equation 11,
on the root below the maximum threshold temperature).
"""

from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from bundled_catalog import with_families

from nomogram.comparison import compose
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
    t_lm = exact_t_lm(g)
    return value(
        "schumann2012_threshold_temperature_fit",
        "K",
        T_LM=Q_(t_lm, "K"),
        p_LM=Q_(p_liq(t_lm), "Pa"),
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
    # saturation vapour pressure: p_liq(T_LM), the input p_LM of the fit
    # of Schumann (2012).
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
