# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the radio refractivity family (ITU-R P.453-14).

Expected values are computed by hand from the equations as printed.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.comparison import feeds
from nomogram.relations import verdict
from nomogram.units import Q_, ScaleType

CATALOG = catalog()
F = CATALOG.formulations


def value(key: str, **inputs: object) -> float:
    return float(F[key].evaluate(**inputs).magnitude)  # type: ignore[arg-type]


def test_refractivity_and_its_terms() -> None:
    p_d, e, t = 1000.0, 10.0, 293.15
    dry = 77.6 * p_d / t
    wet = 72 * e / t + 3.75e5 * e / t**2
    inputs = {"P_d": Q_(p_d, "hPa"), "e": Q_(e, "hPa"), "T": Q_(t, "K")}
    assert value("itu_r_p453_refractivity", **inputs) == pytest.approx(dry + wet)
    assert value(
        "itu_r_p453_refractivity_dry", P_d=inputs["P_d"], T=inputs["T"]
    ) == pytest.approx(dry)
    assert value(
        "itu_r_p453_refractivity_wet", e=inputs["e"], T=inputs["T"]
    ) == pytest.approx(wet)
    assert F["itu_r_p453_refractivity"].output.kind == "RadioRefractivity"
    assert F["itu_r_p453_refractivity_wet"].output.kind == "RadioRefractivityWetTerm"


def test_equation_6_is_equation_2_with_the_total_pressure() -> None:
    relation = CATALOG.relations["itu_r_p453_total_pressure_form"]
    assert verdict(relation, CATALOG).status == "proven"
    p, e, t = 1013.25, 15.0, np.linspace(230.0, 310.0, 9)
    total = F["itu_r_p453_refractivity_total_pressure"].evaluate(
        P=Q_(p, "hPa"), e=Q_(e, "hPa"), T=Q_(t, "K")
    )
    dry_form = F["itu_r_p453_refractivity"].evaluate(
        P_d=Q_(p - e, "hPa"), e=Q_(e, "hPa"), T=Q_(t, "K")
    )
    assert total.magnitude == pytest.approx(dry_form.magnitude)


def test_approximate_form_keeps_its_stated_accuracy_at_saturation() -> None:
    # Within 0.02 % of equation 2 from -50 to +40 degC (P.453 section 1),
    # checked with the vapour pressure at saturation over water.
    t = np.linspace(223.15, 313.15, 91)
    e = F["buck1996"].evaluate(t=Q_(t - 273.15, "degC"))
    p = Q_(1013.25, "hPa")
    approximate = F["itu_r_p453_refractivity_approximate"].evaluate(
        P=p, e=e, T=Q_(t, "K")
    )
    exact = F["itu_r_p453_refractivity_total_pressure"].evaluate(P=p, e=e, T=Q_(t, "K"))
    deviation = np.abs(approximate.magnitude / exact.magnitude - 1)
    assert deviation.max() < 2e-4
    outside = F["itu_r_p453_refractivity_approximate"].evaluate(
        P=p, e=Q_(1.0, "hPa"), T=Q_([220.0, 320.0], "K")
    )
    assert np.isnan(outside.magnitude).all()


def test_refractive_index_and_reference_profile() -> None:
    assert value("itu_r_p453_refractive_index", N=Q_(315.0, "ppm")) == pytest.approx(
        1.000315, abs=1e-12
    )
    profile = F["itu_r_p453_reference_profile"]
    at = profile.evaluate(z=Q_([0.0, 7350.0], "m"))
    assert at.magnitude == pytest.approx([1 + 315e-6, 1 + 315e-6 / math.e], abs=1e-12)
    assert value(
        "itu_r_p453_surface_refractivity", z_s=Q_(7.35, "km")
    ) == pytest.approx(315 / math.e)
    assert profile.coefficient_units["h_0"].origin == "stated"


def test_modified_refractivity() -> None:
    m = value("itu_r_p453_modified_refractivity", N=Q_(300.0, "ppm"), h=Q_(500.0, "m"))
    assert m == pytest.approx(300 + 157 * 0.5)
    kind = CATALOG.kinds["ModifiedRadioRefractivity"]
    assert kind.scale_type is ScaleType.INTERVAL
    assert not kind.delta
    assert CATALOG.kinds["RadioRefractivity"].scale_type is ScaleType.RATIO


def test_altitudes_and_heights_are_distinct() -> None:
    assert not feeds("Height", "Altitude")
    assert not feeds("Altitude", "Height")
    assert feeds("SurfaceAltitude", "Altitude")
    assert CATALOG.kinds["Altitude"].scale_type is ScaleType.INTERVAL
    assert CATALOG.kinds["Height"].scale_type is ScaleType.RATIO
    h = value("height_above_surface", z=Q_(1500.0, "m"), z_s=Q_(0.3, "km"))
    assert h == pytest.approx(1.2)


def test_a_modified_refractivity_from_altitudes(tmp_path: Path) -> None:
    # M = N + 157 (z - z_s): the height above the surface composed into (17).
    document = tmp_path / "personal.toml"
    document.write_text(
        """
[catalog]
name = "personal"
format = 2
requires = ["radio"]

[formulations."personal:m_from_altitude"]
label = "Modified refractivity from altitudes"
composition = { outer = "itu_r_p453_modified_refractivity", inner = { h = "height_above_surface" } }
""",
        encoding="utf-8",
    )
    composed = catalog(extra=[document]).formulations["personal:m_from_altitude"]
    assert [v.kind for v in composed.inputs] == [
        "RadioRefractivity",
        "Altitude",
        "SurfaceAltitude",
    ]
    m = composed.evaluate(N=Q_(300.0, "ppm"), z=Q_(1.0, "km"), z_s=Q_(0.2, "km"))
    assert m.magnitude == pytest.approx(300 + 157 * 0.8)


def test_vapour_pressure_from_relative_humidity_in_moist_air() -> None:
    e = value("itu_r_p453_vapour_pressure", H=Q_(50.0, "percent"), e_s=Q_(20.0, "hPa"))
    assert e == pytest.approx(10.0)
    target = "SaturationVapourPressureInMoistAir"
    assert feeds("SaturationVapourPressureOverWaterInMoistAir", target)
    assert feeds("SaturationVapourPressureOverIceInMoistAir", target)
    assert not feeds("SaturationVapourPressureOverWater", target)


def test_vapour_pressure_from_density() -> None:
    e = value(
        "itu_r_p453_vapour_pressure_from_density",
        rho=Q_(10.0, "g/m**3"),
        T=Q_(300.0, "K"),
    )
    assert e == pytest.approx(10.0 * 300.0 / 216.7)
    # Observation: 216.7 is close to 100 / R_v with R_v in J/(g K).
    ideal = 10.0e-3 * 461.51805 * 300.0 / 100.0
    assert e == pytest.approx(ideal, rel=1e-3)
