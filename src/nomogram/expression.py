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
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any

import sympy
from sympy.codegen.cfunctions import log10
from sympy.core.function import AppliedUndef
from sympy.printing.conventions import split_super_sub
from sympy.printing.latex import LatexPrinter, translate

__all__ = [
    "CONSTANTS",
    "FUNCTIONS",
    "LATEX_COMMANDS",
    "MAX_SOURCE_LENGTH",
    "PIECEWISE",
    "ExpressionError",
    "compile_numeric",
    "latex_commands",
    "parse_expression",
    "to_latex",
    "upright_symbol",
]

#: Functions allowed in a formula, by the name used in the source text.
FUNCTIONS: Mapping[str, Callable[[Any], Any]] = MappingProxyType(
    {
        "exp": sympy.exp,
        "ln": sympy.log,
        "log10": log10,
        "sqrt": sympy.sqrt,
        # Of an angle in radians (the latitude of a normal gravity formula);
        # the catalog refuses an angle in degrees in their argument.
        "sin": sympy.sin,
        "cos": sympy.cos,
    }
)

#: Mathematical constants allowed in a formula, by name. Their names are
#: reserved: no identifier may take them.
CONSTANTS: Mapping[str, Any] = MappingProxyType({"pi": sympy.pi})

#: Name of the piecewise definition, ``piecewise((expr, condition), ...)``;
#: reserved like the functions.
PIECEWISE = "piecewise"


class Piecewise(sympy.Piecewise):  # type: ignore[misc]
    """A piecewise definition kept as written.

    SymPy evaluates a piecewise definition whenever it is built or rebuilt:
    a condition that completes the others (T >= 273.15 after T < 273.15)
    becomes True, and a power is distributed over the branches, which
    rebuilds them (1 / e_s, for a saturation pressure by branches). Here
    the conditions stay as written and a power applies to the whole.

    The class keeps SymPy's name: printers find their method by the name
    of the class (``_print_Piecewise``), not by that of a parent.
    """

    def __new__(cls, *args: Any, **options: Any) -> Any:
        options.setdefault("evaluate", False)
        return super().__new__(cls, *args, **options)

    def _eval_power(self, _exponent: Any) -> None:
        return None


_COMPARISONS: Mapping[type[ast.cmpop], Any] = {
    ast.Lt: sympy.StrictLessThan,
    ast.LtE: sympy.LessThan,
    ast.Gt: sympy.StrictGreaterThan,
    ast.GtE: sympy.GreaterThan,
}

#: Longest accepted source text, to bound parsing work.
MAX_SOURCE_LENGTH = 2000

#: Most decimal digits of a power of two numbers, which SymPy computes
#: exactly when the formula is read: 9 ** 9 ** 9 would never end.
_MAX_POWER_DIGITS = 1000

_GREEK = (
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "varepsilon",
    "zeta",
    "eta",
    "theta",
    "vartheta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "pi",
    "varpi",
    "rho",
    "varrho",
    "sigma",
    "varsigma",
    "tau",
    "upsilon",
    "phi",
    "varphi",
    "chi",
    "psi",
    "omega",
    "Gamma",
    "Delta",
    "Theta",
    "Lambda",
    "Xi",
    "Pi",
    "Sigma",
    "Upsilon",
    "Phi",
    "Psi",
    "Omega",
)

#: LaTeX commands nomogram may emit: the subset common to MathJax (``base``
#: package, loaded by default), KaTeX ("Supported Functions") and
#: matplotlib's mathtext, checked against their lists on 2026-10-17. A
#: formula or a notation needing another command must first be checked
#: in those three lists. Greek letters are those of standard LaTeX (KaTeX
#: also accepts ``\Alpha``..., MathJax does not).
LATEX_COMMANDS: frozenset[str] = frozenset(
    {
        r"\exp",
        r"\ln",
        r"\log",
        r"\sin",
        r"\cos",
        r"\frac",
        r"\sqrt",
        r"\left",
        r"\right",
        r"\mathrm",
        r"\times",
        r"\cdot",
        r"\vert",
        r"\,",
        # Piecewise definitions, written on one line in a left brace (in
        # the lists of MathJax and KaTeX on 2026-10-24; parsed by mathtext).
        r"\{",
        r"\;",
        r"\leq",
        r"\geq",
    }
    | {"\\" + letter for letter in _GREEK}
)

_COMMAND = re.compile(r"\\(?:[A-Za-z]+|[^A-Za-z])")

_BINARY_OPERATORS: Mapping[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: _power(a, b),
}

_UNARY_OPERATORS: Mapping[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: a,
}


def _power(base: Any, exponent: Any) -> Any:
    """A power, refused when two numbers would give too many digits."""
    numbers = isinstance(base, sympy.Number) and isinstance(exponent, sympy.Number)
    if numbers and abs(base) not in (0, 1):
        digits = abs(float(exponent)) * abs(float(sympy.log(abs(base), 10)))
        if digits > _MAX_POWER_DIGITS:
            msg = f"power of two numbers beyond {_MAX_POWER_DIGITS} digits"
            raise ExpressionError(msg)
    return base**exponent


class ExpressionError(ValueError):
    """The source text is not a valid formula expression."""


def parse_expression(source: str, names: Iterable[str], *, exact: bool = False) -> Any:
    """Parse a formula written in restricted Python syntax into a SymPy expression.

    Allowed: numbers, the declared names, the constants of
    :data:`CONSTANTS`, ``+ - * / **``, unary ``-`` and ``+``, parentheses,
    calls to the functions of :data:`FUNCTIONS` with exactly one
    positional argument, and a piecewise definition,
    ``piecewise((expr, condition), ...)``, whose conditions are
    comparisons (``<``, ``<=``, ``>``, ``>=``), possibly chained in one
    direction (``T_ice < T <= T_0``). Everything else (attributes,
    subscripts, keywords, lambdas, comparisons outside a condition,
    ``and``, ``or``, booleans, strings, other calls, undeclared names) is
    rejected. Nothing is evaluated: a piecewise definition keeps its
    conditions as written, and gives NaN where none holds.

    Parameters
    ----------
    source : str
        The expression, for example ``"C * exp(A * t / (B + t))"``.
    names : iterable of str
        The identifiers the expression may use (variables, coefficients
        and constants). Each becomes a real SymPy symbol with that name.
    exact : bool, optional
        Read decimal numbers as exact rationals (273.15 as 5463/20), for
        symbolic proofs: written in two expressions, they then cancel
        exactly, whatever the version of SymPy. By default they are
        floating-point numbers, displayed as written.

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
        reserved = name in FUNCTIONS or name in CONSTANTS or name == PIECEWISE
        if not name.isidentifier() or reserved:
            msg = f"invalid or reserved name: {name!r}"
            raise ExpressionError(msg)
    symbols = {name: sympy.Symbol(name, real=True) for name in allowed}
    number = sympy.Rational if exact else sympy.Float
    try:
        tree = ast.parse(source.strip(), mode="eval")
        return _build(tree.body, symbols, number)
    except SyntaxError as exc:
        msg = f"invalid syntax: {exc.msg}"
        raise ExpressionError(msg) from None
    except RecursionError:
        msg = "expression nested too deeply"
        raise ExpressionError(msg) from None


def _build(node: ast.AST, symbols: Mapping[str, Any], number: Any) -> Any:
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _build(node.left, symbols, number)
        right = _build(node.right, symbols, number)
        return _BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_build(node.operand, symbols, number))
    if isinstance(node, ast.Constant):
        value = node.value
        # bool is a subclass of int: refuse it explicitly.
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"unsupported constant: {value!r}"
            raise ExpressionError(msg)
        if not math.isfinite(value):
            msg = f"number too large: {value!r}"
            raise ExpressionError(msg)
        return sympy.Integer(value) if isinstance(value, int) else number(repr(value))
    if isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        if node.id not in symbols:
            msg = f"undeclared name: {node.id!r}"
            raise ExpressionError(msg)
        return symbols[node.id]
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == PIECEWISE:
            return _piecewise(node, symbols, number)
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            allowed = sorted(FUNCTIONS) + [PIECEWISE]
            msg = "only calls to " + ", ".join(allowed) + " are allowed"
            raise ExpressionError(msg)
        if node.keywords or len(node.args) != 1:
            msg = f"{node.func.id}() takes exactly one positional argument"
            raise ExpressionError(msg)
        return FUNCTIONS[node.func.id](_build(node.args[0], symbols, number))
    if isinstance(node, ast.Compare):
        msg = "comparisons are allowed only as the conditions of piecewise()"
        raise ExpressionError(msg)
    msg = f"unsupported syntax: {type(node).__name__}"
    raise ExpressionError(msg)


def _piecewise(node: ast.Call, symbols: Mapping[str, Any], number: Any) -> Any:
    """A piecewise definition, conditions kept as written."""
    if node.keywords or not node.args:
        msg = f"{PIECEWISE}() takes (expression, condition) pairs"
        raise ExpressionError(msg)
    pairs = []
    for arg in node.args:
        if not isinstance(arg, ast.Tuple) or len(arg.elts) != 2:
            msg = f"{PIECEWISE}() takes (expression, condition) pairs"
            raise ExpressionError(msg)
        expression, condition = arg.elts
        pairs.append(
            (
                _build(expression, symbols, number),
                _condition(condition, symbols, number),
            )
        )
    return Piecewise(*pairs)


@dataclass(frozen=True)
class _Piece:
    """A branch of a piecewise definition, on an interval of one input."""

    expression: Any
    variable: Any
    low: Any
    low_closed: bool
    high: Any
    high_closed: bool


def _pieces(piecewise: Any, inputs: Iterable[str]) -> tuple[_Piece, ...]:
    """The branches of a piecewise definition, each on an interval of one input.

    Every condition bounds the same input, alone on one side of each
    comparison, by expressions free of inputs (numbers, coefficients,
    constants); an end not bounded is infinite.

    Raises
    ------
    ExpressionError
        If a condition is not such an interval, or two conditions bound
        different inputs.
    """
    names = frozenset(inputs)
    pieces: list[_Piece] = []
    for expression, condition in piecewise.args:
        relations = condition.args if isinstance(condition, sympy.And) else (condition,)
        ends: dict[str, tuple[Any, bool]] = {}
        variable = None
        for relation in relations:
            alone = [
                side
                for side in (relation.lhs, relation.rhs)
                if side.is_Symbol and side.name in names
            ]
            other = relation.rhs if relation.lhs in alone else relation.lhs
            if len(alone) != 1 or any(s.name in names for s in other.free_symbols):
                msg = f"the condition {condition} does not bound one input alone"
                raise ExpressionError(msg)
            if variable not in (None, alone[0]):
                msg = f"the condition {condition} bounds two inputs"
                raise ExpressionError(msg)
            variable = alone[0]
            below = (relation.rel_op in ("<", "<=")) == (relation.rhs == variable)
            ends["low" if below else "high"] = (other, relation.rel_op in ("<=", ">="))
        if pieces and pieces[0].variable != variable:
            msg = f"the conditions bound {pieces[0].variable} and {variable}"
            raise ExpressionError(msg)
        low, low_closed = ends.get("low", (-sympy.oo, False))
        high, high_closed = ends.get("high", (sympy.oo, False))
        pieces.append(_Piece(expression, variable, low, low_closed, high, high_closed))
    return tuple(pieces)


def _call_sites(source: str, aliases: Iterable[str]) -> tuple[str, list[ast.Call]]:
    """Calls of formulations in an expression, each replaced by a placeholder.

    Returns the source with each call of an alias replaced by the name
    ``_call_<i>``, and the calls, in order of appearance (left to right,
    outer first). The calls are not checked: the catalog does it.

    Raises
    ------
    ExpressionError
        If the text is not valid Python syntax.
    """
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError as exc:
        msg = f"invalid syntax: {exc.msg}"
        raise ExpressionError(msg) from None
    callable_names = frozenset(aliases)
    found: list[ast.Call] = []

    class Replace(ast.NodeTransformer):
        def visit_Call(self, node: ast.Call) -> ast.AST:
            if isinstance(node.func, ast.Name) and node.func.id in callable_names:
                found.append(node)
                return ast.copy_location(
                    ast.Name(f"_call_{len(found) - 1}", ast.Load()), node
                )
            self.generic_visit(node)
            return node

    text = ast.unparse(Replace().visit(tree))
    return text, found


def _opaque_calls(
    source: str, names: Iterable[str], calls: Iterable[tuple[str, Iterable[str]]]
) -> Any:
    """An expression whose calls of formulations stay opaque functions.

    ``calls`` gives, in order of appearance, the alias of each call and its
    arguments in the order of the called formulation's inputs.
    """
    pairs = [(alias, tuple(arguments)) for alias, arguments in calls]
    text, found = _call_sites(source, {alias for alias, _ in pairs})
    placeholders = [f"_call_{i}" for i in range(len(found))]
    expr = parse_expression(text, [*names, *placeholders])
    return expr.xreplace(
        {
            sympy.Symbol(name, real=True): sympy.Function(alias)(
                *(sympy.Symbol(a, real=True) for a in arguments)
            )
            for name, (alias, arguments) in zip(placeholders, pairs, strict=True)
        }
    )


def _variants(expr: Any) -> list[Any]:
    """The expression with each piecewise definition replaced by each branch.

    For a check that needs one expression per branch (the units of a
    quantity equation, which pint evaluates).
    """
    node = next(
        (n for n in sympy.preorder_traversal(expr) if isinstance(n, sympy.Piecewise)),
        None,
    )
    if node is None:
        return [expr]
    return [v for e, _ in node.args for v in _variants(expr.xreplace({node: e}))]


def _relations(expr: Any) -> list[Any]:
    """The comparisons of the conditions of the piecewise definitions."""
    found = []
    for node in sympy.preorder_traversal(expr):
        if isinstance(node, sympy.Piecewise):
            for _, condition in node.args:
                is_chain = isinstance(condition, sympy.And)
                found += list(condition.args) if is_chain else [condition]
    return found


def _condition(node: ast.expr, symbols: Mapping[str, Any], number: Any) -> Any:
    """A comparison, or two chained in one direction (``a < x <= b``)."""
    if not isinstance(node, ast.Compare) or not all(
        type(op) in _COMPARISONS for op in node.ops
    ):
        msg = "a condition of piecewise() is a comparison: <, <=, > or >="
        raise ExpressionError(msg)
    if len(node.ops) > 2:
        msg = "a condition of piecewise() chains at most two comparisons"
        raise ExpressionError(msg)
    terms = [_build(term, symbols, number) for term in (node.left, *node.comparators)]
    relations = [
        _COMPARISONS[type(op)](left, right, evaluate=False)
        for op, left, right in zip(node.ops, terms, terms[1:], strict=False)
    ]
    if len(relations) == 1:
        return relations[0]
    increasing = {type(op) in (ast.Lt, ast.LtE) for op in node.ops}
    if len(increasing) != 1:
        msg = "chained comparisons of piecewise() go in one direction"
        raise ExpressionError(msg)
    chained = sympy.And(*relations, evaluate=False)
    if not isinstance(chained, sympy.And):
        # SymPy reduces some chains even so (280 < T <= 280 to False), which
        # would drop the branch without a word.
        msg = (
            f"the condition {ast.unparse(node)} reduces to {chained}: write an "
            "interval of one input"
        )
        raise ExpressionError(msg)
    return chained


class _NotationPrinter(LatexPrinter):  # type: ignore[misc]
    """LaTeX printer for formulas.

    The exponential is written ``\\exp\\left(...\\right)`` rather than
    ``e^{...}``: in meteorology ``e`` denotes the vapour pressure. The
    decimal logarithm is written ``\\log_{10}``, as in the sources.
    """

    def _print_ExpBase(self, expr: Any, exp: Any = None) -> str:
        tex = r"\exp\left(" + self._print(expr.args[0]) + r"\right)"
        return f"{tex}^{{{exp}}}" if exp is not None else tex

    def _print_log10(self, expr: Any, exp: Any = None) -> str:
        tex = r"\log_{10}\left(" + self._print(expr.args[0]) + r"\right)"
        return f"{tex}^{{{exp}}}" if exp is not None else tex

    def _print_Function(self, expr: Any, exp: Any = None) -> str:
        """A call of a formulation, kept opaque: its alias, then its arguments."""
        if not isinstance(expr, AppliedUndef):
            return str(super()._print_Function(expr, exp))
        name = self._print(sympy.Symbol(expr.func.__name__, real=True))
        arguments = ", ".join(str(self._print(a)) for a in expr.args)
        tex = rf"{name}\left({arguments}\right)"
        return f"{tex}^{{{exp}}}" if exp is not None else tex

    def _print_Piecewise(self, expr: Any, exp: str | None = None) -> str:
        """On one line, in a left brace: mathtext has no cases environment.

        A power of the definition (``exp``) applies to it in parentheses.
        """
        pieces = [
            rf"{self._print(e)} \;\mathrm{{if}}\; {self._condition(c)}"
            for e, c in expr.args
        ]
        text = r"\left\{" + r",\; ".join(pieces) + r"\right."
        return text if exp is None else rf"\left({text}\right)^{{{exp}}}"

    def _condition(self, condition: Any) -> str:
        if not isinstance(condition, sympy.And):
            return str(self._print(condition))
        # And sorts its terms: the chain is written again, lower bound first.
        bounds: dict[str, tuple[Any, str]] = {}
        (variable,) = set(condition.args[0].args) & set(condition.args[1].args)
        for relation in condition.args:
            strict = relation.rel_op in ("<", ">")
            below = (relation.rel_op in ("<", "<=")) == (relation.rhs == variable)
            bound = relation.lhs if relation.rhs == variable else relation.rhs
            bounds["lower" if below else "upper"] = (bound, "<" if strict else r"\leq")
        (low, low_op), (high, high_op) = bounds["lower"], bounds["upper"]
        return (
            f"{self._print(low)} {low_op} {self._print(variable)} "
            f"{high_op} {self._print(high)}"
        )


def latex_commands(tex: str) -> set[str]:
    """The LaTeX commands used in a LaTeX string (``\\frac``, ``\\,``...)."""
    return set(_COMMAND.findall(tex))


def upright_symbol(identifier: str) -> str:
    """LaTeX symbol of an identifier, descriptive parts in upright type.

    ISO 80000-2 sets symbols of variables in italic and descriptive
    subscripts in upright (roman) type: ``e_s`` gives ``e_{\\mathrm{s}}``.
    An identifier is split as SymPy splits symbol names: Greek names and
    numeric indices keep their usual rendering, every other subscript is
    taken as descriptive, and a base name of several letters as an
    abbreviation (``RH`` gives ``\\mathrm{RH}``, never a product R H). A
    running index (x_i) needs a notation. The result stays within
    :data:`LATEX_COMMANDS`: a name SymPy would write with another command
    (``Tbar`` as ``\\bar{T}``, ``hbar``, ``ell``) is written upright as
    it is spelt (``\\mathrm{Tbar}``).

    Parameters
    ----------
    identifier : str
        An identifier of a formula, for example ``"rho_v"``.

    Returns
    -------
    str
        The LaTeX symbol, for example ``\\rho_{\\mathrm{v}}``.
    """
    base, supers, subs = split_super_sub(identifier)

    def part(text: str, *, base: bool = False) -> str:
        translated = str(translate(text))
        if translated != text and latex_commands(translated) <= LATEX_COMMANDS:
            return translated
        if translated == text and (text.isdigit() or (base and len(text) == 1)):
            return text
        return rf"\mathrm{{{text}}}"

    tex = part(base, base=True)
    if subs:
        tex += "_{" + ",".join(part(s) for s in subs) + "}"
    if supers:
        tex += "^{" + ",".join(part(s) for s in supers) + "}"
    return tex


def to_latex(
    expr: Any,
    notation: Mapping[str, str] | None = None,
    *,
    mul_symbol: str | None = None,
    decimal_separator: str = "period",
    upright: bool = False,
) -> str:
    """Render an expression in LaTeX, in a given notation.

    The default rendering of identifiers stays within
    :data:`LATEX_COMMANDS` (the symbols of a notation are used as given),
    rendered alike by MathJax, KaTeX and matplotlib's mathtext, so that one
    string serves documentation, notebooks and plot labels. The defaults reproduce
    SymPy's own rendering; :mod:`nomogram.display` chooses the typography.

    Parameters
    ----------
    expr : sympy.Expr
        An expression returned by :func:`parse_expression`.
    notation : mapping of str to str, optional
        LaTeX symbol for each identifier, for example
        ``{"e_s": r"E_{\\mathrm{w}}"}``, used as given (the catalog checks
        the symbols of its notations against :data:`LATEX_COMMANDS`).
        Identifiers not listed keep SymPy's default rendering, or
        :func:`upright_symbol` if ``upright``; a default rendering that
        would use another command (``Tbar`` as ``\\bar{T}``) is replaced
        by :func:`upright_symbol`.
    mul_symbol : {None, "times", "dot", "ldot"}, optional
        Multiplication sign, passed to SymPy's printer: ``None`` writes
        products by juxtaposition.
    decimal_separator : {"period", "comma"}, optional
        Decimal separator, passed to SymPy's printer.
    upright : bool, optional
        Whether identifiers outside the notation follow
        :func:`upright_symbol`.

    Returns
    -------
    str
        The LaTeX code, without surrounding dollar signs.
    """
    names = {}
    default = _NotationPrinter()
    # The name of a formulation called is written like an identifier.
    called = {
        sympy.Symbol(c.func.__name__, real=True) for c in expr.atoms(AppliedUndef)
    }
    for symbol in expr.free_symbols | called:
        if notation and symbol.name in notation:
            names[symbol] = notation[symbol.name]
        elif upright or not latex_commands(default.doprint(symbol)) <= LATEX_COMMANDS:
            names[symbol] = upright_symbol(symbol.name)
    printer = _NotationPrinter(
        {
            "symbol_names": names,
            "ln_notation": True,
            "mul_symbol": mul_symbol,
            "decimal_separator": decimal_separator,
        }
    )
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
