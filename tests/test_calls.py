# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for formulations that call others: syntax, checks, values, display."""

import re
from importlib.resources import files
from importlib.resources.abc import Traversable

import numpy as np
import pytest
import sympy
from matplotlib.mathtext import MathTextParser

from nomogram.catalog import Catalog, CatalogError, catalog, load_catalog
from nomogram.expression import LATEX_COMMANDS, latex_commands, to_latex
from nomogram.model import Formulation
from nomogram.units import Q_

SOURCE = """
[references.src]
authors = "A."
title = "T"
status = "verified"
"""


def magnus(key: str, a: float, b: float, low: float, high: float) -> str:
    """A Magnus form over [low, high] degC, written for a test."""
    return f"""
[formulations.{key}]
label = "{key}"
expression = "C * exp(A * t / (B + t))"
fixed_units = true
output = {{ identifier = "e_s", kind = "VapourPressure", unit = "HectoPA", description = "e" }}
inputs = [{{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }}]
coefficients = {{ A = {a}, B = {b}, C = 6.112 }}

[[formulations.{key}.citations]]
reference = "src"

[[formulations.{key}.citations.domains]]
bounds = {{ t = [{low}, {high}] }}
"""


WATER = magnus("ew", 17.62, 243.12, -45.0, 60.0)
ICE = magnus("ei", 22.46, 272.62, -65.0, 0.0)

POINTS = (
    '{ identifier = "t_d", kind = "DewPointTemperature", unit = "DEG_C", description = "t_d" }, '
    '{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }'
)


def caller(
    expression: str,
    calls: str = '{ e_w = "ew" }',
    *,
    inputs: str = POINTS,
    fixed: bool = True,
    extra: str = "",
) -> str:
    """A formulation calling others, written for a test."""
    return f"""
[formulations.rh]
label = "rh"
expression = "{expression}"
calls = {calls}
fixed_units = {"true" if fixed else "false"}
output = {{ identifier = "RH", kind = "RelativeHumidity", unit = "PERCENT", description = "RH" }}
inputs = [{inputs}]
{extra}
[[formulations.rh.citations]]
reference = "src"
"""


def load(*documents: str) -> Catalog:
    return load_catalog([SOURCE + WATER + ICE + "".join(documents)])


def rh(document: str) -> Formulation:
    loaded = load_catalog([SOURCE + WATER + ICE + document])
    return loaded.formulations["rh"]


GRID = Q_(np.array([-40.0, -10.0, 0.0, 15.0, 30.0]), "degC")


# --- Values -------------------------------------------------------------------


def test_each_call_takes_its_own_arguments() -> None:
    f = rh(caller("100 * e_w(t=t_d) / e_w(t=t)"))
    loaded = load()
    water = loaded.formulations["ew"]
    t = Q_(25.0, "degC")
    expected = 100 * water.evaluate(t=GRID).magnitude / water.evaluate(t=t).magnitude
    assert f.evaluate(t_d=GRID, t=t).magnitude == pytest.approx(expected)


def test_a_dew_point_equal_to_the_temperature_gives_100_percent() -> None:
    f = rh(caller("100 * e_w(t=t_d) / e_w(t=t)"))
    values = f.evaluate(t_d=GRID, t=GRID).magnitude
    assert values == pytest.approx(np.full(GRID.shape, 100.0), rel=0, abs=1e-12)
    # Symbolically too: with t_d = t, the developed expression is 100.
    t_d, t = sympy.symbols("t_d t", real=True)
    developed = f.sympy_expression.xreplace({t_d: t})
    assert sympy.simplify(developed) == 100


def test_the_domains_of_the_called_formulation_apply_to_each_call() -> None:
    f = rh(caller("100 * e_w(t=t_d) / e_w(t=t)"))
    values = f.evaluate(t_d=Q_([-50.0, 10.0], "degC"), t=Q_(20.0, "degC")).magnitude
    assert np.isnan(values[0])
    assert not np.isnan(values[1])
    values = f.evaluate(t_d=Q_(10.0, "degC"), t=Q_(70.0, "degC")).magnitude
    assert np.isnan(values)


def test_a_domain_of_the_caller_adds_to_those_of_the_calls() -> None:
    extra = "[[formulations.rh.citations.domains]]\nbounds = { t = [0.0, 40.0] }\n"
    document = caller("100 * e_w(t=t_d) / e_w(t=t)").replace(
        'reference = "src"\n', 'reference = "src"\n' + extra
    )
    f = rh(document)
    # t_d = -50 degC lies outside the domain of ew, which still applies.
    value = f.evaluate(t_d=Q_(-50.0, "degC"), t=Q_(20.0, "degC")).magnitude
    assert np.isnan(value)


def test_evaluation_converts_arguments_to_their_declared_units() -> None:
    f = rh(caller("100 * e_w(t=t_d) / e_w(t=t)"))
    in_kelvins = f.evaluate(t_d=Q_(285.15, "K"), t=Q_(20.0, "degC")).magnitude
    in_celsius = f.evaluate(t_d=Q_(12.0, "degC"), t=Q_(20.0, "degC")).magnitude
    assert in_kelvins == pytest.approx(in_celsius)


def test_the_way_of_writing_changes_neither_inputs_nor_values() -> None:
    first = rh(caller("100 * e_w(t=t_d) / e_w(t=t)"))
    second = rh(caller("e_w(t=t_d) / e_w(t=t) * 100"))
    assert [v.identifier for v in first.inputs] == [v.identifier for v in second.inputs]
    t = Q_(20.0, "degC")
    assert first.evaluate(t_d=GRID, t=t).magnitude == pytest.approx(
        second.evaluate(t_d=GRID, t=t).magnitude
    )


def test_a_piecewise_formulation_called_twice_keeps_its_conditions() -> None:
    # Ice below -20 degC, water from 0 degC: a gap between, where no branch
    # holds; each call has its own conditions.
    pieces = WATER.replace(
        "C * exp(A * t / (B + t))",
        "piecewise((C * exp(22.46 * t / (272.62 + t)), t < -20), (C * exp(A * t / (B + t)), t >= 0))",
    ).replace("formulations.ew", "formulations.pw")
    f = rh(pieces + caller("100 * e_w(t=t_d) / e_w(t=t)", '{ e_w = "pw" }'))
    t = Q_(20.0, "degC")
    values = f.evaluate(t_d=Q_([-30.0, -10.0, 10.0], "degC"), t=t).magnitude
    assert np.isnan(values[1])
    assert not np.isnan(values[0])
    assert not np.isnan(values[2])
    assert np.isnan(f.evaluate(t_d=Q_(10.0, "degC"), t=Q_(-10.0, "degC")).magnitude)


# --- Renaming -------------------------------------------------------------------


def test_one_formulation_called_twice_shares_its_coefficients() -> None:
    f = rh(caller("100 * e_w(t=t_d) / e_w(t=t)"))
    names = [c.identifier for c in f.coefficients]
    assert names == ["A__ew", "B__ew", "C__ew"]
    # The shared C cancels in the developed expression, yet stays declared.
    free = {s.name for s in f.sympy_expression.free_symbols}
    assert "C__ew" not in free


def test_two_formulations_keep_their_coefficients_apart() -> None:
    # The relative humidity at the frost point over water, 100 e_i(t_f)/e_w(t):
    # both Magnus forms name their coefficients A, B and C.
    inputs = POINTS.replace("DewPointTemperature", "CelsiusTemperature")
    document = caller(
        "100 * e_i(t=t_d) / e_w(t=t)", '{ e_i = "ei", e_w = "ew" }', inputs=inputs
    )
    f = rh(document)
    names = {c.identifier for c in f.coefficients}
    assert {"A__ei", "A__ew", "B__ei", "B__ew", "C__ei", "C__ew"} == names
    loaded = load()
    ice, water = (loaded.formulations[k] for k in ("ei", "ew"))
    t_f, t = Q_(-10.0, "degC"), Q_(-5.0, "degC")
    expected = 100 * ice.evaluate(t=t_f).magnitude / water.evaluate(t=t).magnitude
    assert f.evaluate(t_d=t_f, t=t).magnitude == pytest.approx(expected)


def test_inputs_take_the_scale_of_the_inputs_they_feed() -> None:
    document = caller("100 * e_w(t=t_d) / e_w(t=t)")
    water = WATER.replace(
        'reference = "src"\n', 'reference = "src"\nscales = { t = "its90" }\n'
    )
    f = with_catalog(SOURCE + water + ICE + document).formulations["rh"]
    assert {v.identifier: getattr(v.scale, "key", None) for v in f.inputs} == {
        "t_d": "its90",
        "t": "its90",
    }


# --- Checks ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "calls", "message"),
    [
        ("100 * e_w(t_d) / e_w(t=t)", '{ e_w = "ew" }', "name its arguments"),
        ("100 * e_w(t=t_d, t=t) / e_w(t=t)", '{ e_w = "ew" }', "given twice"),
        ("100 * e_w(**k) / e_w(t=t)", '{ e_w = "ew" }', "name its arguments"),
        ("100 * e_w(t=e_w(t=t)) / e_w(t=t)", '{ e_w = "ew" }', "is an input"),
        ("100 * e_w(t=2) / e_w(t=t)", '{ e_w = "ew" }', "is an input"),
        ("100 * e_w(u=t_d) / e_w(t=t)", '{ e_w = "ew" }', "unknown u"),
        ("100 * e_w() / e_w(t=t)", '{ e_w = "ew" }', "missing t"),
        ("100 * e_w / e_w(t=t)", '{ e_w = "ew" }', "is called with its arguments"),
        ("100 * e_w(t=t_d) / e_w(t=t)", '{ e_w = "ew", e_i = "ei" }', "not called"),
        ("100 * e_w(t=t_d) / e_w(t=t)", '{ e_w = "nowhere" }', "unknown formulation"),
        ("100 * exp(t=t_d) / exp(t=t)", '{ exp = "ew" }', "reserved"),
        ("100 * pi(t=t_d) / pi(t=t)", '{ pi = "ew" }', "reserved"),
        ("100 * piecewise(t=t_d) / piecewise(t=t)", '{ piecewise = "ew" }', "reserved"),
        ("100 * t(t=t_d) / t(t=t)", '{ t = "ew" }', "reserved or already used"),
        ("100 * e_w(t=t_d) / e_w(t=t)", '"ew"', "expected a table"),
        (
            "piecewise((100 * e_w(t=t_d) / e_w(t=t), t > 0), (100, t <= 0))",
            '{ e_w = "ew" }',
            "piecewise definition",
        ),
    ],
)
def test_malformed_calls_are_refused(expression: str, calls: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        rh(caller(expression, calls))


def test_an_argument_of_another_kind_is_refused() -> None:
    inputs = POINTS.replace(
        '"DewPointTemperature", unit = "DEG_C"', '"TemperatureDifference", unit = "K"'
    )
    with pytest.raises(CatalogError, match="takes t as CelsiusTemperature"):
        rh(caller("100 * e_w(t=t_d) / e_w(t=t)", inputs=inputs))


def test_an_argument_in_another_unit_is_refused() -> None:
    inputs = POINTS.replace(
        '"DewPointTemperature", unit = "DEG_C"', '"DewPointTemperature", unit = "K"'
    )
    with pytest.raises(CatalogError, match="takes t in DEG_C"):
        rh(caller("100 * e_w(t=t_d) / e_w(t=t)", inputs=inputs))


def test_calling_a_fixed_units_formulation_needs_fixed_units() -> None:
    with pytest.raises(CatalogError, match="write fixed_units = true"):
        rh(caller("100 * e_w(t=t_d) / e_w(t=t)", fixed=False))


def test_an_expression_may_start_with_a_space() -> None:
    # As in a formulation that calls none.
    assert rh(caller(" 100 * e_w(t=t_d) / e_w(t=t)")).calls


def test_double_underscores_are_kept_for_qualified_names() -> None:
    inputs = POINTS.replace('"t_d"', '"t__d"')
    with pytest.raises(CatalogError, match="'__' is kept"):
        rh(caller("100 * e_w(t=t__d) / e_w(t=t)", inputs=inputs))


def test_an_input_feeding_two_scales_is_refused() -> None:
    water = WATER.replace(
        'reference = "src"\n', 'reference = "src"\nscales = { t = "its90" }\n'
    )
    ice = ICE.replace(
        'reference = "src"\n', 'reference = "src"\nscales = { t = "ipts68" }\n'
    )
    inputs = POINTS.replace("DewPointTemperature", "CelsiusTemperature")
    document = caller(
        "100 * e_i(t=t) / e_w(t=t) + 0 * t_d",
        '{ e_i = "ei", e_w = "ew" }',
        inputs=inputs,
    )
    with pytest.raises(CatalogError, match="feeds inputs on different scales"):
        with_catalog(SOURCE + water + ice + document)


def test_a_difference_is_no_argument_for_a_temperature_point() -> None:
    # QUDT makes a temperature difference a temperature: a 10 K difference
    # would be read as -263.15 degC.
    generic = magnus("eg", 17.62, 243.12, -45.0, 60.0).replace(
        'kind = "CelsiusTemperature", unit = "DEG_C"',
        'kind = "Temperature", unit = "K"',
    )
    inputs = POINTS.replace(
        '"DewPointTemperature", unit = "DEG_C"', '"TemperatureDifference", unit = "K"'
    ).replace('"CelsiusTemperature", unit = "DEG_C"', '"Temperature", unit = "K"')
    document = caller("100 * e_g(t=t_d) / e_g(t=t)", '{ e_g = "eg" }', inputs=inputs)
    with pytest.raises(CatalogError, match="takes t as Temperature"):
        load_catalog([SOURCE + generic + document])


DEW = """
[formulations.dew]
label = "dew"
expression = "B * ln(e / C) / (A - ln(e / C))"
fixed_units = true
output = { identifier = "t_d", kind = "DewPointTemperature", unit = "DEG_C", description = "t_d" }
inputs = [{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }]
coefficients = { A = 17.62, B = 243.12, C = 6.112 }

[[formulations.dew.citations]]
reference = "src"
scales = { t_d = "ipts68" }
"""


def mean_dew_point(extra: str = "") -> str:
    return f"""
[formulations.mean]
label = "mean"
expression = "(d(e=e_1) + d(e=e_2)) / 2"
calls = {{ d = "dew" }}
fixed_units = true
output = {{ identifier = "t_d", kind = "DewPointTemperature", unit = "DEG_C", description = "t_d" }}
inputs = [
  {{ identifier = "e_1", kind = "VapourPressure", unit = "HectoPA", description = "e_1" }},
  {{ identifier = "e_2", kind = "VapourPressure", unit = "HectoPA", description = "e_2" }},
]

[[formulations.mean.citations]]
reference = "src"
{extra}
"""


def test_a_result_on_another_scale_is_converted_back() -> None:
    # The dew point is given on IPTS-68: the caller states it, and its
    # result returns to ITS-90 as the called formulation's does.
    with pytest.raises(CatalogError, match="state that scale for the output of mean"):
        with_catalog(SOURCE + DEW + mean_dew_point())
    loaded = with_catalog(SOURCE + DEW + mean_dew_point('scales = { t_d = "ipts68" }'))
    mean = loaded.formulations["mean"]
    assert mean.output.scale is not None
    assert mean.output.scale.key == "ipts68"
    e = Q_(12.0, "hPa")
    dew = loaded.formulations["dew"].evaluate(e=e).magnitude
    assert mean.evaluate(e_1=e, e_2=e).magnitude == pytest.approx(dew)


def test_formulations_calling_each_other_are_refused() -> None:
    first = caller("100 * other(t_d=t_d, t=t) / 100", '{ other = "rh2" }')
    second = first.replace("formulations.rh", "formulations.rh2").replace(
        '{ other = "rh2" }', '{ other = "rh" }'
    )
    with pytest.raises(CatalogError, match="cycle"):
        load_catalog([SOURCE + WATER + ICE + first + second])


# --- The catalog ------------------------------------------------------------------

CATALOG = catalog()
FROM_DEW_POINT = CATALOG.formulations["wmo_relative_humidity_from_dew_point"]


def test_wmo_relative_humidity_from_the_dew_point() -> None:
    # Equation 4.B.11: U = 100 e'_w(p, t_d) / e'_w(p, t).
    moist = CATALOG.formulations["wmo_es_water_moist_air"]
    p, t = Q_(1013.25, "hPa"), Q_(20.0, "degC")
    t_d = Q_(np.array([-10.0, 5.0, 12.0, 20.0]), "degC")
    expected = (
        100 * moist.evaluate(p=p, t=t_d).magnitude / moist.evaluate(p=p, t=t).magnitude
    )
    found = FROM_DEW_POINT.evaluate(t_d=t_d, t=t, p=p).to("percent").magnitude
    assert found == pytest.approx(expected)
    assert found[-1] == pytest.approx(100.0, abs=1e-12)


def test_the_enhancement_factor_cancels_but_p_stays_an_input() -> None:
    assert [v.identifier for v in FROM_DEW_POINT.inputs] == ["t_d", "t", "p"]
    t_d, t = Q_(5.0, "degC"), Q_(20.0, "degC")
    low = FROM_DEW_POINT.evaluate(t_d=t_d, t=t, p=Q_(800.0, "hPa")).magnitude
    high = FROM_DEW_POINT.evaluate(t_d=t_d, t=t, p=Q_(1050.0, "hPa")).magnitude
    assert low == pytest.approx(high)


def test_a_formulation_with_calls_is_found_and_linked() -> None:
    # A dew point is one of its inputs.
    found = {f.key for f in CATALOG.search(input="DewPointTemperature").formulations}
    assert FROM_DEW_POINT.key in found
    used = {e.key for e in CATALOG.uses(f"formulations.{FROM_DEW_POINT.key}")}
    assert "wmo_es_water_moist_air" in used
    using = {e.key for e in CATALOG.used_by("formulations.wmo_es_water_moist_air")}
    assert FROM_DEW_POINT.key in using
    assert FROM_DEW_POINT.derivation is not None
    assert FROM_DEW_POINT.derivation.method == "calls"
    assert set(FROM_DEW_POINT.derivation.parts) == {"e_w(p=p, t=t_d)", "e_w(p=p, t=t)"}
    # A coefficient of a formulation called, by the name it is written with.
    found = {f.key for f in CATALOG.search(symbol="f_0").formulations}
    assert FROM_DEW_POINT.key in found


def test_a_formulation_with_calls_is_shown_as_written() -> None:
    rendering = FROM_DEW_POINT.render()
    assert r"e_{\mathrm{w}}\left(p, t_{\mathrm{d}}\right)" in rendering.latex
    assert latex_commands(rendering.latex) <= LATEX_COMMANDS
    MathTextParser("path").parse(rendering.mathtext)
    assert "$C = 6.112$ hPa (unit inferred by nomogram), of sonntag1990_magnus" in (
        rendering.markdown
    )
    assert "Calls e_w(p=p, t=t_d) with wmo_es_water_moist_air" in rendering.markdown


def test_a_composition_of_compositions_infers_the_units_of_its_coefficients() -> None:
    # The units of the coefficients of an inner composition come from its own
    # intermediate quantities (the enhancement factor, a pure number).
    nested = """
[formulations.u_moist]
label = "u_moist"
composition = { outer = "wmo_relative_humidity", inner = { e_ws = "wmo_es_water_moist_air" } }
"""
    loaded = with_catalog(nested)
    units = loaded.formulations["u_moist"].coefficient_units
    assert str(units["f_1"].unit) == "1 / hectopascal"
    assert str(units["C"].unit) == "hectopascal"


def with_catalog(*documents: str) -> Catalog:
    """The bundled catalog, with documents written for a test."""
    bundled: list[Traversable] = sorted(
        (
            f
            for f in files("nomogram.data.catalog").iterdir()
            if f.name.endswith(".toml")
        ),
        key=lambda f: f.name,
    )
    return load_catalog([*(f.read_text(encoding="utf-8") for f in bundled), *documents])


# --- More paths -------------------------------------------------------------------

MIXING = """
[formulations.difference]
label = "difference"
expression = "{expression}"
calls = {{ w = "mixing_ratio_from_vapour_pressure" }}
fixed_units = false
output = {{ identifier = "dr", kind = "MassRatioOfWaterVapourToDryGas", unit = "KiloGM-PER-KiloGM", description = "dr" }}
inputs = [
  {{ identifier = "e", kind = "VapourPressure", unit = "PA", description = "e" }},
  {{ identifier = "e_2", kind = "VapourPressure", unit = "PA", description = "e_2" }},
  {{ identifier = "p", kind = "Pressure", unit = "PA", description = "p" }},
]
{constants}
[[formulations.difference.citations]]
reference = "src"
"""


def test_a_constant_of_the_formulations_called_is_shared() -> None:
    document = MIXING.format(expression="w(e=e, p=p) - w(e=e_2, p=p)", constants="")
    f = with_catalog(SOURCE + document).formulations["difference"]
    assert [k.identifier for k in f.constants] == ["epsilon"]
    w = CATALOG.formulations["mixing_ratio_from_vapour_pressure"]
    e, e_2, p = Q_(2000.0, "Pa"), Q_(1000.0, "Pa"), Q_(1.0e5, "Pa")
    expected = w.evaluate(e=e, p=p).magnitude - w.evaluate(e=e_2, p=p).magnitude
    assert f.evaluate(e=e, e_2=e_2, p=p).magnitude == pytest.approx(expected)


def test_a_constant_of_the_same_name_but_another_source_stays_apart() -> None:
    # The epsilon of ASHRAE in the formulation called, that of the IFS here.
    document = MIXING.format(
        expression="w(e=e, p=p) - epsilon * e_2 / (p - e_2)",
        constants='constants = ["epsilon_ecmwf_ifs"]',
    )
    f = with_catalog(SOURCE + document).formulations["difference"]
    assert {k.identifier: k.key for k in f.constants} == {
        "epsilon": "epsilon_ecmwf_ifs",
        "epsilon__epsilon_ashrae2017": "epsilon_ashrae2017",
    }


def test_a_quantity_equation_called_in_fixed_units_keeps_its_value() -> None:
    # The part gives hPa from Pa: a factor 0.01 the call keeps.
    part = """
[formulations.to_hpa]
label = "to_hpa"
expression = "e_pa"
fixed_units = false
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }
inputs = [{ identifier = "e_pa", kind = "VapourPressure", unit = "PA", description = "e" }]

[[formulations.to_hpa.citations]]
reference = "src"
"""
    inputs = (
        '{ identifier = "x", kind = "VapourPressure", unit = "PA", description = "x" }'
    )
    document = caller("50 * conv(e_pa=x)", '{ conv = "to_hpa" }', inputs=inputs)
    f = rh(part + document)
    assert f.evaluate(x=Q_(2000.0, "Pa")).to("percent").magnitude == pytest.approx(
        1000.0
    )


def test_a_formulation_may_call_one_that_calls_others() -> None:
    second = """
[formulations.ratio]
label = "ratio"
expression = "humidity(t_d=t_d, t=t) / 100"
calls = { humidity = "rh" }
fixed_units = true
output = { identifier = "U", kind = "RelativeHumidity", unit = "UNITLESS", description = "U" }
inputs = [{inputs}]

[[formulations.ratio.citations]]
reference = "src"
""".replace("{inputs}", POINTS)
    loaded = load(caller("100 * e_w(t=t_d) / e_w(t=t)"), second)
    first, outer = loaded.formulations["rh"], loaded.formulations["ratio"]
    assert [c.identifier for c in outer.coefficients] == ["A__ew", "B__ew", "C__ew"]
    t_d, t = Q_(5.0, "degC"), Q_(20.0, "degC")
    expected = first.evaluate(t_d=t_d, t=t).magnitude / 100
    assert outer.evaluate(t_d=t_d, t=t).magnitude == pytest.approx(expected)


def test_a_declared_scale_must_be_that_of_the_input_fed() -> None:
    water = WATER.replace(
        'reference = "src"\n', 'reference = "src"\nscales = { t = "its90" }\n'
    )
    inputs = POINTS.replace(
        '"CelsiusTemperature", unit = "DEG_C", description = "t"',
        '"CelsiusTemperature", unit = "DEG_C", description = "t", scale = "ipts68", '
        'scale_basis = "inferred-from-date"',
    )
    document = caller("100 * e_w(t=t_d) / e_w(t=t)", inputs=inputs)
    with pytest.raises(CatalogError, match="is on ipts68, but feeds ew on its90"):
        with_catalog(SOURCE + water + ICE + document)


@pytest.mark.parametrize(
    ("expression", "message"),
    [("3", "expected a string"), ("'100 * ('", "invalid syntax")],
)
def test_an_unreadable_expression_is_refused(expression: str, message: str) -> None:
    document = caller("X").replace('expression = "X"', f"expression = {expression}")
    with pytest.raises(CatalogError, match=message):
        rh(document)


def test_a_call_may_stand_inside_a_function() -> None:
    f = rh(caller("100 * exp(ln(e_w(t=t_d) / e_w(t=t)))"))
    plain = rh(caller("100 * e_w(t=t_d) / e_w(t=t)"))
    t = Q_(20.0, "degC")
    assert f.evaluate(t_d=GRID, t=t).magnitude == pytest.approx(
        plain.evaluate(t_d=GRID, t=t).magnitude
    )


def test_other_functions_keep_their_rendering() -> None:
    x = sympy.Symbol("x", real=True)
    assert r"\sin" in to_latex(sympy.sin(x))


def test_an_unknown_constant_is_refused() -> None:
    document = caller("100 * e_w(t=t_d) / e_w(t=t)", extra='constants = ["nowhere"]')
    with pytest.raises(CatalogError, match="unknown constant 'nowhere'"):
        rh(document)


def test_a_dew_point_feeds_a_thermodynamic_temperature_in_the_same_unit() -> None:
    part = """
[formulations.twice]
label = "twice"
expression = "2 * T"
fixed_units = false
output = { identifier = "y", kind = "ThermodynamicTemperature", unit = "K", description = "y" }
inputs = [{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "T" }]

[[formulations.twice.citations]]
reference = "src"

[formulations.at_dew_point]
label = "at_dew_point"
expression = "twice(T=T_d)"
calls = { twice = "twice" }
fixed_units = false
output = { identifier = "z", kind = "ThermodynamicTemperature", unit = "K", description = "z" }
inputs = [{ identifier = "T_d", kind = "DewPointTemperature", unit = "K", description = "T_d" }]

[[formulations.at_dew_point.citations]]
reference = "src"
"""
    f = load(part).formulations["at_dew_point"]
    assert f.evaluate(T_d=Q_(280.0, "K")).magnitude == pytest.approx(560.0)


def test_calls_keep_their_arguments_in_the_order_of_the_inputs_called() -> None:
    f = rh(caller("100 * e_w(t=t_d) / e_w(t=t)"))
    assert [dict(c.arguments) for c in f.calls] == [{"t": "t_d"}, {"t": "t"}]
    assert [c.alias for c in f.calls] == ["e_w", "e_w"]
    assert FROM_DEW_POINT.calls[0].arguments == {"p": "p", "t": "t_d"}
    assert list(FROM_DEW_POINT.calls[0].arguments) == ["p", "t"]


def test_without_calls_the_written_expression_is_the_expression() -> None:
    water = CATALOG.formulations["sonntag1990_magnus"]
    assert water.written is None
    assert water.written_expression == water.sympy_expression


# --- Formulations reached through others ---------------------------------------

INVERSE = """
[formulations.ew_inverse]
label = "ew_inverse"
expression = "b * ln(e / c) / (a - ln(e / c))"
fixed_units = true
output = { identifier = "t_d", kind = "DewPointTemperature", unit = "DEG_C", description = "t_d" }
inputs = [{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }]
coefficients = { a = 17.62, b = 243.12, c = 6.112 }

[[formulations.ew_inverse.citations]]
reference = "src"

[formulations.round_trip]
label = "round_trip"
composition = { outer = "ew_inverse", inner = { e = "ew" } }
"""


def test_a_formulation_composed_with_its_inverse_is_the_identity() -> None:
    # f^-1(f(t)) = t, with a Magnus form and its inverse written for the test.
    # A call takes inputs, not calls: the nesting is a composition. Its
    # expression simplifies to t once the coefficients of the inverse are
    # those of the form, and ln(exp(x)) is x (SymPy keeps it while B + t
    # may vanish).
    f = load(INVERSE).formulations["round_trip"]
    t = Q_(np.linspace(-40.0, 55.0, 20), "degC")
    back = f.evaluate(t=t).to("degC").magnitude
    assert back == pytest.approx(t.magnitude, abs=1e-9)
    same = {
        sympy.Symbol(x, real=True): sympy.Symbol(x.upper(), real=True) for x in "abc"
    }
    developed = sympy.expand_log(f.sympy_expression.xreplace(same), force=True)
    assert sympy.simplify(developed - sympy.Symbol("t", real=True)) == 0


SCALED = """
[formulations.g]
label = "g"
expression = "A * e_w(t=t)"
calls = { e_w = "ew" }
fixed_units = true
output = { identifier = "e_g", kind = "VapourPressure", unit = "HectoPA", description = "e" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]
coefficients = { A = 2.0 }

[[formulations.g.citations]]
reference = "src"
"""


def test_the_own_coefficients_of_a_formulation_called_stay_its_own() -> None:
    # g names A like the Magnus form it calls: its A is not the form's.
    document = """
[formulations.gap]
label = "gap"
expression = "g(t=t_d) - e_w(t=t)"
calls = { g = "g", e_w = "ew" }
fixed_units = true
output = { identifier = "d", kind = "VapourPressure", unit = "HectoPA", description = "d" }
inputs = [{inputs}]

[[formulations.gap.citations]]
reference = "src"
""".replace("{inputs}", POINTS)
    loaded = load(SCALED, document)
    f = loaded.formulations["gap"]
    values = {c.identifier: c.value for c in f.coefficients}
    assert (values["A__g"], values["A__ew"]) == (2.0, 17.62)
    water = loaded.formulations["ew"]
    t = Q_(20.0, "degC")
    expected = 2 * water.evaluate(t=GRID).magnitude - water.evaluate(t=t).magnitude
    assert f.evaluate(t_d=GRID, t=t).magnitude == pytest.approx(expected)
    markdown = f.render().markdown
    assert "$A = 2.0$ (pure number, inferred by nomogram), of g" in markdown
    assert "$C = 6.112$ hPa (unit inferred by nomogram), of ew" in markdown


def test_a_composition_tells_a_caller_s_own_coefficient_from_the_called_one() -> None:
    outer = """
[formulations.scaled]
label = "scaled"
expression = "{name} * e"
fixed_units = true
output = {{ identifier = "y", kind = "VapourPressure", unit = "HectoPA", description = "y" }}
inputs = [{{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }}]
coefficients = {{ {name} = 3.0 }}

[[formulations.scaled.citations]]
reference = "src"

[formulations.composed]
label = "composed"
composition = {{ outer = "scaled", inner = {{ e = "g" }} }}
"""
    with pytest.raises(CatalogError, match="coefficient A in both scaled and g"):
        load(SCALED, outer.format(name="A"))
    f = load(SCALED, outer.format(name="k")).formulations["composed"]
    water = load().formulations["ew"]
    t = Q_(20.0, "degC")
    assert f.evaluate(t=t).magnitude == pytest.approx(6 * water.evaluate(t=t).magnitude)


def test_branches_tell_a_caller_s_own_coefficient_from_the_called_one() -> None:
    branches = """
[formulations.both]
label = "both"
branches = [{ formulation = "g", where = "t < 0" }, { formulation = "ew", where = "t >= 0" }]
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }
"""
    with pytest.raises(CatalogError, match="coefficient A in both g and ew"):
        load(SCALED, branches)


def superscripts(document: str) -> str:
    """A, B and C as a__w, b__w and c__w, as SymPy writes superscripts."""
    return re.sub(r"\b([ABC])\b", lambda m: f"{m.group(1).lower()}__w", document)


def test_double_underscores_of_a_formulation_called_are_its_own() -> None:
    first = superscripts(magnus("m1", 17.27, 237.3, -45.0, 60.0))
    second = superscripts(magnus("m2", 21.87, 265.5, -65.0, 0.0))
    inputs = POINTS.replace("DewPointTemperature", "CelsiusTemperature")
    document = caller(
        "100 * f(t=t_d) / g(t=t)", '{ f = "m1", g = "m2" }', inputs=inputs
    )
    loaded = load(first, second, document)
    f = loaded.formulations["rh"]
    assert "a__w__m1" in {c.identifier for c in f.coefficients}
    water, ice = (loaded.formulations[k] for k in ("m1", "m2"))
    t_f, t = Q_(-10.0, "degC"), Q_(-5.0, "degC")
    expected = 100 * water.evaluate(t=t_f).magnitude / ice.evaluate(t=t).magnitude
    assert f.evaluate(t_d=t_f, t=t).magnitude == pytest.approx(expected)
    # Shown as written, with their owner; in their own formulation, as always.
    line = r"$a^{\mathrm{w}} = 17.27$ (pure number, inferred by nomogram), of m1"
    assert line in f.render().markdown
    own = loaded.formulations["m1"].render().markdown
    assert r"$a^{\mathrm{w}} = 17.27$" in own
    assert ", of" not in own


def test_a_composition_writes_the_names_of_the_formulations_called() -> None:
    # The part of a composition calls others, whose renamed coefficients
    # the composition prints expanded: as written, never with their owner.
    first = superscripts(magnus("m1", 17.27, 237.3, -45.0, 60.0))
    second = superscripts(magnus("m2", 21.87, 265.5, -65.0, 0.0))
    document = """
[formulations.both]
label = "both"
expression = "f(t=t) + g(t=t)"
calls = { f = "m1", g = "m2" }
fixed_units = true
output = { identifier = "e_b", kind = "VapourPressure", unit = "HectoPA", description = "e" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]

[[formulations.both.citations]]
reference = "src"

[formulations.scaled]
label = "scaled"
expression = "k * e"
fixed_units = true
output = { identifier = "y", kind = "VapourPressure", unit = "HectoPA", description = "y" }
inputs = [{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }]
coefficients = { k = 3.0 }

[[formulations.scaled.citations]]
reference = "src"

[formulations.composed]
label = "composed"
composition = { outer = "scaled", inner = { e = "both" } }
"""
    f = load(first, second, document).formulations["composed"]
    assert "a__w__m1" in {c.identifier for c in f.coefficients}
    latex = f.render().latex
    assert r"a^{\mathrm{w}}" in latex
    assert "m1" not in latex
    assert "m2" not in latex


def test_a_constant_declared_but_used_only_by_a_call_is_refused() -> None:
    document = MIXING.format(
        expression="w(e=e, p=p) - w(e=e_2, p=p)",
        constants='constants = ["epsilon_ashrae2017"]',
    )
    with pytest.raises(CatalogError, match="declared but not used: epsilon"):
        with_catalog(SOURCE + document)


def test_the_name_of_a_call_is_written_like_an_identifier() -> None:
    f = rh(caller("100 * ebar(t=t_d) / ebar(t=t)", '{ ebar = "ew" }'))
    latex = f.render().latex
    assert r"\mathrm{ebar}\left(t_{\mathrm{d}}\right)" in latex
    assert latex_commands(latex) <= LATEX_COMMANDS


def test_a_formulation_calling_others_may_state_its_conditions() -> None:
    f = rh(caller("100 * e_w(t=t_d) / e_w(t=t)", extra='conditions = "Same pressure."'))
    assert f.conditions == "Same pressure."
    with pytest.raises(CatalogError, match="conditions: expected a string"):
        rh(caller("100 * e_w(t=t_d) / e_w(t=t)", extra="conditions = 1"))


def test_a_wet_bulb_temperature_is_a_point_of_evaluation() -> None:
    wet = (
        '{ identifier = "t_w", kind = "WetBulbTemperature", unit = "DEG_C", '
        'description = "t_w" }, '
        '{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }'
    )
    f = rh(caller("100 * e_w(t=t_w) / e_w(t=t)", inputs=wet))
    t = Q_(20.0, "degC")
    assert f.evaluate(t_w=t, t=t).magnitude == pytest.approx(100)
