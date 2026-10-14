# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Temperature scales: ITS-90 inputs converted to the scale of a formulation."""

import math

import numpy as np
import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.comparison import compare, compose
from nomogram.model import ScaleBasis
from nomogram.units import Q_

CATALOG = catalog()
FORMULATIONS = CATALOG.formulations
IPTS68 = CATALOG.temperature_scales["ipts68"]
IAPWS = FORMULATIONS["iapws_sr1_86"]
BOLTON = FORMULATIONS["bolton1980"]


@pytest.mark.parametrize(
    ("t90", "t68"),
    # Table 6 of the ITS-90 text: t90 - t68 = -0.005, -0.026, +0.008 K.
    [(20.0, 20.005), (100.0, 100.026), (-40.0, -40.008), (0.0, 0.0)],
)
def test_ipts68_from_its90_follows_table_6(t90: float, t68: float) -> None:
    converted, outside = IPTS68.from_its90(t90)
    assert float(converted) == pytest.approx(t68, abs=1e-9)
    assert not outside


def test_beyond_the_table_is_nan_and_flagged() -> None:
    converted, outside = IPTS68.from_its90(np.array([20.0, 500.0]))
    assert math.isnan(converted[1])
    assert outside.tolist() == [False, True]


def test_its90_is_the_identity() -> None:
    converted, outside = CATALOG.temperature_scales["its90"].from_its90([12.3])
    assert converted.tolist() == [12.3]
    assert not outside.any()


def test_scales_of_formulations_and_how_they_are_known() -> None:
    assert IAPWS.inputs[0].temperature_scale is not None
    assert IAPWS.inputs[0].temperature_scale.key == "its90"
    assert IAPWS.inputs[0].scale_basis is ScaleBasis.STATED
    assert BOLTON.inputs[0].temperature_scale is IPTS68
    assert BOLTON.inputs[0].scale_basis is ScaleBasis.INFERRED_FROM_DATE
    # Fitted to formulations on several scales: none assigned.
    assert FORMULATIONS["alduchov_eskridge1996"].inputs[0].temperature_scale is None
    # Coefficients transmitted by ASHRAE 2017 behave as ITS-90.
    hyland_wexler = FORMULATIONS["hyland_wexler1983"].inputs[0]
    assert hyland_wexler.temperature_scale is not None
    assert hyland_wexler.temperature_scale.key == "its90"
    assert hyland_wexler.scale_basis is ScaleBasis.INFERRED_FROM_NUMBERS
    assert "0.022 %" in (FORMULATIONS["hyland_wexler1983"].note or "")


def test_conversion_changes_an_ipts68_formulation_by_the_expected_amount() -> None:
    converted = BOLTON.evaluate(t=Q_(20, "degC")).magnitude
    as_is = BOLTON.evaluate(t=Q_(20, "degC"), scale="ignore").magnitude
    # 0.005 K at about 6.2 %/K: about +0.031 %.
    assert converted / as_is - 1 == pytest.approx(0.00031, abs=0.00003)


def test_its90_formulations_are_not_changed() -> None:
    kelvin = Q_(293.15, "K")
    assert IAPWS.evaluate(T=kelvin) == IAPWS.evaluate(T=kelvin, scale="ignore")


def test_conversion_beyond_the_table_gives_nan_even_when_domains_are_ignored() -> None:
    result = BOLTON.evaluate(t=Q_(500, "degC"), outside="ignore")
    assert math.isnan(result.magnitude)


def test_compare_and_compose_pass_the_scale_option() -> None:
    inputs = {"CelsiusTemperature": Q_(20, "degC")}
    converted = compare([BOLTON], IAPWS, inputs).relative_deviations["bolton1980"]
    as_is = compare([BOLTON], IAPWS, inputs, scale="ignore").relative_deviations[
        "bolton1980"
    ]
    assert float(converted) != float(as_is)
    ha = compose(
        FORMULATIONS["mass_concentration_ideal_gas"], {"e_s": BOLTON}, bind={"t": "T"}
    )
    both = [
        ha.evaluate(RH=Q_(1, ""), T=Q_(20, "degC"), scale=s).magnitude
        for s in ("convert", "ignore")
    ]
    assert both[0] != both[1]


SCALES = """
[temperature_scales.s]
label = "Test scale"
differences = {differences}

[formulations.f]
label = "Test formulation"
expression = "2 * t"
fixed_units = true
output = {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }}
inputs = [{{ {variable} }}]
"""

GOOD_VARIABLE = (
    'identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in"'
)


def test_valid_scale_document() -> None:
    document = SCALES.format(
        differences="[[0.0, 0.0], [10.0, -0.1]]",
        variable=GOOD_VARIABLE + ', temperature_scale = "s", scale_basis = "stated"',
    )
    scale = load_catalog([document]).formulations["f"].inputs[0].temperature_scale
    assert scale is not None
    assert scale.difference == (0.0, -0.1)


@pytest.mark.parametrize(
    ("differences", "variable", "message"),
    [
        ("[[0.0, 0.0]]", GOOD_VARIABLE + ', temperature_scale = "s"', "go together"),
        (
            "[[0.0, 0.0]]",
            GOOD_VARIABLE + ', temperature_scale = "x", scale_basis = "stated"',
            "unknown scale 'x'",
        ),
        (
            "[[0.0, 0.0]]",
            GOOD_VARIABLE + ', temperature_scale = "s", scale_basis = "guessed"',
            "is not one of stated, inferred-from-date, inferred-from-numbers",
        ),
        (
            "[[0.0, 0.0]]",
            GOOD_VARIABLE.replace("DEG_C", "DEG_F")
            + ', temperature_scale = "s", scale_basis = "stated"',
            "needs a temperature in K or DEG_C",
        ),
        ("[[10.0, 0.0], [0.0, 0.0]]", GOOD_VARIABLE, "t90 must increase"),
        ("[[10.0]]", GOOD_VARIABLE, "expected \\[t90, t90 - t\\] pairs"),
    ],
)
def test_invalid_scales_are_refused(
    differences: str, variable: str, message: str
) -> None:
    document = SCALES.format(differences=differences, variable=variable)
    with pytest.raises(CatalogError, match=message):
        load_catalog([document])


def test_a_scale_needs_a_temperature() -> None:
    document = SCALES.format(differences="[[0.0, 0.0]]", variable=GOOD_VARIABLE)
    document = document.replace(
        "inputs = [{ " + GOOD_VARIABLE + " }]",
        'inputs = [{ identifier = "t", kind = "VapourPressure", unit = "PA", '
        'description = "in", temperature_scale = "s", scale_basis = "stated" }]',
    )
    with pytest.raises(CatalogError, match="needs a temperature"):
        load_catalog([document])
