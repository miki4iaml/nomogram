# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for relations between formulations, and their verification."""

import dataclasses

import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.model import Relation, RelationKind
from nomogram.relations import Verdict, per_axis, verify

CATALOG = catalog()

#: Alduchov and Eskridge (1996), Table III, as verified: everything is
#: reproduced at the published precision, except SA90.
TABLE_III = {
    "ae96_te30_gg46": "reproduced",
    "ae96_te30_so90": "reproduced",
    "ae96_bu81_gg46": "reproduced",
    "ae96_bu81_so90": "reproduced",
    "ae96_sa90_gg46": "exceeded",
    "ae96_sa90_so90": "held",
    "ae96_bu2_gg46": "reproduced",
    "ae96_bu2_so90": "reproduced",
    "ae96_aekr_gg46": "reproduced",
    "ae96_aekr_so90": "reproduced",
    "ae96_gg46_so90": "reproduced",
    "ae96_so90_gg46": "reproduced",
}


@pytest.mark.parametrize(("key", "status"), sorted(TABLE_III.items()))
def test_table_iii_of_alduchov_and_eskridge(key: str, status: str) -> None:
    relation = CATALOG.relations[key]
    assert relation.kind is RelationKind.APPROXIMATES
    assert relation.citation == "alduchov_eskridge1996"
    verdict = verify(relation, CATALOG)
    assert isinstance(verdict, Verdict)
    assert verdict.status == status
    # Where the maximum lies: the table gives whole degrees.
    for identifier, place in relation.at.items():
        assert verdict.at[identifier] == pytest.approx(place, abs=0.5)


def test_sa90_departs_from_its_published_maxima() -> None:
    gg46 = verify(CATALOG.relations["ae96_sa90_gg46"], CATALOG)
    so90 = verify(CATALOG.relations["ae96_sa90_so90"], CATALOG)
    assert gg46.value == pytest.approx(0.610, abs=5e-4)
    assert so90.value == pytest.approx(0.315, abs=5e-4)


def test_the_table_compares_formulas_as_given() -> None:
    # With conversion of temperature scales, Buck (1981) no longer matches.
    relation = dataclasses.replace(CATALOG.relations["ae96_bu81_so90"], scale="convert")
    verdict = verify(relation, CATALOG)
    assert verdict.status == "exceeded"
    assert verdict.value == pytest.approx(1.494, abs=5e-4)
    assert "scale convert" in verdict.method


BASE = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[formulations.eq2]
label = "Refractivity from dry pressure"
expression = "k1 * P_d / T + k2 * e / T + k3 * e / T ** 2"
fixed_units = true
output = { identifier = "N", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "P_d", kind = "Pressure", unit = "HectoPA", description = "dry pressure" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "vapour pressure" },
  { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "temperature" },
]
coefficients = { k1 = 77.6, k2 = 72, k3 = 3.75e5 }

[formulations.eq6]
label = "Refractivity from total pressure"
expression = "k1 * P / T - k4 * e / T + k3 * e / T ** 2"
fixed_units = true
output = { identifier = "N", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "P", kind = "Pressure", unit = "HectoPA", description = "pressure" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "vapour pressure" },
  { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "temperature" },
]
coefficients = { k1 = 77.6, k3 = 3.75e5, k4 = 5.6 }

[formulations.eq7]
label = "Approximate refractivity"
expression = "k1 / T * (P + k5 * e / T)"
fixed_units = true
output = { identifier = "N", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "P", kind = "Pressure", unit = "HectoPA", description = "pressure" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "vapour pressure" },
  { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "temperature" },
]
coefficients = { k1 = 77.6, k5 = 4810 }

[formulations.logs]
label = "Sum of logarithms"
expression = "log10(x) + log10(y)"
fixed_units = true
output = { identifier = "z", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "x", kind = "RelativeHumidity", unit = "UNITLESS", description = "x" },
  { identifier = "y", kind = "RelativeHumidity", unit = "UNITLESS", description = "y" },
]

[formulations.log_product]
label = "Logarithm of a product"
expression = "log10(x * y)"
fixed_units = true
output = { identifier = "z", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "x", kind = "RelativeHumidity", unit = "UNITLESS", description = "x" },
  { identifier = "y", kind = "RelativeHumidity", unit = "UNITLESS", description = "y" },
]
"""

RELATION = """
[relations.r]
kind = "equivalent"
subject = "{subject}"
object = "{object}"
citation = "src"
{extra}
"""


def relation(subject: str, other: str, extra: str = "") -> tuple[Relation, object]:
    loaded = load_catalog(
        [BASE + RELATION.format(subject=subject, object=other, extra=extra)]
    )
    return loaded.relations["r"], loaded


def test_equivalence_given_a_relation_between_inputs_is_proven() -> None:
    found, loaded = relation("eq6", "eq2", 'given = { P_d = "P - e" }')
    verdict = verify(found, loaded)  # type: ignore[arg-type]
    assert verdict.status == "proven"
    assert "exact rationals" in verdict.method


def test_an_approximation_is_refuted_as_an_equivalence() -> None:
    bounds = "bounds = { P = [500.0, 1100.0], e = [0.0, 50.0], T = [220.0, 320.0] }"
    found, loaded = relation("eq7", "eq6", bounds)
    verdict = verify(found, loaded)  # type: ignore[arg-type]
    assert verdict.status == "refuted"
    assert set(verdict.at) == {"P", "e", "T"}
    assert verdict.detail is not None
    assert "e" in verdict.detail


def test_an_equivalence_sympy_cannot_settle_stays_unproven() -> None:
    found, loaded = relation("log_product", "logs")
    verdict = verify(found, loaded)  # type: ignore[arg-type]
    assert verdict.status == "unproven"
    assert verdict.detail is not None


@pytest.mark.parametrize(
    ("subject", "other", "extra", "message"),
    [
        ("nope", "eq2", "", "unknown formulation 'nope'"),
        ("eq6", "logs", "", "inputs of logs matching no input of eq6: x, y"),
        ("eq6", "eq2", 'given = { x = "P" }', "'x' is not an input of eq2"),
        ("eq6", "eq2", 'given = { P_d = "P - q" }', "given.P_d"),
        ("eq6", "eq2", "accuracy = 0.1", "accuracy: only for an approximation"),
        ("eq6", "eq2", 'scale = "maybe"', "expected convert or ignore"),
        ("eq6", "eq2", "at = { x = 1.0 }", "'x' is not an input of eq6"),
    ],
)
def test_invalid_relations_are_refused(
    subject: str, other: str, extra: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        relation(subject, other, extra)


APPROXIMATION = """
[relations.a]
kind = "approximates"
subject = "eq7"
object = "eq6"
citation = "src"
{extra}
"""


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("accuracy = 0.02", "states its accuracy and bounds every input of eq7"),
        ("accuracy = 0.02\nbounds = { P = [500.0, 1100.0] }", "bounds every input"),
        (
            (
                "accuracy = 0.02\n"
                "bounds = { P = [500.0, 1100.0], e = [0.0, 50.0], T = [220.0, 320.0] }\n"
                'given = { P = "P" }'
            ),
            "given: only for an equivalence",
        ),
    ],
)
def test_invalid_approximations_are_refused(extra: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([BASE + APPROXIMATION.format(extra=extra)])


def test_the_citation_of_a_relation_must_be_a_reference() -> None:
    bounds = "bounds = { P = [500.0, 1100.0], e = [0.0, 50.0], T = [220.0, 320.0] }"
    document = BASE + APPROXIMATION.format(extra=f"accuracy = 0.02\n{bounds}").replace(
        'citation = "src"', 'citation = "nope"'
    )
    with pytest.raises(CatalogError, match="unknown reference 'nope'"):
        load_catalog([document])


PRESSURE = """
[formulations.pressure]
label = "A pressure"
expression = "2 * P"
fixed_units = true
output = { identifier = "q", kind = "Pressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "P", kind = "Pressure", unit = "HectoPA", description = "pressure" }]
"""


def test_outputs_of_different_kinds_are_refused() -> None:
    document = (
        BASE + PRESSURE + RELATION.format(subject="eq6", object="pressure", extra="")
    )
    with pytest.raises(
        CatalogError, match="eq6 computes RelativeHumidity, pressure computes Pressure"
    ):
        load_catalog([document])


def test_a_relation_belongs_to_a_family_requiring_its_formulations() -> None:
    header = '[catalog]\nname = "{name}"\nformat = 2\nrequires = [{requires}]\n'
    formulas = header.format(name="formulas", requires="") + BASE
    claims = header.format(name="claims", requires="") + RELATION.format(
        subject="eq6", object="eq2", extra='given = { P_d = "P - e" }'
    )
    with pytest.raises(
        CatalogError, match="relations.r uses formulations.eq2 from family formulas"
    ):
        load_catalog([formulas, claims])
    fixed = claims.replace("requires = []", 'requires = ["formulas"]')
    assert load_catalog([formulas, fixed]).relations["r"].subject == "eq6"


PEAK = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[formulations.plane]
label = "A plane"
expression = "x + y + z + 3"
fixed_units = true
output = { identifier = "w", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "x", kind = "RelativeHumidity", unit = "UNITLESS", description = "x" },
  { identifier = "y", kind = "RelativeHumidity", unit = "UNITLESS", description = "y" },
  { identifier = "z", kind = "RelativeHumidity", unit = "UNITLESS", description = "z" },
]

[formulations.peak]
label = "The plane with a narrow bump of 1 %"
expression = "(x + y + z + 3) * (1 + 0.01 * exp(-((x - 0.3) ** 2 + (y - 0.6) ** 2 + (z - 0.45) ** 2) / 0.002))"
fixed_units = true
output = { identifier = "w", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "x", kind = "RelativeHumidity", unit = "UNITLESS", description = "x" },
  { identifier = "y", kind = "RelativeHumidity", unit = "UNITLESS", description = "y" },
  { identifier = "z", kind = "RelativeHumidity", unit = "UNITLESS", description = "z" },
]

[relations.bump]
kind = "approximates"
subject = "peak"
object = "plane"
citation = "src"
accuracy = 1.0
bounds = { x = [0.0, 1.0], y = [0.0, 1.0], z = [0.0, 1.0] }
"""


def test_refinement_finds_an_interior_maximum_in_three_variables() -> None:
    loaded = load_catalog([PEAK])
    verdict = verify(loaded.relations["bump"], loaded)
    # The grid alone (58 points per axis) peaks near 0.9 %; the refinement
    # reaches the maximum itself.
    assert verdict.value == pytest.approx(1.0, abs=1e-6)
    assert dict(verdict.at) == pytest.approx({"x": 0.3, "y": 0.6, "z": 0.45}, abs=1e-4)
    assert verdict.status == "reproduced"
    assert "grid of 58 points per axis (3 input(s))" in verdict.method


def test_points_per_axis_follow_the_number_of_inputs() -> None:
    assert [per_axis(d) for d in range(1, 8)] == [9001, 447, 58, 21, 11, 7, 5]
    assert per_axis(1, budget=101) == 101
