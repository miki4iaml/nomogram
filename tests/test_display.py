# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.display`: typography, options and Markdown."""

import dataclasses
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from nomogram.catalog import catalog
from nomogram.display import (
    DisplayOptions,
    FormulaTable,
    Rendering,
    axis_label,
    display_options,
    get_display_options,
    reference_scale,
    render,
    symbol,
    table,
)
from nomogram.expression import LATEX_COMMANDS, latex_commands
from nomogram.model import Notation

CATALOG = catalog()
FORMULATIONS = CATALOG.formulations
MAGNUS = FORMULATIONS["sonntag1990_magnus"]
IDEAL_GAS = FORMULATIONS["mass_concentration_ideal_gas"]
WMO = CATALOG.notations["wmo"]

OPTION_SETS = [
    DisplayOptions(),
    DisplayOptions.SYMPY,
    DisplayOptions(mul_symbol="dot", decimal_separator="comma", values=True),
    DisplayOptions(mul_symbol="ldot", upright=False, values=True),
]


def test_default_typography_marks_every_product_and_sets_subscripts_upright() -> None:
    assert IDEAL_GAS.latex() == (
        r"\rho_{\mathrm{v}} = \frac{\mathrm{RH} \times e_{\mathrm{s}}}"
        r"{R_{\mathrm{v}} \times T}"
    )
    assert (
        MAGNUS.latex()
        == r"e_{\mathrm{s}} = C \times \exp\left(\frac{A \times t}{B + t}\right)"
    )


def test_sympy_preset_gives_sympy_rendering() -> None:
    assert MAGNUS.latex(options=DisplayOptions.SYMPY) == (
        r"e_{s} = C \exp\left(\frac{A t}{B + t}\right)"
    )


def test_notation_takes_priority_over_upright_symbols() -> None:
    assert MAGNUS.latex(WMO).startswith(r"e_{\mathrm{w}} = C \times \exp")


def test_coefficients_as_values_keep_the_form_and_their_digits() -> None:
    assert MAGNUS.latex(values=True) == (
        r"e_{\mathrm{s}} = 6.112 \times \exp\left(\frac{17.62 \times t}{243.12 + t}\right)"
    )
    iapws = FORMULATIONS["iapws_r14_08_sublimation"].latex(values=True)
    assert r"\left(-21.2144006\right) \times" in iapws
    assert r"\frac{T}{273.16}" in iapws


def test_decimal_comma_and_powers_of_ten() -> None:
    hyland = FORMULATIONS["hyland_wexler1983_ice"]
    latex = hyland.latex(values=True, decimal_separator="comma")
    assert r"6{,}2215701 \times 10^{-7} \times T^{2}" in latex
    # Only x between numbers (SI Brochure, 9th edition, 5.4.6).
    dotted = hyland.latex(values=True, mul_symbol="dot")
    assert r"6.2215701 \times 10^{-7} \cdot T^{2}" in dotted


def test_options_levels_keyword_over_block_over_defaults() -> None:
    assert get_display_options() == DisplayOptions()
    with display_options(mul_symbol="dot") as inside:
        assert inside == get_display_options()
        assert r"A \cdot t" in MAGNUS.latex()
        assert r"A \times t" in MAGNUS.latex(mul_symbol="times")
        compact = DisplayOptions(mul_symbol=None)
        assert r"A t" in render(MAGNUS, options=compact).latex
        with display_options(upright=False):
            assert get_display_options().mul_symbol == "dot"
            assert MAGNUS.latex().startswith("e_{s}")
    assert get_display_options() == DisplayOptions()


def test_block_options_are_restored_after_an_exception() -> None:
    with pytest.raises(RuntimeError), display_options(values=True):
        raise RuntimeError
    assert get_display_options().values is False


def test_block_options_stay_in_their_thread() -> None:
    with display_options(mul_symbol="dot"), ThreadPoolExecutor(1) as pool:
        seen = pool.submit(get_display_options).result()
    assert seen == DisplayOptions()


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"mul_symbol": "star"}, ValueError),
        ({"decimal_separator": "space"}, ValueError),
        ({"axis_labels": "fancy"}, ValueError),
        ({"colour": "red"}, TypeError),
    ],
)
def test_invalid_options_are_refused(overrides: dict[str, Any], error: type) -> None:
    with pytest.raises(error):
        render(MAGNUS, **overrides)


def test_options_are_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        DisplayOptions().upright = False  # type: ignore[misc]


@pytest.mark.parametrize("options", OPTION_SETS, ids=repr)
def test_every_formula_stays_within_the_common_latex_subset(
    options: DisplayOptions,
) -> None:
    for formulation in FORMULATIONS.values():
        for notation in (None, *CATALOG.notations.values()):
            rendering = render(formulation, notation, options=options)
            assert latex_commands(rendering.latex) <= LATEX_COMMANDS, formulation.key
            assert latex_commands(rendering.markdown) <= LATEX_COMMANDS, formulation.key


def test_rendering_targets() -> None:
    rendering = MAGNUS.render()
    assert isinstance(rendering, Rendering)
    assert rendering.mathtext == f"${rendering.latex}$"
    assert rendering._repr_markdown_() == rendering.markdown
    assert MAGNUS._repr_latex_() == f"$${MAGNUS.latex()}$$"
    assert repr(rendering) == "Rendering('sonntag1990_magnus', notation=None)"
    assert repr(MAGNUS.render(WMO)) == "Rendering('sonntag1990_magnus', notation='wmo')"
    pair = table([MAGNUS, IDEAL_GAS])
    assert repr(pair) == (
        "FormulaTable(2 formulations: sonntag1990_magnus, mass_concentration_ideal_gas)"
    )


def test_markdown_explains_each_symbol_with_its_unit() -> None:
    lines = MAGNUS.render().markdown.splitlines()
    assert lines[0] == f"**{MAGNUS.label}**"
    assert lines[2:5] == ["$$", MAGNUS.latex(), "$$"]
    assert r"- $e_{\mathrm{s}}$: Saturation vapour pressure over water [hPa]" in lines
    assert "- $t$: Celsius temperature [°C]" in lines
    assert "- $A = 17.62$ (pure number, inferred by nomogram)" in lines
    assert "- $B = 243.12$ °C (unit inferred by nomogram)" in lines  # from B + t
    assert "- $C = 6.112$ hPa (unit inferred by nomogram)" in lines
    assert (
        lines[-1]
        == r"The coefficients hold for $e_{\mathrm{s}}$ in hPa, $t$ in °C only."
    )
    murray = FORMULATIONS["murray1967"].render().markdown.splitlines()
    assert "- $B = 35.86$ K (unit inferred by nomogram)" in murray
    iapws = FORMULATIONS["iapws_sr1_86"].render().markdown.splitlines()
    assert "- $T_{\\mathrm{c}} = 647.096$ K (unit from the source)" in iapws
    gg = FORMULATIONS["goff_gratch1946"].render().markdown.splitlines()
    assert "- $e_{\\mathrm{st}} = 1013.246$ hPa (unit added by nomogram)" in gg
    sonntag = FORMULATIONS["sonntag1990"].render().markdown.splitlines()
    assert (
        r"- $a_{3} = 1.673952 \times 10^{-5}$ 1/K² (unit inferred by nomogram)"
        in sonntag
    )
    with_values = MAGNUS.render(values=True).markdown
    assert "$A = " not in with_values


def test_markdown_falls_back_to_declared_units_when_they_contradict() -> None:
    coefficients = tuple(
        dataclasses.replace(c, unit="HectoPA") if c.identifier == "B" else c
        for c in MAGNUS.coefficients
    )
    broken = dataclasses.replace(MAGNUS, coefficients=coefficients)
    assert "- $B = 243.12$ hPa" in broken.render().markdown.splitlines()


def test_origin_of_units_only_in_the_legend_of_one_formulation() -> None:
    undetermined = dataclasses.replace(
        MAGNUS, expression="A * B * t", coefficients=MAGNUS.coefficients[:2]
    )
    assert "- $A = 17.62$ (unit undetermined)" in undetermined.render().markdown
    assert "inferred" not in table([MAGNUS]).to_markdown()
    assert "inferred" not in symbol(MAGNUS.output)


def test_quantity_equations_have_no_fixed_units_line() -> None:
    markdown = FORMULATIONS["mixing_ratio_from_vapour_pressure"].render().markdown
    assert "coefficients hold" not in markdown


def test_markdown_lists_constants_and_omits_unitless_symbols() -> None:
    markdown = FORMULATIONS["mixing_ratio_from_vapour_pressure"].render().markdown
    assert r"- $\epsilon = 0.621945$: Ratio of the molar masses" in markdown
    assert "一" not in markdown


def test_symbol_labels_an_axis() -> None:
    assert symbol(MAGNUS.output, WMO) == r"$e_{\mathrm{w}}$/hPa"
    assert symbol(MAGNUS.output, WMO, axis_labels="simple") == r"$e_{\mathrm{w}}$ [hPa]"
    assert symbol(MAGNUS.inputs[0]) == "$t_{90}$/°C"
    assert symbol(MAGNUS.output, unit=False) == r"$e_{\mathrm{s}}$"
    assert symbol(IDEAL_GAS.inputs[0], upright=False) == "$RH$"


def test_table_of_formulations() -> None:
    ice = CATALOG.formulations_of("SaturationVapourPressureOverIce")
    result = table(ice)
    assert isinstance(result, FormulaTable)
    lines = result.to_markdown().splitlines()
    assert lines[0] == "| Formulation | Equation | Validity | References |"
    assert len(lines) == 2 + len(ice)
    assert "$T$: 50 to 273.16 K (stated)" in lines[2]
    assert result._repr_markdown_() == result.to_markdown()


def test_table_follows_options_and_escapes_vertical_bars() -> None:
    bars = Notation("bars", "Bars", {"e_s": "|e|"}, None)
    row = table([MAGNUS], bars, decimal_separator="comma").to_markdown().splitlines()[2]
    assert r"\vert e\vert" in row
    assert "|e|" not in row
    assert (
        "-40 to 50 °C (stated)"
        in table([FORMULATIONS["alduchov_eskridge1996"]]).to_markdown()
    )
    commas = table(
        [FORMULATIONS["iapws_r14_08_sublimation"]], decimal_separator="comma"
    )
    assert "50 to 273,16 K" in commas.to_markdown()


def test_axis_labels_in_the_three_styles() -> None:
    its90 = reference_scale("CelsiusTemperature")
    assert its90 is not None
    assert (its90.symbol, its90.subscript) == ("ITS-90", "90")
    args = ("Celsius temperature", "t", "°C")
    assert axis_label(*args, scale=its90) == "Celsius temperature $t_{90}$/°C"
    assert (
        axis_label(*args, scale=its90, axis_labels="explicit")
        == "Celsius temperature - $t$ [°C] {ITS-90}"
    )
    assert axis_label(*args, scale=its90, axis_labels="simple") == (
        "Celsius temperature $t$ [°C]"
    )
    with display_options(axis_labels="simple"):
        assert axis_label(*args, scale=its90) == "Celsius temperature $t$ [°C]"


def test_axis_label_details() -> None:
    # A compound unit goes in parentheses; a name alone keeps the slash apart.
    assert axis_label(None, r"\rho_{\mathrm{v}}", "g/m³") == (
        r"$\rho_{\mathrm{v}}$/(g/m³)"
    )
    assert axis_label("Height", None, "km") == "Height / km"
    # A number has no unit, except in brackets.
    assert axis_label("Practical salinity", "S", "") == "Practical salinity $S$"
    assert axis_label("Ratio", None, "", axis_labels="explicit") == "Ratio [1]"
    assert axis_label(None, None, "Pa", axis_labels="explicit") == "[Pa]"
    assert axis_label(None, None, "Pa") == "[Pa]"
    # The scale subscript joins an existing one, upright when not a number.
    its90 = reference_scale("CelsiusTemperature")
    assert its90 is not None
    scale = dataclasses.replace(its90, subscript="P")
    assert axis_label(None, r"T_{\mathrm{d}}", "K", scale=scale) == (
        r"$T_{\mathrm{d},\mathrm{P}}$/K"
    )
    assert reference_scale("VapourPressure") is None
