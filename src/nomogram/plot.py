# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Plots of comparisons, with matplotlib (extra ``viz``).

matplotlib is imported inside the functions only, so that the package
works without it; a missing extra gives an explicit message
(``pip install nomogram[viz]``).

Values outside a formulation's validity domain are NaN (see
:meth:`nomogram.model.Formulation.evaluate`), so they show as gaps in the
curves: the domains are visible on the plot.

Axis labels mark the reference scale of a kind (ITS-90 for temperatures)
only when the comparison converted the values to it (``scale="convert"``,
the default of :func:`nomogram.comparison.compare`). How much the axes
and the legend say follows the display options ``axis_detail`` and
``legend_detail``, each short, standard or full, and
``off_scale_notes`` (:class:`nomogram.display.DisplayOptions`); the
preset ``DisplayOptions.DOCUMENTATION`` gives the figures of nomogram's
documentation.

A curve whose deviation stands far above those of the others is drawn off
scale, so that it does not flatten them (:func:`plot_deviations`); values
spanning several decades are plotted on a logarithmic scale
(:func:`plot_values`).

The figures these functions create are signed with the logo, at the
right of the x-axis label (:func:`sign`); a figure given through ``ax`` is
never signed, so that plots stay reusable in a layout of one's own.
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal

import numpy as np

from nomogram.comparison import TEMPERATURE_POINTS, Comparison, feeds, same_state
from nomogram.dimensions import unit_text
from nomogram.display import (
    DisplayOptions,
    axis_label,
    display_options,
    get_display_options,
    reference_scale,
    sentence_case,
    symbol,
)
from nomogram.model import Citation, ConventionalScale, Notation
from nomogram.units import is_offset_unit, ureg

__all__ = [
    "SIGNATURE_HEIGHT",
    "plot_deviations",
    "plot_profile",
    "plot_profiles",
    "plot_values",
    "sign",
]

#: Height of the signature, in points.
SIGNATURE_HEIGHT = 16.0

#: A curve goes off scale when its largest deviation exceeds, by this
#: factor, those of all the curves left on scale.
_OFF_SCALE_RATIO = 3.0

#: Entries beyond which a legend of short labels takes two columns, and
#: the longest of them, in characters.
_LEGEND_COLUMN = 10
_SHORT_ENTRY = 30

#: Opacity of the grid of the display option ``grid``.
_GRID_ALPHA = 0.3

#: Share of a panel's width its legend or its x label may take, side by
#: side (:func:`plot_profiles`); beyond, the figure is widened.
_LEGEND_FILL = 0.9

#: Largest deviations smaller than this share of the largest of all are
#: rounding: they count as zero when curves go off scale.
_NEGLIGIBLE = 1e-9

#: A personal author, "Surname, I.": initials follow the comma.
_INITIALS = re.compile(r",\s*[A-ZÀ-Þ][.-]")


def _pyplot() -> Any:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        msg = "nomogram.plot needs matplotlib: install the extra, nomogram[viz]"
        raise ImportError(msg) from exc
    return plt


def _axes(ax: Any) -> Any:
    if ax is not None:
        return ax
    # The tight layout makes room for labels of two lines, whatever size
    # the figure is given later.
    _, created = _pyplot().subplots(layout="tight")
    return created


def _abscissa(
    comparison: Comparison,
    kind: str | None,
    notation: Notation | None = None,
    axis: str = "x",
) -> tuple[str, Any]:
    """The input plotted along ``axis``, x by default: its label and its values."""
    if kind is None:
        varying = [k for k, q in comparison.inputs.items() if np.ndim(q.magnitude) == 1]
        if len(varying) != 1:
            msg = (
                f"choose the input to plot along {axis} with input_kind; "
                f"one-dimensional inputs: {', '.join(sorted(varying)) or 'none'}"
            )
            raise ValueError(msg)
        kind = varying[0]
    if kind not in comparison.inputs:
        msg = f"no input of kind {kind!r} in the comparison"
        raise ValueError(msg)
    quantity = comparison.inputs[kind]
    name, shown = None, kind
    if kind in TEMPERATURE_POINTS:
        # The values say which temperature is plotted: in degC a Celsius
        # temperature t, in an absolute unit (K, degR) a thermodynamic
        # temperature T; another offset unit (degF) is neither.
        if quantity.units == ureg.degC:
            shown = "CelsiusTemperature"
        elif not is_offset_unit(quantity.units):
            shown = "ThermodynamicTemperature"
        else:
            name, shown = "Temperature", ""
    tex = _symbol_of(comparison, shown, notation)
    if tex and tex[0] in "tT" and kind not in TEMPERATURE_POINTS:
        # Another temperature point (a dew point) follows the values too:
        # t_d in degC, T_d in K (ISO 80000-5).
        absolute = not is_offset_unit(quantity.units)
        if quantity.units == ureg.degC:
            tex = "t" + tex[1:]
        elif absolute and quantity.dimensionality == ureg.kelvin.dimensionality:
            tex = "T" + tex[1:]
    label = _axis_text(
        name or _kind_name(shown),
        tex,
        unit_text(quantity.units),
        _scale(comparison, kind if not shown else shown),
    )
    return label, np.asarray(quantity.magnitude, dtype=float)


def _axis_text(
    name: str | None,
    tex: str | None,
    unit: str,
    scale: ConventionalScale | None,
    second: str | None = None,
) -> str:
    """An axis label at the ``axis_detail`` of the display options.

    Short, the name is left out when a symbol says it; full, a second line
    names the scale, or says what ``second`` gives instead.
    """
    detail = get_display_options().axis_detail
    if detail == "short" and tex:
        name = None
    label = axis_label(name, tex, unit, scale=scale)
    if detail == "full":
        second = second or (f"on the {scale.label}" if scale is not None else None)
        if second:
            label += f"\n{second}"
    return label


def _scale(comparison: Comparison, kind: str) -> ConventionalScale | None:
    """The scale marking an axis: the reference scale of the kind, if any.

    Only a comparison made with ``scale="convert"`` has its values on the
    reference scales; with ``"ignore"``, each formulation took them on its
    own scale, and the axes claim none.
    """
    return reference_scale(kind) if comparison.scale == "convert" else None


#: Symbols of ISO 80000-5 for the temperatures; other kinds take the
#: symbol of the reference formulation's input.
_KIND_SYMBOLS = {"ThermodynamicTemperature": "T", "CelsiusTemperature": "t"}


def _kind_name(kind: str) -> str:
    from nomogram.catalog import catalog

    kinds = catalog().kinds
    return sentence_case(kinds[kind].label) if kind in kinds else kind


def _symbol_of(
    comparison: Comparison, kind: str, notation: Notation | None
) -> str | None:
    if kind in _KIND_SYMBOLS:
        return _KIND_SYMBOLS[kind]
    reference = comparison.formulations.get(comparison.reference)
    for variable in getattr(reference, "inputs", ()):
        if same_state(variable.kind, kind):
            return symbol(variable, notation, unit=False)[1:-1]
    return None


#: Line styles taken in turn once the colour cycle (10 colours) is used up.
_LINESTYLES = ("-", "-.", ":")


def _style(index: int) -> dict[str, str]:
    """Distinct styles beyond ten curves: the colour cycle repeats."""
    return {"linestyle": _LINESTYLES[(index // 10) % len(_LINESTYLES)]}


def _label(comparison: Comparison, key: str) -> str:
    formulation = comparison.formulations.get(key)
    label = getattr(formulation, "label", None)
    return str(label) if label else key


def _authors(text: str) -> str:
    """The authors as a text cites them: Buck; Wagner and Pruß; Dickson et al.

    A personal author keeps the surname ("Buck, A. L." is Buck); a body
    keeps its whole name ("IOC, SCOR and IAPSO").
    """
    names = [
        author.split(",")[0].strip() if _INITIALS.search(author) else author.strip()
        for author in text.split(";")
    ]
    return f"{names[0]} et al." if len(names) > 2 else " and ".join(names)


def _cited(comparison: Comparison, key: str) -> str | None:
    """The first citation of a formulation: authors, year, equation.

    ``None`` when the formulation cites nothing, or a reference the bundled
    catalog does not hold (a personal one): a later citation would name
    another source.
    """
    from nomogram.catalog import catalog

    citations: tuple[Citation, ...] = tuple(
        getattr(comparison.formulations.get(key), "citations", ())
    )
    if not citations:
        return None
    reference = catalog().references.get(citations[0].reference)
    if reference is None:
        return None
    text = _authors(reference.authors)
    if reference.year is not None:
        text += f" ({reference.year})"
    if citations[0].equation:
        text += f", eq. {citations[0].equation}"
    return text


def _names(comparison: Comparison, keys: Iterable[str]) -> dict[str, str]:
    """The legend entries of formulations, at the ``legend_detail`` in force.

    Short, the first citation (``Bechtold (2015), eq. 54``), unless two
    formulations of the plot would share it: they keep their label. Full,
    the label, then the first citation on a second line.
    """
    detail = get_display_options().legend_detail
    labels = {key: _label(comparison, key) for key in keys}
    if detail == "standard":
        return labels
    cited = {key: _cited(comparison, key) for key in labels}
    if detail == "full":
        return {
            key: f"{label}\n{cited[key]}" if cited[key] else label
            for key, label in labels.items()
        }
    short = {key: cited[key] or labels[key] for key in labels}
    counts = Counter(short.values())
    return {
        key: short[key] if counts[short[key]] == 1 else labels[key] for key in labels
    }


def _grid(ax: Any) -> None:
    """A light grid behind the curves, when the display options ask for it."""
    if get_display_options().grid:
        ax.grid(alpha=_GRID_ALPHA)


def _legend(ax: Any) -> None:
    """The legend: two columns of short labels when they are many.

    Only when every entry is short: a label kept on a collision, or a note
    that a curve is off scale, would make two columns wider than the axes.
    No legend without a curve (a formulation compared with itself alone).
    """
    labels = ax.get_legend_handles_labels()[1]
    if not labels:
        return
    short = get_display_options().legend_detail == "short" and all(
        len(label) <= _SHORT_ENTRY for label in labels
    )
    columns = 2 if short and len(labels) > _LEGEND_COLUMN else 1
    ax.legend(fontsize="small", ncols=columns)


def _off_scale(curves: Mapping[str, Any]) -> dict[str, float]:
    """The curves to draw off scale, with their largest deviation.

    The largest absolute deviations of the curves, in increasing order,
    split where one exceeds the previous by more than three times, in the
    upper half: the curves above the largest such split go off scale, so
    that they do not flatten the others. At least half of the curves stay
    on scale. A curve equal to the reference to rounding (a largest
    deviation below a billionth of the largest of all) splits nothing.
    """
    peaks = {}
    for key, values in curves.items():
        finite = values[np.isfinite(values)]
        if finite.size:
            peaks[key] = float(finite[np.argmax(np.abs(finite))])
    order = sorted(peaks, key=lambda key: abs(peaks[key]))
    sizes = [abs(peaks[key]) for key in order]
    floor = _NEGLIGIBLE * max(sizes, default=0.0)
    splits = [
        (sizes[i + 1] / sizes[i], i)
        for i in range((len(sizes) + 1) // 2 - 1, len(sizes) - 1)
        if sizes[i] > floor
    ]
    ratio, index = max(splits, default=(0.0, 0))
    if ratio <= _OFF_SCALE_RATIO:
        return {}
    return {key: peaks[key] for key in order[index + 1 :]}


def _beyond(curves: Mapping[str, Any], low: Any, high: Any) -> dict[str, float]:
    """The curves leaving given y limits, with their extreme value beyond them.

    An end given as ``None`` does not bound.
    """
    bottom = -np.inf if low is None else low
    top = np.inf if high is None else high
    found = {}
    for key, values in curves.items():
        finite = values[np.isfinite(values)]
        outside = finite[(finite < bottom) | (finite > top)]
        if outside.size:
            found[key] = float(outside[np.argmax(np.abs(outside))])
    return found


def _within(curves: Mapping[str, Any], x: Any, window: Any) -> Mapping[str, Any]:
    """The points of the curves shown within x limits given, if any.

    An end given as ``None`` does not bound; the limits may be reversed.
    """
    if window is None:
        return curves
    left = -np.inf if window[0] is None else window[0]
    right = np.inf if window[1] is None else window[1]
    shown = (x >= min(left, right)) & (x <= max(left, right))
    return {key: values[shown] for key, values in curves.items()}


def _off_scale_label(label: str, peak: float) -> str:
    """The legend entry of a curve off scale: how far it goes, on its first line."""
    head, newline, tail = label.partition("\n")
    way = "up" if peak > 0 else "down"
    return f"{head} (off scale, {way} to {peak:.3g} %){newline}{tail}"


def _values_scale(curves: Iterable[Any]) -> str:
    """Logarithmic when every value is positive and they span over two decades."""
    finite = np.concatenate([values[np.isfinite(values)] for values in curves])
    if finite.size and finite.min() > 0 and finite.max() > 100 * finite.min():
        return "log"
    return "linear"


def plot_deviations(
    comparison: Comparison,
    *,
    input_kind: str | None = None,
    ax: Any = None,
    signature: bool = True,
    off_scale: bool | None = None,
    options: DisplayOptions | None = None,
    **axes: Any,
) -> Any:
    """Plot the relative deviation of each formulation from the reference, in %.

    A curve whose largest deviation exceeds those of all the others by more
    than three times is drawn off scale: the y axis holds the others, the
    curve leaves it, and its legend entry says how far it goes. At least
    half of the curves stay on scale. On axes given through ``ax``, which
    may hold other curves, the limits are left to the caller unless
    ``off_scale`` is true. Limits given (``ylim=(-1, 1)``) replace those
    chosen: the curves leaving them are off scale. An x range given
    (``xlim``) narrows what the y axis holds to the points shown. The
    display option ``off_scale_notes`` says whether legend entries tell
    how far the curves off scale go.

    Parameters
    ----------
    comparison : Comparison
        The result of :func:`nomogram.comparison.compare`.
    input_kind : str, optional
        Quantity kind of the input plotted along x; needed only when
        several inputs are one-dimensional arrays.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on; new ones are created otherwise.
    signature : bool
        Sign the figure with the logo (:func:`sign`) when the function
        creates it; a figure given through ``ax`` is never signed.
    off_scale : bool, optional
        Draw off scale the curves standing far above the others; ``False``
        holds every curve on the y axis. By default, only on axes the
        function creates.
    options : DisplayOptions, optional
        Display options for this call, such as a preset
        (``DisplayOptions.DOCUMENTATION``); those in force otherwise
        (:func:`nomogram.display.display_options`).
    **axes
        Properties of the axes, set once the curves are drawn
        (:meth:`matplotlib.axes.Axes.set`): ``ylim=(-1, 1)`` zooms in, the
        curves beyond going off scale; ``xlim=(0, 80)`` narrows the x axis,
        and the y axis holds what it shows; ``title``...

    Returns
    -------
    matplotlib.axes.Axes
        The axes, for further customisation.

    Raises
    ------
    ImportError
        If matplotlib is not installed (extra ``viz``).
    ValueError
        If the input to plot along x cannot be determined.
    """
    with display_options(options):
        x_label, x = _abscissa(comparison, input_kind)
        created = ax is None
        ax = _axes(ax)
        curves = {
            key: 100 * np.broadcast_to(np.asarray(deviation, dtype=float), x.shape)
            for key, deviation in comparison.relative_deviations.items()
            if key != comparison.reference
        }
        automatic = created if off_scale is None else off_scale
        window = axes.get("xlim")
        shown = _within(curves, x, window)
        limits = axes.get("ylim")
        if limits is not None:
            off = _beyond(shown, *limits)
        elif automatic:
            off = _off_scale(shown)
        else:
            off = {}
        names = _names(comparison, curves)
        notes = get_display_options().off_scale_notes
        for index, (key, values) in enumerate(curves.items()):
            label = names[key]
            if key in off and notes:
                label = _off_scale_label(label, off[key])
            ax.plot(x, values, label=label, **_style(index))
        ax.axhline(0.0, color="0.4", linewidth=0.8, linestyle="--")
        if limits is None and (off or (automatic and window is not None)):
            kept = np.concatenate(
                [
                    np.zeros(1),
                    *(v[np.isfinite(v)] for k, v in shown.items() if k not in off),
                ]
            )
            low, high = float(kept.min()), float(kept.max())
            if high > low:
                margin = 0.05 * (high - low)
                ax.set_ylim(low - margin, high + margin)
        ax.set_xlabel(x_label)
        label = _label(comparison, comparison.reference)
        cited = _cited(comparison, comparison.reference)
        name = f"Relative deviation from {cited or label}"
        ax.set_ylabel(_axis_text(name, r"\delta", "%", None, second=label))
        ax.set(**axes)
        _grid(ax)
        _legend(ax)
        if created and signature:
            sign(ax.figure, axes=ax)
        return ax


def plot_values(
    comparison: Comparison,
    *,
    input_kind: str | None = None,
    notation: Notation | None = None,
    ax: Any = None,
    signature: bool = True,
    yscale: Literal["auto", "linear", "log"] = "auto",
    options: DisplayOptions | None = None,
    **axes: Any,
) -> Any:
    """Plot the values of each formulation, the reference included.

    Parameters
    ----------
    comparison : Comparison
        The result of :func:`nomogram.comparison.compare`.
    input_kind : str, optional
        Quantity kind of the input plotted along x.
    notation : Notation, optional
        Notation of the y-axis symbol (for example the WMO one); the
        display options in force otherwise (:mod:`nomogram.display`).
    ax : matplotlib.axes.Axes, optional
        Axes to draw on; new ones are created otherwise.
    signature : bool
        Sign the figure with the logo (:func:`sign`) when the function
        creates it; a figure given through ``ax`` is never signed.
    yscale : {"auto", "linear", "log"}
        Scale of the y axis; ``"auto"`` is logarithmic when every value is
        positive and they span more than two decades, linear otherwise, and
        leaves the scale of axes given through ``ax`` as it is.
    options : DisplayOptions, optional
        Display options for this call, such as a preset
        (``DisplayOptions.DOCUMENTATION``); those in force otherwise
        (:func:`nomogram.display.display_options`).
    **axes
        Properties of the axes, set once the curves are drawn
        (:meth:`matplotlib.axes.Axes.set`): ``ylim``, ``xlim``, ``title``...

    Returns
    -------
    matplotlib.axes.Axes
        The axes, for further customisation.

    Raises
    ------
    ImportError
        If matplotlib is not installed (extra ``viz``).
    ValueError
        If the input to plot along x cannot be determined, or ``yscale``
        is none of its values.
    """
    if yscale not in ("auto", "linear", "log"):
        msg = f"yscale must be auto, linear or log, not {yscale!r}"
        raise ValueError(msg)
    with display_options(options):
        x_label, x = _abscissa(comparison, input_kind, notation)
        created = ax is None
        ax = _axes(ax)
        curves = {
            key: np.broadcast_to(np.asarray(quantity.magnitude, dtype=float), x.shape)
            for key, quantity in comparison.values.items()
        }
        names = _names(comparison, curves)
        for index, (key, values) in enumerate(curves.items()):
            style = (
                {"color": "black", "linestyle": "--"}
                if key == comparison.reference
                else _style(index)
            )
            ax.plot(x, values, label=names[key], **style)
        if yscale != "auto":
            ax.set_yscale(yscale)
        elif created:
            # Points of an interval scale (degC) have no ratio: never logarithmic.
            offset = is_offset_unit(comparison.values[comparison.reference].units)
            ax.set_yscale("linear" if offset else _values_scale(curves.values()))
        ax.set_ylabel(_values_label(comparison, notation))
        ax.set_xlabel(x_label)
        ax.set(**axes)
        _grid(ax)
        _legend(ax)
        if created and signature:
            sign(ax.figure, axes=ax)
        return ax


def _values_label(comparison: Comparison, notation: Notation | None) -> str:
    """The label of the values: the output of the reference formulation."""
    reference = comparison.formulations.get(comparison.reference)
    unit = unit_text(comparison.values[comparison.reference].units)
    if reference is None:
        return axis_label(None, None, unit)
    output = reference.output
    return _axis_text(
        _kind_name(output.kind),
        symbol(output, notation, unit=False)[1:-1],
        unit,
        _scale(comparison, output.kind),
    )


def plot_profile(
    comparison: Comparison,
    *,
    input_kind: str | None = None,
    notation: Notation | None = None,
    ax: Any = None,
    signature: bool = True,
    options: DisplayOptions | None = None,
    **axes: Any,
) -> Any:
    """Plot a vertical profile: the values of each formulation against the input.

    The input, a vertical coordinate, goes along y and the values along x,
    the reference included. On axes the function creates, a pressure goes
    downwards on a logarithmic axis, labelled with plain numbers, as on
    soundings; a height upwards on a linear one.

    Parameters
    ----------
    comparison : Comparison
        The result of :func:`nomogram.comparison.compare`, over a vertical
        coordinate.
    input_kind : str, optional
        Quantity kind of the vertical coordinate.
    notation : Notation, optional
        Notation of the symbol of the values; the display options in force
        otherwise (:mod:`nomogram.display`).
    ax : matplotlib.axes.Axes, optional
        Axes to draw on; new ones are created otherwise.
    signature : bool
        Sign the figure with the logo (:func:`sign`) when the function
        creates it; a figure given through ``ax`` is never signed.
    options : DisplayOptions, optional
        Display options for this call, such as a preset
        (``DisplayOptions.DOCUMENTATION``); those in force otherwise
        (:func:`nomogram.display.display_options`).
    **axes
        Properties of the axes, set once the curves are drawn
        (:meth:`matplotlib.axes.Axes.set`): ``ylim=(1000, 100)``,
        ``xlim``, ``title``...

    Returns
    -------
    matplotlib.axes.Axes
        The axes, for further customisation.

    Raises
    ------
    ImportError
        If matplotlib is not installed (extra ``viz``).
    ValueError
        If the vertical coordinate cannot be determined.
    """
    with display_options(options):
        kind = input_kind or _varying_kind(comparison)
        y_label, y = _abscissa(comparison, kind, notation, axis="y")
        created = ax is None
        ax = _axes(ax)
        curves = {
            key: np.broadcast_to(np.asarray(quantity.magnitude, dtype=float), y.shape)
            for key, quantity in comparison.values.items()
        }
        names = _names(comparison, curves)
        for index, (key, values) in enumerate(curves.items()):
            style = (
                {"color": "black", "linestyle": "--"}
                if key == comparison.reference
                else _style(index)
            )
            ax.plot(values, y, label=names[key], **style)
        if created:
            _vertical_axis(ax, kind)
        ax.set_xlabel(_values_label(comparison, notation))
        ax.set_ylabel(y_label)
        ax.set(**axes)
        _grid(ax)
        _legend(ax)
        if created and signature:
            sign(ax.figure, axes=ax)
        return ax


def plot_profiles(
    comparisons: Iterable[Comparison],
    *,
    input_kind: str | None = None,
    notation: Notation | None = None,
    signature: bool = True,
    options: DisplayOptions | None = None,
    **axes: Any,
) -> tuple[Any, ...]:
    """Plot vertical profiles side by side, one panel per comparison.

    Quantities of different kinds share no axis of values: a temperature,
    a specific humidity and a relative humidity each get a panel, drawn as
    by :func:`plot_profile`, and the panels share the vertical coordinate.

    Parameters
    ----------
    comparisons : iterable of Comparison
        Results of :func:`nomogram.comparison.compare` over one vertical
        coordinate, in the order of the panels, from left to right.
    input_kind : str, optional
        Quantity kind of the vertical coordinate.
    notation : Notation, optional
        Notation of the symbols of the values; the display options in force
        otherwise (:mod:`nomogram.display`).
    signature : bool
        Sign the figure with the logo (:func:`sign`), under the last panel.
    options : DisplayOptions, optional
        Display options for this call, such as a preset
        (``DisplayOptions.DOCUMENTATION``); those in force otherwise
        (:func:`nomogram.display.display_options`).
    **axes
        Properties set on every panel once the curves are drawn
        (:meth:`matplotlib.axes.Axes.set`), such as ``ylim=(850, 500)``;
        those of one panel, on the axes returned.

    Returns
    -------
    tuple of matplotlib.axes.Axes
        The panels, from left to right.

    Raises
    ------
    ImportError
        If matplotlib is not installed (extra ``viz``).
    ValueError
        If there is no comparison, or the vertical coordinate is not one
        kind, determined, for every panel.
    """
    comparisons = list(comparisons)
    if not comparisons:
        msg = "plot_profiles needs at least one comparison"
        raise ValueError(msg)
    with display_options(options):
        kinds = {input_kind or _varying_kind(c) for c in comparisons}
        if len(kinds) != 1 or None in kinds:
            msg = (
                "the panels share their vertical coordinate: compare over one "
                "input kind, or give input_kind"
            )
            raise ValueError(msg)
        (kind,) = kinds
        assert kind is not None  # checked above
        comparisons = _one_unit(comparisons, kind)
        figure, panels = _pyplot().subplots(
            1,
            len(comparisons),
            sharey=True,
            squeeze=False,
            figsize=(max(6.4, 3.2 * len(comparisons)), 4.8),
        )
        row = tuple(panels[0])
        for index, (comparison, ax) in enumerate(zip(comparisons, row, strict=True)):
            plot_profile(comparison, input_kind=kind, notation=notation, ax=ax)
            if index:
                ax.set_ylabel("")
        # Shared: the scale and the direction set on one panel hold for all.
        _vertical_axis(row[0], kind)
        for ax in row:
            ax.set(**axes)
        # The signature in a band of its own, under the labels of the x axes,
        # which the last panel brings to the right edge.
        band = (SIGNATURE_HEIGHT + 8.0) / (72.0 * 4.8) if signature else 0.0
        figure.set_layout_engine("tight", rect=(0.0, band, 1.0, 1.0))
        _fit_text(figure, row)
        if signature:
            sign(figure)
        return row


def _one_unit(comparisons: list[Comparison], kind: str) -> list[Comparison]:
    """The comparisons, their vertical coordinate in the unit of the first."""
    first = comparisons[0].inputs.get(kind)
    if first is None:
        return comparisons
    converted = []
    for comparison in comparisons:
        quantity = comparison.inputs.get(kind)
        if quantity is not None and quantity.units != first.units:
            inputs = {**comparison.inputs, kind: quantity.to(first.units)}
            comparison = dataclasses.replace(comparison, inputs=inputs)
        converted.append(comparison)
    return converted


def _fit_text(figure: Any, row: tuple[Any, ...]) -> None:
    """Widen the figure until the legend and the x label of every panel fit in it."""
    for _ in range(3):
        figure.draw_without_rendering()
        renderer = figure.canvas.get_renderer()
        texts = [
            (text, ax)
            for ax in row
            for text in (ax.get_legend(), ax.xaxis.label)
            if text is not None and text.get_visible()
        ]
        fill = max(
            (
                text.get_window_extent(renderer).width
                / ax.get_window_extent(renderer).width
                for text, ax in texts
            ),
            default=0.0,
        )
        if fill <= _LEGEND_FILL:
            return
        width, height = figure.get_size_inches()
        figure.set_size_inches(width * fill / _LEGEND_FILL, height)


def _vertical_axis(ax: Any, kind: str | None) -> None:
    """A pressure downwards on a logarithmic axis, labelled with plain numbers."""
    if kind is None or not feeds(kind, "Pressure"):
        return
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(subs=(1.0, 2.0, 3.0, 5.0)))
    # Each tick on its own: a shared offset or precision would print 0.1 hPa as 0.
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.invert_yaxis()


def _varying_kind(comparison: Comparison) -> str | None:
    """The only one-dimensional input, if there is one: a missing kind."""
    varying = [k for k, q in comparison.inputs.items() if np.ndim(q.magnitude) == 1]
    return varying[0] if len(varying) == 1 else None


def sign(figure: Any, *, axes: Any = None, height: float = SIGNATURE_HEIGHT) -> Any:
    """Sign a figure with the logo, at its right edge.

    The logo is drawn with matplotlib artists, ``height`` points high
    whatever the size of the figure, and stays vector in SVG and PDF. Its
    colours follow the background of the figure, light or dark. It takes
    no part in the layout, but a figure saved with ``bbox_inches="tight"``
    keeps it whole; no setting of matplotlib is changed.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The figure to sign.
    axes : matplotlib.axes.Axes, optional
        Axes whose x-axis label the signature follows: it sits at the right
        edge of the figure, on the line of that label, below the tick
        labels whatever the layout. Without, at the bottom right corner.
    height : float
        Height of the logo, in points.

    Returns
    -------
    matplotlib.artist.Artist
        The signature; its ``remove()`` takes it off.
    """
    from matplotlib.colors import to_rgba
    from matplotlib.offsetbox import AnchoredOffsetbox, AnnotationBbox, DrawingArea

    from nomogram import _logo

    shapes, width, logo_height = _logo.logo()
    scale = height / logo_height
    red, green, blue, alpha = to_rgba(figure.get_facecolor())
    dark = alpha > 0 and 0.2126 * red + 0.7152 * green + 0.0722 * blue < 0.5
    colours = _logo.THEMES["dark" if dark else "light"]

    def point(p: tuple[float, float]) -> tuple[float, float]:
        # SVG units, y downward, to points, y upward.
        return p[0] * scale, (logo_height - p[1]) * scale

    area = DrawingArea(width * scale, height, clip=False)
    for shape in shapes:
        area.add_artist(_artist(shape, point, scale, colours))
    box: Any
    if axes is None:
        box = AnchoredOffsetbox(
            loc="lower right",
            child=area,
            pad=0.0,
            borderpad=0.3,
            frameon=False,
            bbox_to_anchor=(1.0, 0.0),
            bbox_transform=figure.transFigure,
        )
    else:
        # x: the right edge of the figure; y: the middle of the axis label.
        box = AnnotationBbox(
            area,
            (1.0, 0.5),
            xycoords=("figure fraction", axes.xaxis.label),
            xybox=(-4.0, 0.0),
            boxcoords="offset points",
            box_alignment=(1.0, 0.5),
            frameon=False,
            pad=0.0,
        )
    figure.add_artist(box)
    return box


def _artist(
    shape: Any,
    point: Callable[[tuple[float, float]], tuple[float, float]],
    scale: float,
    colours: Mapping[str, str],
) -> Any:
    """A shape of the logo as a matplotlib artist."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Ellipse

    from nomogram import _logo

    ink, accent = colours["ink"], colours["accent"]
    strokes = {
        "ink": (ink, 1.0),
        "fine": (ink, _logo.FINE_OPACITY),
        "read": (accent, 1.0),
    }
    fills = {"sea": colours["sea"], "dot": accent, "node": ink}
    if isinstance(shape, _logo.Line | _logo.Polyline):
        ends = (
            (shape.start, shape.end) if isinstance(shape, _logo.Line) else shape.points
        )
        xs, ys = zip(*(point(p) for p in ends), strict=True)
        colour, opacity = strokes[shape.role]
        return Line2D(
            xs,
            ys,
            color=colour,
            alpha=opacity,
            linewidth=shape.width * scale,
            solid_capstyle="round",
            solid_joinstyle="round",
        )
    if isinstance(shape, _logo.Circle):
        rx = ry = shape.radius
    else:
        rx, ry = shape.rx, shape.ry
    centre, size = point(shape.centre), (2 * rx * scale, 2 * ry * scale)
    if shape.width:
        colour, opacity = strokes[shape.role]
        return Ellipse(
            centre,
            *size,
            facecolor="none",
            edgecolor=colour,
            alpha=opacity,
            linewidth=shape.width * scale,
        )
    return Ellipse(centre, *size, facecolor=fills[shape.role], edgecolor="none")
