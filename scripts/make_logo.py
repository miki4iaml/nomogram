# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Write the nomogram logo as SVG files, from its geometry.

The geometry of NOMO lives in :mod:`nomogram._logo`, shared with
:func:`nomogram.plot.sign`; this script writes it as SVG. The banner of
the README adds the word "nomogram" below, drawn with strokes too, so
that no font is needed. Each file is written in light and dark variants,
or carries its dark variant as a CSS media query. The files in
``docs/images`` are generated, never edited by hand; a test checks that
they match this script.

Usage::

    uv run python scripts/make_logo.py [OUTPUT_DIRECTORY]
"""

from __future__ import annotations

import sys
from pathlib import Path

from nomogram import _logo
from nomogram._logo import FINE_OPACITY, THEMES, Point

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "images"


def style(theme: str | None) -> str:
    """CSS of a file: fixed colours, or light with a dark media query."""
    colours = THEMES[theme or "light"]
    rules = (
        f"  .ink {{ stroke: {colours['ink']}; fill: none; "
        "stroke-linecap: round; stroke-linejoin: round; }\n"
        f"  .fine {{ stroke: {colours['ink']}; fill: none; "
        f"stroke-linecap: round; opacity: {FINE_OPACITY}; }}\n"
        f"  .sea {{ fill: {colours['sea']}; stroke: none; }}\n"
        f"  .read {{ stroke: {colours['accent']}; fill: none; "
        "stroke-linecap: round; }\n"
        f"  .dot {{ fill: {colours['accent']}; }}\n"
        f"  .node {{ fill: {colours['ink']}; }}\n"
    )
    if theme is None:
        dark = THEMES["dark"]
        rules += (
            "  @media (prefers-color-scheme: dark) {\n"
            f"    .ink, .fine {{ stroke: {dark['ink']}; }}\n"
            f"    .sea {{ fill: {dark['sea']}; }}\n"
            f"    .read {{ stroke: {dark['accent']}; }}\n"
            f"    .dot {{ fill: {dark['accent']}; }}\n"
            f"    .node {{ fill: {dark['ink']}; }}\n"
            "  }\n"
        )
    return rules


def f(x: float) -> str:
    """A coordinate, short and exact enough."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def circle(centre: Point, radius: float, cls: str, width: float = 0.0) -> str:
    stroke = f' stroke-width="{f(width)}"' if width else ""
    return (
        f'<circle cx="{f(centre[0])}" cy="{f(centre[1])}" r="{f(radius)}" '
        f'class="{cls}"{stroke}/>'
    )


def path(data: str, cls: str, width: float) -> str:
    return f'<path d="{data}" class="{cls}" stroke-width="{f(width)}"/>'


def element(shape: _logo.Shape) -> str:
    """One shape of the logo as an SVG element."""
    if isinstance(shape, _logo.Line):
        (x1, y1), (x2, y2) = shape.start, shape.end
        return (
            f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" '
            f'class="{shape.role}" stroke-width="{f(shape.width)}"/>'
        )
    if isinstance(shape, _logo.Circle):
        return circle(shape.centre, shape.radius, shape.role, shape.width)
    if isinstance(shape, _logo.Ellipse):
        cx, cy = shape.centre
        return (
            f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(shape.rx)}" ry="{f(shape.ry)}" '
            f'class="{shape.role}" stroke-width="{f(shape.width)}"/>'
        )
    data = "M " + " L ".join(f"{f(x)},{f(y)}" for x, y in shape.points)
    return path(data, shape.role, shape.width)


def wordmark(
    x: float, top: float, height: float, width: float
) -> tuple[list[str], float]:
    """The word "nomogram" in geometric lowercase strokes; returns its width.

    ``height`` is the x-height; round letters are circles of that diameter.
    """
    r = height / 2
    base = top + height
    gap = 0.32 * height
    parts: list[str] = []

    def stem(at: float) -> str:
        return f"M {f(at)},{f(base)} V {f(top)}"

    def arch(at: float, radius: float) -> str:
        return (
            f"M {f(at)},{f(top + radius)} A {f(radius)} {f(radius)} 0 0 1 "
            f"{f(at + 2 * radius)},{f(top + radius)} V {f(base)}"
        )

    def n(at: float) -> float:
        parts.append(path(f"{stem(at)} {arch(at, r)}", "ink", width))
        return 2 * r

    def o(at: float) -> float:
        parts.append(circle((at + r, top + r), r, "ink", width))
        return 2 * r

    def m(at: float) -> float:
        small = 0.4 * height
        data = f"{stem(at)} {arch(at, small)} {arch(at + 2 * small, small)}"
        parts.append(path(data, "ink", width))
        return 4 * small

    def g(at: float) -> float:
        hook, depth = 0.8 * r, 0.6 * height
        right, low = at + 2 * r, base + depth - hook
        data = (
            f"M {f(right)},{f(top)} V {f(low)} A {f(hook)} {f(hook)} 0 0 1 "
            f"{f(right - 2 * hook)},{f(low)}"
        )
        parts.append(circle((at + r, top + r), r, "ink", width))
        parts.append(path(data, "ink", width))
        return 2 * r

    def letter_r(at: float) -> float:
        shoulder = 0.35 * height
        data = (
            f"{stem(at)} M {f(at)},{f(top + shoulder)} A {f(shoulder)} {f(shoulder)} "
            f"0 0 1 {f(at + shoulder)},{f(top)} H {f(at + shoulder + 0.15 * height)}"
        )
        parts.append(path(data, "ink", width))
        return shoulder + 0.15 * height

    def a(at: float) -> float:
        parts.append(circle((at + r, top + r), r, "ink", width))
        parts.append(path(f"M {f(at + 2 * r)},{f(top)} V {f(base)}", "ink", width))
        return 2 * r

    at = x
    for draw in (n, o, m, o, g, letter_r, a, m):
        at += draw(at) + gap
    return parts, at - gap - x


def svg(parts: list[str], width: float, height: float, theme: str | None) -> str:
    body = "\n  ".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(width)} '
        f'{f(height)}" role="img" aria-label="nomogram">\n'
        f"  <title>nomogram</title>\n  <style>\n{style(theme)}  </style>\n"
        f"  {body}\n</svg>\n"
    )


def logo() -> str:
    """NOMO, its dark variant as a media query."""
    shapes, width, height = _logo.logo()
    return svg([element(s) for s in shapes], width, height, None)


def banner(theme: str) -> str:
    """NOMO above the word "nomogram", in fixed colours (README)."""
    shapes, total, height = _logo.logo()
    parts = [element(s) for s in shapes]
    x_height = 34.0
    words, width = wordmark(0.0, 0.0, x_height, _logo.STROKE * 0.75)
    left = (total - width) / 2
    parts.append(f'<g transform="translate({f(left)} {f(height)})">')
    parts += words
    parts.append("</g>")
    return svg(parts, total, height + x_height * 1.6 + 22.0, theme)


def icon(*, small: bool = False) -> str:
    """The N chart alone; ``small`` drops the graduations (favicon)."""
    shapes, width, height = _logo.icon(small=small)
    return svg([element(s) for s in shapes], width, height, None)


def files() -> dict[str, str]:
    """Every file the script writes, by name."""
    return {
        "logo.svg": logo(),
        "logo-icon.svg": icon(),
        "logo-favicon.svg": icon(small=True),
        "banner-light.svg": banner("light"),
        "banner-dark.svg": banner("dark"),
    }


def main(argv: list[str]) -> int:
    """Write the files to the directory given, by default ``docs/images``."""
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTPUT
    out.mkdir(parents=True, exist_ok=True)
    for name, text in files().items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
