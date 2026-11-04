# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Randomized tests of the expression parser.

Not coverage-guided fuzzing: a seeded generator writes formulas from the
whitelist, mutates the expressions of the catalog and slips fragments of
Python into them. The parser must accept each text or refuse it with
:class:`ExpressionError`, never fail otherwise, and answer quickly. The
seed is fixed, so that a failure can be replayed.
"""

import random
import string
import time
from typing import Any

import pytest
import sympy

from nomogram.catalog import catalog
from nomogram.expression import (
    CONSTANTS,
    FUNCTIONS,
    MAX_SOURCE_LENGTH,
    PIECEWISE,
    ExpressionError,
    parse_expression,
)

SEED = 20261104
CASES = 600
NAMES = ("x", "y", "T", "e_s", "a1")
#: Longest time one text may take to parse, generous for slow runners.
SECONDS = 2.0
#: Python a formula must never reach, alone or slipped into a formula.
HOSTILE = (
    "__import__('os')",
    "().__class__",
    "x.__class__",
    "lambda: 1",
    "x.real",
    "x[0]",
    "[x for x in y]",
    "{x: y}",
    "x, y",
    "open('f')",
    "eval('1')",
    "exec('1')",
    "print(x)",
    "1 if x else 2",
    "(y := 1)",
    "f'{x}'",
    "'x'",
    "b'x'",
    "x and y",
    "x or y",
    "not x",
    "x @ y",
    "x // y",
    "x % y",
    "x << 1",
    "~x",
    "x < y",
    "True",
    "None",
    "...",
    "1j",
    "1e999",
    "9 ** 9 ** 9",
    "exp(x, y)",
    "exp()",
    "exp(x=1)",
    "exp(*x)",
    "atan2(x, y)",
    "piecewise(x)",
    "piecewise((x, x and y))",
    "z",
)
#: Characters inserted by mutation: printable ASCII, and a few others a
#: copied text may carry (Greek, accents, invisible and bidirectional
#: controls).
ALPHABET = string.printable + "πθéμ√∞−\u200b\u202e\u00a0"


def outcome(source: str, names: tuple[str, ...]) -> Any:
    """The parsed expression, or None if refused; any other error fails."""
    start = time.perf_counter()
    try:
        expr = parse_expression(source, names)
    except ExpressionError:
        expr = None
    except Exception as exc:
        msg = f"{type(exc).__name__} on {source!r}: {exc}"
        raise AssertionError(msg) from exc
    elapsed = time.perf_counter() - start
    assert elapsed < SECONDS, (source, elapsed)
    if expr is not None:
        # Accepted: only the declared names are free.
        assert {str(s) for s in expr.free_symbols} <= set(names), source
    return expr


def number(rng: random.Random) -> str:
    return rng.choice(
        [
            str(rng.randint(0, 1000)),
            f"{rng.uniform(-1e3, 1e3):.6g}",
            f"{rng.uniform(0, 10):.3f}e{rng.randint(-30, 30)}",
            str(rng.randint(0, 10**30)),
        ]
    )


def formula(rng: random.Random, depth: int) -> str:
    """A random text built from the whitelist, valid or not."""
    if depth == 0 or rng.random() < 0.25:
        return rng.choice([rng.choice(NAMES), number(rng), *CONSTANTS])
    branch = rng.random()
    if branch < 0.45:
        operator = rng.choice(["+", "-", "*", "/", "**"])
        return f"({formula(rng, depth - 1)} {operator} {formula(rng, depth - 1)})"
    if branch < 0.55:
        return f"-{formula(rng, depth - 1)}"
    if branch < 0.85:
        return f"{rng.choice(list(FUNCTIONS))}({formula(rng, depth - 1)})"
    comparison = rng.choice(["<", "<=", ">", ">="])
    condition = f"{rng.choice(NAMES)} {comparison} {number(rng)}"
    pieces = f"({formula(rng, depth - 1)}, {condition})"
    return f"{PIECEWISE}({pieces}, ({formula(rng, depth - 1)}, True))"


def mutate(rng: random.Random, source: str) -> str:
    """The text with one to three random edits."""
    for _ in range(rng.randint(1, 3)):
        at = rng.randint(0, len(source))
        edit = rng.random()
        if edit < 0.3:
            source = source[:at] + rng.choice(ALPHABET) + source[at:]
        elif edit < 0.55:
            source = source[:at] + source[at + rng.randint(1, 5) :]
        elif edit < 0.75:
            source = source[:at] + rng.choice(HOSTILE) + source[at:]
        elif edit < 0.9:
            end = min(len(source), at + rng.randint(1, 10))
            source = source[:at] + source[at:end] * 2 + source[end:]
        else:
            source = source[:at] + rng.choice("()") + source[at:]
    return source


@pytest.mark.parametrize("source", HOSTILE)
def test_python_outside_the_whitelist_is_refused(source: str) -> None:
    assert outcome(source, NAMES) is None


def test_random_formulas_are_parsed_or_refused() -> None:
    rng = random.Random(SEED)
    accepted = sum(
        outcome(formula(rng, rng.randint(1, 6)), NAMES) is not None
        for _ in range(CASES)
    )
    # Most are valid; some are refused (an exact power too large, a
    # piecewise with True, a non-finite number).
    assert CASES // 2 < accepted < CASES


def test_mutated_catalog_expressions_are_parsed_or_refused() -> None:
    sources = [
        (f.expression, f.names)
        for f in catalog().formulations.values()
        if f.expression and len(f.expression) <= MAX_SOURCE_LENGTH
    ]
    rng = random.Random(SEED + 1)
    refused = 0
    for _ in range(CASES):
        source, names = rng.choice(sources)
        refused += outcome(mutate(rng, source), names) is None
    assert refused > 0


@pytest.mark.parametrize(
    "source",
    [
        "x" * (MAX_SOURCE_LENGTH + 1),
        "(" * 500 + "x" + ")" * 500,
        "-" * (MAX_SOURCE_LENGTH - 1) + "x",
        "x" + " ** x" * 400,
        "exp(" * 300 + "x" + ")" * 300,
        "9" * 1000 + " ** 9",
    ],
)
def test_texts_at_the_limits_are_refused_or_parsed_quickly(source: str) -> None:
    expr = outcome(source, NAMES)
    assert expr is None or isinstance(expr, sympy.Basic)
