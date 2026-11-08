# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The values a quantity kind admits by its definition, applied by default."""

import math

import numpy as np
import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.comparison import feeds
from nomogram.inversion import dew_point, invert
from nomogram.model import Formulation, ValidityWarning, Variable
from nomogram.semantics import KindBounds
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


COMPOSED = """
[formulations.g]
label = "g"
expression = "b * x"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }
inputs = [{ identifier = "x", kind = "Pressure", unit = "HectoPA", description = "x" }]
coefficients = { b = 2.0 }

[formulations.f]
label = "f"
expression = "a * e"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "Pressure", unit = "HectoPA", description = "y" }
inputs = [{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }]
coefficients = { a = 3.0 }

[formulations.c]
label = "c"
composition = { outer = "f", inner = { e = "g" } }

[[formulations.c.citations]]
reference = "src"

[[formulations.c.citations.domains]]
bounds = { x = [-100, 100] }
criterion = "Where the source of the composition vouches for it."
"""


@pytest.mark.parametrize("basis", ["stated", "physical", "all"])
def test_an_intermediate_value_keeps_the_bounds_of_its_kind(basis: str) -> None:
    # The domain stated for the composition replaces those of its parts,
    # not the bounds of their kinds: a negative vapour pressure stays NaN.
    c = load_catalog([SOURCE + COMPOSED]).formulations["c"]
    y = c.evaluate(x=Q_(np.array([-1.0, 1.0]), "hPa"), basis=basis).magnitude  # type: ignore[arg-type]
    assert np.isnan(y).tolist() == [True, False]
    with pytest.warns(ValidityWarning, match="beyond the bounds of the kinds"):
        c.evaluate(x=Q_(-1.0, "hPa"), outside="warn")


INVERTED = """
[formulations.h]
label = "h"
expression = "c * u"
fixed_units = true
output = { identifier = "p", kind = "Pressure", unit = "HectoPA", description = "p" }
inputs = [{ identifier = "u", kind = "DimensionlessRatio", unit = "UNITLESS", description = "u" }]
coefficients = { c = 10.0 }

[[formulations.h.citations]]
reference = "src"

[[formulations.h.citations.domains]]
bounds = { u = [-1, 1] }
criterion = "Where the source vouches for it."
"""


@pytest.mark.parametrize("method", ["symbolic", "numerical"])
def test_an_inverse_applies_the_bounds_of_its_own_kinds(method: str) -> None:
    # Narrower than the source's: a relative humidity, never negative.
    h = load_catalog([SOURCE + INVERTED]).formulations["h"]
    inverse = invert(
        h,
        "u",
        output=Variable("RH", "RelativeHumidity", "UNITLESS", "RH"),
        input=Variable("p", "VapourPressure", "HectoPA", "p"),
        method=method,  # type: ignore[arg-type]
    )
    result = inverse.evaluate(p=Q_(np.array([-5.0, 5.0]), "hPa")).magnitude
    assert np.isnan(result[0])
    assert result[1] == pytest.approx(0.5)


def test_an_inverse_keeps_the_bounds_its_caller_gives() -> None:
    h = load_catalog([SOURCE + INVERTED]).formulations["h"]
    narrow = KindBounds(0.0, 0.4, "UNITLESS", "Given by the caller.")
    output = Variable("RH", "RelativeHumidity", "UNITLESS", "RH", kind_bounds=narrow)
    inverse = invert(
        h, "u", output=output, input=Variable("p", "VapourPressure", "HectoPA", "p")
    )
    assert inverse.output.kind_bounds == narrow
    assert np.isnan(inverse.evaluate(p=Q_(5.0, "hPa")).magnitude)


def test_a_value_on_another_scale_is_bounded_on_the_reference_one() -> None:
    # Knudsen salinity, in per mille: carried to the reference scale first.
    sverdrup = F["sverdrup1942_vapour_pressure_ratio"]
    s = Q_(np.array([-5.0, 35.0, 1200.0]), "g/kg")
    assert np.isnan(sverdrup.evaluate(S=s).magnitude).tolist() == [True, False, True]
    # IPTS-68 beyond its conversion: compared as it is, 0 K holding on every scale.
    bolton = F["bolton1980"]
    t = Q_(np.array([-300.0, 20.0]), "degC")
    result = bolton.evaluate(t=t, scale="ignore").magnitude
    assert np.isnan(result).tolist() == [True, False]


def test_every_variable_of_the_catalog_carries_the_bounds_of_its_kind() -> None:
    for f in F.values():
        for v in (*f.inputs, f.output):
            assert v.kind_bounds == CATALOG.bounds_of(v.kind), (f.key, v.identifier)


def test_no_bound_under_a_kind_of_differences() -> None:
    document = KIND.format(
        parent="TemperatureDifference", extra='scale_type = "interval"'
    )
    loaded = load_catalog([SOURCE + document])
    assert loaded.kinds["Part"].delta is False
    assert loaded.bounds_of("Part") is None


@pytest.mark.parametrize(
    ("low", "high"), [(-math.inf, math.inf), (1.0, 0.0), (0.0, math.nan)]
)
def test_invalid_bounds_of_a_kind_are_refused(low: float, high: float) -> None:
    with pytest.raises(ValueError, match="expected low < high, one of them finite"):
        KindBounds(low, high, "K", "c")
