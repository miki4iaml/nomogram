# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Display of formulations: LaTeX, plot labels, Markdown and notebooks.

Everything derives from one LaTeX string, produced by
:func:`nomogram.expression.to_latex` from the SymPy expression:

- :func:`render` gives a :class:`Rendering`: the equation in LaTeX, as a
  matplotlib label (``mathtext``), and in Markdown with the meaning and
  unit of each symbol;
- :func:`symbol` gives the label of one variable, for an axis or a
  legend;
- :func:`table` gives a Markdown table of several formulations;
- :func:`axis_label` gives the label of a plot axis, in the style of the
  ``axis_labels`` option, with :func:`reference_scale` and
  :func:`sentence_case` as helpers.

In a Jupyter notebook, a :class:`Rendering` or a :class:`FormulaTable`
left at the end of a cell displays itself, through ``_repr_markdown_``;
nomogram never imports IPython. Its Markdown string also works with
``IPython.display.display_markdown(text, raw=True)``, on GitHub, or in
Sphinx and MkDocs pages.

The typography follows :class:`DisplayOptions`. By default every product
shows a multiplication sign (×), so that a juxtaposition such as RH can
never be read as a product, and descriptive subscripts are upright, as
in ISO 80000-2. Options are set at three levels, highest priority
first:

1. keywords of a call: ``render(f, mul_symbol="dot")``;
2. a reusable :class:`DisplayOptions`: ``render(f, options=compact)``;
3. a block: ``with display_options(decimal_separator="comma"): ...``,
   held in a :class:`contextvars.ContextVar` as ``numpy.printoptions``
   is: it applies to the current thread or task only, and is restored
   when the block ends. There is no global setter.
"""

from __future__ import annotations

import contextlib
import dataclasses
import re
from collections.abc import Iterable, Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cached_property
from typing import Any, ClassVar, Literal

import sympy

from nomogram.dimensions import DimensionError, unit_text
from nomogram.expression import to_latex
from nomogram.model import (
    Coefficient,
    ConventionalScale,
    Formulation,
    Notation,
    Variable,
)
from nomogram.semantics import semantic_catalog

__all__ = [
    "DisplayOptions",
    "FormulaTable",
    "Rendering",
    "axis_label",
    "display_options",
    "get_display_options",
    "reference_scale",
    "render",
    "sentence_case",
    "symbol",
    "table",
]

MulSymbol = Literal["times", "dot", "ldot"] | None
DecimalSeparator = Literal["period", "comma"]
AxisLabels = Literal["si", "explicit", "simple"]

_MUL_SYMBOLS = ("times", "dot", "ldot", None)
_DECIMAL_SEPARATORS = ("period", "comma")
_AXIS_LABELS = ("si", "explicit", "simple")

#: How the origin of a coefficient unit reads in a legend.
_ORIGINS: Mapping[str, str] = {
    "stated": "from the source",
    "added": "added by nomogram",
    "inferred": "inferred by nomogram",
}

#: Units shown without a symbol (QUDT's symbol for UNITLESS is a CJK sign).
_NO_SYMBOL = frozenset({"UNITLESS"})


@dataclass(frozen=True)
class DisplayOptions:
    """Typography of displayed formulas.

    The first two fields keep the names of the SymPy printer settings they
    are passed to.

    Attributes
    ----------
    mul_symbol : {"times", "dot", "ldot", None}
        Multiplication sign: × (default), a centred dot, a low dot, or
        ``None`` for juxtaposition.
    decimal_separator : {"period", "comma"}
        Decimal separator of the numbers shown.
    upright : bool
        Whether descriptive subscripts and abbreviations are upright
        (:func:`nomogram.expression.upright_symbol`); a notation always
        takes priority.
    values : bool
        Whether coefficients appear as their values instead of their
        symbols.
    axis_labels : {"si", "explicit", "simple"}
        How axis labels read (:func:`axis_label`): the quotient of the
        quantity by its unit, the scale as a subscript of the symbol, as
        the SI Brochure writes them (``t₉₀/°C``, default); name, symbol,
        unit in brackets and scale in braces (``t [°C] {ITS-90}``); or
        name, symbol and unit only (``t [°C]``).
    """

    mul_symbol: MulSymbol = "times"
    decimal_separator: DecimalSeparator = "period"
    upright: bool = True
    values: bool = False
    axis_labels: AxisLabels = "si"

    #: SymPy's own rendering: juxtaposition, default symbols.
    SYMPY: ClassVar[DisplayOptions]

    def __post_init__(self) -> None:
        if self.mul_symbol not in _MUL_SYMBOLS:
            msg = f"mul_symbol must be one of {_MUL_SYMBOLS}, not {self.mul_symbol!r}"
            raise ValueError(msg)
        if self.decimal_separator not in _DECIMAL_SEPARATORS:
            msg = (
                f"decimal_separator must be one of {_DECIMAL_SEPARATORS}, "
                f"not {self.decimal_separator!r}"
            )
            raise ValueError(msg)
        if self.axis_labels not in _AXIS_LABELS:
            msg = f"axis_labels must be one of {_AXIS_LABELS}, not {self.axis_labels!r}"
            raise ValueError(msg)


DisplayOptions.SYMPY = DisplayOptions(mul_symbol=None, upright=False)

_DEFAULT = DisplayOptions()
_OPTIONS: ContextVar[DisplayOptions] = ContextVar(
    "nomogram_display_options", default=_DEFAULT
)


def get_display_options() -> DisplayOptions:
    """The options in force: those of the innermost :func:`display_options`."""
    return _OPTIONS.get()


@contextlib.contextmanager
def display_options(
    options: DisplayOptions | None = None, **overrides: Any
) -> Iterator[DisplayOptions]:
    """Set display options for a block, in the current thread or task.

    Parameters
    ----------
    options : DisplayOptions, optional
        Options to start from; those in force otherwise.
    **overrides
        Fields of :class:`DisplayOptions` to change.

    Yields
    ------
    DisplayOptions
        The options in force inside the block.

    Examples
    --------
    >>> with display_options(mul_symbol="dot") as options:
    ...     options.mul_symbol
    'dot'
    """
    token = _OPTIONS.set(_resolve(options, overrides))
    try:
        yield _OPTIONS.get()
    finally:
        _OPTIONS.reset(token)


def _resolve(
    options: DisplayOptions | None, overrides: Mapping[str, Any]
) -> DisplayOptions:
    base = options if options is not None else _OPTIONS.get()
    return dataclasses.replace(base, **overrides) if overrides else base


def _tex(expr: Any, symbols: Mapping[str, str], options: DisplayOptions) -> str:
    return to_latex(
        expr,
        symbols,
        mul_symbol=options.mul_symbol,
        decimal_separator=options.decimal_separator,
        upright=options.upright,
    )


def _identifier(name: str, symbols: Mapping[str, str], options: DisplayOptions) -> str:
    return _tex(sympy.Symbol(name, real=True), symbols, options)


def _number(value: float, options: DisplayOptions) -> str:
    """A number in LaTeX, with the digits of the catalog.

    A power of ten is always written with ×, whatever ``mul_symbol``: the
    SI Brochure (9th edition, section 5.4.6) allows only × between
    numbers.
    """
    return str(
        sympy.latex(
            sympy.Float(repr(value)),
            mul_symbol="times",
            decimal_separator=options.decimal_separator,
        )
    )


def _plain_number(value: float, options: DisplayOptions) -> str:
    text = repr(value).removesuffix(".0")
    return text.replace(".", ",") if options.decimal_separator == "comma" else text


def _unit(key: str | None) -> str:
    """The symbol of a unit, as text; empty for a number without unit."""
    if key is None or key in _NO_SYMBOL:
        return ""
    unit = semantic_catalog().units.get(key)
    return unit.symbol if unit is not None and unit.symbol else key


def _with_unit(text: str, unit: str | None) -> str:
    symbol = _unit(unit)
    return f"{text} {symbol}" if symbol else text


def _coefficient_unit(formulation: Formulation, coefficient: Coefficient) -> str:
    """The unit of a coefficient and its origin, as text.

    For example ``°C (unit inferred by nomogram)``, ``K (unit from the
    source)`` or, for a pure number, ``(pure number, inferred by
    nomogram)``. The origin is shown only in the legend of a single
    formulation, never in tables or plot labels.
    """
    try:
        found = formulation.coefficient_units[coefficient.identifier]
    except DimensionError:
        return _unit(coefficient.unit)
    if found.origin is None:
        return "(unit undetermined)"
    origin = _ORIGINS[found.origin]
    text = unit_text(found.unit)
    return f"{text} (unit {origin})" if text else f"(pure number, {origin})"


@dataclass(frozen=True, repr=False)
class Rendering:
    """A formulation displayed in one notation, with given options.

    Attributes
    ----------
    formulation : Formulation
        The formulation displayed.
    notation : Notation or None
        The notation of its symbols.
    options : DisplayOptions
        The typography.
    """

    formulation: Formulation
    notation: Notation | None
    options: DisplayOptions

    @cached_property
    def _symbols(self) -> Mapping[str, str]:
        symbols = dict(self.notation.symbols) if self.notation else {}
        if self.options.values:
            for coefficient in self.formulation.coefficients:
                number = _number(coefficient.value, self.options)
                negative = coefficient.value < 0
                symbols[coefficient.identifier] = (
                    rf"\left({number}\right)" if negative else number
                )
        return symbols

    @cached_property
    def latex(self) -> str:
        """The equation in LaTeX, without dollar signs."""
        formulation = self.formulation
        left = _identifier(formulation.output.identifier, self._symbols, self.options)
        right = _tex(formulation.sympy_expression, self._symbols, self.options)
        return f"{left} = {right}"

    @property
    def mathtext(self) -> str:
        """The equation between dollar signs, for a matplotlib title or label."""
        return f"${self.latex}$"

    @cached_property
    def markdown(self) -> str:
        """The name, the equation and the meaning of each symbol, in Markdown."""
        formulation, options = self.formulation, self.options
        symbols = dict(self.notation.symbols) if self.notation else {}
        lines = [
            f"**{formulation.label}**",
            "",
            "$$",
            self.latex,
            "$$",
            "",
            "where",
            "",
        ]
        for variable in (formulation.output, *formulation.inputs):
            label = _identifier(variable.identifier, symbols, options)
            unit = _unit(variable.unit)
            meaning = (
                f"{variable.description} [{unit}]" if unit else variable.description
            )
            lines.append(f"- ${label}$: {meaning}")
        if not options.values:
            for coefficient in formulation.coefficients:
                label = _identifier(coefficient.identifier, symbols, options)
                value = f"${label} = {_number(coefficient.value, options)}$"
                unit = _coefficient_unit(formulation, coefficient)
                lines.append(f"- {value} {unit}" if unit else f"- {value}")
        for constant in formulation.constants:
            label = _identifier(constant.identifier, symbols, options)
            value = f"${label} = {_number(constant.value, options)}$"
            lines.append(
                f"- {_with_unit(value, constant.unit)}: {constant.description}"
            )
        if formulation.fixed_units and formulation.coefficients:
            held = [
                f"${_identifier(v.identifier, symbols, options)}$ in {_unit(v.unit)}"
                for v in (formulation.output, *formulation.inputs)
                if _unit(v.unit)
            ]
            lines += ["", f"The coefficients hold for {', '.join(held)} only."]
        derivation = formulation.derivation
        if derivation is not None and derivation.method == "composition":
            parts = " and ".join(
                f"{key} ({identifier})" for identifier, key in derivation.parts.items()
            )
            lines += ["", f"Composed of {parts} in {derivation.source}."]
        return "\n".join(lines) + "\n"

    def _repr_markdown_(self) -> str:
        return self.markdown

    def __repr__(self) -> str:
        notation = self.notation.key if self.notation else None
        return f"Rendering({self.formulation.key!r}, notation={notation!r})"


def render(
    formulation: Formulation,
    notation: Notation | None = None,
    *,
    options: DisplayOptions | None = None,
    **overrides: Any,
) -> Rendering:
    """Display a formulation.

    Parameters
    ----------
    formulation : Formulation
        The formulation to display.
    notation : Notation, optional
        The notation of its symbols (for example the WMO one).
    options : DisplayOptions, optional
        Options to start from; those in force otherwise
        (:func:`display_options`).
    **overrides
        Fields of :class:`DisplayOptions` to change for this call.

    Returns
    -------
    Rendering
        The equation in LaTeX, as a matplotlib label and in Markdown; it
        displays itself in a notebook.
    """
    return Rendering(formulation, notation, _resolve(options, overrides))


def reference_scale(kind: str) -> ConventionalScale | None:
    """The reference scale of a quantity kind in the bundled catalog.

    Plots and :func:`symbol` read the bundled catalog: the scales of a
    personal catalog do not reach their labels.

    Values of the kind are given and returned on it (ITS-90 for the
    temperatures); ``None`` for a kind without conventional scale.
    """
    from nomogram.catalog import catalog

    for scale in catalog().scales.values():
        if scale.is_reference and kind in scale.kinds:
            return scale
    return None


def _with_subscript(tex: str, subscript: str) -> str:
    """A symbol marked with a scale: ``t`` gives ``t_{90}``.

    The mark joins an existing subscript group (``T_{d}`` gives
    ``T_{d,90}``), never a superscript.
    """
    mark = subscript if subscript.isdigit() else rf"\mathrm{{{subscript}}}"
    start = tex.find("_{")
    if start < 0:
        return f"{tex}_{{{mark}}}"
    depth = 0
    for index in range(start + 1, len(tex)):
        depth += {"{": 1, "}": -1}.get(tex[index], 0)
        if depth == 0:
            return f"{tex[:index]},{mark}{tex[index:]}"
    return f"{tex}_{{{mark}}}"


#: Words kept capitalised when a label is put in sentence case.
_PROPER_NOUNS = frozenset({"Celsius", "Fahrenheit", "Kelvin", "Rankine"})


def sentence_case(label: str) -> str:
    """A label in sentence case, as the SI and ISO 80000 write names.

    ``"Celsius Temperature"`` gives ``"Celsius temperature"``; acronyms and
    proper nouns keep their capitals, the first word too.
    """
    words = label.split(" ")
    return " ".join(
        [words[0]]
        + [
            w.lower()
            if w[:1].isupper() and w[1:].islower() and w not in _PROPER_NOUNS
            else w
            for w in words[1:]
        ]
    )


def axis_label(
    name: str | None,
    symbol: str | None,
    unit: str,
    *,
    scale: ConventionalScale | None = None,
    options: DisplayOptions | None = None,
    **overrides: Any,
) -> str:
    """The label of a plot axis, in the style of the display options.

    Parameters
    ----------
    name : str or None
        Name of the quantity, for example ``"Celsius temperature"``.
    symbol : str or None
        Its symbol, in LaTeX without dollars, for example ``"t"``.
    unit : str
        Its unit symbol, for example ``"°C"``; empty for a number.
    scale : ConventionalScale, optional
        The conventional scale of the values (ITS-90...).
    options, **overrides
        As for :func:`render`; ``axis_labels`` chooses the style.

    Returns
    -------
    str
        ``"si"`` (default): ``Celsius temperature $t_{90}$/°C``, the
        quotient of the quantity by its unit and the scale as a subscript
        of the symbol (SI Brochure, 9th edition, 5.4.1 and 5.4.2: a unit
        is never qualified, the information goes on the symbol);
        ``"explicit"``: ``Celsius temperature - $t$ [°C] {ITS-90}``;
        ``"simple"``: ``Celsius temperature $t$ [°C]``.

    Notes
    -----
    A compound unit goes in parentheses in the quotient (``(g/m³)``,
    ``(Pa⋅s)``); a number has no unit (``[1]`` in the explicit style);
    the scale subscript joins an existing subscript; without a name, the
    slash stands apart (``Height / km``); with neither name nor symbol,
    the unit stands alone (``[Pa]`` in the explicit and simple styles).
    """
    chosen = _resolve(options, overrides)
    style = chosen.axis_labels
    if style == "si" and symbol and scale is not None and scale.subscript:
        symbol = _with_subscript(symbol, scale.subscript)
    shown = f"${symbol}$" if symbol else None
    if style == "explicit":
        head = " - ".join(p for p in (name, shown) if p)
        text = f"{head} [{unit or '1'}]" if head else f"[{unit or '1'}]"
        if scale is not None and scale.symbol:
            text += f" {{{scale.symbol}}}"
        return text
    head = " ".join(p for p in (name, shown) if p)
    if not unit:
        return head
    if style == "simple":
        return f"{head} [{unit}]" if head else f"[{unit}]"
    if not head:
        return unit
    quotient = f"({unit})" if re.search(r"[/·⋅×* ]", unit) else unit
    return f"{head}/{quotient}" if shown else f"{head} / {quotient}"


def symbol(
    variable: Variable,
    notation: Notation | None = None,
    *,
    unit: bool = True,
    options: DisplayOptions | None = None,
    **overrides: Any,
) -> str:
    """The label of a variable, for a matplotlib axis or legend.

    Parameters
    ----------
    variable : Variable
        The variable, for example ``formulation.output``.
    notation : Notation, optional
        The notation of its symbol.
    unit : bool, optional
        Whether the unit follows, in the style of the ``axis_labels``
        option (:func:`axis_label`), with the reference scale of the
        variable's kind.
    options, **overrides
        As for :func:`render`.

    Returns
    -------
    str
        For example ``"$e_{\\mathrm{w}}$/hPa"``.
    """
    chosen = _resolve(options, overrides)
    symbols = dict(notation.symbols) if notation else {}
    tex = _identifier(variable.identifier, symbols, chosen)
    if not unit:
        return f"${tex}$"
    scale = reference_scale(variable.kind)
    return axis_label(None, tex, _unit(variable.unit), scale=scale, options=chosen)


def _cell(text: str) -> str:
    return text.replace("|", r"\|")


@dataclass(frozen=True, repr=False)
class FormulaTable:
    """Several formulations side by side, as a Markdown table.

    Attributes
    ----------
    renderings : tuple of Rendering
        One per row.
    """

    renderings: tuple[Rendering, ...]

    #: Column titles.
    HEADER: ClassVar[tuple[str, ...]] = (
        "Formulation",
        "Equation",
        "Validity",
        "References",
    )

    def _validity(self, rendering: Rendering) -> str:
        formulation, options = rendering.formulation, rendering.options
        symbols = dict(rendering.notation.symbols) if rendering.notation else {}
        variables = {v.identifier: v for v in (formulation.output, *formulation.inputs)}
        parts = []
        for domain in formulation.domains:
            for identifier, (low, high) in domain.bounds.items():
                label = _identifier(identifier, symbols, options)
                bounds = (
                    f"{_plain_number(low, options)} to {_plain_number(high, options)}"
                )
                variable = variables.get(identifier)
                text = _with_unit(bounds, variable.unit if variable else None)
                parts.append(f"${label}$: {text} ({domain.basis.value})")
        return "; ".join(parts)

    def to_markdown(self) -> str:
        """The table in Markdown, equations between dollar signs."""
        lines = [
            "| " + " | ".join(self.HEADER) + " |",
            "|" + "---|" * len(self.HEADER),
        ]
        for rendering in self.renderings:
            formulation = rendering.formulation
            equation = rendering.latex.replace("|", r"\vert ")
            cells = (
                _cell(formulation.label),
                f"${equation}$",
                _cell(self._validity(rendering)),
                _cell(", ".join(formulation.references)),
            )
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines) + "\n"

    def _repr_markdown_(self) -> str:
        return self.to_markdown()

    def __repr__(self) -> str:
        keys = ", ".join(r.formulation.key for r in self.renderings)
        return f"FormulaTable({len(self.renderings)} formulations: {keys})"


def table(
    formulations: Iterable[Formulation],
    notation: Notation | None = None,
    *,
    options: DisplayOptions | None = None,
    **overrides: Any,
) -> FormulaTable:
    """Several formulations side by side.

    Parameters
    ----------
    formulations : iterable of Formulation
        For example ``catalog().formulations_of(kind)``.
    notation, options, **overrides
        As for :func:`render`.

    Returns
    -------
    FormulaTable
        Name, equation, validity domains and references of each
        formulation; it displays itself in a notebook.
    """
    chosen = _resolve(options, overrides)
    return FormulaTable(tuple(Rendering(f, notation, chosen) for f in formulations))
