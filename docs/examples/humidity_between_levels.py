# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Interpolate between 850 and 500 hPa by each practice, and plot it.

The lines of ``main`` up to ``plot_profiles`` are the ones shown in
``docs/vertical.md`` (a test checks it); the rest only formats and saves
the figure.

Run from the repository (extra ``viz`` installed)::

    uv run python docs/examples/humidity_between_levels.py docs/images/humidity-between-levels.png
"""

import sys

import matplotlib as mpl
import numpy as np

import nomogram as nomo
from nomogram.catalog import catalog
from nomogram.comparison import compare, compose, partial
from nomogram.inversion import invert
from nomogram.model import Variable
from nomogram.units import Q_

mpl.use("Agg")  # render to a file, without a display


def main(output: str) -> None:
    """Write the three profiles to ``output``."""
    f = catalog().formulations
    # The ITU-R reference atmosphere against the pressure.
    height = invert(
        f["itu_r_p835_pressure"],
        "H",
        output=Variable("H", "GeopotentialHeight", "KiloM", "Geopotential height"),
        input=Variable("p", "Pressure", "HectoPA", "Pressure"),
    )
    temperature = compose(f["itu_r_p835_temperature"], {"H": height}, label="P.835")
    altitude = compose(f["itu_r_p835_geometric_altitude"], {"Z": height})
    density = compose(f["itu_r_p835_water_vapour_density"], {"z": altitude})
    vapour = compose(
        f["itu_r_p453_vapour_pressure_from_density"],
        {"rho": density, "T": temperature},
    )
    mixing = compose(f["metpy171_mixing_ratio"], {"e": vapour})
    humidity = compose(
        f["specific_humidity_from_mixing_ratio"], {"r": mixing}, label="P.835"
    )
    relative = compose(
        f["metpy171_relative_humidity_from_specific_humidity"],
        {"q": humidity, "T": temperature},
        label="P.835",
    )
    dew_point = compose(f["metpy171_dew_point"], {"e": vapour})

    # Its values at 850 and 500 hPa, the two levels interpolated between.
    levels = {"p_1": Q_(850, "hPa"), "p_2": Q_(500, "hPa")}
    for name, profile in [
        ("T", temperature),
        ("q", humidity),
        ("T_d", dew_point),
        ("RH", relative),
    ]:
        levels[f"{name}_1"] = profile.evaluate(p=levels["p_1"])
        levels[f"{name}_2"] = profile.evaluate(p=levels["p_2"])

    def between(key: str, label: str) -> nomo.comparison.Partial:
        """A scheme or a route, its levels fixed."""
        names = {v.identifier for v in f[key].inputs}
        fixed = {n: v for n, v in levels.items() if n in names}
        return partial(f[key], label=label, **fixed)

    temperatures = {
        "log_pressure_interpolation_temperature": "T in ln p (MetPy)",
        "pressure_interpolation_temperature": "T in p (FULL-POS)",
    }
    humidities = {
        "log_pressure_interpolation_specific_humidity": "q in ln p (MetPy)",
        "pressure_interpolation_specific_humidity": "q in p (FULL-POS)",
        "metpy171_isentropic_specific_humidity": "q in θ (MetPy, isentropic)",
        "log_pressure_interpolation_log_specific_humidity": "ln q in ln p (nomogram)",
    }
    routes = {
        "metpy171_relative_humidity_dew_point_log_pressure": "Td, T in ln p (Skew-T)",
        "metpy171_relative_humidity_dew_point_pressure": "Td, T in p (MetPy indices)",
        "metpy171_relative_humidity_specific_humidity_log_pressure": "q, T in ln p",
        "metpy171_relative_humidity_isentropic": "q in θ (isentropic)",
        "relative_humidity_log_specific_humidity_log_pressure": "ln q, T in ln p (nomogram)",
        "pressure_interpolation_relative_humidity": "RH in p (FULL-POS)",
    }
    grid = {"Pressure": Q_(np.linspace(850, 500, 141), "hPa")}
    tables = [
        compare([between(k, label) for k, label in schemes.items()], truth, grid)
        for schemes, truth in [
            (temperatures, temperature),
            (humidities, humidity),
            (routes, relative),
        ]
    ]
    documentation = nomo.display.DisplayOptions.DOCUMENTATION
    axes = nomo.plot.plot_profiles(tables, options=documentation)

    # Formatting only: the size.
    figure = axes[0].figure
    figure.set_size_inches(13, 6.5)
    # No metadata in the image (the image metadata hook refuses it).
    figure.savefig(output, dpi=90, metadata={"Software": None})


if __name__ == "__main__":
    main(sys.argv[1])
