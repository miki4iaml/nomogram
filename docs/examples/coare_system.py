# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The loop of COARE 3.6 as a system of equations of the catalog, solved and
compared with the outputs of the code on its test data.

``docs/coare-system.md`` states the values this script computes (a test
checks them); ``main`` only formats and saves the figure besides.

Run from the repository (extra ``viz`` installed)::

    uv run python docs/examples/coare_system.py docs/images/coare-system.png
"""

import sys
import warnings
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

import nomogram as nomo
from nomogram.catalog import catalog
from nomogram.systems import ConvergenceWarning
from nomogram.units import Q_

mpl.use("Agg")  # render to a file, without a display

#: One row in 20 of the test data of COARE 3.6 (see data/NOTICE.md).
DATA = Path(__file__).parent / "data" / "coare36_test.csv"
CATALOG = catalog()
SYSTEM = CATALOG.systems["coare36_surface_layer"]
#: The variables compared with the outputs of the code: the column of the
#: code and the unit.
COMPARED = {
    "u_s": ("usr", "m/s"),
    "q_s": ("qsr", "kg/kg"),
    "T_s": ("tsr", "K"),
    "L": ("L", "m"),
    "z_0M": ("zo", "m"),
    "u_g": ("gust", "m/s"),
}
#: Newton steps and passes of the code drawn on the figure.
STEPS, PASSES = 4, 10


def measurements() -> dict[str, np.ndarray]:
    """The test data of COARE 3.6 and the outputs of the code, by column."""
    lines = DATA.read_text(encoding="utf-8").splitlines()
    rows = [line.split(",") for line in lines if not line.startswith("#")]
    table = np.array(rows[1:], dtype=float)
    return {name: table[:, i] for i, name in enumerate(rows[0])}


def code_inputs(m: dict[str, np.ndarray]) -> dict[str, Any]:
    """The inputs of the system, as the code of COARE 3.6 computes them: its
    specific humidity at the height of measurement, ``qsat26air`` (the
    saturation vapour pressure of Buck with his enhancement factor, at the
    pressure of the thermometer, lines 304 to 309 and 798 to 830 of
    ``coare36vn_zrf_et.py``), its gravity at the latitude, ``grv`` (lines
    834 to 844), and its viscosity of air."""
    t, rh, zt = m["ta"], m["rh"], m["zt"]
    p_tq = m["P"] - 0.125 * zt
    e_s = 6.1121 * np.exp(17.502 * t / (t + 240.97)) * (1.0007 + 3.46e-6 * p_tq)
    e = 0.01 * rh * e_s
    q = 622 * e / (p_tq - 0.378 * e) / 1000
    x = np.sin(np.radians(m["lat"]))
    g = 9.7803267715 * (
        1 + 0.0052790414 * x**2 + 2.32718e-05 * x**4 + 1.262e-07 * x**6 + 7e-10 * x**8
    )
    viscosity = CATALOG.formulations["coare36_kinematic_viscosity_of_air"]
    return {
        "T": Q_(t + 273.16, "K"),
        "T_surf": Q_(m["T_skin"] + 273.16, "K"),
        "q": Q_(q, "kg/kg"),
        "q_surf": Q_(m["Qs"] / 1000, "kg/kg"),
        "U": Q_(m["u"], "m/s"),
        "z_u": Q_(m["zu"], "m"),
        "z_t": Q_(zt, "m"),
        "z_q": Q_(m["zq"], "m"),
        "z_i": Q_(m["zi"], "m"),
        "nu": viscosity.evaluate(t=Q_(t, "degC")).to("m**2/s"),
        "g": Q_(g, "m/s**2"),
    }


def compute() -> dict[str, Any]:
    """The solution, its deviations from the code, and the residual along
    the Newton steps and along the passes of the code."""
    m = measurements()
    inputs = code_inputs(m)
    solution = SYSTEM.evaluate(**inputs)
    deviations = {}
    for name, (column, unit) in COMPARED.items():
        mine = solution[name].to(unit).magnitude
        relative = np.abs(mine / m[column] - 1.0)
        deviations[name] = (float(np.max(relative)), float(np.median(relative)))
    newton, passes = [], []
    with warnings.catch_warnings():
        # Stopped before convergence on purpose: the residual is what counts.
        warnings.simplefilter("ignore", ConvergenceWarning)
        for steps in range(1, STEPS + 1):
            stopped = SYSTEM.evaluate(iterations=steps, **inputs)
            newton.append(float(np.median(stopped.residual)))
    for count in range(1, PASSES + 1):
        iterated = SYSTEM.evaluate(method="fixed-point", iterations=count, **inputs)
        passes.append(float(np.median(iterated.residual)))
    return {
        "m": m,
        "solution": solution,
        "deviations": deviations,
        "newton": newton,
        "passes": passes,
    }


def main(output: str) -> None:
    """Write the residual of the equations along the Newton steps and along
    the passes of the code."""
    results = compute()

    # Formatting only: the axes, their labels, the size and the signature;
    # the labels and the grid follow the preset of the documentation.
    documentation = nomo.display.DisplayOptions.DOCUMENTATION
    figure, axes = plt.subplots()
    axes.semilogy(
        range(1, STEPS + 1), results["newton"], marker="o", label="Newton's method"
    )
    axes.semilogy(
        range(1, PASSES + 1),
        results["passes"],
        marker="s",
        linestyle="--",
        label="passes of the code (fixed point)",
    )
    axes.axhline(1e-12, color="grey", linewidth=1, label="tolerance, 1e-12")
    label = nomo.display.axis_label
    axes.set_xlabel(label("Newton steps, or passes", None, "", options=documentation))
    axes.set_ylabel(label("Median relative residual", None, "", options=documentation))
    axes.set_title("The equations of COARE 3.6 on its test data")
    axes.legend(fontsize="small")
    if documentation.grid:
        axes.grid(alpha=0.3)
    figure.set_size_inches(8, 5)
    figure.tight_layout()
    nomo.plot.sign(figure, axes=axes)
    # No metadata in the image (the image metadata hook refuses it).
    figure.savefig(output, dpi=90, metadata={"Software": None})


if __name__ == "__main__":
    main(sys.argv[1])
