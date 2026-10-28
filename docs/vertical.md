# Vertical coordinates

A value placed in the vertical needs two things: its coordinate, and the
reference from which it is reckoned. WMO puts it this way: "Height,
level or altitude are presented with respect to a well-defined
reference. Typical references are MSL, station altitude or the
1 013.2 hPa plane" (WMO-No. 8, 2024, Volume I, chapter 1).

nomogram gives each coordinate its own quantity kind, defined after a
text in force: the CF standard names, WMO-No. 8 (2024), the IFS
documentation, and for aviation the SERA regulation (EU) No 923/2012,
which takes over the ICAO definitions (the ICAO Annexes are not freely
available). A result feeds an input of its own kind or of one of its
ancestors, never another (see [catalog.md](catalog.md)): coordinates that
look alike but differ by metres never mix silently.

The kinds live in the `atmosphere` family, with their references, and
the terms each community uses in `trade_terms`.

## Which kind for which coordinate

| Coordinate | Kind | Reckoned from | CF standard name | Defined in |
|---|---|---|---|---|
| Altitude (geometric) | `Altitude` (QUDT) | the geoid, about mean sea level | `altitude` | CF; SERA, Art. 2, point 39 (from mean sea level) |
| Altitude of the surface, elevation of a station | `SurfaceAltitude` | the geoid | `surface_altitude` | CF; WMO-No. 8, Volume I, 1.3.3.2 |
| Height above the surface | `Height` (QUDT) | the surface | `height` | CF; SERA, Art. 2, point 84 (from a specified datum) |
| Geopotential | `Geopotential` | the geoid | `geopotential` (m² s⁻²) | CF; IFS CY49R1, Part III, equation 2.6 |
| Geopotential height | `GeopotentialHeight` | the geoid | `geopotential_height` | CF; WMO-No. 8, Volume I, equation 12.12 |
| Thickness of a layer | `GeopotentialThickness` | its lower level | `atmosphere_layer_thickness_expressed_as_geopotential_height_difference` | CF |
| Pressure altitude, flight level | `PressureAltitude` | the standard atmosphere | none | SERA, Art. 2, points 101 and 78 |
| Ellipsoidal height (satellite positioning) | `EllipsoidalHeight` | a reference ellipsoid | `height_above_reference_ellipsoid` | CF |
| Geoid height | `GeoidHeight` | a reference ellipsoid | `geoid_height_above_reference_ellipsoid` | CF |
| Pressure of an isobaric level | `Pressure` (QUDT) | | `air_pressure` (narrower) | CF |
| Surface pressure | `SurfaceAirPressure` | | `surface_air_pressure` | CF |
| Pressure at mean sea level | `SeaLevelPressure` | | `air_pressure_at_mean_sea_level` | CF; WMO-No. 8, Volume I, 3.7 |
| QNH, QFE | `AltimeterSetting`, `AerodromePressure` | | none | WMO-No. 8, Volume III, 2.9.1 |

Temperature gradients come in two signs: `LapseRate`, −dT/dz, as CF
defines `air_temperature_lapse_rate`, and `VerticalTemperatureGradient`,
dT/dz, as the layers of a standard atmosphere write it.

## What never mixes

- **Geopotential height and altitude.** The geopotential height is the
  geopotential divided by the standard acceleration of free fall,
  g_n = 9.80665 m s⁻² (3rd CGPM, 1901). It is numerically close to the
  altitude, never equal: 25 m apart at 8 km, 220 m at 32 km (WMO-No. 8,
  Volume I, table 12.10). Going from one to the other needs gravity,
  which depends on latitude and height (WMO-No. 8, Volume I, 12.5.5.2).
- **Pressure altitude and altitude.** A pressure altitude is "an
  atmospheric pressure expressed in terms of altitude which corresponds
  to that pressure in the Standard Atmosphere" (SERA, Art. 2, point 101):
  a geopotential height of the standard atmosphere, not of the actual
  one. It feeds the formulas of the standard atmosphere, never an
  altitude.
- **Ellipsoidal height and altitude.** Satellite positioning gives a
  height above an ellipsoid; the altitude is about that height minus the
  geoid height, which reaches tens of metres.
- **Lapse rate and vertical temperature gradient.** The same quantity
  with opposite signs: two sibling kinds.
- **QNH and pressure at mean sea level.** The QNH is computed from the
  QFE through the ICAO standard atmosphere, "this virtual atmosphere";
  the pressure reduced to sea level, through a fictitious column of air
  with the actual temperature (WMO-No. 8, Volume III, 2.9.1; Volume I,
  3.7).

## From one coordinate to another

| From → to | Formulation | Source |
|---|---|---|
| geopotential → geopotential height | `geopotential_height_definition`, Z = Φ / g_n | WMO-No. 8, equation 12.12; CF; ERA5 |
| geometric altitude ↔ geopotential height, radius 6356.766 km | `itu_r_p835_geopotential_height`, `itu_r_p835_geometric_altitude` | ITU-R P.835-7, equations 1a and 1b (the U.S. Standard Atmosphere, 1976) |
| geopotential height → geometric altitude, radius 6371.229 km | `era5_geometric_altitude` | ERA5 documentation (the spherical Earth of the IFS) |
| geometric height and latitude → geopotential height | `wmo_geopotential_height_wgs84`, composed of `wmo_geopotential_height_from_normal_gravity`, `wmo_normal_gravity_wgs84` and `wmo_effective_radius_mahoney` | WMO-No. 8, equations 12.15 and 12.16 |
| latitude → normal gravity | `wmo_normal_gravity_wgs84`, `wmo_normal_gravity_smithsonian` | WMO-No. 8, equations 12.16 and 12.14 |
| altitude and surface altitude → height | `height_above_surface` | CF |

The conversions differ by their Earth: 10 km of geopotential height are
15.7 m higher geometrically on the sphere of the IFS, a little more on
the smaller radius of the standard atmosphere. For a GPS radiosonde, WMO
takes the latitude into account: 30 km of geometric height give
29.7785 km of geopotential height at the Equator and 29.932 km at 80°N.
WMO's equation 12.13 has the same form as 12.15, with the normal gravity
of 12.14 and an effective radius tabulated in the Smithsonian tables:
`wmo_geopotential_height_from_normal_gravity` takes such a radius as an
input.

## Pressure and height in a hydrostatic atmosphere

| Quantity | Formulation | Source |
|---|---|---|
| pressure at the top of a layer, from its thickness and mean virtual temperature | `wmo_hypsometric_pressure` | WMO-No. 8, equation 12.17 |
| geopotential at the top of a layer, from the pressures and the virtual temperature | `ecmwf_ifs_hypsometric_geopotential` | IFS, Part III, equation 2.20 |
| pressure in a layer of constant temperature gradient | `ussa1976_pressure_layer_gradient` | U.S. Standard Atmosphere 1976, equation 33a |
| pressure in an isothermal layer | `ussa1976_pressure_layer_isothermal` | U.S. Standard Atmosphere 1976, equation 33b |
| pressure reduced to sea level | `wmo_sea_level_pressure`, `wmo_sea_level_pressure_log10` | WMO-No. 8, equations 3.2 and 3.1 |
| dry adiabatic gradient of temperature | `bechtold2015_dry_adiabatic_gradient` | Bechtold (2015), equation 38 |

All rest on the hydrostatic equation and the ideal gas law; each
citation records the assumptions its source states. The thickness of a
layer depends on its mean virtual temperature: WMO and the IFS give the
same 5173.9 m from 1000 to 500 hPa at 255 K, to the 3 × 10⁻⁵ by which
their gas constants of dry air differ. The layer formulas of the
standard atmosphere hold for any layer whose temperature varies
linearly with the geopotential height, or not at all: below 80 km, its
molecular-scale temperature is the temperature, and in moist air the
virtual temperature. The unknown of any of them (a thickness, a
pressure, a height) comes by inversion.

The reduction to sea level goes through a fictitious column of air
below the station, of assumed gradient 0.0065 K/gpm, "feasible for
stations below 750 m"; WMO gives it in two forms, which differ by
6.4 × 10⁻⁴ in the exponent, 0.04 hPa for a station at 500 m.

## The reference atmosphere and the pressure altitude

A standard atmosphere is a conventional model, "this virtual
atmosphere" WMO uses to compute the QNH, not a description of the actual
one. Its texts in force are ICAO Doc 7488 and ISO 2533, not freely
available; ITU-R P.835-7 gives its temperature and pressure up to
84.852 km', derived from the U.S. Standard Atmosphere, 1976, itself
identical to the ICAO standard atmosphere up to 32 km.

| Quantity | Formulation | Source |
|---|---|---|
| temperature against geopotential height | `itu_r_p835_temperature` | ITU-R P.835-7, equations 2a to 2g |
| pressure against geopotential height | `itu_r_p835_pressure` | ITU-R P.835-7, equations 3a to 3g |
| pressure altitude, in feet | `nws_pressure_altitude` | NWS calculation sheet |

Each layer of the pressure is the general form of the U.S. Standard
Atmosphere (equation 33a, or 33b when isothermal) with the values of the
layer, kept as coefficients so that the formula keeps the form P.835
prints. The layers meet with small jumps (226.3206 hPa at the top of the
first, 226.3226 hPa at the bottom of the second). A pressure altitude is
the inverse of this pressure; the jumps make the images of two layers
overlap by a few thousandths of a hectopascal, so the inverse is
numerical, within the 0 to 84.852 km' P.835 states:

```python
from nomogram.catalog import catalog
from nomogram.inversion import invert
from nomogram.model import Variable
from nomogram.units import Q_

altitude = invert(
    catalog().formulations["itu_r_p835_pressure"],
    "H",
    output=Variable("H_p", "PressureAltitude", "KiloM", "Pressure altitude"),
    input=Variable("P", "Pressure", "HectoPA", "Pressure"),
)
at_500_hPa = altitude.evaluate(P=Q_(500, "hPa")).to("m")  # 5574.44 m
```

The formula of the NWS, with rounded constants, gives 5572.10 m at
500 hPa: 2.3 m lower.

## Interpolation between two levels

Each interpolation scheme is a formulation, cited by every source that
uses it: schemes compare like any other formulations. The
post-processing of ARPEGE and the IFS (FULL-POS, which produces ERA5's
pressure levels) chooses the scheme by variable; MetPy and earthkit-meteo
leave the choice to the user, linear in the coordinate or in its
logarithm.

| Scheme | Formulation | Sources |
|---|---|---|
| wind linear in ln p | `log_pressure_interpolation_wind` | FULL-POS (3.2.1), MetPy, earthkit-meteo |
| temperature linear in ln p | `log_pressure_interpolation_temperature` | MetPy, earthkit-meteo |
| temperature linear in p | `pressure_interpolation_temperature` | FULL-POS, ECMWF option (3.2.2) |
| specific humidity linear in p | `pressure_interpolation_specific_humidity` | FULL-POS (3.2.5) |
| temperature linear in altitude | `height_interpolation_temperature` | MetPy, earthkit-meteo |
| geopotential height linear in ln p | `log_pressure_interpolation_geopotential_height` | MetPy, earthkit-meteo |

The physics tells them apart. In a layer whose temperature varies
linearly with height, as in the ITU-R reference atmosphere between 850
and 500 hPa, the temperature at 700 hPa is 268.571 K:

| Scheme | At 700 hPa | Error |
|---|---|---|
| temperature linear in altitude | 268.571 K | none |
| temperature linear in ln p | 268.886 K | +0.31 K |
| temperature linear in p | 267.208 K | −1.36 K |
| geopotential height linear in ln p | 2963.8 m | −48.4 m |

The height is linear in ln p only in an isothermal layer (the hypsometric
equation); FULL-POS interpolates instead a departure from a standard
atmosphere, whose own height is computed exactly.

## One word, several quantities

| Term | Community | Kind | Source |
|---|---|---|---|
| geopotential | CF, the IFS | `Geopotential`, in m² s⁻² | CF; IFS, Part III |
| geopotential | WMO upper-air observations | `GeopotentialHeight`, in standard geopotential metres | WMO-No. 8, Volume I, chapter 1 |
| altitude | aviation (SERA) | `Altitude`, from mean sea level | SERA, Art. 2, point 39 |
| altitude | CF | `Altitude`, from the geoid | CF |
| height | aviation (SERA) | `Height`, from a specified datum | SERA, Art. 2, point 84 |
| height | CF | `Height`, from the surface | CF |
| elevation | WMO surface observations | `SurfaceAltitude` | WMO-No. 8, Volume I, 1.3.3.2 |
| flight level | aviation (SERA) | `PressureAltitude` | SERA, Art. 2, point 78 |

Symbols differ too. WMO-No. 8 writes z for the geometric height and Z
for the geopotential height (12.5.5.2); ITU-R P.835 writes H for the
geopotential height and Z for the geometric height; the IFS writes φ for
the geopotential, and ERA5 z for it and h for the geopotential height. Each formulation keeps its source's symbols in the
notation of its citation.

## Units

There is no geopotential metre in nomogram: a geopotential height is in
metres, the kind carrying the meaning. WMO's standard geopotential
metre, "0.980665 of the dynamic metre", gives the same numbers as
Φ / g_n in metres. Pressure altitudes may be in feet.

## In ERA5 and the IFS

The IFS takes the Earth as a sphere of radius 6371.229 km. ERA5 refers
heights to the EGM96 geoid over land and to mean sea level over the
ocean, assumed to coincide with the geoid; its geopotential height is
the geopotential divided by 9.80665 m s⁻², "a fixed value in the IFS"
(ERA5 data documentation and its page on computing heights). ERA5
follows the documentation of IFS cycle CY41R2; the equations used here
have the same numbers in CY49R1 and CY50R1.

## Search

`search("geopotential height")`, a CF name (`geopotential_height`) or a
Wikidata item (`Q12432978`) finds the kind; a term (`search("flight
level")`) finds the trade term, whose meanings name the kinds;
`search(family="atmosphere")` lists the family; `used_by` on a reference
(`references.sera2012`) lists what it defines.
