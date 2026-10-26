# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.catalog`: bundled content and validation."""

import datetime

import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog, main, stats
from nomogram.model import ConstantNature, ReferenceStatus, UnitBasis
from nomogram.semantics import MatchRelation
from nomogram.units import Q_

CATALOG = catalog()

VALID = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[formulations.f]
label = "Test formulation"
expression = "a * t"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 2.0 }
"""


def test_catalog_is_read_once() -> None:
    assert catalog() is CATALOG


def test_kind_defined_by_nomogram() -> None:
    kind = CATALOG.kinds["SaturationVapourPressureOverWater"]
    assert kind.origin == "nomogram"
    assert kind.iri is None
    assert kind.specialization_of == "SaturationVapourPressure"
    assert kind.applicable_units == CATALOG.kinds["VapourPressure"].applicable_units
    assert kind.matches[0].relation is MatchRelation.BROAD
    assert CATALOG.kinds["VapourPressure"].origin == "qudt"
    # Over water or over ice, or over each on one side of a temperature.
    parent = CATALOG.kinds["SaturationVapourPressure"]
    assert parent.specialization_of == "VapourPressure"
    assert parent.matches[0].relation is MatchRelation.CLOSE
    assert CATALOG.kinds["SaturationVapourPressureOverIce"].specialization_of == (
        "SaturationVapourPressure"
    )


def test_formulations_are_grouped_by_computed_kind() -> None:
    keys = [f.key for f in CATALOG.formulations_of("SaturationVapourPressureOverWater")]
    assert set(keys) == {
        "iapws_sr1_86",
        "sonntag1990",
        "sonntag1990_magnus",
        "alduchov_eskridge1996",
        "tetens1930",
        "buck1981",
        "buck1981_magnus",
        "hyland_wexler1983",
        "bolton1980",
        "murray1967",
        "buck1996",
        "goff_gratch1946",
        "goff1957",
        "bechtold2015_saturation_vapour_pressure_constant_latent_heat",
        "bechtold2015_magnus_water",
        "ambaum2020",
        "ambaum2020_constant_latent_heat",
        "metpy171_saturation_vapour_pressure",
    }


def test_references_carry_their_verification_status() -> None:
    assert CATALOG.references["iapws95"].status is ReferenceStatus.VERIFIED
    assert CATALOG.references["sonntag1990"].status is ReferenceStatus.TO_CONFIRM
    assert CATALOG.references["sonntag1990"].note


def test_constant_and_its_source() -> None:
    r_v = CATALOG.constants["R_v_iapws95"]
    assert (r_v.identifier, r_v.value, r_v.unit) == ("R_v", 461.51805, "J-PER-KiloGM-K")
    assert r_v.reference == "iapws95"
    assert r_v.matches[0].verified == datetime.date(2026, 10, 14)


def test_trade_term_points_to_unambiguous_kinds() -> None:
    term = CATALOG.trade_terms["absolute_humidity"]
    assert [m.kind for m in term.meanings] == [
        "MassConcentrationOfWaterVapour",
        "MassRatioOfWaterVapourToDryGas",
    ]
    assert term.meanings[0].sources == ("ams_glossary",)


def test_relative_humidity_has_three_meanings() -> None:
    term = CATALOG.trade_terms["relative_humidity"]
    assert [m.kind for m in term.meanings] == [
        "RelativeHumidity",
        "RelativeHumidity",
        "RelativeMassRatioOfVapour",
    ]
    assert [m.sources for m in term.meanings] == [
        ("wmo2024", "teos10_manual"),
        ("teos10_manual", "bechtold2015"),
        ("teos10_manual",),
    ]
    assert "relative_humidity" in [
        e.key for e in CATALOG.search("relative humidity", section="trade_terms")
    ]


def test_minimal_valid_document() -> None:
    loaded = load_catalog([VALID])
    formulation = loaded.formulations["f"]
    assert formulation.coefficients[0].unit is None
    assert loaded.formulations_of("VapourPressure") == (formulation,)


def test_a_dew_point_may_be_given_in_kelvins() -> None:
    # CF and the IFS give the dew point in K, empirical formulas in degC.
    document = (
        VALID.replace("a * t", "t - a")
        .replace(
            'identifier = "e", kind = "VapourPressure", unit = "HectoPA"',
            'identifier = "T_d", kind = "DewPointTemperature", unit = "K"',
        )
        .replace(
            'identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C"',
            'identifier = "t", kind = "ThermodynamicTemperature", unit = "K"',
        )
    )
    f = load_catalog([document]).formulations["f"]
    dew_point = f.evaluate(t=Q_(293.15, "K"))
    assert f.output.kind == "DewPointTemperature"
    assert dew_point.to("degC").magnitude == pytest.approx(18.0)


def test_documents_are_merged() -> None:
    other = '[references.other]\nauthors = "B"\ntitle = "T"\nstatus = "verified"\n'
    assert set(load_catalog([VALID, other]).references) == {"src", "other"}


def replace(old: str, new: str) -> str:
    assert old in VALID
    return VALID.replace(old, new)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("a = [", "invalid TOML"),
        ("[nothing.x]\n", "unknown sections: nothing"),
        (replace('status = "verified"', 'status = "maybe"'), "is not one of"),
        (
            replace('label = "Test formulation"', 'surplus = "x"'),
            "unknown keys: surplus",
        ),
        (replace('label = "Test formulation"\n', ""), "missing keys: label"),
        (
            replace('expression = "a * t"', 'expression = "a * t * b"'),
            "undeclared name",
        ),
        (
            replace('expression = "a * t"', 'expression = "t"'),
            "declared but not used: a",
        ),
        (replace('reference = "src"', 'reference = "nope"'), "unknown reference"),
        (replace('unit = "HectoPA"', 'unit = "NOPE"'), "unknown unit"),
        (
            replace('unit = "DEG_C"', 'unit = "K"'),
            "K does not apply to CelsiusTemperature",
        ),
        (replace('kind = "VapourPressure"', 'kind = "Nope"'), "unknown kind"),
        (replace('identifier = "e"', 'identifier = "t"'), "declared twice: t"),
        (
            replace("[formulations.f]", "[formulations.f]\nconstants = ['c']"),
            "unknown constant",
        ),
        (replace('label = "Test formulation"', "label = 1\n[x]"), "unknown sections"),
    ],
)
def test_invalid_documents_are_refused(document: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([document])


def test_entry_defined_twice_is_refused() -> None:
    with pytest.raises(CatalogError, match="defined twice: src"):
        load_catalog(
            [
                VALID,
                '[references.src]\nauthors = "B"\ntitle = "T"\nstatus = "verified"\n',
            ]
        )


DOMAIN = """
[[formulations.f.domains]]
{extra}bounds = {{ {name} = [{low}, {high}] }}
"""


@pytest.mark.parametrize(
    ("extra", "name", "low", "high", "message"),
    [
        ("", "x", 0, 1, "'x' is not an input"),
        ("", "t", 1, 0, "empty interval"),
        # A domain stated by a source belongs to its citation.
        ('basis = "stated"\n', "t", 0, 1, "unknown keys: basis"),
    ],
)
def test_invalid_domains_are_refused(
    extra: str, name: str, low: float, high: float, message: str
) -> None:
    domain = DOMAIN.format(extra=extra, name=name, low=low, high=high)
    with pytest.raises(CatalogError, match=message):
        load_catalog([VALID + domain])


QUANTITY = """
[constants.k]
identifier = "k"
value = 2.0
unit = "J-PER-KiloGM-K"
description = "constant"
reference = "src"
nature = "conventional"

[formulations.q]
label = "Quantity equation"
expression = "e / (k * T)"
fixed_units = false
output = {{ identifier = "rho", kind = "MassConcentrationOfWaterVapour", unit = "{unit}", description = "out" }}
inputs = [
  {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "in" }},
  {{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "in" }},
]
constants = ["k"]
"""


def test_quantity_equation_gets_its_unit_factor() -> None:
    loaded = load_catalog([VALID + QUANTITY.format(unit="GM-PER-M3")])
    # hPa / (J kg-1 K-1 * K) = 100 kg/m3 = 100 000 g/m3.
    assert loaded.formulations["q"].output_factor == pytest.approx(1e5)


def test_dimensionally_inconsistent_equation_is_refused() -> None:
    document = VALID + QUANTITY.format(unit="GM-PER-M3").replace(
        'expression = "e / (k * T)"', 'expression = "e / (k * T * T)"'
    )
    with pytest.raises(CatalogError, match="not dimensionally homogeneous"):
        load_catalog([document])


def test_bad_matches_are_refused() -> None:
    bad_date = replace(
        'status = "verified"',
        'status = "verified"\nmatches = [{ target = "x", relation = "exact", verified = "today" }]',
    )
    with pytest.raises(CatalogError, match="expected a date"):
        load_catalog([bad_date])
    bad_relation = bad_date.replace('"today"', "2026-10-14").replace(
        '"exact"', '"same"'
    )
    with pytest.raises(CatalogError, match="is not one of exact"):
        load_catalog([bad_relation])


@pytest.mark.parametrize(
    ("expression", "coefficients", "message"),
    [
        ("a * b * t", "{ a = 2.0, b = 3.0 }", "does not determine the unit of a, b"),
        (
            "c * exp(a * t / (b + t))",
            (
                '{ a = 1.0, b = { value = 2.0, unit = "HectoPA", unit_basis = "added", '
                'note = "x" }, c = 3.0 }'
            ),
            r"units contradict the expression, in b \+ t",
        ),
    ],
)
def test_every_coefficient_needs_a_unit_declared_or_inferred(
    expression: str, coefficients: str, message: str
) -> None:
    document = replace('expression = "a * t"', f'expression = "{expression}"').replace(
        "coefficients = { a = 2.0 }", f"coefficients = {coefficients}"
    )
    with pytest.raises(CatalogError, match=message):
        load_catalog([document])


NOTATION = """
[notations.n]
label = "A notation"
symbols = {{ e = '{symbol}' }}
"""


def test_notation_symbols_stay_within_the_common_latex_subset() -> None:
    accepted = load_catalog([VALID + NOTATION.format(symbol=r"E_{\mathrm{w}}")])
    assert accepted.notations["n"].symbols["e"] == r"E_{\mathrm{w}}"
    with pytest.raises(CatalogError, match=r"notations.n.symbols.e: .*\\textrm"):
        load_catalog([VALID + NOTATION.format(symbol=r"E_{\textrm{w}}")])


KIND = """
[kinds.{name}]
label = "Local kind"
specialization_of = "{parent}"
"""


@pytest.mark.parametrize(
    ("name", "parent", "message"),
    [
        ("VapourPressure", "Pressure", "already a QUDT kind"),
        ("Local", "Nope", "unknown kind 'Nope'"),
    ],
)
def test_invalid_kinds_are_refused(name: str, parent: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([KIND.format(name=name, parent=parent)])


def test_a_local_kind_may_declare_an_interval_scale() -> None:
    document = KIND.format(name="Modified", parent="DimensionlessRatio")
    kind = load_catalog([document + 'scale_type = "interval"\n']).kinds["Modified"]
    assert kind.scale_type.value == "interval"
    assert kind.delta is False
    assert load_catalog([document]).kinds["Modified"].scale_type.value == "ratio"
    with pytest.raises(CatalogError, match="is not one of"):
        load_catalog([document + 'scale_type = "ordinal"\n'])


def test_a_local_kind_may_carry_cf_standard_names() -> None:
    assert CATALOG.kinds["VirtualTemperature"].cf_standard_names == (
        "virtual_temperature",
    )
    assert CATALOG.kinds["DensityOfMoistAir"].cf_standard_names == ("air_density",)
    assert CATALOG.kinds["VirtualPotentialTemperature"].cf_standard_names == ()
    for kind, name in [
        ("MoleFractionOfWaterVapour", "mole_fraction_of_water_vapor_in_air"),
        ("SeaWaterSalinity", "sea_water_salinity"),
        ("SurfaceAltitude", "surface_altitude"),
    ]:
        assert CATALOG.kinds[kind].cf_standard_names == (name,)
    document = KIND.format(name="Local", parent="ThermodynamicTemperature")
    with pytest.raises(CatalogError, match="not in the frozen CF subset: no_such_name"):
        load_catalog([document + 'cf_standard_names = ["no_such_name"]\n'])


def test_table_expected() -> None:
    with pytest.raises(CatalogError, match="expected a table"):
        load_catalog(["[formulations]\nf = 1\n"])


def test_coefficient_with_unit_and_note() -> None:
    document = replace(
        "coefficients = { a = 2.0 }",
        'coefficients = { a = { value = 2.0, unit = "K", unit_basis = "added", '
        'note = "difference" } }',
    ).replace('expression = "a * t"', 'expression = "t * exp(a / t)"')
    coefficient = load_catalog([document]).formulations["f"].coefficients[0]
    assert (coefficient.value, coefficient.unit, coefficient.note) == (
        2.0,
        "K",
        "difference",
    )
    assert coefficient.unit_basis is UnitBasis.ADDED


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ('{ value = 2.0, unit = "K" }', 'needs unit_basis: "added" \\(with a note\\)'),
        ('{ value = 2.0, unit = "K", unit_basis = "stated" }', "goes in its citation"),
        (
            '{ value = 2.0, unit = "K", unit_basis = "added" }',
            "added unit needs a note",
        ),
        ('{ value = 2.0, unit_basis = "stated" }', "unit_basis without a unit"),
        ('{ value = 2.0, unit = "K", unit_basis = "guessed" }', "is not one of"),
    ],
)
def test_declared_units_say_where_they_come_from(table: str, message: str) -> None:
    document = replace(
        "coefficients = { a = 2.0 }", f"coefficients = {{ a = {table} }}"
    )
    document = document.replace('expression = "a * t"', 'expression = "t * exp(a / t)"')
    with pytest.raises(CatalogError, match=message):
        load_catalog([document])


def test_catalog_declares_only_units_inference_cannot_give() -> None:
    origins = {
        (f.key, name): unit.origin
        for f in CATALOG.formulations.values()
        for name, unit in f.coefficient_units.items()
        if unit.origin != "inferred"
    }
    assert origins == {
        ("iapws_sr1_86", "T_c"): "stated",
        ("iapws_sr1_86", "p_c"): "stated",
        ("iapws_r14_08_sublimation", "T_t"): "stated",
        ("iapws_r14_08_sublimation", "p_t"): "stated",
        ("goff_gratch1946", "e_st"): "added",
        ("goff_gratch1946_ice", "e_i0"): "added",
        ("itu_r_p453_reference_profile", "h_0"): "stated",
        ("itu_r_p453_surface_refractivity", "h_0"): "stated",
        ("ittc2011_vapour_pressure", "T_c"): "stated",
        ("ittc2011_vapour_pressure", "p_c"): "stated",
        ("coare36_salinity_factor", "S_0"): "stated",
        ("dickson2007_total_molality", "S_1"): "added",
        ("dickson2007_osmotic_coefficient_of_salinity", "S_1"): "added",
        ("dickson2007_vapour_pressure", "S_1"): "added",
        ("dickson2007_vapour_pressure", "T_c"): "stated",
        ("dickson2007_vapour_pressure", "p_c"): "stated",
        ("ambaum2020_latent_heat_vaporization", "L_0"): "stated",
        ("ambaum2020_latent_heat_vaporization", "Delta_c"): "stated",
        ("ambaum2020_latent_heat_vaporization", "T_0"): "stated",
        ("ambaum2020_latent_heat_fusion", "L_m0"): "stated",
        ("ambaum2020_latent_heat_fusion", "c_l"): "stated",
        ("ambaum2020_latent_heat_fusion", "c_i"): "stated",
        ("ambaum2020_latent_heat_fusion", "T_0"): "stated",
        ("bechtold2015_virtual_temperature_rounded", "a"): "stated",
        (
            "bechtold2015_saturation_vapour_pressure_constant_latent_heat",
            "p_vs0",
        ): "stated",
        ("ambaum2020", "e_s0"): "stated",
        ("ambaum2020", "T_0"): "stated",
        ("ambaum2020", "Delta_c"): "stated",
        ("ambaum2020", "L_0"): "stated",
        ("ambaum2020", "R_v"): "stated",
        ("ambaum2020_constant_latent_heat", "e_s0"): "stated",
        ("ambaum2020_constant_latent_heat", "T_0"): "stated",
        ("ambaum2020_constant_latent_heat", "L_0"): "stated",
        ("ambaum2020_constant_latent_heat", "R_v"): "stated",
        ("ambaum2020_ice", "e_i0"): "stated",
        ("ambaum2020_ice", "T_0"): "stated",
        ("ambaum2020_ice", "Delta_c"): "stated",
        ("ambaum2020_ice", "R_v"): "stated",
        ("ambaum2020_ice", "L_s0"): "added",
        ("metpy171_saturation_vapour_pressure", "e_s0"): "stated",
        ("metpy171_saturation_vapour_pressure", "T_0"): "stated",
        ("metpy171_psychrometric_vapour_pressure", "A"): "stated",
        (
            "metpy171_psychrometric_vapour_pressure",
            "e_s0__metpy171_saturation_vapour_pressure",
        ): "stated",
        (
            "metpy171_psychrometric_vapour_pressure",
            "T_0__metpy171_saturation_vapour_pressure",
        ): "stated",
        ("ashrae2017_mixing_ratio_from_wet_bulb", "A"): "added",
        ("ashrae2017_mixing_ratio_from_wet_bulb", "B"): "added",
        ("ashrae2017_mixing_ratio_from_wet_bulb", "C"): "added",
        ("ashrae2017_mixing_ratio_from_wet_bulb", "D"): "added",
        ("ashrae2017_mixing_ratio_from_wet_bulb", "E"): "added",
        ("ashrae2017_mixing_ratio_from_ice_bulb", "A"): "added",
        ("ashrae2017_mixing_ratio_from_ice_bulb", "B"): "added",
        ("ashrae2017_mixing_ratio_from_ice_bulb", "C"): "added",
        ("ashrae2017_mixing_ratio_from_ice_bulb", "D"): "added",
        ("ashrae2017_mixing_ratio_from_ice_bulb", "E"): "added",
    }


def test_coefficient_table_without_unit() -> None:
    document = replace(
        "coefficients = { a = 2.0 }", "coefficients = { a = { value = 2.0 } }"
    )
    assert load_catalog([document]).formulations["f"].coefficients[0].unit is None


def test_catalog_guide_example_matches_the_catalog() -> None:
    import re
    import tomllib
    from importlib.resources import files
    from pathlib import Path

    guide = Path(__file__).parents[1] / "docs" / "catalog.md"
    block = re.search(
        r"```toml\n(.*?)```", guide.read_text(encoding="utf-8"), re.DOTALL
    )
    assert block is not None
    example = tomllib.loads(block.group(1))["formulations"]["alduchov_eskridge1996"]
    bundled_text = (
        files("nomogram") / "data" / "catalog" / "water-vapour.toml"
    ).read_text(encoding="utf-8")
    bundled = tomllib.loads(bundled_text)["formulations"]["alduchov_eskridge1996"]
    for key, value in example.items():
        assert bundled[key] == value, key


def test_a_scale_short_name_and_subscript() -> None:
    its90 = CATALOG.scales["its90"]
    assert (its90.symbol, its90.subscript) == ("ITS-90", "90")
    assert CATALOG.scales["ipts68"].subscript == "68"
    document = """
[scales.s]
label = "A scale"
kinds = ["CelsiusTemperature"]
symbol = "XYZ-1"
subscript = "x"
"""
    # The short name is searchable, even when the label does not hold it.
    assert load_catalog([document]).search("XYZ-1").refs == ("scales.s",)
    with pytest.raises(CatalogError, match="subscript: expected a non-empty string"):
        load_catalog([document.replace('subscript = "x"', "subscript = 3")])


# --- Numbers, relations and cross-checks ------------------------------------

SECTIONS = """
[formulations.g]
label = "Another test formulation"
expression = "b * t"
fixed_units = true
citations = [{{ reference = "src" }}]
output = {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }}
inputs = [{{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }}]
coefficients = {{ b = 2.01 }}

[relations.r]
kind = "approximates"
subject = "g"
object = "f"
citation = "src"
accuracy = {accuracy}
at = {{ t = {at} }}
bounds = {{ t = {bounds} }}

[cross_checks.x]
implementation = "Other"
version = "1.0"
checked = 2026-10-21
cases = [{{ formulation = "f", inputs = {{ t = {input} }}, value = {value} }}]

[scales.s0]
label = "Reference scale"
kinds = ["CelsiusTemperature"]

[scales.s1]
label = "Older scale"
kinds = ["CelsiusTemperature"]
reference_scale = "s0"
unit = "DEG_C"
differences = {differences}
"""

GOOD = {
    "accuracy": "1.0",
    "at": "10.0",
    "bounds": "[0.0, 10.0]",
    "input": "5.0",
    "value": "10.0",
    "differences": "[[0.0, 0.0], [10.0, 0.01]]",
}


def sections(**changes: str) -> str:
    return VALID + SECTIONS.format(**(GOOD | changes))


def test_a_malformed_given_names_the_relation() -> None:
    document = sections().replace(
        'citation = "src"\naccuracy', 'citation = "src"\ngiven = [1]\naccuracy', 1
    )
    with pytest.raises(CatalogError, match=r"relations\.r\.given: expected a table"):
        load_catalog([document])


@pytest.mark.parametrize(
    ("written", "message"),
    [
        ("bounds = { t = [0.0, 10.0] }", r"relations\.r\.bounds: expected a table"),
        ("at = { t = 10.0 }", r"relations\.r\.at: expected a table"),
    ],
)
def test_relation_bounds_and_at_are_tables(written: str, message: str) -> None:
    key = written.split(" = ")[0]
    with pytest.raises(CatalogError, match=message):
        load_catalog([sections().replace(written, f"{key} = 3", 1)])


def test_relations_cross_checks_and_scale_tables_load() -> None:
    loaded = load_catalog([sections()])
    assert loaded.relations["r"].accuracy == 1.0
    assert dict(loaded.relations["r"].at) == {"t": 10.0}
    assert loaded.cross_checks["x"].cases[0].value == 10.0
    assert loaded.scales["s1"].difference == (0.0, 0.01)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        # A negative or zero accuracy could only ever be exceeded.
        ({"accuracy": "-2.0"}, r"relations\.r\.accuracy: expected a positive"),
        ({"accuracy": "0.0"}, r"relations\.r\.accuracy: expected a positive"),
        ({"accuracy": "nan"}, r"relations\.r\.accuracy: expected a finite number"),
        ({"at": "50.0"}, r"relations\.r\.at\.t: 50\.0 is outside the bounds"),
        ({"at": '"high"'}, r"relations\.r\.at\.t: expected a finite number"),
        ({"bounds": "[0.0, 10.0, 20.0]"}, r"relations\.r\.bounds\.t: expected"),
        ({"bounds": "[0.0, nan]"}, r"relations\.r\.bounds\.t\[1\]: expected a finite"),
        ({"bounds": "5.0"}, r"relations\.r\.bounds\.t: expected"),
        ({"value": '"abc"'}, r"cross_checks\.x\.cases\[0\]\.value: expected a finite"),
        ({"input": "inf"}, r"cross_checks\.x\.cases\[0\]\.inputs\.t: expected"),
        (
            {"differences": '[[0.0, 0.0], ["a", 0.1]]'},
            r"scales\.s1\.differences\[1\]\[0\]: expected a finite number",
        ),
        # NaN would slip past the check that reference values increase.
        (
            {"differences": "[[0.0, 0.0], [nan, 0.1], [10.0, 0.2]]"},
            r"scales\.s1\.differences\[1\]\[0\]: expected a finite number",
        ),
        (
            {"differences": "[[0.0, nan], [10.0, 0.2]]"},
            r"scales\.s1\.differences\[0\]\[1\]: expected a finite number",
        ),
        (
            {"differences": "[[0.0, 0.0, 1.0]]"},
            r"scales\.s1\.differences\[0\]: expected \[reference value",
        ),
        ({"differences": "[]"}, r"scales\.s1\.differences: expected \[reference"),
    ],
)
def test_malformed_numbers_are_refused_with_their_place(
    changes: dict[str, str], message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([sections(**changes)])


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("a = 2.0", 'a = "2.0"', r"formulations\.f\.coefficients\.a: expected"),
        ("a = 2.0", "a = nan", r"formulations\.f\.coefficients\.a: expected"),
        (
            "a = 2.0",
            "a = { value = true }",
            r"formulations\.f\.coefficients\.a\.value: expected a finite number",
        ),
    ],
)
def test_malformed_coefficients_are_refused_with_their_place(
    old: str, new: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([replace(old, new)])


def test_a_domain_bound_must_be_a_finite_number() -> None:
    domain = DOMAIN.format(extra="", name="t", low=0, high="nan")
    with pytest.raises(CatalogError, match=r"bounds\.t\[1\]: expected a finite"):
        load_catalog([VALID + domain])


CONSTANT = """
[constants.c]
identifier = "c"
value = {value}
unit = "J-PER-KiloGM-K"
description = "constant"
reference = "src"
nature = "{nature}"
{extra}
"""


def test_bundled_constants_state_their_nature() -> None:
    natures = {k.nature for k in CATALOG.constants.values()}
    assert natures == {ConstantNature.EXACT, ConstantNature.CONVENTIONAL}
    si = [c for k, c in CATALOG.constants.items() if k.endswith("_si2019")]
    assert {c.identifier for c in si} == {"c", "h", "k", "N_A"}
    assert all(c.nature is ConstantNature.EXACT for c in si)


def test_bundled_derived_constants_link_to_their_components() -> None:
    # CODATA derives R and sigma from the defining constants of the SI.
    assert set(CATALOG.used_by("constants.k_si2019").refs) == {
        "constants.R_codata2022",
        "constants.sigma_codata2022",
    }
    # The IFS derives its gas constants from R = N k.
    assert set(CATALOG.used_by("constants.R_ecmwf_ifs").refs) == {
        "constants.R_d_ecmwf_ifs",
        "constants.R_v_ecmwf_ifs",
    }
    assert CATALOG.constants["c_pd_ecmwf_ifs"].printed == "1004.7090"


def test_a_measured_constant_keeps_its_uncertainty_and_printed_digits() -> None:
    extra = 'uncertainty = 0.0002\nconditions = "at 0 degC"'
    document = CONSTANT.format(value='"287.0500"', nature="measured", extra=extra)
    constant = load_catalog([VALID + document]).constants["c"]
    assert constant.nature is ConstantNature.MEASURED
    assert (constant.value, constant.printed) == (287.05, "287.0500")
    assert (constant.uncertainty, constant.conditions) == (0.0002, "at 0 degC")
    plain = load_catalog([VALID + CONSTANT.format(value=1.5, nature="exact", extra="")])
    assert plain.constants["c"].printed is None


@pytest.mark.parametrize(
    ("value", "nature", "extra", "message"),
    [
        ("1.0", "exact", "uncertainty = 0.1", "an exact constant has none"),
        ("1.0", "measured", "uncertainty = -0.1", "expected a positive number"),
        ("1.0", "known", "", "is not one of exact, conventional, measured"),
        ('"1,5"', "measured", "", "expected a finite decimal number"),
        ('"nan"', "measured", "", "expected a finite decimal number"),
        ('" 1.5"', "measured", "", "expected a finite decimal number"),
        ("1.0", "measured", 'conditions = ""', "expected a non-empty string"),
    ],
)
def test_invalid_constants_are_refused(
    value: str, nature: str, extra: str, message: str
) -> None:
    document = CONSTANT.format(value=value, nature=nature, extra=extra)
    with pytest.raises(CatalogError, match=message):
        load_catalog([VALID + document])


DERIVED = """
[constants.a]
identifier = "a"
value = 1.380649
unit = "UNITLESS"
description = "an exact constant"
reference = "src"
nature = "exact"

[constants.b]
identifier = "b"
value = 6.02214076e23
unit = "UNITLESS"
description = "another exact constant"
reference = "src"
nature = "exact"

[constants.R_d]
identifier = "R_d"
value = 287.0597
unit = "J-PER-KiloGM-K"
description = "gas constant of dry air"
reference = "src"
nature = "conventional"

[constants.R_v]
identifier = "R_v"
value = 461.5250
unit = "J-PER-KiloGM-K"
description = "gas constant of water vapour"
reference = "src"
nature = "conventional"

[constants.c]
identifier = "c"
unit = "{unit}"
description = "a derived constant"
reference = "src"
{fields}
"""


def derived(fields: str, unit: str = "UNITLESS") -> str:
    return VALID + DERIVED.format(unit=unit, fields=fields)


@pytest.mark.parametrize(
    "fields",
    [
        # An exact product, which floats would not reproduce exactly.
        (
            'value = 8.31446261815324e23\nnature = "exact"\n'
            'definition = "a * b"\nconstants = ["a", "b"]'
        ),
        # An exact constant prints a truncation of its definition.
        'value = 40.80262463\nnature = "exact"\ndefinition = "2 * pi ** 5 / 15"',
        # Rounded to half a unit of the last digit (the IFS ratio R_d / R_v).
        (
            'value = 0.6219808\nnature = "conventional"\n'
            'definition = "R_d / R_v"\nconstants = ["R_d", "R_v"]'
        ),
        # Within the uncertainty the source gives.
        (
            'value = 0.62198\nnature = "measured"\nuncertainty = 1e-5\n'
            'definition = "R_d / R_v"\nconstants = ["R_d", "R_v"]'
        ),
        # A source departing from its own formula, said in a note.
        (
            'value = 0.6219812\nnature = "conventional"\n'
            'definition = "R_d / R_v"\nconstants = ["R_d", "R_v"]\n'
            'tolerance = 5e-7\nnote = "The source rounds an intermediate value."'
        ),
    ],
)
def test_a_value_agrees_with_its_definition(fields: str) -> None:
    constant = load_catalog([derived(fields)]).constants["c"]
    assert constant.definition is not None


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            'value = 40.80262464\nnature = "exact"\ndefinition = "2 * pi ** 5 / 15"',
            "prints a truncation of its definition",
        ),
        (
            (
                'value = 0.6219812\nnature = "conventional"\n'
                'definition = "R_d / R_v"\nconstants = ["R_d", "R_v"]'
            ),
            "beyond half a unit of its last digit",
        ),
        # Written as text, the trailing zero counts: 0.6219810, not 0.621981.
        (
            (
                'value = "0.6219810"\nnature = "conventional"\n'
                'definition = "R_d / R_v"\nconstants = ["R_d", "R_v"]'
            ),
            "beyond half a unit of its last digit",
        ),
        (
            (
                'value = 0.6219812\nnature = "conventional"\n'
                'definition = "R_d / R_v"\nconstants = ["R_d", "R_v"]\ntolerance = 5e-7'
            ),
            "a note must say by how much and why",
        ),
        (
            'value = 1.0\ntolerance = 0.1\nnote = "n"',
            "tolerance: only with a definition",
        ),
        ('value = 1.0\nconstants = ["a"]', "constants: only with a definition"),
        (
            'value = 1.0\ndefinition = "a * x"\nconstants = ["a", "x"]',
            "unknown constant 'x'",
        ),
        (
            'value = 1.0\ndefinition = "a"\nconstants = ["a", "b"]',
            "not used by the definition: b",
        ),
        ('value = 1.0\ndefinition = "a * y"\nconstants = ["a"]', "undeclared name"),
        ('value = 1.0\ndefinition = "a"\nconstants = "a"', "a list of constant keys"),
        (
            (
                'value = 1.0\ndefinition = "a"\nconstants = ["a"]\n'
                'tolerance = -1.0\nnote = "n"'
            ),
            "tolerance: expected a positive number",
        ),
    ],
)
def test_a_definition_is_checked(fields: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([derived(fields)])


def chain(r_d: str = "287.0597") -> str:
    """The ECMWF IFS gas constants (CY49R1, section 12.5), without units."""
    constants = [
        ("N", "6.0221367e23", ""),
        ("k", "1.380658e-23", ""),
        ("M_d", "28.9644e-3", ""),
        ("R", "8.31451", 'definition = "N * k"\nconstants = ["N", "k"]'),
        ("R_d", r_d, 'definition = "R / M_d"\nconstants = ["R", "M_d"]'),
        ("c_pd", '"1004.7090"', 'definition = "7 / 2 * R_d"\nconstants = ["R_d"]'),
    ]
    return VALID + "".join(
        f'\n[constants.{key}]\nidentifier = "{key}"\nvalue = {value}\n'
        f'unit = "UNITLESS"\ndescription = "{key}"\nreference = "src"\n'
        f'nature = "conventional"\n{extra}\n'
        for key, value, extra in constants
    )


def test_a_source_may_derive_from_printed_or_unrounded_values() -> None:
    # The IFS prints R = N k = 8.31451, derives R_d = R / M_d = 287.0597
    # from the unrounded product (R / M_d gives 287.05963 with the printed
    # R), then c_pd = 7/2 R_d = 1004.7090 from the printed R_d (7/2 of the
    # unrounded R_d gives 1004.70886).
    loaded = load_catalog([chain()])
    assert loaded.constants["c_pd"].components == ("R_d",)


def test_a_value_agreeing_with_neither_evaluation_is_refused() -> None:
    message = (
        r"287\.0598 departs .* = 287\.0596318.* \(unrounded components: 287\.0596736"
    )
    with pytest.raises(CatalogError, match=message):
        load_catalog([chain(r_d="287.0598")])


def test_a_definition_names_each_component_once() -> None:
    document = derived('value = 1.0\ndefinition = "a"\nconstants = ["a", "a_bis"]') + (
        '\n[constants.a_bis]\nidentifier = "a"\nvalue = 1.0\nunit = "UNITLESS"\n'
        'description = "the same identifier"\nreference = "src"\n'
    )
    with pytest.raises(CatalogError, match="'a' names two constants"):
        load_catalog([document])


def test_a_definition_gives_the_unit_of_its_constant() -> None:
    fields = 'value = 2.0\ndefinition = "a * b"\nconstants = ["a", "b"]'
    with pytest.raises(CatalogError, match="gives 1, not"):
        load_catalog([derived(fields, unit="J-PER-KiloGM-K")])


def test_constants_cannot_define_each_other() -> None:
    document = derived('value = 1.0\ndefinition = "d"\nconstants = ["d"]') + (
        '\n[constants.d]\nidentifier = "d"\nvalue = 1.0\nunit = "UNITLESS"\n'
        'description = "d"\nreference = "src"\ndefinition = "c"\nconstants = ["c"]\n'
    )
    with pytest.raises(CatalogError, match="definitions form a cycle"):
        load_catalog([document])


def test_a_derived_constant_links_to_its_components() -> None:
    fields = (
        'value = 0.6219808\nnature = "conventional"\n'
        'definition = "R_d / R_v"\nconstants = ["R_d", "R_v"]'
    )
    loaded = load_catalog([derived(fields)])
    assert {"constants.R_d", "constants.R_v"} <= set(loaded.uses("constants.c").refs)
    assert loaded.used_by("constants.R_d").refs == ("constants.c",)


def test_a_constant_may_leave_its_nature_out() -> None:
    # Files written for 0.3 have no nature; the bundled catalog states it.
    document = CONSTANT.format(value=1.0, nature="exact", extra="").replace(
        'nature = "exact"\n', ""
    )
    assert load_catalog([VALID + document]).constants["c"].nature is None


def test_a_constant_must_be_a_finite_number() -> None:
    constant = QUANTITY.format(unit="GM-PER-M3").replace("value = 2.0", "value = inf")
    with pytest.raises(CatalogError, match=r"constants\.k\.value: expected a finite"):
        load_catalog([VALID + constant])


# --- Links ---------------------------------------------------------------


def test_uses_and_used_by_follow_the_catalog_order() -> None:
    order = {ref: i for i, ref in enumerate(CATALOG.search().refs)}
    targets = {t for found in CATALOG.links.values() for t in found}
    for ref in CATALOG.links:
        found = CATALOG.uses(ref).refs
        assert list(found) == sorted(found, key=order.__getitem__), ref
    for ref in targets:
        found = CATALOG.used_by(ref).refs
        assert list(found) == sorted(found, key=order.__getitem__), ref


# --- Indicators of the design goals -------------------------------------------

WIKIDATA = 'matches = [{{ target = "http://www.wikidata.org/entity/{q}", relation = "close", verified = 2026-10-24 }}]'

STATS = f"""
[references.read]
authors = "Author, A."
title = "Read"
status = "verified"
{WIKIDATA.format(q="Q1")}

[references.unread]
authors = "Author, B."
title = "Unread"
status = "to-confirm"

[scales.s0]
label = "Reference scale"
kinds = ["CelsiusTemperature"]

[formulations.f]
label = "F"
expression = "a * t"
fixed_units = true
citations = [{{ reference = "read" }}]
{WIKIDATA.format(q="Q2")}
output = {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }}
inputs = [{{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in", scale = "s0", scale_basis = "inferred-from-date" }}]
coefficients = {{ a = 2.0 }}

[[formulations.f.domains]]
bounds = {{ t = [0, 50] }}

[formulations.g]
label = "G"
expression = "b * t"
fixed_units = true
citations = [{{ reference = "unread" }}]
output = {{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }}
inputs = [{{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }}]
coefficients = {{ b = 3.0 }}

[formulations.h]
label = "H"
expression = "c * e"
fixed_units = true
output = {{ identifier = "r", kind = "MassRatioOfWaterVapourToDryGas", unit = "KiloGM-PER-KiloGM", description = "out" }}
inputs = [{{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "in" }}]
coefficients = {{ c = 0.6 }}
"""


def test_stats_counts_the_indicators_of_the_design_goals() -> None:
    lines = stats(load_catalog([STATS])).splitlines()
    assert lines[0] == "Indicators of the design goals (AGENTS.md)"
    assert lines[1:] == [
        "1. Alternatives side by side",
        "  quantity kinds computed by several formulations: 1 of 2",
        "2. Validity, scale and sources stated, never invented",
        "  formulations with a validity domain: 1 of 3",
        "  inputs on a conventional scale with their scale recorded: 1 of 2",
        "  references checked against the source: 1 of 2",
        "  formulations derived by nomogram, which no source prints: 0 of 3",
        "5. Linked to shared vocabularies",
        "  quantity kinds used that are QUDT kinds or specialize one: 3 of 3",
        "  quantity kinds used with a CF standard name: 3 of 3",
        "  quantity kinds used with a Wikidata link: 2 of 3",
        "  formulations with a Wikidata link: 1 of 3",
        "  references with a Wikidata link: 1 of 2",
    ]


def test_every_kind_of_the_bundled_catalog_is_tied_to_qudt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["stats"]) == 0
    line = next(x for x in capsys.readouterr().out.splitlines() if "QUDT" in x)
    count, total = line.rsplit(": ", 1)[1].split(" of ")
    assert count == total
