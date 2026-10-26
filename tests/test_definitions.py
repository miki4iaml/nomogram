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
    identities = {f.key for f in CATALOG.search(nature="identity").formulations}
    assert IDENTITY.key in identities
    assert all(
        CATALOG.formulations[k].nature is FormulationNature.IDENTITY for k in identities
    )
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


# --- WMO-No. 8, Annex 4.A ------------------------------------------------------------


def test_the_wmo_defines_the_vapour_pressure_of_moist_air() -> None:
    # e' = x_v p, with x_v = r / (0.62198 + r) (4.A.5, 4.A.6).
    f = CATALOG.formulations["wmo_vapour_pressure_definition"]
    assert f.nature is FormulationNature.DEFINITION
    assert [(c.reference, c.equation) for c in f.citations] == [("wmo2024", "4.A.6")]
    e = f.evaluate(r=Q_(0.01, "kg/kg"), p=Q_(1000.0, "hPa")).to("hPa").magnitude
    assert e == pytest.approx(0.01 * 1000.0 / (0.62198 + 0.01))


def test_the_relative_humidities_of_the_wmo_are_definitions() -> None:
    water = CATALOG.formulations["wmo_relative_humidity"]
    ice = CATALOG.formulations["wmo_relative_humidity_ice"]
    for f in (water, ice):
        assert f.nature is FormulationNature.DEFINITION
        assert f.fixed_units  # printed as 100 e'/e'_w, in %
        assert f.conditions is not None
        assert "same pressure and temperature" in f.conditions
    assert [c.equation for c in water.citations] == ["4.B.10", "4.A.15"]
    assert [c.equation for c in ice.citations] == ["4.A.17"]
    rh = ice.evaluate(e=Q_(1.0, "hPa"), e_is=Q_(1.25, "hPa")).to("percent")
    assert rh.magnitude == pytest.approx(80.0)
    # Over ice, a sibling of the relative humidity, which QUDT defines over
    # water: never an alternative of it, found with it under their parent.
    assert ice.output.kind == "RelativeHumidityWithRespectToIce"
    assert ice not in CATALOG.formulations_of("RelativeHumidity")
    found = {f.key for f in CATALOG.search(kind="RelativeHumidity").formulations}
    assert water.key in found
    assert ice.key not in found
    found = {f.key for f in CATALOG.search(kind="RelativePartialPressure").formulations}
    assert {water.key, ice.key} <= found


def test_the_other_definitions_of_annex_4a() -> None:
    def value(key: str, **inputs: object) -> float:
        result = CATALOG.formulations[key].evaluate(**inputs)  # type: ignore[arg-type]
        return float(result.magnitude)

    m_v, m_a = Q_(0.01, "kg"), Q_(1.0, "kg")
    assert value("wmo_mixing_ratio_definition", m_v=m_v, m_a=m_a) == pytest.approx(0.01)
    assert value("wmo_specific_humidity_definition", m_v=m_v, m_a=m_a) == (
        pytest.approx(0.01 / 1.01)
    )
    assert value(
        "wmo_vapour_concentration_definition", m_v=m_v, V=Q_(2.0, "m^3")
    ) == pytest.approx(0.005)
    n = Q_(1.0, "mol")
    assert value("wmo_mole_fraction_definition", n_v=n, n_a=3 * n) == (
        pytest.approx(0.25)
    )
    r = Q_(0.01, "kg/kg")
    x_v = value("wmo_mole_fraction_from_mixing_ratio", r=r)
    assert x_v == pytest.approx(0.01 / 0.63198)
    assert value(
        "wmo_saturation_vapour_pressure_water_definition",
        r_w=Q_(0.015, "kg/kg"),
        p=Q_(1000.0, "hPa"),
    ) == pytest.approx(15.0 / 0.63698)
    natures = {
        CATALOG.formulations[k].nature
        for k in (
            "wmo_mole_fraction_from_mixing_ratio",
            "wmo_relative_humidity_from_mixing_ratios",
        )
    }
    assert natures == {FormulationNature.IDENTITY}


def test_the_wmo_relative_humidity_is_not_100_r_over_r_w() -> None:
    # 4.A.16: 100 r (0.62198 + r_w) / (r_w (0.62198 + r)), not 100 r / r_w.
    f = CATALOG.formulations["wmo_relative_humidity_from_mixing_ratios"]
    rh = f.evaluate(r=Q_(0.01, "kg/kg"), r_w=Q_(0.015, "kg/kg")).to("percent")
    expected = 100 * 0.01 * (0.62198 + 0.015) / (0.015 * (0.62198 + 0.01))
    assert rh.magnitude == pytest.approx(expected)
    assert rh.magnitude != pytest.approx(100 * 0.01 / 0.015, rel=1e-3)


def test_the_two_forms_of_4a6_are_proven_equivalent() -> None:
    from nomogram.relations import verify

    relation = CATALOG.relations["wmo_vapour_pressure_two_forms"]
    assert relation.computed
    assert verify(relation, CATALOG).status == "proven"


def test_the_wmo_states_how_far_e_w_may_stand_for_e_prime_w() -> None:
    found = CATALOG.formulations["vapour_pressure_from_relative_humidity"].assumptions
    stated = [a for a in found if a.reference == "wmo2024"]
    assert len(stated) == 1
    assert "within 0.5 %" in stated[0].text


def test_the_mixing_ratio_over_its_saturation_value_is_not_the_wmo_relative_humidity() -> (
    None
):
    # TEOS-10 calls r / r_sat the WMO relative humidity; WMO-No. 8 (4.A.16)
    # writes the mole fraction ratio in mixing ratios, which differs.
    ratio = CATALOG.formulations["teos10_relative_mass_ratio_of_vapour"]
    wmo = CATALOG.formulations["wmo_relative_humidity_from_mixing_ratios"]
    r, r_w = Q_(0.010, "kg/kg"), Q_(0.020, "kg/kg")
    assert ratio.output.kind == "RelativeMassRatioOfVapour"
    assert ratio.evaluate(r=r, r_w=r_w).magnitude == pytest.approx(0.5)
    expected = 100 * 0.010 * (0.62198 + 0.020) / (0.020 * (0.62198 + 0.010))
    assert wmo.evaluate(r=r, r_w=r_w).magnitude == pytest.approx(expected)
    assert expected > 50.7
    # At saturation both give saturation.
    assert ratio.evaluate(r=r_w, r_w=r_w).magnitude == pytest.approx(1)
    assert wmo.evaluate(r=r_w, r_w=r_w).magnitude == pytest.approx(100)
