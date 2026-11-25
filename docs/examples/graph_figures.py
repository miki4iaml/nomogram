# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Figures of three graphs of the catalog, the loop of COARE 3.6, a branch
of the tree of kinds and the kinds of the family of contrails, each in a
light and a dark variant.

The documents are those of ``nomogram.graph``; this script only shapes the
figures. In the loop, each equation is merged with the variable it gives
and numbered as in the table of ``docs/coare-system.md``, and a driver
says how the loop is iterated. protee writes the DOT text and the legend;
this script sets the edges, the font size and the colours of the variant,
and Graphviz (pygraphviz, installed with ``protee[viz]``) lays them out.
The edges of the loop are orthogonal; those of the branch are straight
segments, since the orthogonal routing of the Graphviz that pygraphviz
bundles crashes on it. The legend goes below on the left and the logo below on the
right, at the scale of the figure, so that both keep their size whatever
the width the figure is shown at.

Run from the repository (development dependencies installed)::

    uv run python docs/examples/graph_figures.py docs/images
"""

import base64
import copy
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pygraphviz  # type: ignore[import-untyped]  # ships no type information
from protee import viz

from nomogram.catalog import catalog
from nomogram.graph import kind_graph, system_graph

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "docs" / "images" / "logo.svg"
SYSTEM = catalog().systems["coare36_surface_layer"]
#: The kinds of the branch drawn in docs/graphs.md.
BRANCH = ["RelativeHumidity", "RelativeHumidityWithRespectToIce"]
#: The kinds the family contrail adds, drawn in docs/contrails.md, with
#: the provisional kinds it takes.
CONTRAIL = [
    "OverallPropulsionEfficiency",
    "LowerHeatingValue",
    "EmissionIndexOfWaterVapour",
    "ContrailFactor",
    "ContrailAvailableMoisturePerDegree",
    "MixingLineSlope",
    "SaturationVapourPressureSlopeOverWater",
    "SaturationVapourPressureSlopeOverIce",
    "ContrailMaximumThresholdTemperature",
    "ContrailMaximumThresholdTemperatureWithRespectToIce",
    "ContrailThresholdTemperature",
    "ContrailThresholdTemperatureWithRespectToIce",
    "ContrailCriticalTemperatureAtFixedMixing",
    "ContrailCriticalRelativeHumidity",
]
#: The colours of each variant: background, ink, and ink on a filled node.
THEMES: Mapping[str, Mapping[str, str]] = {
    "light": {"background": "#ffffff", "ink": "#1f2937", "on_fill": "#1f2937"},
    "dark": {"background": "#0d1117", "ink": "#e6edf3", "on_fill": "#0d1117"},
}
#: The colours of the roles and of the reads, the same in every figure.
UNKNOWN, INTERMEDIATE, READS = "#56B4E9", "#009E73", "#E69F00"
#: Points between the figure and what goes below it, and the logo's height.
MARGIN, LOGO_HEIGHT = 12.0, 36.0
_SIZE = re.compile(r'width="([0-9.]+)pt" height="([0-9.]+)pt"')
_ROOT = re.compile(r"<svg\b[^>]*>")
_VIEWBOX = re.compile(r'viewBox="([^"]+)"')

type Styles = dict[str, dict[tuple[str, str], dict[str, str]]]


def loop_document() -> dict[str, Any]:
    """The loop of COARE 3.6: each equation merged with the variable it
    gives, labelled with its rank, which numbers the table of the guide,
    the variable and its unit; the reads between equations; and the driver
    of the loop."""
    base = system_graph(SYSTEM)
    nodes = {node["id"]: node for node in base["nodes"]}
    giver = {
        edge["target"]: edge["source"]
        for edge in base["edges"]
        if edge["type"] == "nomogram:gives"
    }
    merged: list[dict[str, Any]] = []
    for node in base["nodes"]:
        if node["type"] != "nomogram:equation":
            continue
        variable = nodes["variables." + node["id"].split(".", 1)[1]]
        unit = variable.get("unit_symbol")
        merged.append(
            {
                "id": node["id"],
                "label": f"({node['rank']}) {variable['label']}"
                + ("" if unit in (None, "1") else f", {unit}"),
                "type": "nomogram:equation",
                "role": variable["role"],
                "rank": node["rank"],
                "description": node["label"],
            }
        )
    edges: list[dict[str, Any]] = []
    for edge in base["edges"]:
        if edge["type"] == "nomogram:reads" and edge["source"] in giver:
            read = {
                "source": giver[edge["source"]],
                "target": edge["target"],
                "key": 0,
                "type": "nomogram:reads",
            }
            if "role" in edge:
                read["role"] = edge["role"]
            edges.append(read)
    unknowns = [
        n["id"].split(".", 1)[1] for n in merged if n["role"] == "nomogram:unknown"
    ]
    driver = {
        "id": f"solvers.{SYSTEM.key}",
        "label": (
            f"loop driver: {SYSTEM.iterations} passes in the code (fixed point), "
            f"Newton's method in nomogram\niterates {', '.join(unknowns)}"
        ),
        "type": "nomogram:solver",
        "rank": 0,
    }
    document = copy.deepcopy(base)
    document["nodes"] = [driver, *merged]
    document["edges"] = edges
    vocabulary = document["graph"]["vocabulary"]
    vocabulary["type"] = [
        value
        for value in vocabulary["type"]
        if value["id"] not in {"nomogram:gives", "nomogram:variable"}
    ] + [{"id": "nomogram:solver", "on": "node", "label": "loop driver"}]
    vocabulary["role"] = [v for v in vocabulary["role"] if v["id"] != "nomogram:input"]
    return document


def loop_styles(theme: str) -> Styles:
    """The styles of the loop: rounded boxes, the roles in fixed colours,
    the reads that close the loop dashed and free of the ranks."""
    on_fill = THEMES[theme]["on_fill"]
    return {
        "node": {
            ("type", "nomogram:equation"): {"shape": "box", "style": "rounded"},
            ("type", "nomogram:solver"): {
                "shape": "box",
                "style": "rounded,bold",
                "penwidth": "2",
            },
            ("role", "nomogram:unknown"): {
                "style": "rounded,filled",
                "fillcolor": UNKNOWN,
                "penwidth": "2.5",
                "fontcolor": on_fill,
            },
            ("role", "nomogram:intermediate"): {
                "style": "rounded,filled,dashed",
                "fillcolor": INTERMEDIATE,
                "penwidth": "1",
                "fontcolor": on_fill,
            },
        },
        "edge": {
            ("type", "nomogram:reads"): {"color": READS, "fontcolor": READS},
            ("role", "nomogram:closing"): {
                "style": "dashed",
                "constraint": "false",
                "color": READS,
            },
        },
    }


def branch_styles(theme: str) -> Styles:
    """The styles of the branch of kinds: protee's, with the ink of a
    filled node."""
    on_fill = THEMES[theme]["on_fill"]
    return {
        "node": {
            ("origin", "qudt"): {"fontcolor": on_fill},
            ("origin", "nomogram"): {"fontcolor": on_fill},
        },
        "edge": {},
    }


def _defaults(theme: str, splines: str | None = None) -> tuple[str, str, str]:
    """The attributes a variant adds to the graph, the nodes and the edges."""
    colours = THEMES[theme]
    # The colour of the graph is that of the frame of the legend.
    graph = (
        f'bgcolor="{colours["background"]}", color="{colours["ink"]}", '
        f'fontcolor="{colours["ink"]}", fontsize="14", pad="0.2"'
        + (f', splines="{splines}"' if splines else "")
    )
    ink = f'color="{colours["ink"]}", fontcolor="{colours["ink"]}", fontsize="11"'
    return graph, ink, ink


def _themed(dot: str, theme: str, splines: str, rankdir: str | None = None) -> str:
    """The DOT text of protee, with the attributes of the variant; a wide
    tree of many roots is laid out from left to right (``rankdir``)."""
    graph, node, edge = _defaults(theme, splines)
    if rankdir is not None:
        dot = re.sub(r'rankdir="[A-Z]+"', f'rankdir="{rankdir}"', dot, count=1)
    dot = dot.replace("  graph [", f"  graph [{graph}, ", 1)
    dot = dot.replace("  node [", f"  node [{node}, ", 1)
    return dot.replace("  edge [", f"  edge [{edge}, ", 1)


def _legend(document: Mapping[str, Any], styles: Styles, theme: str) -> str:
    """The DOT text of the legend protee writes, alone, in the variant."""
    lines = viz.to_dot(document, styles=styles, legend=True).splitlines()
    start = lines.index("  subgraph cluster_legend {")
    end = lines.index("  }", start)
    graph, node, edge = _defaults(theme)
    head = [
        "digraph legend {",
        f"  graph [{graph}];",
        f'  node [{node}, fontname="Helvetica,Arial,sans-serif"];',
        f'  edge [{edge}, fontname="Helvetica,Arial,sans-serif"];',
    ]
    return "\n".join([*head, *lines[start : end + 1], "}"]) + "\n"


def _render(dot: str) -> str:
    """The SVG Graphviz draws from a DOT text."""
    drawing: bytes = pygraphviz.AGraph(string=dot).draw(format="svg", prog="dot")
    return drawing.decode("utf-8")


def _size(svg: str) -> tuple[float, float]:
    found = _SIZE.search(svg)
    if found is None:
        raise ValueError("an SVG of Graphviz gives its size in points")
    return float(found.group(1)), float(found.group(2))


def _nested(svg: str, prefix: str, x: float, y: float) -> str:
    """An SVG of Graphviz as an element of another, at (x, y) in points,
    its identifiers prefixed so that two drawings never share one."""
    width, height = _size(svg)
    root = _ROOT.search(svg)
    box = _VIEWBOX.search(root.group(0)) if root else None
    if root is None or box is None:
        raise ValueError("an SVG of Graphviz has a root with a viewBox")
    body = re.sub(r'\bid="', f'id="{prefix}', svg[root.end() : svg.rindex("</svg>")])
    return (
        f'<svg x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
        f'viewBox="{box.group(1)}">{body}</svg>'
    )


def _frame_bottom(legend: str) -> float:
    """The bottom of the dashed frame of a legend, in points from its top:
    the lowest point of the cluster, shifted as Graphviz shifts the graph."""
    frame = re.search(
        r'class="cluster">.*?<polygon[^>]*points="([^"]+)"', legend, re.DOTALL
    )
    shift = re.search(
        r'class="graph" transform="[^"]*translate\(([-0-9.]+) ([-0-9.]+)\)"', legend
    )
    if frame is None or shift is None:
        raise ValueError("a legend of protee is a cluster in a graph of Graphviz")
    lowest = max(float(point.split(",")[1]) for point in frame.group(1).split())
    return float(shift.group(2)) + lowest


def _foot(logo: str) -> float:
    """Where the letters of the logo stand, as a share of its height: the
    lowest point of their strokes, round ends included."""
    lowest = 0.0
    for shape in re.finditer(r'<(line|circle|path) ([^>]*)class="ink"([^>]*)>', logo):
        attributes = dict(
            re.findall(r'([a-z0-9-]+)="([^"]*)"', shape.group(2) + shape.group(3))
        )
        half = float(attributes.get("stroke-width", "0")) / 2
        if shape.group(1) == "line":
            low = max(float(attributes["y1"]), float(attributes["y2"]))
        elif shape.group(1) == "circle":
            low = float(attributes["cy"]) + float(attributes["r"])
        else:
            low = max(
                float(y) for y in re.findall(r"[-0-9.]+,([-0-9.]+)", attributes["d"])
            )
        lowest = max(lowest, low + half)
    box = _VIEWBOX.search(logo)
    if box is None or not lowest:
        raise ValueError("the logo has a viewBox and letters of class ink")
    return lowest / float(box.group(1).split()[3])


def _logo(theme: str) -> tuple[str, float]:
    """The logo as a data URI, in the colours of the variant's background
    rather than of the reader's browser, and its width in points."""
    text = LOGO.read_text(encoding="utf-8")
    dark = re.search(
        r"@media \(prefers-color-scheme: dark\) \{(.*?)\n  \}", text, re.DOTALL
    )
    box = _VIEWBOX.search(text)
    if dark is None or box is None:
        raise ValueError("the logo has a viewBox and a dark variant")
    text = (
        text[: dark.start()]
        + (dark.group(1) if theme == "dark" else "")
        + text[dark.end() :]
    )
    _, _, width, height = (float(v) for v in box.group(1).split())
    uri = "data:image/svg+xml;base64," + base64.b64encode(text.encode("utf-8")).decode(
        "ascii"
    )
    return uri, LOGO_HEIGHT * width / height


def compose(figure: str, legend: str, theme: str) -> str:
    """The figure, its legend below on the left and the logo below on the
    right, in one SVG, all at the same scale; the letters of the logo stand
    on the line of the bottom of the legend's frame."""
    figure_width, figure_height = _size(figure)
    legend_width, legend_height = _size(legend)
    logo, logo_width = _logo(theme)
    width = max(figure_width, legend_width + MARGIN + logo_width)
    below = figure_height + MARGIN
    logo_top = max(
        below,
        below
        + _frame_bottom(legend)
        - _foot(LOGO.read_text(encoding="utf-8")) * LOGO_HEIGHT,
    )
    height = max(below + legend_height, logo_top + LOGO_HEIGHT)
    background = THEMES[theme]["background"]
    root = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width:.2f}pt" height="{height:.2f}pt" '
        f'viewBox="0 0 {width:.2f} {height:.2f}">'
    )
    image = (
        f'<image x="{width - logo_width:.2f}" y="{logo_top:.2f}" '
        f'width="{logo_width:.2f}" height="{LOGO_HEIGHT:.2f}" href="{logo}"/>'
    )
    parts = [
        root,
        f'<rect width="{width:.2f}" height="{height:.2f}" fill="{background}"/>',
        _nested(figure, "figure-", (width - figure_width) / 2, 0.0),
        _nested(legend, "legend-", 0.0, below),
        image,
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def figures() -> dict[str, str]:
    """The six figures, by file name: light, then dark."""
    drawn: list[
        tuple[str, dict[str, Any], Callable[[str], Styles], str | None, str, str | None]
    ] = [
        ("coare-loop", loop_document(), loop_styles, "rank", "ortho", None),
        (
            "kinds-relative-humidity",
            kind_graph(BRANCH),
            branch_styles,
            None,
            "polyline",
            None,
        ),
        ("kinds-contrail", kind_graph(CONTRAIL), branch_styles, None, "polyline", "LR"),
    ]
    found: dict[str, str] = {}
    for name, document, styles_of, order_by, splines, rankdir in drawn:
        for theme in THEMES:
            styles = styles_of(theme)
            dot = viz.to_dot(document, styles=styles, order_by=order_by, legend=False)
            figure = _render(_themed(dot, theme, splines, rankdir))
            legend = _render(_legend(document, styles, theme))
            suffix = "" if theme == "light" else "-dark"
            found[f"{name}{suffix}.svg"] = compose(figure, legend, theme)
    return found


def main(directory: str) -> None:
    for name, svg in figures().items():
        (Path(directory) / name).write_text(svg, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(sys.argv[1])
