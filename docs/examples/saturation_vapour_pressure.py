# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Compare every saturation vapour pressure formulation with IAPWS, and plot it.

Run from the repository (extra ``viz`` installed)::

    uv run python docs/examples/saturation_vapour_pressure.py docs/images/saturation-vapour-pressure.png
"""

import sys

import matplotlib as mpl
import numpy as np

from nomogram.catalog import catalog
from nomogram.comparison import compare
from nomogram.plot import plot_deviations
from nomogram.units import Q_

mpl.use("Agg")  # render to a file, without a display
import matplotlib.pyplot as plt


def main(output: str) -> None:
    """Write the comparison plot to ``output``."""
    formulations = catalog().formulations_of("SaturationVapourPressureOverWater")
    reference = catalog().formulations["iapws_sr1_86"]
    temperatures = Q_(np.linspace(-60, 110, 341), "degC")

    # One vectorised pass; NaN outside each formulation's stated domain.
    table = compare(formulations, reference, {"ThermodynamicTemperature": temperatures})

    figure, ax = plt.subplots(figsize=(11, 6.5))
    plot_deviations(table, ax=ax)
    ax.set_ylim(-1.0, 1.0)
    ax.grid(alpha=0.3)
    ax.set_title("Saturation vapour pressure over water: deviation from IAPWS")
    figure.tight_layout()
    figure.savefig(output, dpi=90)


if __name__ == "__main__":
    main(sys.argv[1])
