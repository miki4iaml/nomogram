# The loop of COARE 3.6, solved as a system of equations

- Reference: the COARE 3.6 bulk flux algorithm, Python version
  (NOAA-PSL/COARE-algorithm, commit `bd1cac8` of 2026-03-17, MIT licence),
  its test data and its outputs, one row in 20 (109 rows). Thanks to the
  NOAA Physical Sciences Laboratory for publishing the algorithm with the
  data that test it.
- Computed with the development version of nomogram 0.8 on 2026-11-21;
  the tests compute every value of this page again for each later
  version, and fail if one changes.

COARE 3.6 computes the fluxes of momentum, heat and water vapour between
the sea and the air from the measurements of a ship. At its heart is a
loop: the scales of the surface layer give the Obukhov length, which
gives the roughness lengths, which give the scales again, ten times over.
nomogram writes this loop with formulations of its catalog, each cited
from the code or from the paper behind it, as one system of equations,
`coare36_surface_layer`, and solves it. Given the inputs the code
computes, the system gives back the outputs of the code to a few
millionths.

## The system

Thirteen equations, in the order of the code:

| Equation | Gives | From |
|---|---|---|
| `coare36_obukhov_length` | Obukhov length L | u\*, θ\*, q\*, T, g |
| `edson2013_roughness_length_momentum` | roughness length z₀ | **α**, u\*, ν, g |
| `roughness_reynolds_number` | roughness Reynolds number | z₀, u\*, ν |
| `coare36_roughness_length_humidity` | roughness length for humidity | the Reynolds number |
| `coare36_roughness_length_heat` | roughness length for temperature | the Reynolds number |
| `coare36_friction_velocity` | friction velocity **u\*** | **S**, z₀, L, z_u |
| `coare36_humidity_scale` | humidity scale **q\*** | q, q_s, its roughness length, L, z_q |
| `coare36_temperature_scale` | temperature scale **θ\*** | T, T_s, its roughness length, L, z_t, g |
| `coare36_virtual_temperature_flux` | virtual temperature flux | u\*, θ\*, q\*, q, T |
| `coare36_convective_gust` | gustiness velocity | the flux, T, z_i, g |
| `coare36_wind_speed_with_gust` | wind speed with gustiness **S** | U, the gustiness |
| `coare36_equivalent_neutral_wind_10m` | neutral wind at 10 m | u\*, U, S, z₀ |
| `coare36_charnock_coefficient` | Charnock coefficient **α** | the neutral wind |

The five variables in bold are read before they are computed in a pass:
they are the unknowns of the system. The other eight follow from them and
from the eleven inputs: the temperature and humidity of the air and of
the sea surface, the wind, the heights of measurement, the height of the
boundary layer, the viscosity of air and the gravity.

## Its solution

Solving the system means finding the five unknowns for which the
thirteen equations hold together. nomogram finds them by Newton's
method, in four steps at most on the test data, until every equation
holds to 10⁻¹² of the size of its terms; the ten passes of the code stop
at about 10⁻¹⁰ in median
([figure](images/coare-system.png)).

## Against the code

The relative deviations from the outputs of the code, over its 109 rows,
given the inputs the code computes itself (its humidity, with the
enhancement factor of Buck, its gravity and its viscosity of air):

| Variable | In the code | Largest deviation | Median deviation |
|---|---|---|---|
| friction velocity u\* | `usr` | 5.6 × 10⁻⁷ | 1.3 × 10⁻⁷ |
| humidity scale q\* | `qsr` | 1.8 × 10⁻⁶ | 4.2 × 10⁻⁷ |
| temperature scale θ\* | `tsr` | 5.3 × 10⁻⁵ | 3.4 × 10⁻⁶ |
| Obukhov length L | `L` | 7.4 × 10⁻⁶ | 1.3 × 10⁻⁶ |
| roughness length z₀ | `zo` | 1.5 × 10⁻⁶ | 2.3 × 10⁻⁷ |
| gustiness velocity | `gust` | 2.6 × 10⁻⁶ | 5.5 × 10⁻⁷ |

The temperature scale, from −0.10 K to −0.002 K, small against the
differences of temperature it comes from, follows the skin temperature
of the data, given to seven digits.

## What it leaves out

The system is the loop of the code over the formulations of the
catalog, as its note in the catalog states:

- the cool skin and the warm layer: the surface temperature and humidity
  are inputs, the skin temperature and the humidity at the surface of
  the outputs of the code;
- the Charnock coefficient from the waves: the test data have none;
- the first pass the code keeps where its first guess is very stable
  (ζ above 50), and the roughness length over ice;
- a stable case: the test data are all unstable, L from −326 m to
  −4.5 m.

The first guess is simpler than the code's, so that only the converged
values are compared. [The evaporation duct](evaporation-duct.md) calls
this system on the way to the height of the duct.

The script [docs/examples/coare_system.py](examples/coare_system.py)
computes every value of this page and draws the figure.
