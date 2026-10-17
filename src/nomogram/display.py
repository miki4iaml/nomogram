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
- :func:`table` gives a Markdown table of several formulations.

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
from collections.abc import Iterable, Iterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cached_property
from typing import Any, ClassVar, Literal

import sympy

from nomogram.dimensions import DimensionError, unit_text
from nomogram.expression import to_latex
from nomogram.model import Coefficient, Formulation, Notation, Variable
from nomogram.semantics import semantic_catalog

__all__ = [
    "DisplayOptions",
    "FormulaTable",
    "Rendering",
    "display_options",
    "get_display_options",
    "render",
    "symbol",
    "table",
]

MulSymbol = Literal["times", "dot", "ldot"] | None
DecimalSeparator = Literal["period", "comma"]

_MUL_SYMBOLS = ("times", "dot", "ldot", None)
_DECIMAL_SEPARATORS = ("period", "comma")

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
    """

    mul_symbol: MulSymbol = "times"
    decimal_separator: DecimalSeparator = "period"
    upright: bool = True
    values: bool = False

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
    """The unit of a coefficient, declared or inferred, as text."""
    try:
        unit = formulation.coefficient_units[coefficient.identifier].unit
    except DimensionError:
        return _unit(coefficient.unit)
    return unit_text(unit)


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
        Whether the unit follows, in brackets.
    options, **overrides
        As for :func:`render`.

    Returns
    -------
    str
        For example ``"$e_{\\mathrm{w}}$ [hPa]"``.
    """
    chosen = _resolve(options, overrides)
    symbols = dict(notation.symbols) if notation else {}
    label = f"${_identifier(variable.identifier, symbols, chosen)}$"
    text = _unit(variable.unit) if unit else ""
    return f"{label} [{text}]" if text else label


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
