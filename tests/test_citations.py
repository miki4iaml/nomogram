# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for citations: a formulation written once, cited by sources."""

import numpy as np
import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.inversion import dew_point
from nomogram.model import Citation, DomainBasis, Formulation, ScaleBasis, UnitBasis
from nomogram.units import Q_

CATALOG = catalog()
FORMULATIONS = CATALOG.formulations

BASE = """
[references.one]
authors = "One, A."
title = "First source"
status = "verified"

[references.two]
authors = "Two, B."
title = "Second source"
status = "to-confirm"

[temperature_scales.s1]
label = "Scale one"

[temperature_scales.s2]
label = "Scale two"

[formulations.f]
label = "Test formulation"
expression = "C * exp(A * t / (B + t))"
fixed_units = true
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { A = 17.62, B = 243.12, C = 6.112 }
"""

CITATION = """
[[formulations.f.citations]]
reference = "{reference}"
{fields}
"""


def document(*citations: tuple[str, str]) -> str:
    return BASE + "".join(
        CITATION.format(reference=r, fields=fields) for r, fields in citations
    )


def test_a_citation_carries_what_its_source_states() -> None:
    loaded = load_catalog(
        [
            document(
                (
                    "one",
                    (
                        'equation = 9\nnotation = { C = "a", A = "b" }\n'
                        'units = { C = "HectoPA" }\nscales = { t = "s1" }\n'
                        'accuracy = "0.1 %"\nnote = "as printed"\n\n'
                        "[[formulations.f.citations.domains]]\n"
                        'bounds = { t = [-40.0, 50.0] }\ncriterion = "stated range"'
                    ),
                ),
                ("two", ""),
            )
        ]
    )
    f = loaded.formulations["f"]
    first, second = f.citations
    assert isinstance(first, Citation)
    assert (first.reference, first.equation, first.accuracy, first.note) == (
        "one",
        "9",
        "0.1 %",
        "as printed",
    )
    assert first.notation is not None
    assert dict(first.notation.symbols) == {"C": "a", "A": "b"}
    assert first.notation.reference == "one"
    assert dict(first.units) == {"C": "HectoPA"}
    assert first.scales["t"].key == "s1"
    (domain,) = first.domains
    assert (domain.basis, domain.reference, domain.criterion) == (
        DomainBasis.STATED,
        "one",
        "stated range",
    )
    assert second == Citation("two")
    assert f.references == ("one", "two")
    # What is stated reaches the model.
    coefficient = next(c for c in f.coefficients if c.identifier == "C")
    assert (coefficient.unit, coefficient.unit_basis) == ("HectoPA", UnitBasis.STATED)
    assert f.coefficient_units["C"].citation == "one"
    assert f.coefficient_units["B"].citation is None
    assert f.inputs[0].scale_basis is ScaleBasis.STATED


def test_a_citation_can_use_a_convention_of_the_catalog() -> None:
    convention = '\n[notations.conv]\nlabel = "A convention"\nsymbols = { e = "E" }\n'
    loaded = load_catalog([document(("one", 'notation = "conv"')) + convention])
    notation = loaded.formulations["f"].citations[0].notation
    assert notation is loaded.notations["conv"]


@pytest.mark.parametrize(
    ("citations", "message"),
    [
        ((("nope", ""),), "unknown reference 'nope'"),
        ((("one", "equation = 2"), ("one", "equation = 2")), "cited twice"),
        ((("one", 'units = { x = "K" }'),), "'x' is not a coefficient"),
        ((("one", 'units = { C = "NOPE" }'),), "unknown unit"),
        ((("one", 'scales = { x = "s1" }'),), "'x' is not an input"),
        ((("one", 'scales = { t = "nope" }'),), "unknown scale 'nope'"),
        ((("one", 'notation = "nope"'),), "unknown notation 'nope'"),
        ((("one", 'notation = { x = "X" }'),), "not identifiers of the formulation: x"),
        ((("one", 'notation = { e = "\\\\textrm{e}" }'),), "LaTeX commands outside"),
        (
            (("one", 'units = { C = "HectoPA" }'), ("two", 'units = { C = "PA" }')),
            "different units for C",
        ),
        (
            (("one", 'scales = { t = "s1" }'), ("two", 'scales = { t = "s2" }')),
            "different scales for t",
        ),
        ((("one", "pages = 3"),), "unknown keys: pages"),
    ],
)
def test_invalid_citations_are_refused(
    citations: tuple[tuple[str, str], ...], message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([document(*citations)])


def test_a_stated_scale_needs_a_temperature() -> None:
    pressure = document(("one", 'scales = { t = "s1" }')).replace(
        'kind = "CelsiusTemperature", unit = "DEG_C"',
        'kind = "VapourPressure", unit = "PA"',
    )
    with pytest.raises(CatalogError, match="needs a temperature in K or DEG_C"):
        load_catalog([pressure])


def test_a_unit_is_either_added_or_stated() -> None:
    both = document(("one", 'units = { C = "HectoPA" }')).replace(
        "C = 6.112 }",
        'C = { value = 6.112, unit = "HectoPA", unit_basis = "added", note = "x" } }',
    )
    with pytest.raises(CatalogError, match="both added and stated"):
        load_catalog([both])


def test_a_scale_is_either_inferred_or_stated() -> None:
    both = document(("one", 'scales = { t = "s1" }')).replace(
        'description = "in" }',
        'description = "in", temperature_scale = "s1", scale_basis = "inferred-from-date" }',
    )
    with pytest.raises(CatalogError, match="both inferred and stated"):
        load_catalog([both])


def domain(low: float, high: float) -> str:
    return f"[[formulations.f.citations.domains]]\nbounds = {{ t = [{low}, {high}] }}"


def test_domains_of_different_citations_combine_by_union() -> None:
    loaded = load_catalog(
        [
            document(
                ("one", domain(-40.0, 0.0)),
                ("two", domain(10.0, 50.0)),
                ("one", "equation = 3"),
            )
        ]
    )
    f = loaded.formulations["f"]
    t = Q_(np.array([-50.0, -20.0, 5.0, 30.0, 60.0]), "degC")
    inside = ~np.isnan(f.evaluate(t=t).magnitude)
    # Inside if one source says so; a citation without domain widens nothing.
    assert inside.tolist() == [False, True, False, True, False]
    assert len(f.domains) == 2


def test_domains_of_one_citation_apply_together() -> None:
    both = domain(-40.0, 50.0) + "\n\n" + domain(0.0, 100.0)
    f = load_catalog([document(("one", both))]).formulations["f"]
    t = Q_(np.array([-20.0, 20.0, 70.0]), "degC")
    assert (~np.isnan(f.evaluate(t=t).magnitude)).tolist() == [False, True, False]


def test_physical_domains_always_apply() -> None:
    physical = BASE + "\n[[formulations.f.domains]]\nbounds = { t = [0.0, 100.0] }\n"
    f = load_catalog(
        [physical + CITATION.format(reference="one", fields=domain(-40.0, 50.0))]
    ).formulations["f"]
    t = Q_(np.array([-20.0, 20.0, 70.0]), "degC")
    assert (~np.isnan(f.evaluate(t=t, basis="physical").magnitude)).tolist() == [
        False,
        True,
        True,
    ]
    assert (~np.isnan(f.evaluate(t=t, basis="all").magnitude)).tolist() == [
        False,
        True,
        False,
    ]
    assert f.physical_domains[0].basis is DomainBasis.PHYSICAL


def test_catalog_citations_follow_their_sources() -> None:
    iapws = FORMULATIONS["iapws_sr1_86"]
    assert iapws.references == ("iapws_sr1_86", "wagner_pruss1993")
    assert dict(iapws.citations[0].units) == {"T_c": "K", "p_c": "PA"}
    assert iapws.coefficient_units["T_c"].citation == "iapws_sr1_86"
    # The source of the Goff-Gratch range, once implicit, is now cited.
    assert "gibbins1990" in FORMULATIONS["goff_gratch1946"].references
    sonntag = FORMULATIONS["sonntag1990"]
    stating = [c.reference for c in sonntag.citations if "T" in c.scales]
    assert stating == ["sonntag1990", "alduchov_eskridge1996"]
    r14 = FORMULATIONS["iapws_r14_08_sublimation"]
    assert r14.citations[0].accuracy is not None


def test_inversion_carries_citations_and_their_domains() -> None:
    source = FORMULATIONS["alduchov_eskridge1996"]
    inverse = dew_point(source)
    assert isinstance(inverse, Formulation)
    assert inverse.references == source.references
    (domain_carried,) = inverse.citations[0].domains
    assert set(domain_carried.bounds) == {"e"}
    assert domain_carried.reference == "alduchov_eskridge1996"
    assert all(not c.scales for c in inverse.citations)
