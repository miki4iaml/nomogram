# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The values a quantity kind admits by its definition, applied by default."""

import math

import numpy as np
import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.comparison import feeds
from nomogram.inversion import dew_point
from nomogram.model import Formulation, ValidityWarning, Variable
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("ThermodynamicTemperature", (0.0, math.inf, "K")),
        ("CelsiusTemperature", (0.0, math.inf, "K")),  # inherited from Temperature
        ("DewPointTemperature", (0.0, math.inf, "K")),
        ("VirtualPotentialTemperature", (0.0, math.inf, "K")),
        ("SaturationVapourPressureOverWater", (0.0, math.inf, "PA")),
        ("SpecificHumidity", (0.0, 1.0, "KiloGM-PER-KiloGM")),  # narrows MassRatio
        ("SaturationSpecificHumidity", (0.0, 1.0, "KiloGM-PER-KiloGM")),
        ("MassRatioOfTotalWaterToDryGas", (0.0, math.inf, "KiloGM-PER-KiloGM")),
        ("SeaWaterSalinity", (0.0, 1.0, "UNITLESS")),
        ("RelativeHumidityWithRespectToIce", (0.0, math.inf, "UNITLESS")),
        ("FrictionVelocity", (0.0, math.inf, "M-PER-SEC")),
        ("EvaporationDuctHeight", (0.0, math.inf, "M")),
        ("GeodeticLatitude", (-90.0, 90.0, "DEG")),
    ],
)
def test_bounds_declared_or_inherited(
    kind: str, expected: tuple[float, float, str]
) -> None:
    bounds = CATALOG.bounds_of(kind)
    assert bounds is not None
    assert (bounds.low, bounds.high, bounds.unit) == expected
    assert bounds.criterion


@pytest.mark.parametrize(
    "kind",
    [
        # Differences, signed quantities, and the general kinds left open.
        "TemperatureDifference",
        "SurfaceLayerProfileScaleOfPotentialTemperature",
        "SurfaceLayerProfileScaleOfMixingRatio",
        "SurfaceLayerScaleOfSpecificHumidity",
        "Velocity",
        "ObukhovLength",
        "GradientFunctionForHeat",
        "Pressure",
        "PlaneAngle",
        "Height",
        "SpecificLatentHeatOfFusion",
        "RadioRefractivity",
    ],
)
def test_kinds_without_bounds(kind: str) -> None:
    assert CATALOG.bounds_of(kind) is None


def variable(kind: str, unit: str, **extra: object) -> Variable:
    return Variable("x", kind, unit, "x", kind_bounds=CATALOG.bounds_of(kind), **extra)  # type: ignore[arg-type]


def test_bounds_follow_the_unit_of_each_variable() -> None:
    assert variable("CelsiusTemperature", "DEG_C").bounds_in_unit() == pytest.approx(
        (-273.15, math.inf)
    )
    assert variable("CelsiusTemperature", "DEG_F").bounds_in_unit() == pytest.approx(
        (-459.67, math.inf)
    )
    assert variable("SeaWaterSalinity", "GM-PER-KiloGM").bounds_in_unit() == (
        pytest.approx((0.0, 1000.0))
    )
    assert variable("GeodeticLatitude", "RAD").bounds_in_unit() == pytest.approx(
        (-math.pi / 2, math.pi / 2)
    )


def test_a_value_on_another_scale_keeps_the_bounds_of_its_scale() -> None:
    # A Practical Salinity of 35 is no mass fraction.
    practical = variable("SeaWaterSalinity", "UNITLESS", scale=CATALOG.scales["pss78"])
    assert practical.bounds_in_unit() is None


def test_a_value_beyond_the_bounds_of_its_kind_is_nan_whatever_the_domains() -> None:
    tetens = F["tetens1930"]
    t = Q_(np.array([-300.0, 20.0]), "degC")
    for basis in ("stated", "physical", "all"):
        result = tetens.evaluate(t=t, basis=basis).magnitude
        assert np.isnan(result).tolist() == [True, False]
    assert not math.isnan(tetens.evaluate(t=t, outside="ignore").magnitude[0])
    with pytest.warns(ValidityWarning, match="beyond the bounds of the kinds"):
        tetens.evaluate(t=t, outside="warn")


def test_an_output_beyond_the_bounds_of_its_kind_is_nan() -> None:
    # e > p gives a negative mixing ratio, which no air has.
    r = F["mixing_ratio_from_vapour_pressure"].evaluate(
        e=Q_(np.array([10.0, 1100.0]), "hPa"), p=Q_(1000.0, "hPa")
    )
    assert np.isnan(r.magnitude).tolist() == [False, True]


def test_a_scale_of_the_surface_layer_stays_signed() -> None:
    kind = CATALOG.kinds["SurfaceLayerProfileScaleOfMixingRatio"]
    assert kind.specialization_of == "DimensionlessRatio"
    assert kind.added_units == ("GM-PER-KiloGM", "KiloGM-PER-KiloGM")
    assert not feeds("SurfaceLayerProfileScaleOfMixingRatio", "MassRatio")
    length = F["fairall1978_obukhov_length"].evaluate(
        T=Q_(290.0, "K"),
        u_s=Q_(0.3, "m/s"),
        T_s=Q_(-0.1, "K"),  # a difference: no bound of temperature
        q_s=Q_(-0.2, "g/kg"),
        g=Q_(9.8, "m/s^2"),
    )
    assert length.magnitude < 0  # unstable


def test_an_inverse_takes_the_bounds_of_the_kinds_of_its_variables() -> None:
    inverse = dew_point(F["sonntag1990_magnus"])
    assert isinstance(inverse, Formulation)
    assert inverse.inputs[0].kind_bounds == CATALOG.bounds_of("VapourPressure")
    result = inverse.evaluate(e=Q_(np.array([-1.0, 10.0]), "hPa"), outside="nan")
    assert np.isnan(result.magnitude).tolist() == [True, False]


SOURCE = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"
"""

KIND = """
[kinds.Part]
label = "Part"
specialization_of = "{parent}"
{extra}
"""


@pytest.mark.parametrize(
    ("parent", "extra", "message"),
    [
        (
            "MassFraction",
            'bounds = { low = 0, high = 2, unit = "UNITLESS", criterion = "c" }',
            r"kinds\.Part\.bounds: \[0, 2\] UNITLESS widens those it inherits",
        ),
        (
            "MassFraction",
            'bounds = { low = 0, high = 1, unit = "PA", criterion = "c" }',
            "PA does not apply to Part",
        ),
        (
            "MassFraction",
            'bounds = { low = 0, high = 1, unit = "UNITLESS" }',
            "missing keys: criterion",
        ),
        (
            "MassFraction",
            'bounds = { low = -inf, high = inf, unit = "UNITLESS", criterion = "c" }',
            "one of them finite",
        ),
        ("DimensionlessRatio", 'units = ["PA"]', "PA is not of the dimension"),
    ],
)
def test_invalid_kinds_are_refused(parent: str, extra: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([SOURCE + KIND.format(parent=parent, extra=extra)])


def test_a_kind_of_the_catalog_bounds_its_variables() -> None:
    document = KIND.format(
        parent="DimensionlessRatio",
        extra='bounds = { low = 0, high = 1, unit = "UNITLESS", criterion = "A part." }',
    )
    document += """
[formulations.f]
label = "f"
expression = "a * x"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "Part", unit = "PERCENT", description = "y" }
inputs = [{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }]
coefficients = { a = 100.0 }
"""
    f = load_catalog([SOURCE + document]).formulations["f"]
    assert f.output.bounds_in_unit() == pytest.approx((0.0, 100.0))
    y = f.evaluate(x=Q_(np.array([0.5, 1.5]), "dimensionless")).magnitude
    assert np.isnan(y).tolist() == [False, True]
