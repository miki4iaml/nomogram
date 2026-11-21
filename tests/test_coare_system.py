# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The loop of COARE 3.6, a system of the catalog, against the code's outputs.

The test data of the guide (one row in 20 of the COARE 3.6 test data, see
``docs/examples/data/NOTICE.md``) with the inputs the code computes
itself: the specific humidity of the air by its ``qsat26air`` (Buck's
saturation vapour pressure with his enhancement factor, at the pressure
of the thermometer, lines 304 to 309 and 798 to 830 of
``coare36vn_zrf_et.py``) and the gravity by its ``grv`` (lines 834 to
844), written here as the code writes them.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.systems import CONVERGED, ITERATED
from nomogram.units import Q_

DATA = Path(__file__).parents[1] / "docs" / "examples" / "data" / "coare36_test.csv"
CATALOG = catalog()
SYSTEM = CATALOG.systems["coare36_surface_layer"]


def measurements() -> dict[str, np.ndarray]:
    lines = DATA.read_text(encoding="utf-8").splitlines()
    rows = [line.split(",") for line in lines if not line.startswith("#")]
    table = np.array(rows[1:], dtype=float)
    return {name: table[:, i] for i, name in enumerate(rows[0])}


M = measurements()


def code_inputs(m: dict[str, np.ndarray]) -> dict[str, Any]:
    """The inputs of the system, as the code of COARE 3.6 computes them."""
    t, rh, zt = m["ta"], m["rh"], m["zt"]
    p_tq = m["P"] - 0.125 * zt
    e_s = 6.1121 * np.exp(17.502 * t / (t + 240.97)) * (1.0007 + 3.46e-6 * p_tq)
    e = 0.01 * rh * e_s
    q = 622 * e / (p_tq - 0.378 * e) / 1000
    x = np.sin(np.radians(m["lat"]))
    g = 9.7803267715 * (
        1 + 0.0052790414 * x**2 + 2.32718e-05 * x**4 + 1.262e-07 * x**6 + 7e-10 * x**8
    )
    viscosity = CATALOG.formulations["coare36_kinematic_viscosity_of_air"]
    return {
        "T": Q_(t + 273.16, "K"),
        "T_surf": Q_(m["T_skin"] + 273.16, "K"),
        "q": Q_(q, "kg/kg"),
        "q_surf": Q_(m["Qs"] / 1000, "kg/kg"),
        "U": Q_(m["u"], "m/s"),
        "z_u": Q_(m["zu"], "m"),
        "z_t": Q_(zt, "m"),
        "z_q": Q_(m["zq"], "m"),
        "z_i": Q_(m["zi"], "m"),
        "nu": viscosity.evaluate(t=Q_(t, "degC")).to("m**2/s"),
        "g": Q_(g, "m/s**2"),
    }


def test_the_loop_of_coare_is_a_system_of_the_catalog() -> None:
    assert SYSTEM.unknowns == ("u_s", "T_s", "q_s", "alpha", "S")
    assert set(SYSTEM.inputs) == {
        "T", "T_surf", "q", "q_surf", "U", "z_u", "z_t", "z_q", "z_i", "nu", "g"
    }  # fmt: skip
    assert SYSTEM.reference == "coare36"
    assert SYSTEM.iterations == 10
    assert SYSTEM in CATALOG.systems_of("FrictionVelocity")
    assert CATALOG.systems_of("Pressure") == ()
    assert (
        "systems.coare36_surface_layer" in CATALOG.used_by("kinds.ObukhovLength").refs
    )
    uses = CATALOG.uses("systems.coare36_surface_layer").refs
    assert "formulations.coare36_wind_speed_with_gust" in uses
    assert "references.coare36" in uses
    found = CATALOG.search("COARE", section="systems").refs
    assert found == ("systems.coare36_surface_layer",)
    assert "systems.coare36_surface_layer" in CATALOG.search(kind="ObukhovLength").refs


def test_the_system_gives_back_the_outputs_of_the_code() -> None:
    solution = SYSTEM.evaluate(**code_inputs(M))
    assert (solution.status == CONVERGED).all()
    assert solution.iterations.max() <= 6
    for name, column, unit, rtol in (
        ("u_s", "usr", "m/s", 1e-6),
        ("q_s", "qsr", "kg/kg", 3e-6),
        ("L", "L", "m", 1e-5),
        ("z_0M", "zo", "m", 3e-6),
        ("u_g", "gust", "m/s", 5e-6),
        # The scale nearest 0 (-0.0145 K at most) follows the skin
        # temperature, given to seven digits.
        ("T_s", "tsr", "K", 1e-4),
    ):
        assert solution[name].to(unit).magnitude == pytest.approx(M[column], rel=rtol)


def test_air_and_surface_alike() -> None:
    # The first guess of the humidity scale is 0, that of the temperature
    # scale too where the lapse g z_t / c_pa is in the air temperature: an
    # infinite Obukhov length, where Newton's method starts from a few
    # passes of the loop and converges where the loop does.
    given = code_inputs({k: v[5:6] for k, v in M.items()})
    given["q"] = given["q_surf"]
    lapse = (given["g"] * given["z_t"]).to("m**2/s**2").magnitude / 1004.67
    for warmer in (0.0, lapse):
        given["T"] = given["T_surf"] - Q_(warmer, "K")
        newton = SYSTEM.evaluate(**given)
        passes = SYSTEM.evaluate(method="fixed-point", **given)
        assert (newton.status == CONVERGED).all()
        assert (passes.status == ITERATED).all()
        assert newton["u_s"].magnitude == pytest.approx(
            passes["u_s"].magnitude, rel=1e-6
        )


def test_the_passes_of_the_code_are_a_loop_over_its_formulations() -> None:
    # Ten passes in the order of the code, from the first guess of the
    # system, as a loop over the formulations writes them.
    rows = slice(0, 109, 11)
    m = {k: v[rows] for k, v in M.items()}
    given = code_inputs(m)
    f = CATALOG.formulations
    u = given["U"]
    one = "dimensionless"
    known: dict[str, Any] = {
        "u_s": 0.035 * u,
        "q_s": 0.033 * (given["q"] - given["q_surf"]),
        "T_s": Q_(
            0.033
            * (
                given["T"].magnitude
                + given["g"].magnitude * given["z_t"].magnitude / 1004.67
                - given["T_surf"].magnitude
            ),
            "K",
        ),
        "alpha": Q_(np.full(u.shape, 0.011), one),
        "S": Q_(np.sqrt(u.magnitude**2 + 0.25), "m/s"),
    }
    values = {**given, **known}

    def step(key: str, output: str) -> None:
        formulation = f[key]
        arguments = {v.identifier: values[v.identifier] for v in formulation.inputs}
        values[output] = formulation.evaluate(outside="ignore", **arguments)

    for _ in range(10):
        for key, output in (
            ("coare36_obukhov_length", "L"),
            ("edson2013_roughness_length_momentum", "z_0M"),
            ("roughness_reynolds_number", "R_r"),
            ("coare36_roughness_length_humidity", "z_0Q"),
            ("coare36_roughness_length_heat", "z_0T"),
            ("coare36_friction_velocity", "u_s"),
            ("coare36_humidity_scale", "q_s"),
            ("coare36_temperature_scale", "T_s"),
            ("coare36_virtual_temperature_flux", "Q_0v"),
            ("coare36_convective_gust", "u_g"),
            ("coare36_wind_speed_with_gust", "S"),
            ("coare36_equivalent_neutral_wind_10m", "U_10N"),
            ("coare36_charnock_coefficient", "alpha"),
        ):
            step(key, output)
    passes = SYSTEM.evaluate(method="fixed-point", **given)
    assert (passes.status == ITERATED).all()
    for name in SYSTEM.outputs:
        expected = values[name].to(passes[name].units).magnitude
        assert passes[name].magnitude == pytest.approx(expected, rel=1e-12), name
    # Newton's method solves the equations the passes approach: within 2e-7.
    newton = SYSTEM.evaluate(**given)
    for name in SYSTEM.outputs:
        assert newton[name].magnitude == pytest.approx(passes[name].magnitude, rel=2e-7)
