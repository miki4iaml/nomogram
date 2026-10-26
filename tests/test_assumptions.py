# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the assumptions of formulations, stated or noted."""

import math

import numpy as np
import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.model import AssumptionStatus, Formulation
from nomogram.units import Q_

CATALOG = catalog()

SOURCE = """
[references.src]
authors = "A."
title = "T"
status = "verified"

[references.other]
authors = "B."
title = "U"
status = "verified"
"""


def entry(assumptions: str = "", cited: str = "") -> str:
    """A formulation with assumptions, written for a test."""
    return f"""
[formulations.d]
label = "d"
expression = "p - e"
fixed_units = false
output = {{ identifier = "p_d", kind = "Pressure", unit = "PA", description = "p_d" }}
inputs = [
  {{ identifier = "p", kind = "Pressure", unit = "PA", description = "p" }},
  {{ identifier = "e", kind = "VapourPressure", unit = "PA", description = "e" }},
]
{assumptions}
[[formulations.d.citations]]
reference = "src"
{cited}
"""


def load(document: str) -> Formulation:
    return load_catalog([SOURCE + document]).formulations["d"]


# --- The model -------------------------------------------------------------------


def test_stated_assumptions_come_first_then_the_noted_ones() -> None:
    f = load(
        entry(
            "assumptions = [\n"
            '  { text = "Ideal gases.", status = "stated-by-other", reference = "other" },\n'
            '  { text = "Dry air of fixed composition.", status = "suspected" },\n'
            "]",
            'assumptions = ["Partial pressures add up."]',
        )
    )
    found = [(a.text, a.status, a.reference) for a in f.assumptions]
    assert found == [
        ("Partial pressures add up.", AssumptionStatus.STATED, "src"),
        ("Ideal gases.", AssumptionStatus.STATED_BY_OTHER, "other"),
        ("Dry air of fixed composition.", AssumptionStatus.SUSPECTED, None),
    ]
    markdown = f.render().markdown
    assert "- Partial pressures add up. (stated by src)" in markdown
    assert "(stated by other, not by the sources of the formula)" in markdown
    assert "(suspected by nomogram, to be checked)" in markdown
    found_by_search = load_catalog(
        [
            SOURCE
            + entry('assumptions = [{ text = "Ideal gases.", status = "deduced" }]')
        ]
    ).search(assumption="ideal gas*")
    assert [x.key for x in found_by_search.formulations] == ["d"]


@pytest.mark.parametrize(
    ("assumptions", "cited", "message"),
    [
        (
            'assumptions = [{ text = "A.", status = "stated" }]',
            "",
            "goes in its citation",
        ),
        ('assumptions = [{ text = "A.", status = "guessed" }]', "", "expected one of"),
        (
            'assumptions = [{ text = "A.", status = "stated-by-other" }]',
            "",
            "only for, an assumption stated by another source",
        ),
        (
            'assumptions = [{ text = "A.", status = "deduced", reference = "other" }]',
            "",
            "only for, an assumption stated by another source",
        ),
        ('assumptions = [{ text = " ", status = "deduced" }]', "", "non-empty strings"),
        ('assumptions = { text = "A.", status = "deduced" }', "", "expected a list"),
        ("", "assumptions = [3]", "non-empty strings"),
    ],
)
def test_malformed_assumptions_are_refused(
    assumptions: str, cited: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load(entry(assumptions, cited))


# --- The catalog -------------------------------------------------------------------


def test_the_ifs_states_constant_specific_heats_of_water_and_ice() -> None:
    for key, phase in (
        ("ecmwf_ifs_latent_heat_vaporization", "liquid water"),
        ("ecmwf_ifs_latent_heat_sublimation", "ice"),
    ):
        stated, deduced = CATALOG.formulations[key].assumptions
        assert stated.status is AssumptionStatus.STATED
        assert stated.reference == "ecmwf_ifs_cy49r1"
        assert f"specific heat of {phase} is taken as constant" in stated.text
        assert deduced.status is AssumptionStatus.DEDUCED
        assert "c_pv = 4 R_v" in deduced.text


def test_murray_is_tetens_in_kelvins_with_0_degc_at_273_16_k() -> None:
    # A = 7.5 ln 10 and B = 273.16 - 237.3: Tetens with t = T - 273.16 K.
    murray = CATALOG.formulations["murray1967"]
    tetens = CATALOG.formulations["tetens1930"]
    values = {c.identifier: c.value for c in murray.coefficients}
    assert values["A"] == pytest.approx(7.5 * math.log(10), abs=1e-6)
    assert values["B"] == pytest.approx(273.16 - 237.3)
    temperatures = np.array([253.16, 273.16, 293.16, 313.16])
    ratio = (
        murray.evaluate(T=Q_(temperatures, "K"), scale="ignore").magnitude
        / tetens.evaluate(t=Q_(temperatures - 273.16, "degC"), scale="ignore").magnitude
    )
    assert ratio == pytest.approx(np.full(4, 6.1078 / 6.11))
    # Its C is the value of Goff and Gratch at 273.16 K, their 0 degC.
    goff_gratch = CATALOG.formulations["goff_gratch1946"]
    at_t0 = goff_gratch.evaluate(T=Q_(273.16, "K"), scale="ignore").to("hPa")
    assert at_t0.magnitude == pytest.approx(values["C"], abs=5e-5)
    (assumption,) = murray.assumptions
    assert assumption.status is AssumptionStatus.DEDUCED
    assert "273.16 K" in assumption.text
    assert "triple point" not in values_note(murray, "T_0")


def values_note(formulation: Formulation, identifier: str) -> str:
    (coefficient,) = (c for c in formulation.coefficients if c.identifier == identifier)
    return coefficient.note or ""


def test_leaving_out_the_enhancement_factor_lowers_e_as_stated() -> None:
    # 1/f - 1 with the enhancement factor of WMO-No. 8 (4.B.5), which holds
    # around 1000 hPa only.
    f = CATALOG.formulations["wmo_enhancement_factor"]
    low, high = (
        1 / float(f.evaluate(p=Q_(p, "hPa")).magnitude) - 1 for p in (1000.0, 1100.0)
    )
    assert (round(low * 100, 2), round(high * 100, 2)) == (-0.47, -0.5)
    found = {
        f.key for f in CATALOG.search(assumption="enhancement factor").formulations
    }
    assert found == {
        "mass_concentration_ideal_gas",
        "vapour_pressure_from_relative_humidity",
    }
    assert "0.47 % at 1000 hPa and 0.50 % at 1100 hPa" in (
        CATALOG.formulations["mass_concentration_ideal_gas"].assumptions[1].text
    )


def test_a_composition_holds_under_the_assumptions_of_its_parts() -> None:
    # L_f = L_s - L_v from two IFS latent heats, each with constant specific
    # heats: the difference assumes them too.
    fusion = CATALOG.formulations["ecmwf_ifs_latent_heat_fusion"]
    assert not fusion.citations
    texts = [a.text for a in fusion.assumptions]
    assert len(texts) == len(set(texts)) == 3
    assert any("specific heat of ice" in t for t in texts)
    found = CATALOG.search(assumption="specific heat of ice").refs
    assert "formulations.ecmwf_ifs_latent_heat_fusion" in found


def test_the_source_of_an_assumption_is_linked_and_searched() -> None:
    # 4.A.11 of WMO-No. 8, stated by another source than the one cited.
    key = "formulations.mass_concentration_ideal_gas"
    f = CATALOG.formulations["mass_concentration_ideal_gas"]
    assert "wmo2024" not in f.references
    assert "references.wmo2024" in CATALOG.uses(key).refs
    assert key in CATALOG.used_by("references.wmo2024").refs
    assert key in CATALOG.search(source="wmo2024").refs
