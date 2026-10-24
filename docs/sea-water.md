# Sea water: salinity scales and vapour pressure

The `sea-water` family holds the salinity and the chlorinity of sea water,
their conventional scales, the vapour pressure of sea water, and the
salinity effect on the surface humidity of flux algorithms. This page
shows how to use them, and what the 2 % lowering of the vapour pressure
means at the sea surface.

## Salinity on conventional scales

Salinity is one quantity kind, `SeaWaterSalinity`, measured on scales that
followed one another: Knudsen (1901), Cox (JPOTS 1966), the Practical
Salinity Scale 1978, Reference Salinity (2008, the reference scale) and
Absolute Salinity (TEOS-10). As with temperatures, values are taken on the
reference scale and converted to the scale each formulation was fitted on:

```python
from nomogram.catalog import catalog
from nomogram.units import Q_

c = catalog()
s_r = Q_(35.16504, "g/kg")                     # Reference Salinity of the standard ocean
c.scales["knudsen1901"].from_reference(35.16504)   # (34.99997..., False): S_K, not outside
c.formulations["sverdrup1942_vapour_pressure_ratio"].evaluate(S=s_r)   # 0.981205, on the Knudsen scale
```

Practical Salinity is a number, as CF (canonical unit 1) and TEOS-10
write it: S_P = 35, not 35 per mille, and QUDT's `unit:PSU` is not used.
Knudsen and Cox salinities, mass ratios, stay in per mille. A value taken
as given (`scale="ignore"`) is written as its scale writes it: S_P without
a unit (in per mille or in g/kg it would be read a thousand times
smaller), a Knudsen or Cox salinity with its unit (a bare number would be
read as a fraction); otherwise it is refused. One value cannot be S_P = 35
and S_K = 35 per mille at once: compare such formulations from the
Reference Salinity, the default.

```python
coare = c.formulations["coare36_salinity_factor"]
coare.evaluate(S=s_r)                          # 0.98, from the Reference Salinity
coare.evaluate(S=Q_(35), scale="ignore")       # 0.98, S_P = 35 taken as given
```

Absolute Salinity depends on the location (its anomaly comes from a
look-up table nomogram does not hold): a formulation stated on it, such as
the ITTC vapour pressure, is evaluated with `scale="ignore"`, values as
given, and refuses a conversion otherwise. The scales, their conversions
and the disagreements between sources are described in the
[catalog guide](catalog.md#conventional-scales).

## Vapour pressure of sea water

Sea water evaporates less than pure water at the same temperature. The
sources give the ratio of the two vapour pressures, or the vapour pressure
itself. At 25 degC, for the standard ocean (S_P = 35, S_R = 35.16504 g/kg,
Cl = 19.374 per mille), against the TEOS-10 Manual (section 3.37:
3110.57 Pa over 3169.93 Pa, a ratio of 0.981274):

| Formulation | Source | Value | Deviation from TEOS-10 |
|---|---|---|---|
| `witting1908_vapour_pressure_ratio` | Witting (1908), through Sverdrup et al. (1942) | 0.981227 | -0.005 % |
| `sverdrup1942_vapour_pressure_ratio` | Sverdrup et al. (1942), Knudsen scale | 0.981205 | -0.007 % |
| `robinson1954_vapour_pressure_ratio` | Robinson (1954), 25 degC | 0.981279 | +0.000 % |
| `nayar2016_vapour_pressure_ratio` | Nayar et al. (2016) | 0.981533 | +0.026 % |
| `coare36_salinity_factor` | COARE 3.6 | 0.980000 | -0.130 % |
| `raoult_sharqawy2010` | Raoult's law (Sharqawy et al. 2010, ITTC) | 0.979523 | -0.178 % |
| `dickson2007_vapour_pressure` | Dickson et al. (2007) | 3110.56 Pa | -0.000 % |
| `millero_leung1976_vapour_pressure` | Millero and Leung (1976), p_0 from TEOS-10 | 3111.06 Pa | +0.016 % |
| `weiss_price1980_vapour_pressure` | Weiss and Price (1980) | 3108.79 Pa | -0.057 % |

The ratios based on measurements agree within 0.03 %, and the vapour
pressures of Dickson et al. and of Millero and Leung within 0.02 %;
Weiss and Price is 0.06 % low. Raoult's law, an ideal-solution estimate,
lowers the vapour pressure about 9 % too much. These are observations,
computed by nomogram: no source states them.

Dickson et al. name no salinity scale: their S = 35 for Cl = 19.374 is
taken as Practical Salinity, inferred from these numbers. Two
conversions hold over less than some stated domains: IPTS-48, converted
from -2 to 30 degC, and PSS-78, from 2 to 42. Beyond them the default
evaluation gives NaN: Weiss and Price, stated from 0 to 40 degC and
from S_P = 0, above t90 = 29.98 degC and below S_P = 2; COARE below
S_P = 2.
`scale="ignore"` evaluates the formula as written.

```python
t = Q_(298.15, "K")
c.formulations["dickson2007_vapour_pressure"].evaluate(T=t, S=s_r)   # 3110.56 Pa
c.formulations["ittc2011_vapour_pressure"].evaluate(T=t, S=s_r, scale="ignore")     # Absolute Salinity
c.search(output="RelativeVapourPressureOfSeaWater")    # every ratio
```

Over sea water, "about 98 %" is said of three close quantities, not to be
confused: the relative vapour pressure above, the activity of water, and
the relative humidity of air in equilibrium with sea water (see
[rosetta.md](rosetta.md#ambiguous-trade-terms)).

## The 2 % at the sea surface

Flux algorithms take the humidity at the sea surface as 0.98 times its
value over pure water (`sea_surface_saturation_specific_humidity`: IFS,
Beljaars 1998, Fairall et al. 1996), or as the salinity factor of COARE
3.6. Two ways to see what it changes:

**An equivalent cooling of the sea surface.** Beljaars (1998, p. 46)
defines the decrease of the sea surface temperature that gives the same
change of surface humidity: "about .27 K at 0 degC to about .35 K at
30 degC". nomogram finds it by inverting a saturation vapour pressure, here
the Buck (1981) Magnus form, the Tetens form of the IFS:

```python
from nomogram.inversion import invert
from nomogram.model import Variable

buck = c.formulations["buck1981_magnus"]
inverse = invert(
    buck, "t",
    output=Variable("t", "CelsiusTemperature", "DEG_C", "Celsius temperature"),
    input=Variable("e", "VapourPressure", "HectoPA", "Vapour pressure"),
)
t = Q_(30.0, "degC")
t - inverse.evaluate(e=0.98 * buck.evaluate(t=t))   # 0.351 K
```

| Sea surface temperature | 0 degC | 10 degC | 20 degC | 30 degC |
|---|---|---|---|---|
| Equivalent decrease | 0.278 K | 0.301 K | 0.326 K | 0.351 K |

The inversion is applied to the vapour pressure; Beljaars applies the
factor to the specific humidity, which is not linear in it, hence a small
difference.

**The radio refractivity at the surface.** Evaporation ducts come from the
sharp decrease of humidity just above the sea, so that the refractivity at
the surface, which rests on the surface vapour pressure, sets the strength
of the duct. With ITU-R P.453 (equation 2) at 25 degC and 1013.25 hPa:

| | Vapour pressure | Radio refractivity N |
|---|---|---|
| Pure water (IAPWS SR1-86) | 31.698 hPa | 396.85 |
| Sea water, S = 35 (Robinson ratio) | 31.105 hPa | 394.35 |
| Air at 25 degC and 80 % relative humidity | 25.359 hPa | 370.22 |

Salinity lowers the surface refractivity by 2.5 units; the
surface-to-air difference, 26.6 units over pure water, falls to 24.1 over
sea water: about 9 % less. The height of an evaporation duct follows from
the whole profile, through a surface-layer model (Monin-Obukhov
similarity) that nomogram does not hold; the sources read for this family
give no estimate of the effect on duct height. Babin, Young and Carton
(1997, pp. 200-201) used the correction in two of their evaporation duct
models over the sea off Wallops Island, not over the relatively fresh
water of the tidal Potomac; the Paulus-Jeske model has none.
