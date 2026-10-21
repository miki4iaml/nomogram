# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for conventional scales converted by expression: salinity, temperature.

Expected values come from the sources cited by the catalog (JPOTS 1966,
Saunders 1990, TEOS-10 Manual).
"""

import dataclasses

import numpy as np
import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.model import ScaleConversionError
from nomogram.relations import _conversion_chain
from nomogram.units import Q_

CATALOG = catalog()
SCALES = CATALOG.scales
F = CATALOG.formulations


def test_reference_salinity_from_practical_salinity() -> None:
    # TEOS-10 eq. 2.4.1: S_P = 35 gives S_R = 35.16504 g/kg exactly.
    pss78 = SCALES["pss78"]
    assert pss78.to_reference(35.0) == pytest.approx(35.16504, abs=1e-12)
    back, outside = pss78.from_reference(np.array([35.16504]))
    assert back == pytest.approx([35.0])
    assert not outside.any()
    # Beyond 2 < S_P < 42, no conversion.
    assert np.isnan(pss78.to_reference(np.array([1.0, 45.0]))).all()
    _, outside = pss78.from_reference(np.array([1.0]))
    assert outside.all()


def test_knudsen_and_cox_salinities_from_chlorinity() -> None:
    knudsen, cox = F["knudsen1901_salinity"], F["cox_salinity_jpots1966"]
    assert knudsen.output.scale is SCALES["knudsen1901"]
    assert cox.output.scale is SCALES["cox1967"]

    def gap(salinity: float) -> float:
        chlorinity = Q_((salinity - 0.030) / 1.805, "permille")
        s_k = knudsen.evaluate(Cl=chlorinity, scale="ignore").magnitude
        s_c = cox.evaluate(Cl=chlorinity, scale="ignore").magnitude
        assert s_k == pytest.approx(salinity)
        return float(abs(s_k - s_c))

    # JPOTS 1966, p. 6: zero at 35; about 0.02 at 11 and 0.025 at 6 (Baltic).
    assert gap(35.0) == pytest.approx(0.0, abs=1e-4)
    assert gap(11.0) == pytest.approx(0.02, abs=1e-3)
    assert gap(6.0) == pytest.approx(0.025, abs=1e-3)
    # JPOTS prints 0.0023 at 32 and 38 for the salinity from conductivity,
    # which carries a +0.00018 shift; the two formulas differ by 0.0025.
    assert gap(32.0) == pytest.approx(0.0023 + 0.00018, abs=1e-4)
    # Converted to the reference scale, both near 35.16504 g/kg at Cl = 19.374.
    cl = Q_(19.374, "permille")
    for f in (knudsen, cox):
        assert f.evaluate(Cl=cl).to("g/kg").magnitude == pytest.approx(
            35.1651, abs=1e-4
        )


def test_a_chain_of_scales_is_followed() -> None:
    knudsen = SCALES["knudsen1901"]
    assert knudsen.base is SCALES["pss78"]
    s_k = np.array([10.0, 35.0, 40.0])
    on_reference = knudsen.to_reference(s_k)
    expected = (s_k - 0.03) * 1.80655 / 1.805 * 35.16504 / 35
    assert on_reference == pytest.approx(expected)
    back, outside = knudsen.from_reference(on_reference)
    assert back == pytest.approx(s_k)
    assert not outside.any()
    assert [step[0] for step in _conversion_chain(knudsen)] == ["knudsen1901", "pss78"]
    assert _conversion_chain(SCALES["ipts68"]) == []


def test_temperature_scales_of_oceanography() -> None:
    saunders = SCALES["ipts68_saunders1990"]
    # Saunders (1990): t90 - t68 = -0.007 degC at 30 degC.
    assert saunders.to_reference(30.0) - 30.0 == pytest.approx(-0.007, abs=5e-4)
    assert np.isnan(saunders.to_reference(np.array([45.0]))).all()
    ipts48 = SCALES["ipts48"]
    t48 = np.array([0.0, 10.0, 20.0, 30.0])
    t68 = t48 - 4.4e-6 * t48 * (100 - t48)
    assert ipts48.to_reference(t48) == pytest.approx(SCALES["ipts68"].to_reference(t68))
    # The quadratic has two roots: the inverse iterates instead.
    back, outside = ipts48.from_reference(ipts48.to_reference(t48))
    assert back == pytest.approx(t48, abs=1e-9)
    assert not outside.any()


def test_absolute_salinity_is_not_converted() -> None:
    absolute = SCALES["absolute_salinity2010"]
    assert not absolute.convertible
    with pytest.raises(ScaleConversionError, match="no conversion"):
        absolute.to_reference(35.0)
    with pytest.raises(ScaleConversionError, match='scale="ignore"'):
        absolute.from_reference(35.0)
    # A formulation fitted on it takes values as given.
    document = (
        PARTS
        + """
[formulations.f]
label = "On Absolute Salinity"
expression = "a * S"
fixed_units = true
output = { identifier = "y", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "y" }
inputs = [{ identifier = "S", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "S" }]
coefficients = { a = 2.0 }
citations = [{ reference = "r", scales = { S = "abs", y = "abs" } }]
"""
    )
    f = load_catalog([document]).formulations["f"]
    with pytest.raises(ScaleConversionError):
        f.evaluate(S=Q_(35.0, "permille"))
    assert f.evaluate(S=Q_(35.0, "permille"), scale="ignore").magnitude == 70.0


def test_scales_are_searchable_by_their_cf_names() -> None:
    found = CATALOG.search("sea_water_practical_salinity", section="scales")
    assert found.refs == ("scales.pss78",)
    assert "scales.knudsen1901" in CATALOG.search("knudsen", section="scales").refs
    # The note too: the scales whose conversion sources dispute.
    assert "scales.knudsen1901" in CATALOG.search("disagree", section="scales").refs


PARTS = """
[references.r]
authors = "A"
title = "T"
status = "verified"

[kinds.SeaWaterSalinity]
label = "Sea water salinity"
specialization_of = "MassFraction"

[scales.ref]
label = "Reference"
kinds = ["SeaWaterSalinity"]

[scales.abs]
label = "Absolute"
kinds = ["SeaWaterSalinity"]
reference_scale = "ref"
convertible = false

[scales.p]
label = "Practical"
kinds = ["SeaWaterSalinity"]
reference_scale = "ref"
unit = "PERMILLE"
conversion = "2 * x"
"""


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            '[scales.x]\nlabel = "X"\nkinds = ["Chlorinity"]\nconversion = "x"\n',
            "unknown kind",
        ),
        (
            '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nconversion = "x"\n',
            "a reference scale has no conversion table",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\ndifferences = [[0.0, 0.0]]\n'
            ),
            "differences, or a unit and a conversion",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x + y"\n'
            ),
            "conversion:",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\nbase = "nope"\n'
            ),
            "'nope' is not a scale of the same kinds",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "GM-PER-KiloGM"\nconversion = "x"\nbase = "p"\n'
            ),
            "must lead to ref in the same unit",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\nbounds = [3.0, 1.0]\n'
            ),
            "bounds: empty interval",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'convertible = false\nconversion = "x"\n'
            ),
            "a scale without conversion has no conversion",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\ndifferences = [[0.0, 0.0]]\nbase = "p"\n'
            ),
            "a table converts to the reference scale",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\ndifferences = []\n'
            ),
            "expected \\[reference value",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\nbase = "y"\n'
                '[scales.y]\nlabel = "Y"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\nbase = "x"\n'
            ),
            "conversions form a cycle",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = 3\n'
            ),
            "conversion: expected a non-empty string",
        ),
    ],
)
def test_invalid_scales_are_refused(extra: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([PARTS + extra])


def test_a_conversion_to_the_reference_needs_no_base() -> None:
    document = PARTS + (
        '[scales.q]\nlabel = "Q"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
        'unit = "PERMILLE"\nconversion = "x + 1"\nbase = "ref"\n'
    )
    scale = load_catalog([document]).scales["q"]
    assert scale.base is None
    assert scale.to_reference(1.0) == 2.0
    # A constant conversion broadcasts to the shape of its input.
    constant = dataclasses.replace(scale, conversion="3")
    assert constant.to_reference(np.zeros(3)) == pytest.approx([3.0, 3.0, 3.0])
