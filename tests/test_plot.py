# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.plot` (extra ``viz``)."""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex
from matplotlib.lines import Line2D
from matplotlib.mathtext import MathTextParser
from matplotlib.offsetbox import AnchoredOffsetbox, AnnotationBbox

from nomogram import _logo
from nomogram.catalog import catalog, load_catalog
from nomogram.comparison import Comparison, compare
from nomogram.display import (
    DisplayOptions,
    axis_label,
    display_options,
    reference_scale,
)
from nomogram.expression import LATEX_COMMANDS
from nomogram.plot import plot_deviations, plot_values, sign
from nomogram.units import Q_

CATALOG = catalog()
FORMULATIONS = CATALOG.formulations
IAPWS = FORMULATIONS["iapws_sr1_86"]
SATURATION = CATALOG.formulations_of("SaturationVapourPressureOverWater")
GRID = Q_(np.array([-50.0, 0.01, 20.0, 40.0]), "degC")


@pytest.fixture(autouse=True)
def close_figures() -> Iterator[None]:
    yield
    plt.close("all")


@pytest.fixture
def comparison() -> Comparison:
    return compare(SATURATION, IAPWS, {"ThermodynamicTemperature": GRID})


def test_deviations_one_curve_per_formulation_with_domain_gaps(
    comparison: Comparison,
) -> None:
    ax = plot_deviations(comparison)
    # One curve per formulation but the reference, plus the zero line.
    assert len(ax.lines) == len(SATURATION)
    curve = ax.lines[0].get_ydata()
    # -50 degC is outside the IAPWS domain: a gap, not a value.
    assert np.isnan(curve[0])
    assert "IAPWS" in ax.get_ylabel()
    assert ax.get_ylabel().endswith(r"$\delta$/%")
    # The values are in degC: a Celsius temperature, on ITS-90.
    assert ax.get_xlabel() == "Celsius temperature $t_{90}$/°C"
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert "Magnus form, Sonntag (1990) coefficients" in labels


def test_values_with_a_notation(comparison: Comparison) -> None:
    ax = plot_values(comparison, notation=CATALOG.notations["wmo"])
    assert ax.get_ylabel() == (
        r"Saturation vapour pressure over water $e_{\mathrm{w}}$/Pa"
    )
    assert len(ax.lines) == len(SATURATION)
    reference = next(line for line in ax.lines if line.get_linestyle() == "--")
    assert reference.get_label() == IAPWS.label


def test_existing_axes_are_used(comparison: Comparison) -> None:
    _, ax = plt.subplots()
    assert plot_deviations(comparison, ax=ax) is ax
    assert plot_values(comparison, ax=ax) is ax


def test_input_kind_must_be_clear() -> None:
    two = Comparison(
        "r",
        {
            "ThermodynamicTemperature": Q_(np.array([1.0, 2.0]), "K"),
            "RelativeHumidity": Q_(np.array([0.1, 0.2]), ""),
        },
        {"r": Q_(np.array([1.0, 2.0]), "Pa")},
        {"r": np.zeros(2)},
    )
    with pytest.raises(ValueError, match="choose the input"):
        plot_deviations(two)
    with pytest.raises(ValueError, match="no input of kind 'Nope'"):
        plot_deviations(two, input_kind="Nope")
    # Without the formulations, keys serve as labels and no symbol is shown.
    ax = plot_values(two, input_kind="ThermodynamicTemperature")
    assert ax.get_ylabel() == "Pa"
    assert ax.get_xlabel() == "Thermodynamic temperature $T_{90}$/K"
    assert ax.lines[0].get_label() == "r"
    other = Comparison(
        "r", {"Custom": Q_([1.0, 2.0], "K")}, two.values, two.relative_deviations
    )
    assert plot_values(other).get_xlabel() == "Custom / K"


def test_missing_extra_gives_an_explicit_message(
    monkeypatch: pytest.MonkeyPatch, comparison: Comparison
) -> None:
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    with pytest.raises(ImportError, match=r"nomogram\[viz\]"):
        plot_deviations(comparison)


@pytest.mark.parametrize("notation", [None, *sorted(CATALOG.notations)])
@pytest.mark.parametrize(
    "options",
    [
        DisplayOptions(),
        DisplayOptions.SYMPY,
        DisplayOptions(mul_symbol="dot", values=True),
    ],
    ids=["default", "sympy", "values"],
)
def test_every_formulation_renders_in_mathtext(
    notation: str | None, options: DisplayOptions
) -> None:
    parser = MathTextParser("path")
    chosen = CATALOG.notations[notation] if notation else None
    for formulation in FORMULATIONS.values():
        parser.parse(formulation.render(chosen, options=options).mathtext)


@pytest.mark.parametrize("command", sorted(LATEX_COMMANDS))
def test_every_supported_latex_command_renders_in_mathtext(command: str) -> None:
    pair = r"\left(a\right)"
    samples = {r"\frac": r"\frac{a}{b}", r"\left": pair, r"\right": pair}
    MathTextParser("path").parse(f"$x {samples.get(command, command + '{a}')}$")


@pytest.mark.parametrize(
    "tex", ["T_d", r"\theta_\mathrm{d}", r"T^{a_{b}}", r"T_{\mathrm{d}}^{2}"]
)
def test_scale_marks_render_in_mathtext(tex: str) -> None:
    label = axis_label(None, tex, "K", scale=reference_scale("CelsiusTemperature"))
    MathTextParser("path").parse(label)


def test_curves_beyond_ten_change_line_style(comparison: Comparison) -> None:
    ax = plot_deviations(comparison)
    styles = [line.get_linestyle() for line in ax.lines[:-1]]
    assert styles[:10] == ["-"] * 10
    assert set(styles[10:]) == {"-."}


def test_abscissa_symbol_from_the_reference_formulation() -> None:
    from nomogram.comparison import compare

    vapour = CATALOG.formulations["vapour_pressure_from_relative_humidity"]
    found = compare(
        [vapour],
        vapour,
        {
            "RelativeHumidity": Q_(np.array([0.2, 0.5, 0.8]), ""),
            "SaturationVapourPressureOverWater": Q_(2000.0, "Pa"),
        },
    )
    label = plot_values(found, input_kind="RelativeHumidity").get_xlabel()
    assert label == r"Relative humidity $\mathrm{RH}$"
    # The input of the reference matching the kind gives the symbol, in the
    # notation of the plot (ASHRAE writes the saturation pressure p_ws).
    found_es = compare(
        [vapour],
        vapour,
        {
            "RelativeHumidity": Q_(0.5, ""),
            "SaturationVapourPressureOverWater": Q_(np.array([1.0e3, 2.0e3]), "Pa"),
        },
    )
    ashrae = CATALOG.notations["ashrae"]
    assert plot_values(found_es, notation=ashrae).get_xlabel() == (
        r"Saturation vapour pressure over water $p_{\mathrm{ws}}$/Pa"
    )


def test_axes_follow_the_display_options(comparison: Comparison) -> None:
    with display_options(axis_labels="explicit"):
        ax = plot_values(comparison)
    assert ax.get_xlabel() == "Celsius temperature - $t$ [°C] {ITS-90}"
    with display_options(axis_labels="simple"):
        ax = plot_deviations(comparison)
    assert ax.get_xlabel() == "Celsius temperature $t$ [°C]"
    assert ax.get_ylabel().endswith(r"$\delta$ [%]")


def legend(ax: Any) -> list[str]:
    return [t.get_text() for t in ax.get_legend().get_texts()]


def test_labels_follow_the_detail_option(comparison: Comparison) -> None:
    # Standard: the name of each quantity, the reference by its source.
    ax = plot_deviations(comparison)
    assert ax.get_ylabel() == r"Relative deviation from IAPWS (1992) $\delta$/%"
    assert "Magnus form in kelvins (Bechtold 2015)" in legend(ax)
    # Short: symbols and units, a formulation by its first citation, in
    # two columns beyond ten curves.
    with display_options(label_detail="short"):
        ax = plot_deviations(comparison)
        values = plot_values(comparison)
    assert ax.get_xlabel() == "$t_{90}$/°C"
    assert ax.get_ylabel() == r"$\delta$/%"
    assert values.get_ylabel() == r"$e_{\mathrm{s}}$/Pa"
    assert "Bechtold (2015), eq. 54" in legend(ax)
    assert "IAPWS (1992)" in legend(values)
    assert ax.get_legend()._ncols == 2
    # Two formulations citing first Sonntag (1990) keep their labels.
    assert "Magnus form, Sonntag (1990) coefficients" in legend(ax)
    assert "Sonntag (1990) formulation over water (SO90)" in legend(ax)
    # Full: a second line, the scale of an axis, the reference's label and
    # the first citation of each formulation.
    with display_options(label_detail="full"):
        ax = plot_deviations(comparison)
    assert ax.get_xlabel() == (
        "Celsius temperature $t_{90}$/°C\n"
        "on the International Temperature Scale of 1990 (ITS-90)"
    )
    assert ax.get_ylabel().endswith(f"$\\delta$/%\n{IAPWS.label}")
    assert "Magnus form in kelvins (Bechtold 2015)\nBechtold (2015), eq. 54" in (
        legend(ax)
    )
    assert ax.get_legend()._ncols == 1


def test_authors_are_cited_as_texts_cite_them() -> None:
    from nomogram.plot import _authors

    assert _authors("Buck, A. L.") == "Buck"
    assert _authors("Wagner, W.; Pruß, A.") == "Wagner and Pruß"
    assert _authors("Dickson, A. G.; Sabine, C. L.; Christian, J. R. (eds.)") == (
        "Dickson et al."
    )
    assert _authors("IAPWS") == "IAPWS"


def test_without_a_known_source_a_formulation_keeps_its_label() -> None:
    elsewhere = load_catalog(
        [
            """
[references.elsewhere]
authors = "Nobody, N."
title = "Not in the bundled catalog"
status = "verified"

[formulations.twice]
label = "Twice"
expression = "2 * T"
fixed_units = true
output = { identifier = "q", kind = "Pressure", unit = "PA", description = "out" }
inputs = [{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "in" }]

[[formulations.twice.citations]]
reference = "elsewhere"
"""
        ]
    ).formulations["twice"]
    found = compare(
        [elsewhere], elsewhere, {"ThermodynamicTemperature": Q_([1.0, 2.0], "K")}
    )
    for detail in ("short", "full"):
        with display_options(label_detail=detail):
            assert legend(plot_values(found)) == ["Twice"]


def test_curves_far_above_the_others_go_off_scale() -> None:
    # The figure of the README: the two forms with a constant latent heat
    # reach 27 %, the others stay within 4.3 %.
    temperatures = Q_(np.linspace(-60, 110, 341), "degC")
    table = compare(SATURATION, IAPWS, {"ThermodynamicTemperature": temperatures})
    ax = plot_deviations(table)
    off = [label for label in legend(ax) if "off scale" in label]
    assert off == [
        (
            "Clausius-Clapeyron with a constant latent heat (Bechtold 2015) "
            "(off scale, up to 26.7 %)"
        ),
        (
            "Ambaum (2020) approximation with a constant latent heat "
            "(off scale, up to 26.9 %)"
        ),
    ]
    low, high = ax.get_ylim()
    assert -3.0 < low < -2.5
    assert 4.3 < high < 4.6
    # Still drawn, beyond the axis.
    assert np.nanmax(ax.lines[0].get_ydata()) > 26
    assert plot_deviations(table, off_scale=False).get_ylim()[1] > 26


def test_an_off_scale_curve_says_how_far_down_it_goes() -> None:
    x = Q_(np.array([1.0, 2.0]), "K")
    deviations = {
        "r": np.zeros(2),
        "a": np.array([0.001, np.nan]),
        "b": np.array([0.002, 0.001]),
        "c": np.array([-0.5, 0.0]),
        "d": np.full(2, np.nan),
    }
    found = Comparison(
        "r",
        {"ThermodynamicTemperature": x},
        {k: Q_(np.ones(2), "Pa") for k in deviations},
        deviations,
    )
    ax = plot_deviations(found)
    assert "c (off scale, down to -50 %)" in legend(ax)
    # The axis holds a and b, and zero; d is nowhere finite.
    assert ax.get_ylim() == pytest.approx((-0.01, 0.21))
    # Curves of comparable sizes never go off scale.
    level = {**deviations, "c": np.array([-0.005, 0.0])}
    found = Comparison("r", found.inputs, found.values, level)
    assert not [t for t in legend(plot_deviations(found)) if "off scale" in t]


@pytest.mark.parametrize(
    ("grid", "yscale", "expected"),
    [
        # From 1.9 Pa to 180 kPa: logarithmic.
        (np.linspace(-60, 110, 18), "auto", "log"),
        # From 2.3 to 4.2 kPa: linear.
        (np.linspace(20, 30, 5), "auto", "linear"),
        (np.linspace(-60, 110, 18), "linear", "linear"),
        (np.linspace(20, 30, 5), "log", "log"),
    ],
)
def test_values_spanning_decades_are_plotted_on_a_logarithmic_scale(
    grid: Any, yscale: Any, expected: str
) -> None:
    table = compare(SATURATION, IAPWS, {"ThermodynamicTemperature": Q_(grid, "degC")})
    assert plot_values(table, yscale=yscale).get_yscale() == expected


def test_an_unknown_yscale_is_refused(comparison: Comparison) -> None:
    with pytest.raises(ValueError, match="yscale must be auto, linear or log"):
        plot_values(comparison, yscale="symlog")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("unit", "values", "expected"),
    [
        # Fahrenheit is neither a Celsius nor a thermodynamic temperature.
        ("degF", [32.0, 90.0], "Temperature / °F"),
        ("degR", [492.0, 560.0], "Thermodynamic temperature $T_{90}$/°R"),
    ],
)
def test_temperature_axis_follows_the_unit(
    unit: str, values: list[float], expected: str
) -> None:
    found = compare(SATURATION, IAPWS, {"ThermodynamicTemperature": Q_(values, unit)})
    assert plot_values(found).get_xlabel() == expected


def test_without_scale_conversion_the_axes_claim_no_scale() -> None:
    # Weiss and Price took the values as given, on IPTS-48 and PSS-78:
    # neither T_90 nor S_R may label them.
    weiss = FORMULATIONS["weiss_price1980_vapour_pressure"]
    t = Q_(np.array([10.0, 20.0]), "degC")
    # Practical Salinity is a number; Reference Salinity is in g/kg.
    as_given = {"ThermodynamicTemperature": t, "SeaWaterSalinity": Q_([30.0, 35.0])}
    reference = {
        "ThermodynamicTemperature": t,
        "SeaWaterSalinity": Q_(np.array([30.0, 35.0]), "g/kg"),
    }
    ignored = compare([weiss], weiss, as_given, scale="ignore")
    ax = plot_values(ignored, input_kind="ThermodynamicTemperature")
    assert ax.get_xlabel() == "Celsius temperature $t$/°C"
    salinity = plot_values(ignored, input_kind="SeaWaterSalinity").get_xlabel()
    assert salinity == "Sea water salinity $S$"
    with display_options(axis_labels="explicit"):
        ax = plot_values(ignored, input_kind="SeaWaterSalinity")
    assert ax.get_xlabel().endswith("$S$ [1]")
    converted = compare([weiss], weiss, reference)
    ax = plot_values(converted, input_kind="SeaWaterSalinity")
    assert ax.get_xlabel().endswith(r"$S_{\mathrm{R}}$/(g/kg)")


def test_units_are_written_as_the_si_brochure_does() -> None:
    # A temperature difference is in degC, never a qualified "delta degC";
    # a product unit goes in parentheses.
    values = {"r": Q_([1.0, 2.0], "Pa*s")}
    found = Comparison(
        "r",
        {"TemperatureDifference": Q_([1.0, 2.0], "delta_degC")},
        values,
        {"r": np.zeros(2)},
    )
    ax = plot_values(found)
    assert ax.get_xlabel() == "Temperature difference / °C"
    # The middle dot of the catalog symbols, whatever the version of pint.
    assert ax.get_ylabel() == "Pa\u00b7s"


# --- Signature -------------------------------------------------------------


def signatures(figure: Any) -> list[Any]:
    return [
        a for a in figure.artists if isinstance(a, AnchoredOffsetbox | AnnotationBbox)
    ]


def drawing(mark: Any) -> Any:
    """The drawing area of a signature."""
    return mark.offsetbox if isinstance(mark, AnnotationBbox) else mark.get_child()


def inks(mark: Any) -> set[str]:
    return {
        to_hex(a.get_color())
        for a in drawing(mark).get_children()
        if isinstance(a, Line2D)
    }


def test_a_figure_drawn_by_nomogram_is_signed(comparison: Comparison) -> None:
    for draw in (plot_deviations, plot_values):
        assert len(signatures(draw(comparison).figure)) == 1


def test_a_figure_given_through_ax_is_not_signed(comparison: Comparison) -> None:
    _, ax = plt.subplots()
    plot_deviations(comparison, ax=ax)
    plot_values(comparison, ax=ax)
    assert signatures(ax.figure) == []


def test_the_signature_can_be_left_out_or_removed(comparison: Comparison) -> None:
    assert signatures(plot_deviations(comparison, signature=False).figure) == []
    figure = plot_values(comparison).figure
    (mark,) = signatures(figure)
    mark.remove()
    assert signatures(figure) == []


def test_sign_draws_the_whole_logo_and_changes_no_setting() -> None:
    before = dict(matplotlib.rcParams)
    mark = sign(plt.figure(), height=30.0)
    assert dict(matplotlib.rcParams) == before
    # Without axes, at the bottom right corner; no part in the layout.
    assert isinstance(mark, AnchoredOffsetbox)
    assert not mark.get_in_layout()
    shapes, width, height = _logo.logo()
    assert len(drawing(mark).get_children()) == len(shapes)
    assert drawing(mark).height == 30.0
    assert drawing(mark).width == pytest.approx(30.0 * width / height)


def test_the_signature_follows_the_background() -> None:
    light = sign(plt.figure())
    with plt.style.context("dark_background"):
        dark = sign(plt.figure())
    assert _logo.THEMES["light"]["ink"] in inks(light)
    assert _logo.THEMES["dark"]["ink"] in inks(dark)


@pytest.mark.parametrize("extension", ["png", "svg", "pdf"])
def test_a_signed_figure_is_saved(
    comparison: Comparison, tmp_path: Path, extension: str
) -> None:
    path = tmp_path / f"plot.{extension}"
    plot_deviations(comparison).figure.savefig(path)
    assert path.stat().st_size > 0


@pytest.mark.parametrize(
    ("detail", "size"),
    [
        ("standard", None),
        ("standard", (11.0, 6.5)),
        ("short", None),
        # A second line under the x axis, beside the signature.
        ("full", (11.0, 6.5)),
    ],
)
def test_the_signature_covers_no_text(
    detail: Any, size: tuple[float, float] | None
) -> None:
    # The figure of the README example, at the default size and at its own.
    temperatures = Q_(np.linspace(-60, 110, 341), "degC")
    table = compare(SATURATION, IAPWS, {"ThermodynamicTemperature": temperatures})
    with display_options(label_detail=detail):
        ax = plot_deviations(table)
    ax.set_title("Saturation vapour pressure over water: deviation from IAPWS")
    if size is not None:
        ax.figure.set_size_inches(*size)
    ax.figure.tight_layout()
    ax.figure.canvas.draw()
    renderer = ax.figure.canvas.get_renderer()
    (mark,) = signatures(ax.figure)
    box = mark.get_window_extent(renderer)
    # The tick labels drawn: those within the limits of the axes.
    low, high = sorted(ax.get_xlim())
    ticks = [t for t in ax.get_xticklabels() if low <= t.get_position()[0] <= high]
    texts = [
        *ticks,
        *ax.get_yticklabels(),
        ax.xaxis.label,
        ax.yaxis.label,
        ax.title,
        *ax.get_legend().get_texts(),
    ]
    covered = [
        t.get_text()
        for t in texts
        if t.get_text() and box.overlaps(t.get_window_extent(renderer))
    ]
    assert covered == []
