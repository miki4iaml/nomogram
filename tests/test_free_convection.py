# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Free convection in the surface layer: the virtual temperature flux, the
free convection velocity scale and the wind of the IFS (equations 3.10,
3.19, 3.20), and the gustiness and the viscosity of air of the code of
COARE 3.6, against its test data."""

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
ONE = "dimensionless"
DATA = Path(__file__).parents[1] / "docs" / "examples" / "data" / "coare36_test.csv"


def coare_test_data() -> dict[str, np.ndarray]:
    lines = DATA.read_text(encoding="utf-8").splitlines()
    rows = [line.split(",") for line in lines if not line.startswith("#")]
    table = np.array(rows[1:], dtype=float)
    return {name: table[:, i] for i, name in enumerate(rows[0])}


def test_the_gust_of_coare_from_its_own_scales() -> None:
    # The scales COARE gives, through the virtual temperature flux and the
    # gust of its code, give back the gust it gives, to 1e-5.
    m = coare_test_data()
    t_a = Q_(m["ta"] + 273.16, "K")
    e_s = F["buck1981"].evaluate(t=Q_(m["ta"], "degC"))
    p_t = Q_(m["P"] - 0.125 * m["zt"], "hPa")  # as the code takes it
    q = F["ecmwf_ifs_specific_humidity_from_vapour_pressure"].evaluate(
        e=m["rh"] / 100 * e_s, p=p_t
    )
    flux = F["coare36_virtual_temperature_flux"].evaluate(
        u_s=Q_(m["usr"], "m/s"),
        T_s=Q_(m["tsr"], "K"),
        q_s=Q_(m["qsr"], "kg/kg"),
        q=q,
        T=t_a,
    )
    assert np.all(flux.magnitude > 0)  # a sea warmer than the air
    gravity = F["wmo_normal_gravity_wgs84"].evaluate(phi=Q_(m["lat"], "deg"))
    gust = F["coare36_convective_gust"].evaluate(
        T=t_a, Q_0v=flux, z_i=Q_(m["zi"], "m"), g=gravity
    )
    np.testing.assert_allclose(gust.to("m/s").magnitude, m["gust"], rtol=1e-5)


def test_the_gust_of_coare_without_upward_buoyancy() -> None:
    gust = F["coare36_convective_gust"].evaluate(
        T=Q_(290.0, "K"),
        Q_0v=Q_(np.array([-0.01, 0.0]), "K*m/s"),
        z_i=Q_(600.0, "m"),
        g=Q_(9.8, "m/s**2"),
    )
    np.testing.assert_array_equal(gust.to("m/s").magnitude, [0.2, 0.2])


def test_the_viscosity_of_air_of_coare_and_of_iso_2533() -> None:
    # At the sea level of the standard atmosphere, 15 degC and 101325 Pa,
    # the polynomial of COARE departs from ISO 2533 by -0.15 %.
    coare = F["coare36_kinematic_viscosity_of_air"].evaluate(t=Q_(15.0, "degC"))
    iso = F["iso2533_kinematic_viscosity_of_air"].evaluate(
        T=Q_(288.15, "K"), p=Q_(101325.0, "Pa")
    )
    assert round(100 * float(coare / iso - 1), 2) == -0.15


def test_the_virtual_temperature_flux_of_the_obukhov_length_of_the_ifs() -> None:
    # Equation 3.10: L = -u_*^3 T_n / (kappa g Q_0v), with the flux of its own
    # formulation, positive upward when the surface heats the air.
    scales: dict[str, Any] = {
        "u_s": Q_(np.array([0.3, 0.2]), "m/s"),
        "s_s": Q_(np.array([-20.0, 15.0]), "J/kg"),
        "q_s": Q_(np.array([-1e-4, 2e-5]), "kg/kg"),
        "T_n": Q_(290.0, "K"),
    }
    flux = F["ecmwf_ifs_virtual_temperature_flux"].evaluate(**scales)
    length = F["ecmwf_ifs_obukhov_length"].evaluate(**scales)
    kappa, g = 0.4, 9.80665
    expected = -(scales["u_s"].magnitude ** 3) * 290.0 / (kappa * g * flux.magnitude)
    np.testing.assert_allclose(length.to("m").magnitude, expected, rtol=1e-12)


def test_the_free_convection_velocity_and_wind_of_the_ifs() -> None:
    w = F["ecmwf_ifs_free_convection_velocity_scale"]
    heated = w.evaluate(T_n=Q_(300.0, "K"), Q_0v=Q_(0.01, "K*m/s"))
    assert heated.to("m/s").magnitude == pytest.approx(
        (1000.0 * 9.80665 / 300.0 * 0.01) ** (1 / 3), rel=1e-12
    )
    # Defined where the surface is heated: NaN by default otherwise.
    cooled = w.evaluate(T_n=Q_(300.0, "K"), Q_0v=Q_(-0.01, "K*m/s"))
    assert math.isnan(cooled.magnitude)
    wind = F["ecmwf_ifs_wind_speed_free_convection"].evaluate(
        u_n=Q_(3.0, "m/s"), v_n=Q_(-4.0, "m/s"), w_s=Q_(0.0, "m/s")
    )
    assert wind.to("m/s").magnitude == pytest.approx(5.0, rel=1e-15)


def test_the_free_convection_entries_are_found() -> None:
    gusts = {f.key for f in CATALOG.formulations_of("ConvectiveVelocityScale")}
    assert gusts == {
        "ecmwf_ifs_free_convection_velocity_scale",
        "coare36_convective_gust",
    }
    fluxes = {f.key for f in CATALOG.formulations_of("KinematicHeatFlux")}
    assert fluxes == {
        "ecmwf_ifs_virtual_temperature_flux",
        "coare36_virtual_temperature_flux",
    }
    assert "kinds.ConvectiveVelocityScale" in CATALOG.search("convective").refs
