# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for relations between formulations, and their verification."""

import dataclasses
from pathlib import Path

import pytest
import sympy

from nomogram.catalog import CatalogError, catalog, check, load_catalog
from nomogram.model import Relation, RelationKind
from nomogram.relations import (
    Verdict,
    _common_bounds,
    match_inputs,
    per_axis,
    report,
    verify,
)

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


PASCALS = """
[formulations.eq2_pa]
label = "Refractivity from dry pressure in pascals"
expression = "k1 * P_d / T + k2 * e / T + k3 * e / T ** 2"
fixed_units = true
output = { identifier = "N", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "P_d", kind = "Pressure", unit = "PA", description = "dry pressure" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "vapour pressure" },
  { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "temperature" },
]
coefficients = { k1 = 0.776, k2 = 72, k3 = 3.75e5 }

[formulations.eq2_percent]
label = "Refractivity from dry pressure, in percent"
expression = "k1 * P_d / T + k2 * e / T + k3 * e / T ** 2"
fixed_units = true
output = { identifier = "N", kind = "RelativeHumidity", unit = "PERCENT", description = "out" }
inputs = [
  { identifier = "P_d", kind = "Pressure", unit = "HectoPA", description = "dry pressure" },
  { identifier = "e", kind = "VapourPressure", unit = "PA", description = "vapour pressure" },
  { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "temperature" },
]
coefficients = { k1 = 7760, k2 = 72, k3 = 3.75e7 }
"""


@pytest.mark.parametrize(
    ("other", "message"),
    [
        ("eq2_pa", "P_d in PA fed by P in HectoPA; P_d in PA fed by e in HectoPA"),
        ("eq2_percent", "output in UNITLESS and PERCENT; e in PA fed by e in HectoPA"),
    ],
)
def test_an_equivalence_needs_the_same_units(other: str, message: str) -> None:
    extra = 'given = { P_d = "P - e" }'
    document = (
        BASE + PASCALS + RELATION.format(subject="eq6", object=other, extra=extra)
    )
    with pytest.raises(CatalogError, match="proved on the expressions as written"):
        load_catalog([document])
    with pytest.raises(CatalogError, match=message):
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


def test_inputs_are_matched_by_identifier_then_by_a_single_kind() -> None:
    loaded = load_catalog([BASE])
    eq2, eq6 = loaded.formulations["eq2"], loaded.formulations["eq6"]
    # e and T by identifier; P_d by its kind, P being the only pressure.
    assert match_inputs(eq6, eq2) == {"P_d": "P", "e": "e", "T": "T"}
    second = dataclasses.replace(eq6.inputs[0], identifier="P_0")
    # Two pressures could feed P_d: it is left without match.
    assert match_inputs(
        dataclasses.replace(eq6, inputs=(*eq6.inputs, second)), eq2
    ) == {"e": "e", "T": "T"}
    celsius = dataclasses.replace(
        eq6.inputs[2], identifier="t", kind="CelsiusTemperature", unit="DEG_C"
    )
    # A Celsius temperature feeds a thermodynamic one.
    assert match_inputs(
        dataclasses.replace(eq6, inputs=(*eq6.inputs[:2], celsius)), eq2
    ) == {"P_d": "P", "e": "e", "T": "t"}


def pressure_formulation(
    key: str, expression: str, *, input: str = "P", fixed_units: bool = True
) -> str:
    """A formulation of a pressure from a pressure, written for a test."""
    return f"""
[formulations.{key}]
label = "{key}"
expression = "{expression}"
fixed_units = {str(fixed_units).lower()}
output = {{ identifier = "q", kind = "Pressure", unit = "PA", description = "out" }}
inputs = [{{ identifier = "{input}", kind = "Pressure", unit = "HectoPA", description = "pressure" }}]
"""


def equivalence(subject: str, other: str, extra: str = "") -> str:
    return RELATION.format(subject=subject, object=other, extra=extra)


def test_an_input_matched_by_kind_is_replaced_in_an_equivalence() -> None:
    document = (
        BASE
        + pressure_formulation("square", "(P + 1) ** 2")
        + pressure_formulation("expanded", "Q ** 2 + 2 * Q + 1", input="Q")
        + equivalence("square", "expanded")
    )
    loaded = load_catalog([document])
    assert verify(loaded.relations["r"], loaded).status == "proven"


@pytest.mark.parametrize(
    ("other", "status"),
    [
        # 2 P in hPa is 200 P in Pa: equal results.
        ("doubled_value", "proven"),
        # The same text with fixed units gives results 100 times smaller.
        ("doubled_raw", "refuted"),
    ],
)
def test_an_equivalence_compares_results_in_the_output_unit(
    other: str, status: str
) -> None:
    document = (
        BASE
        + pressure_formulation("doubled_quantity", "2 * P", fixed_units=False)
        + pressure_formulation("doubled_value", "200 * P")
        + pressure_formulation("doubled_raw", "2 * P")
        + equivalence("doubled_quantity", other)
    )
    loaded = load_catalog([document])
    assert loaded.formulations["doubled_quantity"].output_factor != 1.0
    assert verify(loaded.relations["r"], loaded).status == status


SCALED = """
[scales.ref]
label = "Reference scale"
kinds = ["CelsiusTemperature"]

[scales.old]
label = "Old scale"
kinds = ["CelsiusTemperature"]
reference_scale = "ref"
unit = "DEG_C"
differences = [[0.0, 0.0], [400.0, 0.1]]
"""


def celsius_formulation(key: str, expression: str, scale: str | None) -> str:
    """A formulation of a pressure from a Celsius temperature, for a test."""
    on = f', scale = "{scale}", scale_basis = "inferred-from-date"' if scale else ""
    return f"""
[formulations.{key}]
label = "{key}"
expression = "{expression}"
fixed_units = true
output = {{ identifier = "q", kind = "Pressure", unit = "PA", description = "out" }}
inputs = [{{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in"{on} }}]
"""


@pytest.mark.parametrize(
    ("subject", "extra", "status", "method"),
    [
        ("old_square", "", "unverified", "t on ref fed by t on old"),
        ("old_square", 'scale = "ignore"', "proven", "scales ignored: t on ref"),
        # No scale and the reference scale are evaluated alike.
        ("plain_square", "", "proven", "exact rationals"),
    ],
)
def test_an_equivalence_with_conversion_needs_the_same_scales(
    subject: str, extra: str, status: str, method: str
) -> None:
    document = (
        BASE
        + SCALED
        + celsius_formulation("old_square", "(t + 300) ** 2", "old")
        + celsius_formulation("plain_square", "t * (t + 600) + 90000", None)
        + celsius_formulation("ref_square", "t ** 2 + 600 * t + 90000", "ref")
        + equivalence(subject, "ref_square", extra)
    )
    loaded = load_catalog([document])
    verdict = verify(loaded.relations["r"], loaded)
    assert verdict.status == status
    assert method in verdict.method
    assert (subject == "old_square") == ("scale" in verdict.method)


LOGARITHMS = """
[formulations.log_sum]
label = "Sum of logarithms of pressures"
expression = "ln(P - e) + ln(P)"
fixed_units = true
output = { identifier = "z", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "P", kind = "Pressure", unit = "HectoPA", description = "pressure" },
  { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "vapour pressure" },
]

[formulations.log_of_product]
label = "Logarithm of a product of pressures"
expression = "ln(P_d * P)"
fixed_units = true
output = { identifier = "z", kind = "RelativeHumidity", unit = "UNITLESS", description = "out" }
inputs = [
  { identifier = "P_d", kind = "Pressure", unit = "HectoPA", description = "dry pressure" },
  { identifier = "P", kind = "Pressure", unit = "HectoPA", description = "pressure" },
]
"""


@pytest.mark.parametrize(
    ("bounds", "method"),
    [
        # P - e < 0 on part of the samples: those are left aside.
        ("", "samples real and finite"),
        ("bounds = { P = [0.5, 1.0], e = [1.5, 2.0] }", "none of 200 samples"),
    ],
)
def test_samples_where_a_side_is_not_real_are_left_aside(
    bounds: str, method: str
) -> None:
    extra = 'given = { P_d = "P - e" }\n' + bounds
    document = BASE + LOGARITHMS + equivalence("log_sum", "log_of_product", extra)
    loaded = load_catalog([document])
    verdict = verify(loaded.relations["r"], loaded)
    assert verdict.status == "unproven"
    assert method in verdict.method


ROOTED = """
[formulations.square]
label = "square"
expression = "(P + 1) ** 2"
fixed_units = true
output = { identifier = "q", kind = "Pressure", unit = "PA", description = "out" }
inputs = [{ identifier = "P", kind = "Pressure", unit = "HectoPA", description = "pressure" }]

[formulations.rooted]
label = "rooted"
expression = "(P + 1) ** 2 + sqrt(P - 2000)"
fixed_units = true
output = { identifier = "q", kind = "Pressure", unit = "PA", description = "out" }
inputs = [{ identifier = "P", kind = "Pressure", unit = "HectoPA", description = "pressure" }]
"""

ROOTED_RELATION = """
[relations.a]
kind = "approximates"
subject = "rooted"
object = "square"
citation = "src"
accuracy = 1.0
"""


def test_an_approximation_finite_nowhere_is_unverified() -> None:
    document = BASE + ROOTED + ROOTED_RELATION + "bounds = { P = [500.0, 1100.0] }\n"
    loaded = load_catalog([document])
    verdict = verify(loaded.relations["a"], loaded)
    assert verdict.status == "unverified"
    assert verdict.value is None
    assert "no point" in verdict.method


def test_an_approximation_finite_on_part_of_its_domain_says_so() -> None:
    document = BASE + ROOTED + ROOTED_RELATION + "bounds = { P = [500.0, 2500.0] }\n"
    loaded = load_catalog([document])
    verdict = verify(loaded.relations["a"], loaded)
    assert verdict.status == "held"
    assert verdict.value is not None
    assert 0 < verdict.value < 1
    assert verdict.at["P"] >= 2000
    assert "deviation finite on 25.01 % of the grid only" in verdict.method


def test_a_report_says_which_pairs_it_could_not_compare() -> None:
    document = (
        BASE
        + ROOTED
        + pressure_formulation("rooted_twice", "(P + 1) ** 2 + 2 * sqrt(P - 2000)")
        + "[[formulations.rooted.domains]]\nbounds = { P = [500.0, 1100.0] }\n"
        + "[[formulations.rooted_twice.domains]]\nbounds = { P = [500.0, 2500.0] }\n"
    )
    loaded = load_catalog([document])
    text = report(loaded, ["rooted", "rooted_twice"], budget=1000)
    assert (
        "not compared with square: no point of the common domain where both "
        "give a finite value"
    ) in text
    assert "numerically identical" not in text
    assert "% of the common domain only)" in text


def test_a_report_compares_where_both_sources_state_validity() -> None:
    square = ROOTED.split("[formulations.rooted]")[0]
    document = (
        BASE
        + square
        + pressure_formulation("cubed", "(P + 1) ** 2 + P ** 3 / 1e9")
        + "[[formulations.square.domains]]\nbounds = { P = [0.0, 100000.0] }\n"
        + '[[formulations.square.citations]]\nreference = "src"\n'
        + "[[formulations.square.citations.domains]]\n"
        + "bounds = { P = [500.0, 1100.0] }\n"
        + '[[formulations.cubed.citations]]\nreference = "src"\n'
        + "[[formulations.cubed.citations.domains]]\nbounds = { P = [0.0, 2000.0] }\n"
    )
    loaded = load_catalog([document])
    square_f, cubed = loaded.formulations["square"], loaded.formulations["cubed"]
    # The physical domain of square is wider than what its source states.
    assert _common_bounds(cubed, square_f) == {"P": (500.0, 1100.0)}
    assert _common_bounds(square_f, cubed) == {"P": (500.0, 1100.0)}
    assert "from square: " in report(loaded, ["cubed"], budget=1000)
    assert "at P = 1100" in report(loaded, ["cubed"], budget=1000)


def test_a_report_skips_scales_it_cannot_convert() -> None:
    folder = Path(__file__).parents[1] / "src" / "nomogram" / "data" / "catalog"
    text = check(folder / "sea-water.toml")
    assert (
        "raoult_sharqawy2010 (RelativeVapourPressureOfSeaWater)\n"
        "  not compared with nayar2016_vapour_pressure_ratio: nomogram holds no "
        "conversion of absolute_salinity2010 to the reference scale"
    ) in text
    assert "observed max deviation from dickson2007_vapour_pressure" in text


def test_an_isolated_finite_point_stays_the_best_found() -> None:
    # Finite only at P = 4500, a point of the grid (9001 integers): the
    # refinement around it finds no finite value and keeps it.
    isolated = pressure_formulation(
        "isolated", "(P + 1) ** 2 + sqrt(P - 4500) + sqrt(4500 - P)"
    )
    document = (
        BASE
        + ROOTED.split("[formulations.rooted]")[0]
        + isolated
        + ROOTED_RELATION.replace('subject = "rooted"', 'subject = "isolated"')
        + "bounds = { P = [0.0, 9000.0] }\n"
    )
    loaded = load_catalog([document])
    verdict = verify(loaded.relations["a"], loaded)
    assert verdict.status == "held"
    assert verdict.at["P"] == 4500.0
    assert "of the grid only" in verdict.method


def test_an_equivalence_with_outputs_on_different_scales_is_unverified() -> None:
    def on(key: str, expression: str, scale: str) -> str:
        return f"""
[formulations.{key}]
label = "{key}"
expression = "{expression}"
fixed_units = true
output = {{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "out", scale = "{scale}", scale_basis = "inferred-from-date" }}
inputs = [{{ identifier = "P", kind = "Pressure", unit = "HectoPA", description = "pressure" }}]
"""

    document = (
        BASE
        + SCALED
        + on("old_out", "2 * P", "old")
        + on("ref_out", "(P + 1) ** 2 - P ** 2 - 1", "ref")
        + equivalence("old_out", "ref_out")
    )
    loaded = load_catalog([document])
    verdict = verify(loaded.relations["r"], loaded)
    assert verdict.status == "unverified"
    assert "output on old and ref" in verdict.method


def test_exact_rationals_and_real_values() -> None:
    from nomogram.relations import _exact, _real

    assert _exact(0.001) == sympy.Rational(1, 1000)
    # Beyond the denominators tried, the float's own decimal fraction.
    assert _exact(1e-30) == sympy.Rational(1, 10**30)
    x, y = sympy.symbols("x y", real=True)
    assert _real(2 * x, {x: 1.5}) == 3.0
    assert _real(x + y, {x: 1.0}) is None  # not a number
    assert _real(sympy.exp(x), {x: 1000.0}) is None  # not finite
    assert _real(sympy.sqrt(x), {x: -4.0}) is None  # not real
