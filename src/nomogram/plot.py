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
``legend_detail``, each short, standard or full
(:class:`nomogram.display.DisplayOptions`).

A curve whose deviation stands far above those of the others is drawn off
scale, so that it does not flatten them (:func:`plot_deviations`); values
spanning several decades are plotted on a logarithmic scale
(:func:`plot_values`).

The figures these functions create are signed with the logo, at the
right of the x-axis label (:func:`sign`); a figure given through ``ax`` is
never signed, so that plots stay reusable in a layout of one's own.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal

import numpy as np

from nomogram.comparison import TEMPERATURE_POINTS, Comparison, same_state
from nomogram.dimensions import unit_text
from nomogram.display import (
    axis_label,
    get_display_options,
    reference_scale,
    sentence_case,
    symbol,
)
from nomogram.model import Citation, ConventionalScale, Notation
from nomogram.units import is_offset_unit, ureg

__all__ = ["SIGNATURE_HEIGHT", "plot_deviations", "plot_values", "sign"]

#: Height of the signature, in points.
SIGNATURE_HEIGHT = 16.0

#: A curve goes off scale when its largest deviation exceeds, by this
#: factor, those of all the curves left on scale.
_OFF_SCALE_RATIO = 3.0

#: Entries beyond which a legend of short labels takes two columns.
_LEGEND_COLUMN = 10


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
    _, created = _pyplot().subplots()
    return created


def _abscissa(
    comparison: Comparison, kind: str | None, notation: Notation | None = None
) -> tuple[str, Any]:
    """The input plotted along x: its label and its values."""
    if kind is None:
        varying = [k for k, q in comparison.inputs.items() if np.ndim(q.magnitude) == 1]
        if len(varying) != 1:
            msg = (
                "choose the input to plot along x with input_kind; "
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
    label = _axis_text(
        name or _kind_name(shown),
        _symbol_of(comparison, shown, notation),
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
    """The authors as a text cites them: Buck; Wagner and Pruß; Dickson et al."""
    names = [author.split(",")[0].strip() for author in text.split(";")]
    return f"{names[0]} et al." if len(names) > 2 else " and ".join(names)


def _sources(comparison: Comparison, key: str) -> list[str]:
    """The citations of a formulation: authors, year, equation."""
    from nomogram.catalog import catalog

    references = catalog().references
    citations: Iterable[Citation] = getattr(
        comparison.formulations.get(key), "citations", ()
    )
    found = []
    for citation in citations:
        reference = references.get(citation.reference)
        if reference is None:
            continue
        text = _authors(reference.authors)
        if reference.year is not None:
            text += f" ({reference.year})"
        if citation.equation:
            text += f", eq. {citation.equation}"
        found.append(text)
    return found


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
    sources = {key: _sources(comparison, key) for key in labels}
    if detail == "full":
        return {
            key: f"{label}\n{sources[key][0]}" if sources[key] else label
            for key, label in labels.items()
        }
    short = {key: (sources[key] or [labels[key]])[0] for key in labels}
    counts = Counter(short.values())
    return {
        key: short[key] if counts[short[key]] == 1 else labels[key] for key in labels
    }


def _legend(ax: Any) -> None:
    """The legend: two columns of short labels when they are many.

    Longer labels in two columns would be wider than the axes.
    """
    entries = len(ax.get_legend_handles_labels()[1])
    short = get_display_options().legend_detail == "short"
    ax.legend(fontsize="small", ncols=2 if short and entries > _LEGEND_COLUMN else 1)


def _off_scale(curves: Mapping[str, Any]) -> dict[str, float]:
    """The curves to draw off scale, with their largest deviation.

    The largest absolute deviations of the curves, in increasing order,
    split where one exceeds the previous by more than three times, in the
    upper half: the curves above the largest such split go off scale, so
    that they do not flatten the others. At least half of the curves stay
    on scale.
    """
    peaks = {}
    for key, values in curves.items():
        finite = values[np.isfinite(values)]
        if finite.size:
            peaks[key] = float(finite[np.argmax(np.abs(finite))])
    order = sorted(peaks, key=lambda key: abs(peaks[key]))
    sizes = [abs(peaks[key]) for key in order]
    splits = [
        (sizes[i + 1] / sizes[i], i)
        for i in range((len(sizes) + 1) // 2 - 1, len(sizes) - 1)
        if sizes[i] > 0
    ]
    ratio, index = max(splits, default=(0.0, 0))
    if ratio <= _OFF_SCALE_RATIO:
        return {}
    return {key: peaks[key] for key in order[index + 1 :]}


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
    off_scale: bool = True,
) -> Any:
    """Plot the relative deviation of each formulation from the reference, in %.

    A curve whose largest deviation exceeds those of all the others by more
    than three times is drawn off scale: the y axis holds the others, the
    curve leaves it, and its legend entry says how far it goes. At least
    half of the curves stay on scale.

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
    off_scale : bool
        Draw off scale the curves standing far above the others; ``False``
        holds every curve on the y axis.

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
    x_label, x = _abscissa(comparison, input_kind)
    created = ax is None
    ax = _axes(ax)
    curves = {
        key: 100 * np.broadcast_to(np.asarray(deviation, dtype=float), x.shape)
        for key, deviation in comparison.relative_deviations.items()
        if key != comparison.reference
    }
    off = _off_scale(curves) if off_scale else {}
    names = _names(comparison, curves)
    for index, (key, values) in enumerate(curves.items()):
        label = _off_scale_label(names[key], off[key]) if key in off else names[key]
        ax.plot(x, values, label=label, **_style(index))
    ax.axhline(0.0, color="0.4", linewidth=0.8, linestyle="--")
    if off:
        kept = np.concatenate(
            [v[np.isfinite(v)] for k, v in curves.items() if k not in off]
        )
        low, high = min(0.0, float(kept.min())), max(0.0, float(kept.max()))
        margin = 0.05 * (high - low)
        ax.set_ylim(low - margin, high + margin)
    ax.set_xlabel(x_label)
    label = _label(comparison, comparison.reference)
    cited = _sources(comparison, comparison.reference)
    name = f"Relative deviation from {cited[0] if cited else label}"
    ax.set_ylabel(_axis_text(name, r"\delta", "%", None, second=label))
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
        positive and they span more than two decades, linear otherwise.

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
    chosen: str = yscale
    if yscale == "auto":
        # Points of an interval scale (degC) have no ratio: never logarithmic.
        offset = is_offset_unit(comparison.values[comparison.reference].units)
        chosen = "linear" if offset else _values_scale(curves.values())
    ax.set_yscale(chosen)
    reference = comparison.formulations.get(comparison.reference)
    unit = unit_text(comparison.values[comparison.reference].units)
    if reference is not None:
        output = reference.output
        ax.set_ylabel(
            _axis_text(
                _kind_name(output.kind),
                symbol(output, notation, unit=False)[1:-1],
                unit,
                _scale(comparison, output.kind),
            )
        )
    else:
        ax.set_ylabel(axis_label(None, None, unit))
    ax.set_xlabel(x_label)
    _legend(ax)
    if created and signature:
        sign(ax.figure, axes=ax)
    return ax


def sign(figure: Any, *, axes: Any = None, height: float = SIGNATURE_HEIGHT) -> Any:
    """Sign a figure with the logo, at its right edge.

    The logo is drawn with matplotlib artists, ``height`` points high
    whatever the size of the figure, and stays vector in SVG and PDF. Its
    colours follow the background of the figure, light or dark. It takes
    no part in the layout, and no setting of matplotlib is changed.

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
    box.set_in_layout(False)
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
