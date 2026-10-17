# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Plots of comparisons, with matplotlib (extra ``viz``).

matplotlib is imported inside the functions only, so that the package
works without it; a missing extra gives an explicit message
(``pip install nomogram[viz]``).

Values outside a formulation's validity domain are NaN (see
:meth:`nomogram.model.Formulation.evaluate`), so they show as gaps in the
curves: the domains are visible on the plot.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from nomogram.comparison import Comparison
from nomogram.display import symbol
from nomogram.model import Notation
from nomogram.semantics import semantic_catalog

__all__ = ["plot_deviations", "plot_values"]


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


def _abscissa(comparison: Comparison, kind: str | None) -> tuple[str, Any]:
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
    kinds = semantic_catalog().quantity_kinds
    name = kinds[kind].label if kind in kinds else kind
    return f"{name} [{quantity.units:~P}]", np.asarray(quantity.magnitude, dtype=float)


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
    comparison: Comparison, *, input_kind: str | None = None, ax: Any = None
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
    ax = _axes(ax)
    others = [k for k in comparison.relative_deviations if k != comparison.reference]
    for index, key in enumerate(others):
        deviation = comparison.relative_deviations[key]
        values = np.broadcast_to(np.asarray(deviation, dtype=float), x.shape)
        ax.plot(x, 100 * values, label=_label(comparison, key), **_style(index))
    ax.axhline(0.0, color="0.4", linewidth=0.8, linestyle="--")
    ax.set_xlabel(x_label)
    ax.set_ylabel(f"Deviation from {_label(comparison, comparison.reference)} [%]")
    ax.legend(fontsize="small")
    return ax


def plot_values(
    comparison: Comparison,
    *,
    input_kind: str | None = None,
    notation: Notation | None = None,
    ax: Any = None,
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
    unit = comparison.values[comparison.reference].units
    if reference is not None:
        ax.set_ylabel(f"{symbol(reference.output, notation, unit=False)} [{unit:~P}]")
    else:
        ax.set_ylabel(f"[{unit:~P}]")
    ax.set_xlabel(x_label)
    ax.legend(fontsize="small")
    return ax
