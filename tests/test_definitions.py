# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for definitions, identities and formulations derived by nomogram."""

import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog, stats
from nomogram.model import FormulationNature
from nomogram.units import Q_

CATALOG = catalog()
IDENTITY = CATALOG.formulations["latent_heat_fusion_identity"]
DERIVED = CATALOG.formulations["ecmwf_ifs_latent_heat_fusion"]

SOURCE = """
[references.src]
authors = "A."
title = "T"
status = "verified"
"""


def ratio(extra: str = "", nature: str = 'nature = "definition"') -> str:
    """A Dalton-like definition, written for a test."""
    return f"""
[formulations.d]
label = "d"
{nature}
expression = "p - e"
fixed_units = false
output = {{ identifier = "p_d", kind = "Pressure", unit = "PA", description = "p_d" }}
inputs = [
  {{ identifier = "p", kind = "Pressure", unit = "PA", description = "p" }},
  {{ identifier = "e", kind = "VapourPressure", unit = "PA", description = "e" }},
]
{extra}
[[formulations.d.citations]]
reference = "src"
"""


def load(document: str) -> object:
    return load_catalog([SOURCE + document]).formulations["d"]


# --- Definitions and identities --------------------------------------------------


def test_the_latent_heat_of_fusion_is_an_identity_cited_where_printed() -> None:
    assert IDENTITY.nature is FormulationNature.IDENTITY
    assert IDENTITY.conditions is not None
    assert "same temperature" in IDENTITY.conditions
    assert [(c.reference, c.equation) for c in IDENTITY.citations] == [
        ("bechtold2015", "40"),
        ("ambaum2020", None),
    ]
    assert not IDENTITY.derived
    l_s, l_v = Q_(2.8345e6, "J/kg"), Q_(2.5008e6, "J/kg")
    assert IDENTITY.evaluate(L_s=l_s, L_v=l_v).to("J/kg").magnitude == pytest.approx(
        333700.0
    )


def test_a_definition_is_stated_as_such() -> None:
    f = load(ratio('conditions = "In the same volume."'))
    assert f.nature is FormulationNature.DEFINITION  # type: ignore[attr-defined]
    markdown = f.render().markdown  # type: ignore[attr-defined]
    assert "A definition: true by definition." in markdown
    assert "Conditions: In the same volume." in markdown


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (ratio(nature='nature = "law"'), "unknown nature 'law'"),
        (
            ratio("coefficients = { k = 1.0 }").replace("p - e", "k * p - e"),
            "no empirical coefficient",
        ),
        (
            ratio().replace("fixed_units = false", "fixed_units = true"),
            "fixed_units = false",
        ),
        (ratio("conditions = 3"), "expected a string"),
        (
            ratio()
            + """
[[formulations.d.citations.domains]]
bounds = { p = [0.0, 1.0e5] }
""",
            "without a stated domain",
        ),
    ],
)
def test_what_a_definition_cannot_have(document: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load(document)


# --- Formulations derived by nomogram -----------------------------------------------


def test_the_ifs_latent_heat_of_fusion_is_derived_from_its_latent_heats() -> None:
    assert DERIVED.derived
    assert DERIVED.nature is None
    assert not DERIVED.citations
    assert DERIVED.derivation is not None
    assert DERIVED.derivation.source == "latent_heat_fusion_identity"
    # L_s0 - L_v0 at the triple point, then c_l - c_s per kelvin.
    t = Q_([273.16, 263.16], "K")
    values = DERIVED.evaluate(T=t).to("J/kg").magnitude
    assert values == pytest.approx([333700.0, 333700.0 - 2112.0 * 10])
    sublimation = CATALOG.formulations["ecmwf_ifs_latent_heat_sublimation"]
    vaporization = CATALOG.formulations["ecmwf_ifs_latent_heat_vaporization"]
    expected = sublimation.evaluate(T=t) - vaporization.evaluate(T=t)
    assert values == pytest.approx(expected.to("J/kg").magnitude)


def test_the_legend_says_what_nomogram_derived() -> None:
    assert "Derived by nomogram: no source prints this formulation." in (
        DERIVED.render().markdown
    )
    identity = IDENTITY.render().markdown
    assert "An identity: an exact consequence of definitions." in identity
    assert "Derived by nomogram" not in identity


def test_definitions_and_derived_formulations_are_found() -> None:
    identities = CATALOG.search(nature="identity").formulations
    assert [f.key for f in identities] == [IDENTITY.key]
    derived = {f.key for f in CATALOG.search(provenance="derived").formulations}
    assert DERIVED.key in derived
    assert IDENTITY.key not in derived
    cited = {f.key for f in CATALOG.search(provenance="cited").formulations}
    assert IDENTITY.key in cited
    assert DERIVED.key not in cited
    assert IDENTITY.key in {f.key for f in CATALOG.search("identity").formulations}
    melting = "ambaum2020_latent_heat_fusion"
    names = [f.key for f in CATALOG.formulations_of("SpecificLatentHeatOfFusion")]
    assert names == [melting, IDENTITY.key, DERIVED.key]


def test_the_indicators_count_the_formulations_derived_by_nomogram() -> None:
    line = next(x for x in stats(CATALOG).splitlines() if "derived by nomogram" in x)
    count, _ = line.rsplit(": ", 1)[1].split(" of ")
    assert int(count) >= 1
