# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Formula expressions: safe parsing, LaTeX rendering and numeric evaluation.

A formula's mathematical content is written once, in a restricted Python
syntax such as ``C * exp(A * t / (B + t))``. That text is the single
source of truth: it is parsed with :mod:`ast` against a whitelist and
turned directly into a SymPy expression, without ever calling
:func:`eval` (``sympy.parse_expr`` relies on ``eval`` and is not meant for
untrusted input). Everything else derives from the SymPy expression:

- LaTeX, rendered in any author's notation;
- numeric evaluation, vectorised with numpy through ``lambdify``;
- symbolic computation.

Names in an expression are semantic *identifiers* (``t``, ``RH``,
``e_s``...), each becoming a SymPy symbol of that name. They are never
glyphs: the symbol a reader sees (QUDT's ``symbol``/``latexSymbol``)
belongs to a notation. See ``docs/rosetta.md`` for the vocabulary.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Mapping
from functools import lru_cache
from typing import Any

import sympy
from sympy.printing.latex import LatexPrinter

__all__ = [
    "FUNCTIONS",
    "MAX_SOURCE_LENGTH",
    "ExpressionError",
    "compile_numeric",
    "parse_expression",
    "to_latex",
]

#: Functions allowed in a formula, by the name used in the source text.
FUNCTIONS: Mapping[str, Callable[[Any], Any]] = {
    "exp": sympy.exp,
    "ln": sympy.log,
    "sqrt": sympy.sqrt,
}

#: Longest accepted source text, to bound parsing work.
MAX_SOURCE_LENGTH = 2000

_BINARY_OPERATORS: Mapping[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a**b,
}

_UNARY_OPERATORS: Mapping[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: a,
}


class ExpressionError(ValueError):
    """The source text is not a valid formula expression."""


def parse_expression(source: str, names: Iterable[str]) -> Any:
    """Parse a formula written in restricted Python syntax into a SymPy expression.

    Allowed: numbers, the declared names, ``+ - * / **``, unary ``-`` and
    ``+``, parentheses, and calls to the functions of :data:`FUNCTIONS`
    with exactly one positional argument. Everything else (attributes,
    subscripts, keywords, lambdas, comparisons, strings, other calls,
    undeclared names) is rejected. Nothing is evaluated.

    Parameters
    ----------
    source : str
        The expression, for example ``"C * exp(A * t / (B + t))"``.
    names : iterable of str
        The identifiers the expression may use (variables, coefficients
        and constants). Each becomes a real SymPy symbol with that name.

    Returns
    -------
    sympy.Expr
        The parsed expression.

    Raises
    ------
    ExpressionError
        If the text is too long, is not valid Python syntax, or uses
        anything outside the whitelist.
    """
    if len(source) > MAX_SOURCE_LENGTH:
        msg = f"expression longer than {MAX_SOURCE_LENGTH} characters"
        raise ExpressionError(msg)
    allowed = frozenset(names)
    for name in allowed:
        if not name.isidentifier() or name in FUNCTIONS:
            msg = f"invalid or reserved name: {name!r}"
            raise ExpressionError(msg)
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError as exc:
        msg = f"invalid syntax: {exc.msg}"
        raise ExpressionError(msg) from None
    symbols = {name: sympy.Symbol(name, real=True) for name in allowed}
    return _build(tree.body, symbols)


def _build(node: ast.AST, symbols: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left, right = _build(node.left, symbols), _build(node.right, symbols)
        return _BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_build(node.operand, symbols))
    if isinstance(node, ast.Constant):
        value = node.value
        # bool is a subclass of int: refuse it explicitly.
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"unsupported constant: {value!r}"
            raise ExpressionError(msg)
        return (
            sympy.Integer(value) if isinstance(value, int) else sympy.Float(repr(value))
        )
    if isinstance(node, ast.Name):
        if node.id not in symbols:
            msg = f"undeclared name: {node.id!r}"
            raise ExpressionError(msg)
        return symbols[node.id]
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            msg = "only calls to " + ", ".join(sorted(FUNCTIONS)) + " are allowed"
            raise ExpressionError(msg)
        if node.keywords or len(node.args) != 1:
            msg = f"{node.func.id}() takes exactly one positional argument"
            raise ExpressionError(msg)
        return FUNCTIONS[node.func.id](_build(node.args[0], symbols))
    msg = f"unsupported syntax: {type(node).__name__}"
    raise ExpressionError(msg)


class _NotationPrinter(LatexPrinter):  # type: ignore[misc]
    """LaTeX printer for formulas.

    The exponential is written ``\\exp\\left(...\\right)`` rather than
    ``e^{...}``: in meteorology ``e`` denotes the vapour pressure.
    """

    def _print_ExpBase(self, expr: Any, exp: Any = None) -> str:
        tex = r"\exp\left(" + self._print(expr.args[0]) + r"\right)"
        return f"{tex}^{{{exp}}}" if exp is not None else tex


def to_latex(expr: Any, notation: Mapping[str, str] | None = None) -> str:
    """Render an expression in LaTeX, in a given notation.

    The output stays within what both matplotlib's mathtext and MathJax
    render (``\\frac``, ``\\exp``, ``\\ln``, ``\\left``/``\\right``, braced
    subscripts), so that one string serves documentation and plot labels.

    Parameters
    ----------
    expr : sympy.Expr
        An expression returned by :func:`parse_expression`.
    notation : mapping of str to str, optional
        LaTeX symbol for each identifier, for example
        ``{"e_s": r"E_{\\mathrm{w}}"}``. Identifiers not listed keep
        SymPy's default rendering.

    Returns
    -------
    str
        The LaTeX code, without surrounding dollar signs.
    """
    names = {}
    for symbol in expr.free_symbols:
        if notation and symbol.name in notation:
            names[symbol] = notation[symbol.name]
    printer = _NotationPrinter({"symbol_names": names, "ln_notation": True})
    return str(printer.doprint(expr))


def compile_numeric(expr: Any, arguments: tuple[str, ...]) -> Callable[..., Any]:
    """Compile an expression into a numeric function, vectorised with numpy.

    The compiled function is cached: compiling a SymPy expression is costly
    and deterministic.

    Parameters
    ----------
    expr : sympy.Expr
        An expression returned by :func:`parse_expression`.
    arguments : tuple of str
        Identifiers of the function's positional arguments, in order.
        Every identifier used by the expression must be listed.

    Returns
    -------
    callable
        A function of the given arguments, accepting numbers or numpy
        arrays (broadcast together).

    Raises
    ------
    ExpressionError
        If an identifier used by the expression is not among the
        arguments.
    """
    missing = sorted(s.name for s in expr.free_symbols if s.name not in arguments)
    if missing:
        msg = "missing arguments: " + ", ".join(missing)
        raise ExpressionError(msg)
    return _lambdify(expr, arguments)


@lru_cache(maxsize=256)
def _lambdify(expr: Any, arguments: tuple[str, ...]) -> Callable[..., Any]:
    symbols = [sympy.Symbol(name, real=True) for name in arguments]
    function: Callable[..., Any] = sympy.lambdify(symbols, expr, modules="numpy")
    return function
