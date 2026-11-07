# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Roughness of the sea surface: Charnock's relation and its coefficient,
the roughness Reynolds number, the scalar roughness lengths."""

import math

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
NU = 1.5e-5


def evaluate(key: str, outside: str = "nan", **inputs: object) -> np.ndarray:
    result = F[key].evaluate(outside=outside, **inputs)  # type: ignore[arg-type]
    return np.asarray(result.magnitude)


def speed(*values: float) -> object:
    return Q_(np.array(values), "m/s")


# --- Charnock's relation (Businger 1985, p. 11) ---------------------------------


def test_charnock_with_businger_values_and_the_rough_flow_threshold() -> None:
    u_s, g = Q_(0.29, "m/s"), Q_(9.8, "m/s**2")
    z_0 = float(
        evaluate("charnock1955_roughness_length", alpha=Q_(0.015, ""), u_s=u_s, g=g)
    )
    # u_* = 0.29 m/s gives z_0 = 1.3e-4 m, and Rr = 2.5, rough flow (p. 11).
    assert z_0 == pytest.approx(1.3e-4, rel=0.01)
    r_r = float(
        evaluate(
            "roughness_reynolds_number", z_0M=Q_(z_0, "m"), u_s=u_s, nu=Q_(NU, "m**2/s")
        )
    )
    assert r_r == pytest.approx(2.5, rel=0.01)
    # Ru = u_*^3/(nu g) = 167 there, as printed.
    assert 0.29**3 / (NU * 9.8) == pytest.approx(167, rel=0.01)
    businger = evaluate(
        "businger1985_roughness_length_charnock", u_s=speed(0.2, 0.29), g=g
    )
    assert math.isnan(businger[0])
    assert businger[1] == pytest.approx(z_0, rel=1e-12)


# --- The Charnock coefficient from the wind --------------------------------------


def test_edson_coare_and_fairall_charnock_coefficients() -> None:
    edson = evaluate(
        "edson2013_charnock_coefficient", U_10N=speed(5.0, 10.0, 18.0, 20.0)
    )
    assert math.isnan(edson[0])
    assert math.isnan(edson[3])
    np.testing.assert_allclose(edson[1:3], [0.012, 0.0256], rtol=1e-12)
    coare = evaluate("coare36_charnock_coefficient", U_10N=speed(2.0, 10.0, 18.0, 25.0))
    # Below 2.94 m/s the line is negative, beyond the bounds of the kind.
    assert math.isnan(coare[0])
    np.testing.assert_allclose(coare[1:], [0.012, 0.0256, 0.0273], rtol=1e-12)
    ignored = evaluate(
        "coare36_charnock_coefficient", outside="ignore", U_10N=Q_(2.0, "m/s")
    )
    assert float(ignored) == pytest.approx(-0.0016)
    fairall = evaluate(
        "fairall2003_charnock_coefficient", U_10N=speed(5.0, 10.0, 14.0, 18.0, 20.0)
    )
    np.testing.assert_allclose(
        fairall, [0.011, 0.011, 0.0145, 0.018, 0.018], rtol=1e-12
    )


def test_edson_roughness_length_is_that_of_the_ifs_with_its_values() -> None:
    nu = CATALOG.constants["nu_ecmwf_ifs"].value
    g_n = CATALOG.constants["g_n_cgpm1901"].value
    u_s = speed(0.05, 0.3, 1.0)
    edson = evaluate(
        "edson2013_roughness_length_momentum",
        alpha=Q_(0.018, ""),
        u_s=u_s,
        nu=Q_(nu, "m**2/s"),
        g=Q_(g_n, "m/s**2"),
    )
    np.testing.assert_allclose(
        edson, evaluate("ecmwf_ifs_roughness_length_momentum_sea", u_s=u_s), rtol=1e-12
    )


# --- Scalar roughness lengths ------------------------------------------------------


def test_the_scalar_roughness_lengths_of_coare() -> None:
    r_r = Q_(np.array([0.1, 1.0, 100.0]), "")
    fairall = evaluate("fairall2003_roughness_length_humidity", R_r=r_r)
    np.testing.assert_allclose(
        fairall, [1.1e-4, 5.5e-5, 5.5e-5 * 100**-0.6], rtol=1e-12
    )
    np.testing.assert_allclose(
        evaluate("fairall2003_roughness_length_heat", R_r=r_r), fairall
    )
    code = evaluate("coare36_roughness_length_humidity", R_r=r_r)
    # The code departs from equation 28: +45 % on the plateau, -39 % at 100.
    departure = 100 * (code / fairall - 1)
    np.testing.assert_allclose(departure[[0, 2]], [45.45, -39.32], atol=0.01)
    # The two pieces meet where the minimum switches.
    for key in (
        "fairall2003_roughness_length_humidity",
        "coare36_roughness_length_humidity",
    ):
        f = F[key]
        values = {c.identifier: c.value for c in f.coefficients}
        x = values["R_x"]
        assert values["B"] * x ** -values["p"] == pytest.approx(values["A"], rel=1e-12)


def test_the_scalar_roughness_lengths_of_beljaars_and_of_the_ifs() -> None:
    u_s, nu = Q_(0.3, "m/s"), Q_(NU, "m**2/s")
    heat = float(evaluate("beljaars1992_roughness_length_heat", u_s=u_s, nu=nu))
    humidity = float(evaluate("beljaars1992_roughness_length_humidity", u_s=u_s, nu=nu))
    assert heat == pytest.approx(1.4e-5 + 0.40 * NU / 0.3)
    assert humidity == pytest.approx(1.3e-4 + 0.62 * NU / 0.3)
    nu_ifs = CATALOG.constants["nu_ecmwf_ifs"].value
    z_0m = Q_(2e-4, "m")
    simplified = float(
        evaluate("ecmwf_ifs_roughness_length_heat_sea_simplified", u_s=u_s, z_0M=z_0m)
    )
    assert simplified == pytest.approx(math.sqrt(0.40 * nu_ifs / 0.3 * 2e-4), rel=1e-12)


# --- Search ---------------------------------------------------------------------------


def test_the_charnock_coefficient_and_its_names_are_found() -> None:
    coefficients = {f.key for f in CATALOG.formulations_of("CharnockCoefficient")}
    assert coefficients == {
        "edson2013_charnock_coefficient",
        "coare36_charnock_coefficient",
        "fairall2003_charnock_coefficient",
    }
    term = CATALOG.search("Charnock parameter", section="trade_terms")
    assert [e.ref for e in term.entries] == ["trade_terms.charnock_parameter"]
    meaning = CATALOG.trade_terms["charnock_parameter"].meanings[0]
    assert meaning.kind == "CharnockCoefficient"
    charnock = {f.key for f in CATALOG.search(keyword="Charnock").formulations}
    assert {
        "charnock1955_roughness_length",
        "edson2013_roughness_length_momentum",
    } <= charnock
    assert CATALOG.references["charnock1955"].status.value == "to-confirm"


# --- The sea state in the IFS: equations 3.30 to 3.34, and the wave model ---------


def test_the_sea_state_roughness_of_the_ifs_and_its_limits() -> None:
    nu = CATALOG.constants["nu_ecmwf_ifs"].value
    g_n = CATALOG.constants["g_n_cgpm1901"].value
    key = "ecmwf_ifs_roughness_length_heat_sea_state"
    # z_m = 0 when the Charnock length equals the background: z_0H = z_nu.
    u_s = 0.3
    z_b = Q_(0.018 * u_s**2 / g_n, "m")
    smooth = evaluate(key, u_s=Q_(u_s, "m/s"), alpha_Ch=Q_(0.018, ""), z_b=z_b)
    assert float(smooth) == pytest.approx(0.40 * nu / u_s, rel=1e-12)
    # Without background roughness, close to z_nu at low wind, far below it
    # at high wind; the approximation 3.34 departs from it there.
    low = evaluate(key, u_s=Q_(0.05, "m/s"), alpha_Ch=Q_(0.018, ""), z_b=Q_(0.0, "m"))
    high = evaluate(key, u_s=Q_(0.5, "m/s"), alpha_Ch=Q_(0.018, ""), z_b=Q_(0.0, "m"))
    assert float(low) / (0.40 * nu / 0.05) == pytest.approx(1.0092, abs=1e-4)
    z_0m = evaluate("ecmwf_ifs_roughness_length_momentum_sea", u_s=Q_(0.5, "m/s"))
    approximation = evaluate(
        "ecmwf_ifs_roughness_length_heat_sea_simplified",
        u_s=Q_(0.5, "m/s"),
        z_0M=Q_(float(z_0m), "m"),
    )
    assert float(approximation) / float(high) == pytest.approx(1.82, abs=0.01)
    humidity = evaluate(
        "ecmwf_ifs_roughness_length_humidity_sea_state",
        u_s=Q_(u_s, "m/s"),
        alpha_Ch=Q_(0.018, ""),
        z_b=z_b,
    )
    assert float(humidity) == pytest.approx(0.62 * nu / u_s, rel=1e-12)


def test_the_background_roughness_of_the_wave_model() -> None:
    g_n = CATALOG.constants["g_n_cgpm1901"].value
    alpha = evaluate(
        "ecmwf_wam_background_charnock_coefficient", U_10=speed(10.0, 33.0, 50.0)
    )
    np.testing.assert_allclose(alpha, [0.006, 0.00305, 0.0001], rtol=1e-6)
    z_b = evaluate(
        "ecmwf_wam_background_roughness_length",
        alpha_hat=Q_(0.006, ""),
        u_s=Q_(0.5, "m/s"),
    )
    assert float(z_b) == pytest.approx(0.006 * 0.25 / g_n, rel=1e-12)
