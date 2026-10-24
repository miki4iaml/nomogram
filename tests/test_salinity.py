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
from nomogram.inversion import invert
from nomogram.model import ScaleConversionError, Variable
from nomogram.relations import (
    _common_bounds,
    _conversion_chain,
    _on_reference,
    fingerprint,
    report,
)
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


def test_an_interval_of_salinity_is_carried_to_the_reference_scale() -> None:
    u_ps = 35.16504 / 35
    pss78 = SCALES["pss78"]
    # Below S_P = 2 nothing converts: the interval starts there.
    interval = pss78.interval_to_reference(0.0, 40.0)
    assert interval == pytest.approx((2 * u_ps, 40 * u_ps))
    assert pss78.interval_to_reference(45.0, 50.0) is None
    # Knudsen to Cox to Reference Salinity, without bounds: an infinite end
    # stays infinite.
    knudsen = SCALES["knudsen1901"]
    interval = knudsen.interval_to_reference(-np.inf, 35.0)
    assert interval == pytest.approx((-np.inf, float(knudsen.to_reference(35.0))))
    with pytest.raises(ScaleConversionError):
        SCALES["absolute_salinity2010"].interval_to_reference(0.0, 40.0)


def test_a_domain_beyond_its_scale_conversion_is_not_compared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Stated valid only above S_P = 42, where PSS-78 does not convert.
    dickson = F["dickson2007_vapour_pressure"]
    assert _on_reference(dickson, {"S": (45.0, 50.0)}) is None
    monkeypatch.setattr(
        "nomogram.relations._valid_extent", lambda _: {"S": (45.0, 50.0)}
    )
    assert _common_bounds(dickson, F["weiss_price1980_vapour_pressure"]) is None


def test_salinity_formulations_are_compared_on_the_reference_scale() -> None:
    # Weiss and Price (1980) are stated valid up to 313 K, but their IPTS-48
    # temperatures convert to ITS-90 up to 30 degC only: the comparison
    # stops there instead of leaving a quarter of its grid without values.
    text = report(CATALOG, ["weiss_price1980_vapour_pressure"], budget=1000)
    assert "from dickson2007_vapour_pressure: " in text
    assert "of the common domain only" not in text


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
    # The two chlorinity formulas differ by 0.0025 at 32 and 0.0026 at 38;
    # JPOTS's 0.0023 there concerns the conductivity-defined salinity.
    assert gap(32.0) == pytest.approx(0.00255, abs=5e-5)
    assert gap(38.0) == pytest.approx(0.00261, abs=5e-5)
    # Converted to the reference scale, both near 35.16504 g/kg at Cl = 19.374.
    cl = Q_(19.374, "permille")
    for f in (knudsen, cox):
        assert f.evaluate(Cl=cl).to("g/kg").magnitude == pytest.approx(
            35.1651, abs=1e-4
        )


def test_a_chain_of_scales_is_followed() -> None:
    knudsen = SCALES["knudsen1901"]
    assert knudsen.base is SCALES["cox1967"]
    s_k = np.array([10.0, 35.0, 40.0])
    on_reference = knudsen.to_reference(s_k)
    expected = (s_k - 0.03) * 1.80655 / 1.805 * 35.16504 / 35
    assert on_reference == pytest.approx(expected)
    back, outside = knudsen.from_reference(on_reference)
    assert back == pytest.approx(s_k)
    assert not outside.any()
    assert [step[0] for step in _conversion_chain(knudsen)] == [
        "knudsen1901",
        "cox1967",
    ]
    assert _conversion_chain(SCALES["ipts68"]) == []


def test_chlorinity_salinities_convert_below_the_limits_of_pss78() -> None:
    # TEOS-10 A.4: S_R = u_PS S for salinities measured before PSS-78, with
    # no range; Knudsen goes through Cox. PSS-78 keeps its limits, 2 to 42.
    cox, knudsen = SCALES["cox1967"], SCALES["knudsen1901"]
    assert cox.base is None
    assert cox.bounds is None
    assert knudsen.bounds is None
    s = np.array([0.0, 1.0, 45.0])
    assert cox.to_reference(s) == pytest.approx(35.16504 / 35 * s)
    assert knudsen.to_reference(s) == pytest.approx(
        (s - 0.03) * 1.80655 / 1.805 * 35.16504 / 35
    )
    for scale in (cox, knudsen):
        back, outside = scale.from_reference(scale.to_reference(s))
        assert back == pytest.approx(s)
        assert not outside.any()
    assert np.isnan(SCALES["pss78"].to_reference(np.array([1.0]))).all()
    # Lewis and Perkin (1981, p. 325) find Knudsen salinities within 0.001 of
    # PSS-78 directly for 25 < S < 38; the conversion carried departs from
    # that by up to about 0.009 at 25, the disagreement the note records.
    s_k = np.array([25.0, 32.0, 38.0])
    s_p = SCALES["pss78"].from_reference(knudsen.to_reference(s_k))[0]
    assert s_p - s_k == pytest.approx([-0.0086, -0.0025, 0.0026], abs=5e-5)
    assert "Lewis and Perkin" in (knudsen.note or "")
    assert "0.009" in (knudsen.note or "")


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
    # Fofonoff and Bryden build it over -2 to 30 degC: t90 = 29.98 degC is
    # still inside, t90 = 30 degC (t48 = 30.016) is not.
    back, outside = ipts48.from_reference(np.array([29.98, 30.0]))
    assert back[0] == pytest.approx(29.996, abs=1e-3)
    assert list(outside) == [False, True]
    assert np.isnan(back[1])


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
    assert "scales.knudsen1901" in CATALOG.search("disagree*", section="scales").refs


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
            "'nope' is not a convertible scale of the same kinds",
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


def test_an_inverse_takes_its_input_on_the_scale_of_the_source_output() -> None:
    knudsen = F["knudsen1901_salinity"]
    s_r = knudsen.evaluate(Cl=Q_(19.374, "permille"))
    output = Variable("Cl", "Chlorinity", "PERMILLE", "Chlorinity")
    target = Variable("S", "SeaWaterSalinity", "PERMILLE", "Salinity")
    for method in ("symbolic", "numerical"):
        inverse = invert(
            knudsen,
            "Cl",
            output=output,
            input=target,
            method=method,
            search=(1.0, 25.0),
        )
        assert inverse.inputs[0].scale is SCALES["knudsen1901"]
        found = inverse.evaluate(S=s_r)
        assert found.to("permille").magnitude == pytest.approx(19.374, abs=1e-9), method


def test_scales_of_compositions() -> None:
    document = (
        PARTS
        + """
[formulations.inner]
label = "Inner"
expression = "c * Cl"
fixed_units = true
output = { identifier = "S", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "S" }
inputs = [{ identifier = "Cl", kind = "Chlorinity", unit = "PERMILLE", description = "Cl" }]
coefficients = { c = 1.5 }
citations = [{ reference = "r", scales = { S = "p" } }]

[formulations.outer]
label = "Outer"
expression = "k * S"
fixed_units = true
output = { identifier = "y", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "y" }
inputs = [{ identifier = "S", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "S" }]
coefficients = { k = 3.0 }
citations = [{ reference = "r", scales = { S = "p", y = "p" } }]

[formulations.plain]
label = "Plain outer"
expression = "k * S"
fixed_units = true
output = { identifier = "y", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "y" }
inputs = [{ identifier = "S", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "S" }]
coefficients = { k = 4.0 }
"""
    )
    kinds = (
        '[kinds.Chlorinity]\nlabel = "Chlorinity"\nspecialization_of = "MassFraction"\n'
    )
    composed = """
[formulations.both]
label = "Both"
composition = { outer = "outer", inner = { S = "inner" } }
output = { identifier = "w", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "w" }
"""
    built = load_catalog([document + kinds + composed])
    both = built.formulations["both"]
    # The declared output keeps the scale of the outer output.
    assert both.output.scale is built.scales["p"]
    cl = Q_(2.0, "permille")
    step = built.formulations["outer"].evaluate(
        S=built.formulations["inner"].evaluate(Cl=cl)
    )
    assert both.evaluate(Cl=cl).magnitude == pytest.approx(step.magnitude)
    mismatch = composed.replace('outer = "outer"', 'outer = "plain"')
    with pytest.raises(
        CatalogError, match="gives a value on scale p, but S is on None"
    ):
        load_catalog([document + kinds + mismatch])
    other = composed.replace(
        'description = "w" }',
        'description = "w", scale = "abs", scale_basis = "inferred-from-date" }',
    )
    with pytest.raises(CatalogError, match="the scale is that of outer's output, p"):
        load_catalog([document + kinds + other])


def test_bounds_hold_through_a_chain() -> None:
    document = PARTS + (
        '[scales.b]\nlabel = "Bounded"\nkinds = ["SeaWaterSalinity"]\n'
        'reference_scale = "ref"\nunit = "PERMILLE"\nconversion = "2 * x"\n'
        "bounds = [2.0, 42.0]\n"
        '[scales.k]\nlabel = "On the bounded scale"\nkinds = ["SeaWaterSalinity"]\n'
        'reference_scale = "ref"\nbase = "b"\nunit = "PERMILLE"\nconversion = "x - 1"\n'
    )
    k = load_catalog([document]).scales["k"]
    assert k.to_reference(np.array([11.0])) == pytest.approx([20.0])
    # k = 2 gives b = 1, below the bounds of b: NaN on the reference.
    assert np.isnan(k.to_reference(np.array([2.0]))).all()
    found, outside = k.from_reference(np.array([2.0]))
    assert outside.all()
    assert np.isnan(found).all()


def test_inverse_by_iteration_and_its_convergence() -> None:
    base = dataclasses.replace(SCALES["pss78"], base=None, bounds=None)
    # SymPy cannot solve this one: the inverse iterates, and converges.
    unsolved = dataclasses.replace(base, conversion="x + exp(x ** 2) / 1000")
    y = unsolved.to_reference(np.array([0.5, 1.0]))
    found, outside = unsolved.from_reference(y)
    assert found == pytest.approx([0.5, 1.0], abs=1e-9)
    assert not outside.any()
    # Two roots, and a slope far from 1: no convergence, flagged.
    square = dataclasses.replace(base, conversion="x ** 2", bounds=(1.0, 10.0))
    found, outside = square.from_reference(np.array([9.0]))
    assert outside.all()
    assert np.isnan(found).all()


def test_scales_without_conversion_on_outputs_and_inverses() -> None:
    document = (
        PARTS
        + """
[formulations.g]
label = "Output on Absolute Salinity"
expression = "a * S"
fixed_units = true
output = { identifier = "y", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "y" }
inputs = [{ identifier = "S", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "S" }]
coefficients = { a = 2.0 }
citations = [{ reference = "r", scales = { y = "abs" } }]
"""
    )
    g = load_catalog([document]).formulations["g"]
    with pytest.raises(ScaleConversionError):
        g.evaluate(S=Q_(35.0, "permille"))
    inverse = invert(
        g,
        "S",
        output=Variable("S", "SeaWaterSalinity", "PERMILLE", "S"),
        input=Variable("y", "SeaWaterSalinity", "PERMILLE", "y"),
        method="numerical",
        search=(1.0, 50.0),
    )
    with pytest.raises(ScaleConversionError):
        inverse.evaluate(y=Q_(70.0, "permille"))
    assert inverse.evaluate(y=Q_(70.0, "permille"), scale="ignore").magnitude == (
        pytest.approx(35.0)
    )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("[scales]\nx = 3\n", "scales.x: expected a table"),
        (
            '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = 3\n',
            "reference_scale: expected a scale key",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\nbounds = [1.0]\n'
            ),
            "bounds: expected \\[low, high\\]",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\nbounds = [1.0, inf]\n'
            ),
            "two finite numbers",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'convertible = "false"\n'
            ),
            "convertible: expected true or false",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\nbase = "abs"\n'
            ),
            "'abs' is not a convertible scale",
        ),
        (
            (
                '[scales.x]\nlabel = "X"\nkinds = ["SeaWaterSalinity"]\nreference_scale = "ref"\n'
                'unit = "PERMILLE"\nconversion = "x"\ncf_standard_names = ["sea_water_nonsense"]\n'
            ),
            "not in the frozen CF subset: sea_water_nonsense",
        ),
    ],
)
def test_malformed_scales_are_refused(extra: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([PARTS + extra])


def test_fingerprint_follows_the_whole_conversion() -> None:
    def relation_with(conversion: str) -> str:
        document = PARTS.replace('conversion = "2 * x"', f'conversion = "{conversion}"')
        document += """
[formulations.f1]
label = "F1"
expression = "a * S"
fixed_units = true
output = { identifier = "y", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "y" }
inputs = [{ identifier = "S", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "S" }]
coefficients = { a = 2.0 }
citations = [{ reference = "r", scales = { S = "p" } }]

[formulations.f2]
label = "F2"
expression = "b * S"
fixed_units = true
output = { identifier = "y", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "y" }
inputs = [{ identifier = "S", kind = "SeaWaterSalinity", unit = "PERMILLE", description = "S" }]
coefficients = { b = 3.0 }

[relations.r1]
kind = "equivalent"
subject = "f1"
object = "f2"
citation = "r"
"""
        built = load_catalog([document])
        return fingerprint(built.relations["r1"], built)

    assert relation_with("2 * x") != relation_with("3 * x")
    # A chain through a table records the table too.
    chain = _conversion_chain(SCALES["ipts48"])
    assert [step[0] for step in chain] == ["ipts48", "ipts68"]
