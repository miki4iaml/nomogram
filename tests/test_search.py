# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.search`: words, wildcards, fields, links."""

import pytest

from nomogram.catalog import catalog, load_catalog
from nomogram.search import FIELDS, SECTIONS, Entry, Selection, fold, symbol_form, words

CATALOG = catalog()


def refs(selection: Selection) -> set[str]:
    return set(selection.refs)


# --- Words and symbols --------------------------------------------------


def test_fold_drops_case_accents_and_names_greek_letters() -> None:
    assert fold("Équation") == "equation"
    assert fold("ρ") == fold(r"\rho") == fold("Rhô") == "rho"
    assert fold("Ω ϕ ς µ") == "omega phi sigma mu"


def test_symbol_form() -> None:
    assert symbol_form(r"\rho_{\mathrm{v}}") == "rho_v"
    assert symbol_form("ρ_v") == symbol_form("rho_v") == "rho_v"
    assert symbol_form(r"p_{\mathrm{ws}}") == "p_ws"
    assert symbol_form("e'_w") == "e_prime_w"
    assert symbol_form("T^*") == "t_*"


def test_words_split_identifiers_and_keep_them_whole() -> None:
    found = words("SaturationVapourPressureOverWater itu_r_p453_es_water P.453-14")
    assert {"saturation", "vapour", "pressure", "over", "water"} <= found
    assert "saturationvapourpressureoverwater" in found
    assert {"itu_r_p453_es_water", "itu", "p453", "es"} <= found
    assert {"p.453-14", "453", "14"} <= found
    assert words("IAPWSFormulation") >= {"iapws", "formulation"}
    assert words(r"\varphi khi") >= {"varphi", "phi", "khi", "chi"}
    assert words(" , ... ") == frozenset()
    assert words("trailing_") == {"trailing_", "trailing"}


# --- Searches on the bundled catalog -------------------------------------


def test_terms_are_wildcards_matched_against_words() -> None:
    assert refs(CATALOG.search("buck*", section="formulations")) == {
        "formulations.buck1981",
        "formulations.buck1981_magnus",
        "formulations.buck1981_ice",
        "formulations.buck1996",
        "formulations.buck1996_ice",
    }
    assert refs(CATALOG.search("absolute", "humidity")) == {
        "kinds.AbsoluteHumidity",
        "trade_terms.absolute_humidity",
    }
    assert "kinds.Altitude" in CATALOG.search("Q190200").refs  # a Wikidata item
    assert "references.itu_r_p453_14" in (CATALOG.search("*453*", section="ref*")).refs


def test_every_section_is_searchable() -> None:
    for section in SECTIONS:
        assert CATALOG.search(section=section), section


def test_kind_with_and_without_specializations() -> None:
    kinds = refs(CATALOG.search(kind="VapourPressure", section="kinds"))
    assert {"kinds.VapourPressure", "kinds.SaturationVapourPressureOverWater"} <= kinds
    exact = CATALOG.search(kind="VapourPressure", specializations=False)
    assert "formulations.itu_r_p453_vapour_pressure" in exact.refs
    assert "formulations.buck1996" not in exact.refs
    assert "formulations.buck1996" in (CATALOG.search(kind="VapourPressure")).refs
    assert "formulations.buck1996" in (CATALOG.search(kind="SaturationVapour*")).refs


def test_variables_whatever_their_notation() -> None:
    expected = {
        "formulations.mass_concentration_ideal_gas",
        "formulations.itu_r_p453_vapour_pressure_from_density",
    }
    for pattern in ("rho*", "ρ*", r"\rho*", "rhô*"):
        assert refs(CATALOG.search(variable=pattern)) == expected, pattern
    assert refs(CATALOG.search(variable=r"\rho_{\mathrm{v}}")) == {
        "formulations.mass_concentration_ideal_gas"
    }
    assert (
        "formulations.itu_r_p453_vapour_pressure"
        in (CATALOG.search(input="relative humidity")).refs
    )
    assert (
        "formulations.itu_r_p453_es_water"
        in (CATALOG.search(output="saturation vapour pressure")).refs
    )
    # Coefficients and constants are variables too.
    assert (
        "formulations.mixing_ratio_from_vapour_pressure"
        in (CATALOG.search(variable="epsilon")).refs
    )
    assert "formulations.buck1996" in (CATALOG.search(variable="D")).refs


def test_symbols_in_a_given_notation() -> None:
    ashrae = CATALOG.search(symbol="φ", notation="ashrae", section="formulations")
    assert "formulations.vapour_pressure_from_relative_humidity" in ashrae.refs
    assert not CATALOG.search(symbol="phi", notation="wmo")
    # P.453 writes a, b, c, d for the coefficients of Buck.
    p453 = CATALOG.search(symbol="d", notation="itu_r_p453_es_*")
    assert refs(p453) == {
        "formulations.itu_r_p453_es_water",
        "formulations.itu_r_p453_es_ice",
    }
    assert "notations.wmo" in (CATALOG.search(notation="wmo")).refs


def test_every_symbol_finds_itself_as_its_notation_writes_it() -> None:
    for key, formulation in CATALOG.formulations.items():
        notations = [c.notation for c in formulation.citations if c.notation]
        notations += CATALOG.notations.values()
        identifiers = [
            formulation.output.identifier,
            *(v.identifier for v in formulation.inputs),
            *(c.identifier for c in formulation.coefficients),
            *(k.identifier for k in formulation.constants),
        ]
        for notation in notations:
            for identifier in identifiers:
                tex = notation.symbols.get(identifier)
                if tex is None:
                    continue
                ref = f"formulations.{key}"
                found = CATALOG.search(symbol=tex, notation=notation.key)
                assert ref in found.refs, (notation.key, tex)
                assert ref in CATALOG.search(variable=tex).refs, (notation.key, tex)


def test_a_symbol_with_a_space_is_found_whole_or_by_its_parts() -> None:
    # Dickson writes the total molality \Sigma m_{\mathrm{B}}.
    expected = {
        "formulations.dickson2007_total_molality",
        "formulations.dickson2007_osmotic_coefficient",
        "formulations.vapour_pressure_from_osmotic_coefficient",
    }
    for pattern in (r"\Sigma m_{\mathrm{B}}", "Σ m_B", "Σm_B", "m_B"):
        assert refs(CATALOG.search(symbol=pattern)) == expected, pattern
    assert refs(CATALOG.search(variable=r"\Sigma m_{\mathrm{B}}")) == expected


def test_a_citation_notation_answers_to_its_reference_key() -> None:
    dickson = CATALOG.search(symbol="Σm_B", notation="dickson2007")
    assert "formulations.dickson2007_total_molality" in dickson.refs
    full = "dickson2007_total_molality:dickson2007"
    assert "formulations.dickson2007_total_molality" in (
        CATALOG.search(symbol="Σm_B", notation=full).refs
    )
    assert not CATALOG.search(symbol="Σm_B", notation="dickson2007_total_molality")
    assert not CATALOG.search(symbol="Σm_B", notation="wmo")


def test_units_and_scales_are_found_by_their_symbols() -> None:
    from nomogram.semantics import semantic_catalog

    for name, unit in semantic_catalog().units.items():
        if unit.symbol:
            assert f"units.{name}" in CATALOG.search(unit.symbol).refs, unit.symbol
    for key, scale in CATALOG.scales.items():
        if scale.symbol:
            assert f"scales.{key}" in CATALOG.search(scale.symbol).refs, scale.symbol
    assert refs(CATALOG.search("°C")) >= {"units.DEG_C"}
    assert "units.GM-PER-KiloGM" in CATALOG.search("g/kg").refs
    assert "units.PERCENT" in CATALOG.search("%").refs


def test_source_and_equation_in_the_same_citation() -> None:
    nine = CATALOG.search(source="itu_r_p453*", equation="9")
    assert "formulations.itu_r_p453_es_water" in nine.refs
    assert "formulations.itu_r_p453_vapour_pressure" not in nine.refs
    assert (
        "relations.itu_r_p453_total_pressure_form"
        in (CATALOG.search(source="itu_r_p453*", section="relations")).refs
    )
    assert "formulations.buck1996" in (CATALOG.search(source="buck*")).refs


def test_family_keyword_and_key() -> None:
    radio = CATALOG.search(family="radio", section="formulations")
    assert "formulations.itu_r_p453_refractivity" in radio.refs
    assert "kinds.RadioRefractivity" in (CATALOG.search(family="radio")).refs
    assert "families.radio" in (CATALOG.search(keyword="refractivity")).refs
    assert "formulations.buck1996" in (CATALOG.search(key="buck1996")).refs


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(TypeError, match="unknown search field"):
        CATALOG.search(colour="blue")
    assert set(FIELDS) >= {"kind", "variable", "symbol", "source"}


# --- Links ---------------------------------------------------------------


def test_uses_and_used_by() -> None:
    parts = refs(CATALOG.uses("formulations.itu_r_p453_es_water"))
    assert {
        "formulations.buck1996",
        "formulations.itu_r_p453_ef_water",
        "references.itu_r_p453_14",
    } <= parts
    citing = CATALOG.used_by("references.itu_r_p453_14")
    assert "relations.itu_r_p453_total_pressure_form" in citing.refs
    built_on_buck = CATALOG.used_by("formulations.buck1996") & CATALOG.search(
        source="itu_r_p453*"
    )
    assert refs(built_on_buck) == {"formulations.itu_r_p453_es_water"}
    entry = CATALOG.search(key="radio", section="families")[0]
    assert refs(CATALOG.uses(entry)) == {"families.moist-air"}
    assert "families.radio" in (CATALOG.used_by("families.moist-air")).refs
    assert (
        "cross_checks.itu_rpy_p453"
        in (CATALOG.used_by("formulations.itu_r_p453_refractivity")).refs
    )
    with pytest.raises(KeyError, match="no entry"):
        CATALOG.uses("formulations.nope")
    with pytest.raises(KeyError, match="no entry"):
        CATALOG.used_by("nope")


# --- Selections ----------------------------------------------------------


def test_selections_combine_and_chain() -> None:
    water = CATALOG.search(family="water-vapour", section="formulations")
    buck = CATALOG.search("buck*")
    assert set((water & buck).refs) <= set(water.refs)
    assert len(water | buck) == len(set(water.refs) | set(buck.refs))
    assert not set((water - buck).refs) & set(buck.refs)
    assert water.search("buck*").refs == (water & buck).refs
    with pytest.raises(TypeError):
        _ = water & 3
    with pytest.raises(TypeError):
        _ = water | 3
    with pytest.raises(TypeError):
        _ = water - 3
    # A union keeps the order of the catalog.
    order = list(CATALOG.search().refs)
    tail = CATALOG.search(section="formulations")[-3:]
    union = (tail | buck).refs
    assert list(union) == sorted(union, key=order.index)
    assert set(union) == set(tail.refs) | set(buck.refs)
    other = load_catalog([])
    with pytest.raises(ValueError, match="different catalogs"):
        _ = water & Selection((), other)


def test_selection_behaves_as_a_sequence() -> None:
    found = CATALOG.search("buck*", section="formulations")
    assert isinstance(found[0], Entry)
    assert isinstance(found[1:3], Selection)
    assert len(found[1:3]) == 2
    assert [e.key for e in found] == [e.key for e in found.entries]
    assert "formulations.buck1996" in found  # type: ignore[comparison-overlap]
    assert found[0] in found
    assert 3 not in found  # type: ignore[comparison-overlap]
    assert all(f.key.startswith("buck") for f in found.formulations)
    assert repr(found).startswith("Selection(5 entries: formulations.buck1981_magnus")
    assert repr(found[:2]).endswith("formulations.buck1981)")
    assert found[0].ref == "formulations.buck1981_magnus"


def test_selection_displays_as_a_table() -> None:
    formulas = CATALOG.search("buck1996")
    assert (
        "| Formulation | Equation |"
        in formulas.search(section="formulations").to_markdown()
    )
    mixed = CATALOG.search("buck1996")
    assert "| `references.buck1996` |" in mixed.to_markdown()
    assert mixed._repr_markdown_() == mixed.to_markdown()
    assert CATALOG.search("nothing-matches-this").to_markdown().count("\n") == 2


def test_entries_without_a_reference_are_indexed() -> None:
    document = """
[notations.plain]
label = "Plain"
symbols = { t = "\\\\theta" }

[formulations.f]
label = "Test formulation"
expression = "a * t"
fixed_units = true
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 2.0 }
"""
    loaded = load_catalog([document])
    assert refs(loaded.search(symbol="theta", section="formulations")) == {
        "formulations.f"
    }
    assert "notations.plain" in (loaded.search("plain")).refs
    assert not loaded.uses("formulations.f").search(section="references")


def test_a_symbol_part_without_letters_adds_no_word() -> None:
    from nomogram.search import _symbol_words

    # "{}" has an empty normal form: only "m" and the whole count.
    assert _symbol_words("m {}") == frozenset({"m"})
