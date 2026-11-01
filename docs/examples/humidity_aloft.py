# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Saturation vapour pressure formulations along a vertical profile, and the
false round trip through the dew point, against the producer's formulation.

The lines of ``main`` up to the second ``plot_deviation_profile`` are the
ones shown in ``docs/humidity-aloft.md`` (a test checks it); the rest only
formats and saves the figure.

Run from the repository (extra ``viz`` installed)::

    uv run python docs/examples/humidity_aloft.py docs/images/humidity-aloft.png
"""

import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

import nomogram as nomo
from nomogram.catalog import catalog
from nomogram.comparison import Composition, Evaluable, compare, compose
from nomogram.units import Q_

mpl.use("Agg")  # render to a file, without a display


def main(output: str) -> None:
    """Write the two profiles of deviations to ``output``."""
    f = catalog().formulations
    air = f["itu_r_p835_temperature"]  # the ISO standard atmosphere up to 32 km

    def along(key: str, label: str, temperature: Evaluable = air) -> Composition:
        formulation = f[key]
        point = formulation.inputs[0].identifier
        return compose(formulation, {point: temperature}, label=label)

    producer = "hardy1998_water"  # Wexler refitted to ITS-90, that of the RS41
    users = {
        "metpy171_saturation_vapour_pressure": "MetPy 1.7.1",
        "bolton1980": "Bolton (1980), MetPy's dew point",
        "tetens1930": "Tetens (1930)",
        "sonntag1990_magnus": "Sonntag (1990), WMO",
        "hyland_wexler1983": "Hyland and Wexler (1983)",
        "goff_gratch1946": "Goff and Gratch (1946)",
        "buck1996": "Buck (1996), ITU-R P.453",
        "vaisala2013_water": "Vaisala (2013), equation 6",
    }
    grid = {"GeopotentialHeight": Q_(np.linspace(0, 14, 141), "km")}
    reference = along(producer, "Hardy (1998), RS41")
    saturation = compare(
        [reference, *(along(k, label) for k, label in users.items())], reference, grid
    )
    # The false round trip: the producer codes a dew point with its own
    # inverse, the user takes the vapour pressure back with another formula.
    vapour = compose(f["vapour_pressure_from_relative_humidity"], {"e_s": reference})
    dew_point = compose(f["hardy1998_dew_point"], {"e": vapour})
    names = ("metpy171_saturation_vapour_pressure", "bolton1980", "tetens1930")
    decoders = {k: users[k] for k in (*names, "sonntag1990_magnus")}
    back = along(producer, "Hardy (1998), RS41", dew_point)
    decoded = compare(
        [back, *(along(k, label, dew_point) for k, label in decoders.items())],
        back,
        {**grid, "RelativeHumidity": Q_(0.2, "")},
    )
    oscar = {  # WMO OSCAR, at RH = 100 % (IOM No. 143, Table 9.2)
        "Climate, UTLS, threshold: 1 %RH": (-1, 1),
        "NWP, goal: 2 %RH": (-2, 2),
        "NWP, breakthrough: 5 %RH": (-5, 5),
    }
    documentation = nomo.display.DisplayOptions.DOCUMENTATION
    figure, (left, right) = plt.subplots(1, 2, sharey=True)
    nomo.plot.plot_deviation_profile(
        saturation, references=oscar, ax=left, options=documentation, xlim=(-9, 3)
    )
    nomo.plot.plot_deviation_profile(
        decoded, ax=right, options=documentation, xlim=(-15, 3)
    )

    # Formatting only: the titles, the size and the signature.
    left.set_title("Saturation vapour pressure")
    right.set_title("Vapour pressure back from the dew point, at RH 20 %")
    right.set_ylabel("")
    figure.set_size_inches(13, 6.5)
    figure.tight_layout()
    nomo.plot.sign(figure, axes=right)
    # No metadata in the image (the image metadata hook refuses it).
    figure.savefig(output, dpi=90, metadata={"Software": None})


if __name__ == "__main__":
    main(sys.argv[1])
