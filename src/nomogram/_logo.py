# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Geometry of the logo, NOMO, shared by its SVG files and the plots.

- N is a working alignment chart (an N or Z chart): two parallel scales,
  u read downward on the left stroke and v upward on the right one, and a
  diagonal scale for w = u / v, graduated at s = w / (1 + w) of its
  length. A straight reading line through u and v crosses the diagonal at
  u / v; :func:`n_chart` checks it.
- The first O is a sphere of linked nodes (shared vocabularies), the
  second a globe in orthographic projection (the Earth sciences).
- M is plain, and the reading line runs on through O, M and O.

Shapes are in SVG units, y downward, with a role that says how each is
painted (:data:`THEMES`): ``ink`` and ``fine`` strokes (``fine`` at 55 %
opacity), ``read`` for the reading line, filled ``sea``, ``dot`` and
``node``. ``scripts/make_logo.py`` writes them as SVG,
:func:`nomogram.plot.sign` as matplotlib artists. Standard library only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

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

#: Opacity of the ``fine`` strokes (graduations, graticule, links).
FINE_OPACITY = 0.55

Point = tuple[float, float]


@dataclass(frozen=True)
class Line:
    start: Point
    end: Point
    role: str
    width: float


@dataclass(frozen=True)
class Circle:
    centre: Point
    radius: float
    role: str
    #: Stroke width; 0 for a filled circle.
    width: float = 0.0


@dataclass(frozen=True)
class Ellipse:
    centre: Point
    rx: float
    ry: float
    role: str
    width: float


@dataclass(frozen=True)
class Polyline:
    points: tuple[Point, ...]
    role: str
    width: float


Shape = Line | Circle | Ellipse | Polyline


def n_chart(
    x: float, y: float, w: float, *, stroke: float = STROKE, ticks: bool = True
) -> tuple[list[Shape], Point, Point]:
    """The N as an alignment chart; returns its shapes and the reading points."""
    scale = H / 5.0
    out: list[Shape] = [
        Line((x, y), (x, y + H), "ink", stroke),
        Line((x + w, y), (x + w, y + H), "ink", stroke),
        Line((x, y), (x + w, y + H), "ink", stroke),
    ]
    if ticks:
        # u downward on the left stroke, v upward on the right one.
        for k in range(11):
            value = k / 2.0
            length = TICK * (1.6 if k % 2 == 0 else 1.0)
            left_y, right_y = y + scale * value, y + H - scale * value
            out.append(
                Line(
                    (x - length - stroke / 2, left_y),
                    (x - stroke / 2, left_y),
                    "fine",
                    THIN,
                )
            )
            out.append(
                Line(
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
                Line(
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
    out.append(Circle((x + s * w, y + s * H), stroke * 0.55, "dot"))
    return out, left, right


def reading_line(
    left: Point, right: Point, start: float, end: float, width: float
) -> Line:
    """The straight line through both reading points, from x = start to end."""
    slope = (right[1] - left[1]) / (right[0] - left[0])
    return Line(
        (start, left[1] + slope * (start - left[0])),
        (end, left[1] + slope * (end - left[0])),
        "read",
        width,
    )


def globe(centre: Point, radius: float) -> list[Shape]:
    """A sphere in orthographic projection, seen from the equator."""
    cx, cy = centre
    out: list[Shape] = [Circle(centre, radius, "sea")]
    for longitude in (30.0, 60.0):
        rx = radius * math.sin(math.radians(longitude))
        out.append(Ellipse(centre, rx, radius, "fine", THIN))
    out.append(Line((cx, cy - radius), (cx, cy + radius), "fine", THIN))
    for latitude in (-60.0, -30.0, 0.0, 30.0, 60.0):
        yy = cy - radius * math.sin(math.radians(latitude))
        half = radius * math.cos(math.radians(latitude))
        out.append(Line((cx - half, yy), (cx + half, yy), "fine", THIN))
    out.append(Circle(centre, radius, "ink", STROKE))
    return out


def nodes(centre: Point, radius: float) -> list[Shape]:
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
    out: list[Shape] = []
    for i, point in enumerate(points):
        nearest = sorted(points[i + 1 :], key=lambda p: math.dist(p, point))[:2]
        out += [
            Line(point, other, "fine", THIN)
            for other in nearest
            if math.dist(point, other) < 0.75 * radius
        ]
    out += [Circle(point, 2.2, "node") for point in points]
    out.append(Circle(centre, radius, "ink", STROKE))
    return out


def m_letter(x: float, y: float, w: float) -> list[Shape]:
    points = ((x, y + H), (x, y), (x + w / 2, y + 0.62 * H), (x + w, y), (x + w, y + H))
    return [Polyline(points, "ink", STROKE)]


def logo() -> tuple[list[Shape], float, float]:
    """The shapes of NOMO, with the width and height they take."""
    margin, width, gap = 22.0, 64.0, 26.0
    x_n = margin
    x_nodes = x_n + width + gap
    x_m = x_nodes + H + gap
    x_globe = x_m + width + gap
    y = margin
    shapes, left, right = n_chart(x_n, y, width)
    shapes += nodes((x_nodes + H / 2, y + H / 2), H / 2)
    shapes += m_letter(x_m, y, width)
    shapes += globe((x_globe + H / 2, y + H / 2), H / 2)
    shapes.append(reading_line(left, right, x_n - 12.0, x_globe + H + 12.0, 2.6))
    shapes += [Circle(point, STROKE * 0.55, "dot") for point in (left, right)]
    return shapes, x_globe + H + margin, H + 2 * margin


def icon(*, small: bool = False) -> tuple[list[Shape], float, float]:
    """The N chart alone; ``small`` drops the graduations (favicon)."""
    margin, width = 26.0, 64.0
    stroke = 14.0 if small else STROKE
    shapes, left, right = n_chart(margin, margin, width, stroke=stroke, ticks=not small)
    line_width = 7.0 if small else 3.2
    shapes.append(
        reading_line(left, right, margin - 14.0, margin + width + 14.0, line_width)
    )
    shapes += [Circle(point, stroke * 0.55, "dot") for point in (left, right)]
    return shapes, width + 2 * margin, H + 2 * margin
