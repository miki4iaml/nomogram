# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Contrail formation from aircraft exhaust: the diagram of Schmidt and
Appleman, the threshold temperature along the standard atmosphere, and
Figure 4 of Appleman (1953) computed again.

``docs/contrails.md`` shows lines of ``compute`` and states the values it
computes (a test checks them); ``main`` only formats and saves the three
figures besides.

Run from the repository (extra ``viz`` installed)::

    uv run python docs/examples/contrails.py docs/images
"""

import sys
import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

import nomogram as nomo
from nomogram.catalog import catalog
from nomogram.comparison import compose
from nomogram.units import Q_

mpl.use("Agg")  # render to a file, without a display

#: Table 3 of Schumann (1996): kerosene behind a B747 at 220 hPa, 42 %
#: relative humidity (Table 2), ambient air at -59 degC.
G_TABLE_3, U_TABLE_2, T_E = 1.49, 0.42, -59.0
#: The relative humidities of Figure 4a of Schumann (1996).
HUMIDITIES = (0.0, 0.3, 0.6, 1.0)
#: The relative humidities of Figure 4 of Appleman (1953), in percent.
APPLEMAN_HUMIDITIES = (0, 60, 90, 100)
#: The formulations the page names, whose references it lists.
CALLED = (
    "schumann1996_overall_propulsion_efficiency",
    "schumann1996_emission_index_water_vapour",
    "schumann1996_mixing_line_slope",
    "schumann1996_maximum_threshold_temperature_liquid",
    "schumann1996_maximum_threshold_temperature_ice",
    "schumann1996_threshold_temperature_liquid",
    "schumann1996_threshold_temperature_ice",
    "schumann2012_critical_relative_humidity",
    "schumann1996_maximum_threshold_temperature_fit",
    "schumann1996_maximum_threshold_temperature_ice_fit",
    "gierens2021_maximum_threshold_temperature",
    "schumann2012_threshold_temperature_fit",
    "appleman1953_available_moisture",
    "appleman1953_critical_temperature_fixed_mixing",
    "itu_r_p835_pressure",
    "itu_r_p835_temperature",
)


def bibliography(called: Iterable[str]) -> list[str]:
    """The references of the formulations called, and of what they use.

    Followed through the links of the catalog (``Catalog.uses``): the
    formulations a formulation calls, is made of or derives from, the
    constants it takes and the scales of its variables, each with its own
    references; one Markdown line per reference.
    """
    c = catalog()
    queue = [f"formulations.{key}" for key in called]
    seen: set[str] = set()
    cited: set[str] = set()
    while queue:
        entry = queue.pop()
        if entry in seen:
            continue
        seen.add(entry)
        for ref in c.uses(entry).refs:
            section, _, key = ref.partition(".")
            if section == "references":
                cited.add(key)
            elif section in ("formulations", "constants", "scales"):
                queue.append(ref)
    lines = []
    for reference in sorted(
        (c.references[key] for key in cited),
        key=lambda r: (r.authors.casefold(), r.year or 0),
    ):
        link = f"https://doi.org/{reference.doi}" if reference.doi else reference.url
        container = f" {reference.container}." if reference.container else ""
        lines.append(
            f"- {reference.authors} ({reference.year or 'n.d.'}). "
            f"*{reference.title}*."
            f"{container}" + (f" <{link}>" if link else "")
        )
    return lines


def crossings(
    saturation: Any, e_e: float, slope: float, t_e: float, t_max: float
) -> tuple[float, float]:
    """Where the mixing line through the ambient point meets a saturation
    curve, above and below its point of tangency t_max (Schumann 1996,
    equations 13 and 14; not in the catalog, which solves for one root of
    an implicit equation only): by bisection, in kelvins."""

    def residual(t: float) -> float:
        return float(saturation(t) - e_e - slope * (t - t_e))

    found = []
    for low, high in ((t_max, 320.0), (150.0, t_max)):
        for _ in range(80):
            middle = 0.5 * (low + high)
            if np.sign(residual(middle)) == np.sign(residual(low)):
                low = middle
            else:
                high = middle
        found.append(0.5 * (low + high))
    return found[0], found[1]


def compute() -> dict[str, Any]:
    """The values of the three figures and of the guide."""
    warnings.simplefilter("ignore")  # NaN where a curve leaves its domain
    c = catalog()
    f = c.formulations

    # Table 3 of Schumann (1996): the exact threshold temperatures.
    exact = c.systems["schumann1996_threshold_temperature"]
    over_ice = c.systems["schumann1996_threshold_temperature_ice"]
    liquid = exact.evaluate(G=Q_(1.49, "Pa/K"), U=Q_(0.42, ""))
    ice = over_ice.evaluate(G=Q_(1.49, "Pa/K"), U=Q_(0.42, ""))

    p_liq = f["schumann2012_saturation_vapour_pressure_liquid"]
    p_ice = f["schumann2012_saturation_vapour_pressure_ice"]

    def pascals(entry: Any, t: Any) -> Any:
        return entry.evaluate(T=Q_(t, "K")).to("Pa").magnitude

    t_lm = float(liquid["T_LM"].to("K").magnitude)
    t_im = float(ice["T_IM"].to("K").magnitude)
    t_e = T_E + 273.15
    e_e = U_TABLE_2 * float(pascals(p_liq, t_e))
    l1, l2 = crossings(lambda t: pascals(p_liq, t), e_e, G_TABLE_3, t_e, t_lm)
    i1, i2 = crossings(lambda t: pascals(p_ice, t), e_e, G_TABLE_3, t_e, t_im)
    t = np.linspace(-70.0, -20.0, 501) + 273.15
    diagram = {
        "T": t - 273.15,
        "e_L": pascals(p_liq, t),
        "e_I": pascals(p_ice, t),
        "T_LM": t_lm - 273.15,
        "T_LC": float(liquid["T_LC"].to("degC").magnitude),
        "T_IM": t_im - 273.15,
        "T_IC": float(ice["T_IC"].to("degC").magnitude),
        "e_LM": float(pascals(p_liq, t_lm)),
        "e_E": e_e,
        "L1": l1 - 273.15,
        "L2": l2 - 273.15,
        "I1": i1 - 273.15,
        "I2": i2 - 273.15,
    }

    # The threshold along the standard atmosphere: kerosene, eta = 0.3.
    slope = compose(
        f["schumann1996_mixing_line_slope"], {"p": f["itu_r_p835_pressure"]}
    )
    maximum = compose(
        f["schumann1996_maximum_threshold_temperature_liquid"], {"G": slope}
    )
    threshold = compose(
        f["schumann1996_threshold_temperature_liquid"], {"T_LM": maximum, "G": slope}
    )
    kerosene: dict[str, Any] = {
        "EI": Q_(1.25, "kg/kg"),
        "c_p": Q_(1004, "J/(kg*K)"),
        "Q": Q_(43, "MJ/kg"),
        "eta": Q_(0.3, ""),
    }
    h = Q_(np.linspace(0, 16, 1601), "km")  # geopotential height
    air = f["itu_r_p835_temperature"].evaluate(H=h).to("degC").magnitude
    by_humidity = {
        u: threshold.evaluate(H=h, U=Q_(u, ""), **kerosene).to("degC").magnitude
        for u in HUMIDITIES
    }
    layers = {}
    for u, t_lc in by_humidity.items():
        forming = np.flatnonzero(air <= t_lc)
        layers[u] = (float(h.magnitude[forming[0]]), float(h.magnitude[forming[-1]]))
    profile = {"H": h.magnitude, "T": air, "T_LC": by_humidity, "layers": layers}

    # Figure 4 of Appleman (1953): the highest critical temperature over the
    # mixing, Delta T from 0.5 to 60 degrees as his tables; below -50 degC,
    # where the Goff-Gratch equation stops, outside="ignore" goes on.
    critical = f["appleman1953_critical_temperature_fixed_mixing"]
    pressures = np.linspace(1000.0, 100.0, 37)
    rise = Q_(np.geomspace(0.5, 60, 121), "K")
    highest = {}
    tangent = {}
    for f_w in APPLEMAN_HUMIDITIES:
        t_c = critical.evaluate(
            f_w=Q_(f_w, "percent"),
            p=Q_(pressures[:, np.newaxis], "hPa"),
            dT=rise,
            outside="ignore",
        )
        highest[f_w] = np.nanmax(t_c.to("degC").magnitude, axis=1)
        # The tangent criterion of Schumann (1996) with Appleman's fuel and
        # engine: 1.4 g of water and 10 000 cal per gram, eta = 0.
        g = f["schumann1996_mixing_line_slope"].evaluate(
            EI=Q_(1.4, "kg/kg"),
            c_p=Q_(0.24, "cal/(g*K)"),
            p=Q_(pressures, "hPa"),
            Q=Q_(10, "kcal/g"),
            eta=Q_(0.0, ""),
        )
        t_lc = exact.evaluate(G=g, U=Q_(f_w / 100, ""))["T_LC"]
        tangent[f_w] = t_lc.to("degC").magnitude
    height = Q_(np.linspace(0, 16, 161), "km")
    standard = {
        "p": f["itu_r_p835_pressure"].evaluate(H=height).to("hPa").magnitude,
        "T": f["itu_r_p835_temperature"].evaluate(H=height).to("degC").magnitude,
    }
    appleman = {
        "p": pressures,
        "highest": highest,
        "tangent": tangent,
        "standard": standard,
    }
    return {
        "diagram": diagram,
        "profile": profile,
        "appleman": appleman,
        "called": CALLED,
    }


def _finish(figure: Any, axes: Any, output: Path) -> None:
    documentation = nomo.display.DisplayOptions.DOCUMENTATION
    if documentation.grid:
        axes.grid(alpha=0.3)
    axes.legend(fontsize="small")
    figure.set_size_inches(8, 5)
    figure.tight_layout()
    nomo.plot.sign(figure, axes=axes)
    # No metadata in the image (the image metadata hook refuses it).
    figure.savefig(output, dpi=90, metadata={"Software": None})
    plt.close(figure)


def main(directory: str) -> None:
    """Write the three figures in ``directory``."""
    results = compute()
    folder = Path(directory)
    documentation = nomo.display.DisplayOptions.DOCUMENTATION
    label = nomo.display.axis_label

    # Formatting only: axes, labels, sizes and the signature; the labels and
    # the grid follow the preset of the documentation.
    d = results["diagram"]
    figure, axes = plt.subplots()
    axes.plot(d["T"], d["e_L"], color="C0", label="saturation over liquid water")
    axes.plot(d["T"], d["e_I"], color="C1", label="saturation over ice")
    tangent = d["e_LM"] + G_TABLE_3 * (d["T"] - d["T_LM"])
    axes.plot(
        d["T"],
        tangent,
        color="C2",
        label=r"mixing line at the threshold, $T_\mathrm{LC}$",
    )
    through = d["e_E"] + G_TABLE_3 * (d["T"] - T_E)
    axes.plot(
        d["T"], through, color="C3", linestyle="--", label="mixing line at -59 °C"
    )
    offsets = {"L1": (4, -10), "I1": (4, -10), "L2": (6, 2), "I2": (-16, 2)}
    for name, offset in offsets.items():
        on_curve = d["e_E"] + G_TABLE_3 * (d[name] - T_E)
        axes.plot(d[name], on_curve, "o", color="C3")
        axes.annotate(
            name, (d[name], on_curve), textcoords="offset points", xytext=offset
        )
    axes.plot(d["T_LM"], d["e_LM"], "o", color="C2")
    axes.annotate(
        "LM", (d["T_LM"], d["e_LM"]), textcoords="offset points", xytext=(-18, 4)
    )
    axes.set_xlim(-70, -20)
    axes.set_ylim(0, 60)
    axes.set_xlabel(label("Temperature", "T", "°C", options=documentation))
    axes.set_ylabel(
        label("Water vapour partial pressure", "e", "Pa", options=documentation)
    )
    axes.set_title("Kerosene, G = 1.49 Pa/K, U = 42 % (Schumann 1996, Table 3)")
    _finish(figure, axes, folder / "contrails-diagram.png")

    p = results["profile"]
    figure, axes = plt.subplots()
    axes.plot(p["T"], p["H"], color="black", label="ISO standard atmosphere")
    for index, (u, t_lc) in enumerate(p["T_LC"].items()):
        axes.plot(
            t_lc,
            p["H"],
            color=f"C{index}",
            linestyle="--",
            label=rf"$T_\mathrm{{LC}}$, U = {u:.0%}",
        )
    axes.set_xlim(-70, -10)
    axes.set_ylim(0, 16)
    axes.set_xlabel(label("Temperature", "T", "°C", options=documentation))
    axes.set_ylabel(label("Geopotential height", "H", "km", options=documentation))
    axes.set_title("Kerosene, η = 0.3: contrails form left of the dashed curves")
    _finish(figure, axes, folder / "contrails-profile.png")

    a = results["appleman"]
    figure, axes = plt.subplots()
    for index, f_w in enumerate(APPLEMAN_HUMIDITIES):
        axes.plot(
            a["highest"][f_w],
            a["p"],
            color=f"C{index}",
            label=f"Appleman, f_w = {f_w} %",
        )
        axes.plot(a["tangent"][f_w], a["p"], color=f"C{index}", linestyle=":")
    axes.plot(
        a["standard"]["T"],
        a["standard"]["p"],
        color="black",
        linestyle="--",
        label="ISO standard atmosphere",
    )
    axes.plot([], [], color="grey", linestyle=":", label="Schumann (1996), η = 0")
    axes.set_yscale("log")
    axes.set_ylim(1000, 100)
    axes.set_yticks([1000, 700, 500, 300, 200, 100])
    axes.set_yticklabels(["1000", "700", "500", "300", "200", "100"])
    axes.yaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    axes.set_xlim(-80, -20)
    axes.set_xlabel(label("Temperature", "T", "°C", options=documentation))
    axes.set_ylabel(label("Pressure", "p", "hPa", options=documentation))
    axes.set_title("Figure 4 of Appleman (1953), computed again")
    _finish(figure, axes, folder / "contrails-appleman.png")


if __name__ == "__main__":
    main(sys.argv[1])
