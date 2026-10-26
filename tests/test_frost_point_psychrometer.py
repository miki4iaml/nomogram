# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the end of WMO-No. 8, Annex 4.B: frost point, relative
humidity with respect to ice from it, and the Assmann psychrometer."""

import math

import pytest

from nomogram.catalog import catalog
from nomogram.comparison import feeds
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
P = Q_(1000, "hPa")


def enhancement(hectopascal: float) -> float:
    """WMO-No. 8, 4.B.5."""
    return 1.0016 + 3.15e-6 * hectopascal - 0.074 / hectopascal


def magnus(celsius: float, a: float, b: float) -> float:
    """WMO-No. 8, 4.B.1 (water) or 4.B.3 (ice), in hPa."""
    return 6.112 * math.exp(a * celsius / (b + celsius))


@pytest.mark.parametrize("celsius", [-60.0, -40.0, -20.0, -1.0])
def test_the_frost_point_inverts_the_saturation_pressure_over_ice(
    celsius: float,
) -> None:
    e = F["wmo_es_ice_moist_air"].evaluate(p=P, t=Q_(celsius, "degC"))
    found = F["wmo_frost_point_moist_air"].evaluate(e=e, p=P)
    assert found.to("degC").magnitude == pytest.approx(celsius)


def test_relative_humidity_over_ice_from_the_frost_point() -> None:
    f = F["relative_humidity_ice_from_frost_point"]
    assert f.derived
    assert not f.citations
    t = Q_(-20, "degC")
    assert f.evaluate(t_f=t, t=t, p=P).magnitude == pytest.approx(100)
    found = f.evaluate(t_f=Q_(-25, "degC"), t=t, p=P).magnitude
    expected = 100 * magnus(-25, 22.46, 272.62) / magnus(-20, 22.46, 272.62)
    assert found == pytest.approx(expected)
    # The enhancement factor cancels: the value does not depend on p.
    aloft = f.evaluate(t_f=Q_(-25, "degC"), t=t, p=Q_(500, "hPa")).magnitude
    assert aloft == pytest.approx(found)


def test_the_assmann_psychrometer_with_a_wet_bulb() -> None:
    f = F["wmo_psychrometer_water"]
    p = Q_(1013.25, "hPa")
    same = f.evaluate(t=Q_(20, "degC"), t_w=Q_(20, "degC"), p=p)
    saturated = F["wmo_es_water_moist_air"].evaluate(t=Q_(20, "degC"), p=p)
    assert same.magnitude == pytest.approx(saturated.magnitude)
    found = f.evaluate(t=Q_(20, "degC"), t_w=Q_(15, "degC"), p=p).magnitude
    expected = enhancement(1013.25) * magnus(15, 17.62, 243.12) - 6.53e-4 * (
        1 + 0.000944 * 15
    ) * 1013.25 * (20 - 15)
    assert found == pytest.approx(expected)
    assert f.conditions is not None
    assert f.conditions.startswith("An Assmann aspirated psychrometer")


def test_the_assmann_psychrometer_with_an_ice_bulb() -> None:
    found = F["wmo_psychrometer_ice"].evaluate(
        t=Q_(-5, "degC"), t_i=Q_(-8, "degC"), p=P
    )
    expected = enhancement(1000) * magnus(-8, 22.46, 272.62) - 5.75e-4 * 1000 * 3
    assert found.magnitude == pytest.approx(expected)


def test_a_frost_point_is_a_temperature_but_not_a_dew_point() -> None:
    assert feeds("FrostPointTemperature", "Temperature")
    assert not feeds("FrostPointTemperature", "DewPointTemperature")
    assert not feeds("IceBulbTemperature", "WetBulbTemperature")
    assert CATALOG.kinds["WetBulbTemperature"].cf_standard_names == (
        "wet_bulb_temperature",
    )


@pytest.mark.parametrize(
    ("kind", "applies"),
    [
        ("FrostPointTemperature", True),
        ("IceBulbTemperature", True),
        ("WetBulbTemperature", True),
        ("VirtualTemperature", True),
        ("DewPointTemperature", True),
        ("TemperatureDifference", False),
        ("Pressure", False),
    ],
)
def test_a_temperature_scale_applies_to_every_temperature(
    kind: str, applies: bool
) -> None:
    its90 = CATALOG.scales["its90"]
    assert its90.applies_to(kind, CATALOG.kinds) is applies
    assert its90.applies_to("Unknown", CATALOG.kinds) is False
