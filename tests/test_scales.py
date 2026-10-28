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
IPTS68 = CATALOG.scales["ipts68"]
IAPWS = FORMULATIONS["iapws_sr1_86"]
BOLTON = FORMULATIONS["bolton1980"]


@pytest.mark.parametrize(
    ("t90", "t68"),
    # Table 6 of the ITS-90 text: t90 - t68 = -0.005, -0.026, +0.008 K.
    [(20.0, 20.005), (100.0, 100.026), (-40.0, -40.008), (0.0, 0.0)],
)
def test_ipts68_from_reference_follows_table_6(t90: float, t68: float) -> None:
    converted, outside = IPTS68.from_reference(t90)
    assert float(converted) == pytest.approx(t68, abs=1e-9)
    assert not outside


def test_beyond_the_table_is_nan_and_flagged() -> None:
    converted, outside = IPTS68.from_reference(np.array([20.0, 500.0]))
    assert math.isnan(converted[1])
    assert outside.tolist() == [False, True]


def test_its90_is_the_identity() -> None:
    converted, outside = CATALOG.scales["its90"].from_reference([12.3])
    assert converted.tolist() == [12.3]
    assert not outside.any()


def test_an_interval_on_a_table_scale_is_carried_to_its90() -> None:
    # Table 6: t68 = 20.005 degC is t90 = 20 degC.
    interval = IPTS68.interval_to_reference(0.0, 20.005)
    assert interval == pytest.approx((0.0, 20.0), abs=1e-9)
    # The table spans -190 to 390 degC on ITS-90; nothing converts beyond.
    assert IPTS68.interval_to_reference(-math.inf, math.inf) == (-190.0, 390.0)
    assert IPTS68.interval_to_reference(500.0, 600.0) is None
    its90 = CATALOG.scales["its90"]
    assert its90.interval_to_reference(-math.inf, 12.3) == (-math.inf, 12.3)


def test_scales_of_formulations_and_how_they_are_known() -> None:
    assert IAPWS.inputs[0].scale is not None
    assert IAPWS.inputs[0].scale.key == "its90"
    assert IAPWS.inputs[0].scale_basis is ScaleBasis.STATED
    assert BOLTON.inputs[0].scale is IPTS68
    assert BOLTON.inputs[0].scale_basis is ScaleBasis.INFERRED_FROM_DATE
    # Fitted to formulations on several scales: none assigned.
    assert FORMULATIONS["alduchov_eskridge1996"].inputs[0].scale is None
    # Coefficients transmitted by ASHRAE 2017 behave as ITS-90.
    hyland_wexler = FORMULATIONS["hyland_wexler1983"].inputs[0]
    assert hyland_wexler.scale is not None
    assert hyland_wexler.scale.key == "its90"
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
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[scales.ref]
label = "Reference scale"
kinds = ["CelsiusTemperature"]

[scales.s]
label = "Test scale"
kinds = ["CelsiusTemperature"]
reference_scale = "ref"
unit = "DEG_C"
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
        variable=GOOD_VARIABLE + ', scale = "s", scale_basis = "inferred-from-date"',
    )
    scale = load_catalog([document]).formulations["f"].inputs[0].scale
    assert scale is not None
    assert scale.difference == (0.0, -0.1)


def test_a_stated_scale_comes_from_a_citation() -> None:
    document = SCALES.format(differences="[[0.0, 0.0]]", variable=GOOD_VARIABLE)
    document += (
        '\n[[formulations.f.citations]]\nreference = "src"\nscales = { t = "s" }\n'
    )
    variable = load_catalog([document]).formulations["f"].inputs[0]
    assert variable.scale is not None
    assert variable.scale.key == "s"
    assert variable.scale_basis is ScaleBasis.STATED
    in_the_input = SCALES.format(
        differences="[[0.0, 0.0]]",
        variable=GOOD_VARIABLE + ', scale = "s", scale_basis = "stated"',
    )
    with pytest.raises(CatalogError, match="goes in its citation"):
        load_catalog([in_the_input])


@pytest.mark.parametrize(
    ("differences", "variable", "message"),
    [
        ("[[0.0, 0.0]]", GOOD_VARIABLE + ', scale = "s"', "go together"),
        (
            "[[0.0, 0.0]]",
            GOOD_VARIABLE + ', scale = "x", scale_basis = "inferred-from-date"',
            "unknown scale 'x'",
        ),
        (
            "[[0.0, 0.0]]",
            GOOD_VARIABLE + ', scale = "s", scale_basis = "guessed"',
            "is not one of stated, inferred-from-date, inferred-from-numbers",
        ),
        (
            "[[0.0, 0.0]]",
            GOOD_VARIABLE.replace(
                "CelsiusTemperature", "ThermodynamicTemperature"
            ).replace("DEG_C", "K")
            + ', scale = "s", scale_basis = "inferred-from-date"',
            "scale s does not apply to ThermodynamicTemperature",
        ),
        ("[[10.0, 0.0], [0.0, 0.0]]", GOOD_VARIABLE, "reference values must increase"),
        ("[[10.0]]", GOOD_VARIABLE, "expected \\[reference value"),
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
        'description = "in", scale = "s", scale_basis = "inferred-from-date" }]',
    )
    with pytest.raises(CatalogError, match="scale s does not apply to VapourPressure"):
        load_catalog([document])


TABLE = """
[scales.ref]
label = "Reference"
kinds = ["CelsiusTemperature", "VapourPressure"]

[scales.p]
label = "Derived for pressures"
kinds = ["VapourPressure"]
reference_scale = "ref"
unit = "DEG_C"
differences = [[0.0, 0.0], [10.0, 0.1]]
"""


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ('[scales.x]\nlabel = "X"\nkinds = []\n', "at least one quantity kind"),
        ('[scales.x]\nlabel = "X"\nkinds = ["Nope"]\n', "unknown kind"),
        (
            '[scales.x]\nlabel = "X"\nkinds = ["CelsiusTemperature"]\n',
            "CelsiusTemperature already has a reference scale, ref",
        ),
        (
            '[scales.x]\nlabel = "X"\nkinds = ["Pressure"]\nunit = "K"\n',
            "a reference scale has no conversion table",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["CelsiusTemperature"]\n'
                'reference_scale = "p"\nunit = "DEG_C"\ndifferences = [[0.0, 0.0]]\n'
            ),
            "'p' is not a reference scale",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["Pressure"]\nreference_scale = "ref"\n'
                'unit = "DEG_C"\ndifferences = [[0.0, 0.0]]\n'
            ),
            "Pressure not covered by ref",
        ),
        (
            '[scales.x]\nlabel = "X"\nkinds = ["CelsiusTemperature"]\nreference_scale = "ref"\n',
            "a derived scale needs a unit and differences",
        ),
        # A reference scale of Temperature would be that of the Celsius
        # temperature too, which has one.
        (
            '[scales.x]\nlabel = "X"\nkinds = ["Temperature"]\n',
            "CelsiusTemperature already has a reference scale, ref",
        ),
    ],
)
def test_invalid_scale_tables_are_refused(extra: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([TABLE + extra])


def test_scales_follow_the_specializations_of_their_kinds() -> None:
    # A reference scale of Temperature covers a derived scale of the
    # Celsius temperature, and leaves it no reference scale of its own.
    general = (
        '[scales.ref]\nlabel = "Reference"\nkinds = ["Temperature"]\n'
        '[scales.old]\nlabel = "Old"\nkinds = ["CelsiusTemperature"]\n'
        'reference_scale = "ref"\nunit = "DEG_C"\ndifferences = [[0.0, 0.0]]\n'
    )
    assert load_catalog([general]).scales["old"].reference_scale == "ref"
    second = '[scales.x]\nlabel = "X"\nkinds = ["CelsiusTemperature"]\n'
    with pytest.raises(CatalogError, match="already has a reference scale, ref"):
        load_catalog([general + second])


def test_a_number_on_a_scale_of_numbers_has_no_unit() -> None:
    # Practical Salinity is a number since 0.4: 35 is not 35 per mille.
    def document(unit: str) -> str:
        return (
            '[scales.ref]\nlabel = "Reference"\nkinds = ["RelativeHumidity"]\n'
            '[scales.n]\nlabel = "Numbers"\nkinds = ["RelativeHumidity"]\n'
            'reference_scale = "ref"\nunit = "UNITLESS"\n'
            "differences = [[0.0, 0.0], [40.0, 0.0]]\n"
            '\n[formulations.f]\nlabel = "F"\nexpression = "2 * S"\n'
            'fixed_units = true\noutput = { identifier = "y", kind = '
            '"RelativeHumidity", unit = "UNITLESS", description = "out" }\n'
            'inputs = [{ identifier = "S", kind = "RelativeHumidity", '
            f'unit = "{unit}", description = "in", scale = "n", '
            'scale_basis = "inferred-from-date" }]\n'
        )

    with pytest.raises(CatalogError, match="n gives numbers"):
        load_catalog([document("PERCENT")])
    assert "f" in load_catalog([document("UNITLESS")]).formulations


def test_a_scale_needs_a_convertible_unit() -> None:
    document = TABLE + (
        '\n[formulations.f]\nlabel = "F"\nexpression = "2 * p"\nfixed_units = true\n'
        'output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", '
        'description = "out" }\n'
        'inputs = [{ identifier = "p", kind = "VapourPressure", unit = "PA", '
        'description = "in", scale = "p", scale_basis = "inferred-from-date" }]\n'
    )
    with pytest.raises(CatalogError, match="PA cannot be converted to DEG_C"):
        load_catalog([document])


def test_conventional_scales_follow_the_vim() -> None:
    its90, ipts68 = CATALOG.scales["its90"], CATALOG.scales["ipts68"]
    assert its90.is_reference
    assert not ipts68.is_reference
    assert ipts68.reference_scale == "its90"
    assert ipts68.unit == "DEG_C"
    assert set(ipts68.kinds) <= set(its90.kinds)
