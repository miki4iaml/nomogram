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
the default of :func:`nomogram.comparison.compare`).

The figures these functions create are signed with the logo, at the
right of the x-axis label (:func:`sign`); a figure given through ``ax`` is
never signed, so that plots stay reusable in a layout of one's own.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from nomogram.comparison import TEMPERATURE_POINTS, Comparison, same_state
from nomogram.dimensions import unit_text
from nomogram.display import axis_label, reference_scale, sentence_case, symbol
from nomogram.model import ConventionalScale, Notation
from nomogram.units import is_offset_unit, ureg

__all__ = ["SIGNATURE_HEIGHT", "plot_deviations", "plot_values", "sign"]

#: Height of the signature, in points.
SIGNATURE_HEIGHT = 16.0


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
    label = axis_label(
        name or _kind_name(shown),
        _symbol_of(comparison, shown, notation),
        unit_text(quantity.units),
        scale=_scale(comparison, kind if not shown else shown),
    )
    return label, np.asarray(quantity.magnitude, dtype=float)


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


def plot_deviations(
    comparison: Comparison,
    *,
    input_kind: str | None = None,
    ax: Any = None,
    signature: bool = True,
) -> Any:
    """Plot the relative deviation of each formulation from the reference, in %.

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
    others = [k for k in comparison.relative_deviations if k != comparison.reference]
    for index, key in enumerate(others):
        deviation = comparison.relative_deviations[key]
        values = np.broadcast_to(np.asarray(deviation, dtype=float), x.shape)
        ax.plot(x, 100 * values, label=_label(comparison, key), **_style(index))
    ax.axhline(0.0, color="0.4", linewidth=0.8, linestyle="--")
    ax.set_xlabel(x_label)
    name = f"Relative deviation from {_label(comparison, comparison.reference)}"
    ax.set_ylabel(axis_label(name, r"\delta", "%"))
    ax.legend(fontsize="small")
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
    x_label, x = _abscissa(comparison, input_kind, notation)
    created = ax is None
    ax = _axes(ax)
    for index, (key, quantity) in enumerate(comparison.values.items()):
        values = np.broadcast_to(np.asarray(quantity.magnitude, dtype=float), x.shape)
        style = (
            {"color": "black", "linestyle": "--"}
            if key == comparison.reference
            else _style(index)
        )
        ax.plot(x, values, label=_label(comparison, key), **style)
    reference = comparison.formulations.get(comparison.reference)
    unit = unit_text(comparison.values[comparison.reference].units)
    if reference is not None:
        output = reference.output
        ax.set_ylabel(
            axis_label(
                _kind_name(output.kind),
                symbol(output, notation, unit=False)[1:-1],
                unit,
                scale=_scale(comparison, output.kind),
            )
        )
    else:
        ax.set_ylabel(axis_label(None, None, unit))
    ax.set_xlabel(x_label)
    ax.legend(fontsize="small")
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
