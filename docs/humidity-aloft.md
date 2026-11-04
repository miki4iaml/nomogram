# Humidity aloft: the formula of the producer and that of the user

Air humidity has several representations: with the temperature, the
relative humidity (over water or over ice), the dew or frost point, the
vapour pressure, the absolute humidity, the wet-bulb temperature; with
the pressure as well, the specific humidity, the mixing ratio, the mole
fraction. Several formulations, and sets of formulations, convert one
into another, and they disagree: as the air cools aloft, a conversion,
and more so a chain of them, can bias the data by as much as their
uncertainty, or more. Such a bias can be corrected only when the data
name the formulations that made them.

The lineage of an observation, a computation or a model output should
therefore cite its formulas, as it cites its instruments; without that,
the uncertainty paid for in a sensor, a measuring chain or a model can be
lost at the first post-processing.

The report of the 2022 upper-air instrument intercomparison of the World
Meteorological Organization (WMO), held at Lindenberg in August and
September 2022 (IOM No. 143, 2024), gives the occasion to measure these
gaps. It names the vapour pressure equation of each radiosonde, finds
that the dew point and the relative humidity of the same sounding
disagree aloft, and recalls that converting between them requires the
vapour pressure equation and its inverse (section 10.1.4). This page
computes, with nomogram, the gaps these formulations produce along a
vertical profile, through the dew point, over water or over ice, and
sets them against WMO's requirements.

## The formula of each radiosonde

The report names, in its Table 3.3, the vapour pressure equation of
each radiosonde, as its manufacturer states it:

| Radiosonde | Vapour pressure equation | In the catalog |
|---|---|---|
| RS41 (Vaisala), iMet-54 | Wexler, modified by Hardy (1998) for ITS-90 | `hardy1998_water` |
| CF-06-AH, DFM-17, iMS-100 | Hyland and Wexler (1983) | `hyland_wexler1983` |
| GTH3 | Goff and Gratch (1946) | `goff_gratch1946` |
| M20 | Sonntag (1990) | `sonntag1990` |
| PS-B3 | Bolton (1980) | `bolton1980` |
| WxR-301D | Buck (1981), the variant not stated | `buck1981` |

The report names these formulas and does not print them: the catalog
records it in their notes, with the keyword `radiosonde`. Vaisala also
publishes simplified conversion formulas (`vaisala2013_water`,
`vaisala2013_ice`), fitted to Wagner and Pruss within 0.083 % from -20 to
50 °C and to its equation over ice within 0.052 %: both fits are
relations nomogram verifies, and reproduces. That note is general, and
its simplified form over water stops at -20 °C; the RS41 computes with
Hardy (1998), whose formulation over water covers -100 to 100 °C.

## Two definitions of the relative humidity

WMO relates the relative humidity to the saturation of moist air, larger
than that of pure water by the enhancement factor, about 0.5 % near
1000 hPa, and so does ITU-R P.453 (`itu_r_p453_es_water`, Buck 1996 times
the enhancement factor). Vaisala relates it to the saturation vapour
pressure of pure water, below 0 °C to that of supercooled water. The
catalog keeps the two apart, as
`SaturationVapourPressureOverWater` and
`SaturationVapourPressureOverWaterInMoistAir`: `compare` puts them in one
table only when asked for a kind they share, `kind="VapourPressure"`. The
difference does not show in the formulas; recomputing an
absolute humidity with P.453 from a relative humidity of Vaisala gives
it 0.2 to 0.4 % larger between the ground and 5 km.

## Along a vertical profile

The figure follows the reference atmosphere of ITU-R P.835, identical to
the ISO 2533 standard atmosphere up to 32 km, from the ground to 14 km.
On the left, each formulation a user may take, against the producer's,
Hardy (1998), that of the RS41. In the middle, the false round trip: the
producer codes a dew point with its own inverse, as BUFR messages
require, and the user takes the vapour pressure back with another
formulation, at a relative humidity of 20 %. On the right, the
saturation over ice, or in mixed phase, against the same reference
(see [Over water or over ice](#over-water-or-over-ice)).

```python
import numpy as np

import nomogram as nomo
from nomogram.catalog import catalog
from nomogram.comparison import Composition, Evaluable, compare, compose
from nomogram.units import Q_

import matplotlib.pyplot as plt

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
    "murphy_koop2005_water": "Murphy and Koop (2005)",
}
grid = {"GeopotentialHeight": Q_(np.linspace(0, 14, 141), "km")}
reference = along(producer, "Hardy (1998), RS41")
saturation = compare(
    [reference, *(along(k, label) for k, label in users.items())], reference, grid
)
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
```

![Deviation of saturation vapour pressure formulations from Hardy (1998) along the reference atmosphere, of the vapour pressure taken back from the dew point, and of the saturation over ice or in mixed phase](images/humidity-aloft.png)

Each curve stops where its source stops answering: Vaisala's simplified
form at -20 °C, near 5.4 km, the Magnus form of WMO at -45 °C, Goff and
Gratch at -50 °C; the saturation over ice of IAPWS starts at the triple
point, near 2.3 km. At 11 km, where the temperature reaches -56.5 °C:

| Formulation | Saturation vapour pressure | Vapour pressure back from the dew point, RH 20 % |
|---|---|---|
| MetPy 1.7.1 | -0.62 % | -1.14 % |
| Bolton (1980), MetPy's dew point | -2.32 % | -5.33 % |
| Tetens (1930) | -7.73 % | -13.63 % |
| Buck (1996), ITU-R P.453 | -1.09 % | |
| Hyland and Wexler (1983) | +0.18 % | |
| Murphy and Koop (2005) | -3.34 % | |

The round trip widens the gap 1.8 to 2.3 times: it evaluates the two
formulations at the dew point, -68.9 °C there, colder than the air. The intercomparison saw
the same in practice: between the BUFR messages and the files of the
manufacturers, relative humidity and dew point disagree negligibly near
the surface, and by more than 10 % in the upper troposphere, beyond
typical measurement uncertainties, possibly through the inverse of the
vapour pressure equation (IOM No. 143, section 10.1.4).

## Over water or over ice

Below 0 °C, the same water vapour gives two relative humidities: over
supercooled water, and over ice. WMO recommends the first, and the
radiosondes report it, including below freezing (IOM No. 143, section
1.5); the report recalls that it is lower than the relative humidity
over ice for the same water vapour content (chapter 6). Other codes
take another saturation below 0 °C:

| Relative humidity | Saturation below 0 °C | In the catalog |
|---|---|---|
| WMO, radiosondes, Vaisala | over supercooled water | `hardy1998_water`, `vaisala2013_water` |
| MetPy 1.7.1, with `phase='auto'` (over water by default) | over ice, from the triple point, 273.16 K | `metpy171_saturation_vapour_pressure_auto` |
| IFS CY49R1, diagnostic relative humidity | over ice below 250.16 K (-23 °C); from there to 0 °C, weighted by a liquid fraction quadratic in temperature | `ecmwf_ifs_saturation_mixed_phase` |

The catalog keeps the saturation over water and over ice as sibling
kinds, `SaturationVapourPressureOverWater` and
`SaturationVapourPressureOverIce`, both a `SaturationVapourPressure`:
`compare` puts them in one table only when asked for that kind,
`kind="SaturationVapourPressure"`, as on the right of the figure. MetPy
changes phase at the triple point, the IFS gradually from 0 to -23 °C.
At 11 km, the saturation over ice is 42.6 % below that over water: air
saturated over ice has a relative humidity of 57 % over water. Between
the relative humidity of a radiosonde and that of the IFS, the gap of
convention is there more than five times the largest gap of formulation
on the left of the figure, that of Tetens.

## Against the requirements of WMO

The OSCAR requirements the intercomparison uses (IOM No. 143, Table 9.2)
give the uncertainty of the relative humidity in percentage points
(%RH), at one standard deviation, bias and random error combined:

| Application | Threshold | Breakthrough | Goal |
|---|---|---|---|
| Numerical weather prediction, boundary layer and free troposphere | 10 %RH | 5 %RH | 2 %RH |
| Climate, boundary layer and free troposphere | 0.5 %RH | 0.25 %RH | 0.05 %RH |
| Climate, upper troposphere and lower stratosphere | 1.0 %RH | 0.5 %RH | 0.25 %RH |

A relative deviation becomes percentage points when multiplied by the
relative humidity: at saturation, as on the left of the figure, 1 % is
1 %RH. In the lower troposphere, the choice of formulation stays well
under the goal of numerical weather prediction. Aloft, Bolton's form
reaches that goal and Tetens' goes beyond the breakthrough. For climate, even the
difference of definition, 0.2 to 0.4 %RH, takes most of the threshold.
The gap is a bias, not a noise: it does not average out.

## Search

`search(keyword="radiosonde")` finds the formulations a radiosonde uses,
`search(keyword="mixed phase")` those that join water and ice,
`search("RS41")` the intercomparison report, and
`used_by("references.vaisala2013")` what Vaisala's formulas give,
including its citation of Wagner and Pruss.
