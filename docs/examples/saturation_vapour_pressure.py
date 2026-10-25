# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Compare every saturation vapour pressure formulation with IAPWS, and plot it.

The lines of ``main`` up to ``plot_deviations`` are the ones shown in the
README (a test checks it); the rest only formats and saves the figure.

Run from the repository (extra ``viz`` installed)::

    uv run python docs/examples/saturation_vapour_pressure.py docs/images/saturation-vapour-pressure.png
"""

import sys

import matplotlib as mpl
import numpy as np

import nomogram as nomo
from nomogram.units import Q_

mpl.use("Agg")  # render to a file, without a display


def main(output: str) -> None:
    """Write the comparison plot to ``output``."""
    catalog = nomo.catalog.catalog()
    formulations = catalog.formulations_of("SaturationVapourPressureOverWater")
    reference = catalog.formulations["iapws_sr1_86"]
    temperatures = Q_(np.linspace(-60, 110, 341), "degC")

    table = nomo.comparison.compare(
        formulations, reference, {"ThermodynamicTemperature": temperatures}
    )
    ax = nomo.plot.plot_deviations(table)

    # Formatting only.
    ax.set_ylim(-1.0, 1.0)
    ax.grid(alpha=0.3)
    ax.set_title("Saturation vapour pressure over water: deviation from IAPWS")
    ax.figure.set_size_inches(11, 6.5)
    ax.figure.tight_layout()
    # No metadata in the image (the image metadata hook refuses it).
    ax.figure.savefig(output, dpi=90, metadata={"Software": None})


if __name__ == "__main__":
    main(sys.argv[1])
