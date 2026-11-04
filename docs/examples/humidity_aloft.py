# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Saturation vapour pressure formulations along a vertical profile, the
false round trip through the dew point, and the junctions of water and ice,
against the formulation WMO names for radiosondes.

The lines of ``main`` up to the third ``plot_deviation_profile`` are the
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
from nomogram.inversion import invert
from nomogram.model import Variable
from nomogram.units import Q_

mpl.use("Agg")  # render to a file, without a display


def main(output: str) -> None:
    """Write the three profiles of deviations to ``output``."""
    f = catalog().formulations
    air = f["itu_r_p835_temperature"]  # the ISO standard atmosphere up to 32 km

    def along(key: str, label: str, temperature: Evaluable = air) -> Composition:
        formulation = f[key]
        point = formulation.inputs[0].identifier
        return compose(formulation, {point: temperature}, label=label)

    wmo = "hyland_wexler1983"  # named by WMO for radiosondes (WMO-No. 8, 12.4.1)
    users = {
        "hardy1998_water": "Hardy (1998), RS41",
        "metpy171_saturation_vapour_pressure": "MetPy 1.7.1",
        "bolton1980": "Bolton (1980), MetPy's dew point",
        "tetens1930": "Tetens (1930)",
        "sonntag1990_magnus": "Sonntag (1990), WMO's Magnus form",
        "goff_gratch1946": "Goff and Gratch (1946)",
        "buck1996": "Buck (1996), ITU-R P.453",
        "murphy_koop2005_water": "Murphy and Koop (2005)",
    }
    grid = {"GeopotentialHeight": Q_(np.linspace(0, 12, 121), "km")}
    reference = along(wmo, "Hyland and Wexler (1983)")
    saturation = compare(
        [reference, *(along(k, label) for k, label in users.items())], reference, grid
    )
    # The false round trip: the producer codes a dew point with the inverse of
    # its formulation, the user takes the vapour pressure back with another.
    inverse = invert(  # the dew point, solved numerically in the interval searched
        f[wmo],
        "T",
        output=Variable("T_d", "DewPointTemperature", "K", "Dew point temperature"),
        input=Variable("e", "VapourPressure", "PA", "Vapour pressure"),
        search=(173.15, 373.15),
    )
    vapour = compose(f["vapour_pressure_from_relative_humidity"], {"e_s": reference})
    dew_point = compose(inverse, {"e": vapour})
    names = ("hardy1998_water", "metpy171_saturation_vapour_pressure", "bolton1980")
    decoders = {k: users[k] for k in (*names, "tetens1930", "sonntag1990_magnus")}
    back = along(wmo, "Hyland and Wexler (1983), strict round trip", dew_point)
    decoded = compare(
        [back, *(along(k, label, dew_point) for k, label in decoders.items())],
        back,
        {**grid, "RelativeHumidity": Q_(0.2, "")},
    )
    # Over ice below the triple point, or in mixed phase: sibling kinds of the
    # saturation over water, compared only when asked.
    phases = {
        "iapws_r14_08_sublimation": "IAPWS R14-08, over ice",
        "metpy171_saturation_vapour_pressure_auto": "MetPy 1.7.1, phase='auto'",
        "ecmwf_ifs_saturation_mixed_phase": "IFS CY49R1, mixed phase",
    }
    junctions = compare(
        [reference, *(along(k, label) for k, label in phases.items())],
        reference,
        grid,
        kind="SaturationVapourPressure",
    )
    oscar = {  # WMO OSCAR, at RH = 100 % (IOM No. 143, Table 9.2)
        "Climate, UTLS, threshold: 1 %RH": (-1, 1),
        "NWP, goal: 2 %RH": (-2, 2),
        "NWP, breakthrough: 5 %RH": (-5, 5),
    }
    documentation = nomo.display.DisplayOptions.DOCUMENTATION
    figure, (left, middle, right) = plt.subplots(1, 3, sharey=True)
    nomo.plot.plot_deviation_profile(
        saturation, references=oscar, ax=left, options=documentation, xlim=(-9, 3)
    )
    nomo.plot.plot_deviation_profile(
        decoded, ax=middle, options=documentation, xlim=(-15, 3)
    )
    nomo.plot.plot_deviation_profile(
        junctions, ax=right, options=documentation, xlim=(-50, 5)
    )

    # Formatting only: the titles, the size and the signature.
    left.set_title("Saturation vapour pressure over water")
    middle.set_title(r"False round trip $g \circ f^{-1}$, RH 20 %")
    right.set_title("Over ice or in mixed phase")
    for axes in (middle, right):
        axes.set_ylabel("")
    figure.set_size_inches(19, 7)
    figure.tight_layout()
    nomo.plot.sign(figure, axes=right)
    # No metadata in the image (the image metadata hook refuses it).
    figure.savefig(output, dpi=90, metadata={"Software": None})


if __name__ == "__main__":
    main(sys.argv[1])
