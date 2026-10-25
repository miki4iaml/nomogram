# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Draw the nomogram logo as SVG: geometry computed, nothing drawn by hand.

The logo spells NOMO:

- N is a working alignment chart (an N or Z chart): two parallel scales,
  u read downward on the left stroke and v upward on the right one, and a
  diagonal scale for w = u / v, graduated at s = w / (1 + w) of its
  length. A straight reading line through u and v crosses the diagonal at
  u / v; :func:`n_chart` checks it.
- The first O is a sphere of linked nodes (shared vocabularies), the
  second a globe in orthographic projection (the Earth sciences).
- M is plain, and the reading line runs on through O, M and O.

The banner of the README adds the word "nomogram" below, drawn with
strokes too, so that no font is needed. Each file is written in light
and dark variants, or carries its dark variant as a CSS media query. The
files in ``docs/images`` are generated, never edited by hand; a test
checks that they match this script.

Usage::

    uv run python scripts/make_logo.py [OUTPUT_DIRECTORY]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

#: Letter height and stroke widths, in SVG units.
H = 100.0
STROKE = 8.0
THIN = 1.6
TICK = 5.0

#: Reading line: u on the left scale, v on the right one (0 to 5).
U, V = 3.0, 2.2

#: Colours: ink, sea of the globe, accent of the reading line.
THEMES = {
    "light": {"ink": "#1f2937", "sea": "#dbeafe", "accent": "#c2410c"},
    "dark": {"ink": "#e5e7eb", "sea": "#1e3a5f", "accent": "#fb923c"},
}

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "images"

Point = tuple[float, float]


def style(theme: str | None) -> str:
    """CSS of a file: fixed colours, or light with a dark media query."""
    colours = THEMES[theme or "light"]
    rules = (
        f"  .ink {{ stroke: {colours['ink']}; fill: none; "
        "stroke-linecap: round; stroke-linejoin: round; }\n"
        f"  .fine {{ stroke: {colours['ink']}; fill: none; "
        "stroke-linecap: round; opacity: 0.55; }\n"
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


def line(start: Point, end: Point, cls: str, width: float) -> str:
    return (
        f'<line x1="{f(start[0])}" y1="{f(start[1])}" x2="{f(end[0])}" '
        f'y2="{f(end[1])}" class="{cls}" stroke-width="{f(width)}"/>'
    )


def circle(centre: Point, radius: float, cls: str, width: float = 0.0) -> str:
    stroke = f' stroke-width="{f(width)}"' if width else ""
    return (
        f'<circle cx="{f(centre[0])}" cy="{f(centre[1])}" r="{f(radius)}" '
        f'class="{cls}"{stroke}/>'
    )


def path(data: str, cls: str, width: float) -> str:
    return f'<path d="{data}" class="{cls}" stroke-width="{f(width)}"/>'


def n_chart(
    x: float, y: float, w: float, *, stroke: float = STROKE, ticks: bool = True
) -> tuple[list[str], Point, Point]:
    """The N as an alignment chart; returns its elements and the reading points."""
    scale = H / 5.0
    out = [
        line((x, y), (x, y + H), "ink", stroke),
        line((x + w, y), (x + w, y + H), "ink", stroke),
        line((x, y), (x + w, y + H), "ink", stroke),
    ]
    if ticks:
        # u downward on the left stroke, v upward on the right one.
        for k in range(11):
            value = k / 2.0
            length = TICK * (1.6 if k % 2 == 0 else 1.0)
            left_y, right_y = y + scale * value, y + H - scale * value
            out.append(
                line(
                    (x - length - stroke / 2, left_y),
                    (x - stroke / 2, left_y),
                    "fine",
                    THIN,
                )
            )
            out.append(
                line(
                    (x + w + stroke / 2, right_y),
                    (x + w + stroke / 2 + length, right_y),
                    "fine",
                    THIN,
                )
            )
        # w = u / v on the diagonal, at s = w / (1 + w) from its top end.
        norm = math.hypot(w, H)
        nx, ny = H / norm, -w / norm  # unit normal, up and right
        for value in (0.25, 0.5, 1.0, 2.0, 4.0):
            s = value / (1.0 + value)
            cx, cy = x + s * w, y + s * H
            near, far = stroke / 2, stroke / 2 + 1.6 * TICK
            out.append(
                line(
                    (cx + nx * near, cy + ny * near),
                    (cx + nx * far, cy + ny * far),
                    "fine",
                    THIN,
                )
            )
    left = (x, y + scale * U)
    right = (x + w, y + H - scale * V)
    # The reading line crosses the diagonal at w = U / V: check it.
    s = (U / V) / (1.0 + U / V)
    crossing = (left[1] - y) / ((left[1] - y) + (y + H - right[1]))
    if abs(crossing - s) > 1e-12:  # pragma: no cover - a broken chart
        msg = f"the reading line crosses the diagonal at {crossing}, not {s}"
        raise AssertionError(msg)
    out.append(circle((x + s * w, y + s * H), stroke * 0.55, "dot"))
    return out, left, right


def reading_line(
    left: Point, right: Point, start: float, end: float, width: float
) -> str:
    """The straight line through both reading points, from x = start to end."""
    slope = (right[1] - left[1]) / (right[0] - left[0])
    return line(
        (start, left[1] + slope * (start - left[0])),
        (end, left[1] + slope * (end - left[0])),
        "read",
        width,
    )


def globe(centre: Point, radius: float) -> list[str]:
    """A sphere in orthographic projection, seen from the equator."""
    cx, cy = centre
    out = [circle(centre, radius, "sea")]
    for longitude in (30.0, 60.0):
        rx = radius * math.sin(math.radians(longitude))
        out.append(
            f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx)}" ry="{f(radius)}" '
            f'class="fine" stroke-width="{f(THIN)}"/>'
        )
    out.append(line((cx, cy - radius), (cx, cy + radius), "fine", THIN))
    for latitude in (-60.0, -30.0, 0.0, 30.0, 60.0):
        yy = cy - radius * math.sin(math.radians(latitude))
        half = radius * math.cos(math.radians(latitude))
        out.append(line((cx - half, yy), (cx + half, yy), "fine", THIN))
    out.append(circle(centre, radius, "ink", STROKE))
    return out


def nodes(centre: Point, radius: float) -> list[str]:
    """A sphere of linked nodes: a Fibonacci lattice, its visible side."""
    cx, cy = centre
    count, points = 24, []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(count):
        z = 1.0 - 2.0 * (i + 0.5) / count
        ring = math.sqrt(1.0 - z * z)
        x3, y3 = ring * math.cos(golden * i), ring * math.sin(golden * i)
        if x3 > -0.1:
            points.append((cx + 0.82 * radius * y3, cy - 0.82 * radius * z))
    out = []
    for i, point in enumerate(points):
        nearest = sorted(points[i + 1 :], key=lambda p: math.dist(p, point))[:2]
        out += [
            line(point, other, "fine", THIN)
            for other in nearest
            if math.dist(point, other) < 0.75 * radius
        ]
    out += [circle(point, 2.2, "node") for point in points]
    out.append(circle(centre, radius, "ink", STROKE))
    return out


def m_letter(x: float, y: float, w: float) -> list[str]:
    points = (
        (x, y + H),
        (x, y),
        (x + w / 2, y + 0.62 * H),
        (x + w, y),
        (x + w, y + H),
    )
    data = "M " + " L ".join(f"{f(px)},{f(py)}" for px, py in points)
    return [path(data, "ink", STROKE)]


def logo_parts() -> tuple[list[str], float]:
    """The elements of NOMO and the width they take."""
    margin, width, gap = 22.0, 64.0, 26.0
    x_n = margin
    x_nodes = x_n + width + gap
    x_m = x_nodes + H + gap
    x_globe = x_m + width + gap
    total = x_globe + H + margin
    y = margin
    parts, left, right = n_chart(x_n, y, width)
    parts += nodes((x_nodes + H / 2, y + H / 2), H / 2)
    parts += m_letter(x_m, y, width)
    parts += globe((x_globe + H / 2, y + H / 2), H / 2)
    parts.append(reading_line(left, right, x_n - 12.0, x_globe + H + 12.0, 2.6))
    parts += [circle(point, STROKE * 0.55, "dot") for point in (left, right)]
    return parts, total


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
    parts, total = logo_parts()
    return svg(parts, total, H + 44.0, None)


def banner(theme: str) -> str:
    """NOMO above the word "nomogram", in fixed colours (README)."""
    parts, total = logo_parts()
    height = 34.0
    words, width = wordmark(0.0, 0.0, height, STROKE * 0.75)
    left = (total - width) / 2
    parts.append(f'<g transform="translate({f(left)} {f(H + 44.0)})">')
    parts += words
    parts.append("</g>")
    return svg(parts, total, H + 44.0 + height * 1.6 + 22.0, theme)


def icon(*, small: bool = False) -> str:
    """The N chart alone; ``small`` drops the graduations (favicon)."""
    margin, width = 26.0, 64.0
    stroke = 14.0 if small else STROKE
    parts, left, right = n_chart(margin, margin, width, stroke=stroke, ticks=not small)
    parts.append(
        reading_line(
            left, right, margin - 14.0, margin + width + 14.0, 7.0 if small else 3.2
        )
    )
    parts += [circle(point, stroke * 0.55, "dot") for point in (left, right)]
    return svg(parts, width + 2 * margin, H + 2 * margin, None)


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
