# The evaporation duct: from shipboard measurements to the duct height

- Measurements and reference values: the test data of COARE 3.6 and its
  outputs, Python version (NOAA-PSL/COARE-algorithm, commit `bd1cac8` of
  2026-03-17, MIT licence). Thanks to the NOAA Physical Sciences
  Laboratory for publishing the algorithm with the data that test it.
- Computed with nomogram 0.7.0, in development, on 2026-11-08; the tests
  compute every value of this page again for each later version, and fail
  if one changes.

Over the sea, the humidity falls quickly with height in the first metres,
and with it the radio refractivity N. A horizontal wave whose refraction
exceeds the curvature of the Earth is trapped, or ducted (Fairall et al.
1978, p. 11): below the height where the modified refractivity
M = N + 157 h (h in km, ITU-R P.453, equation 17) is at its minimum, the
evaporation duct. Its height is computed from routine measurements at
sea, through the surface layer, by several methods that disagree.

This page chains the formulations of the catalog from the measurements of
a ship to the height of the duct, with two algorithms of the surface
layer, COARE 3.6 and the IFS, and four ways to the height. Every step
names its entry of the catalog; the few that are not in it are said.

## The measurements

The test data of COARE 3.6 (NOAA-PSL/COARE-algorithm, MIT licence), one
row in 20 (`docs/examples/data/coare36_test.csv`, see its notice): 109
measurements between 13° N and 16° N, the wind at 18 m, the temperature and
the relative humidity at 17 m, the pressure, and the sea temperature, a
little more than 1 °C above the air's (median 1.1 °C). All are unstable:
the Obukhov length COARE gives runs from -326 m to -4.5 m, for winds of
2.3 to 12.4 m/s.

The skin temperature and the humidity at the sea surface are the ones
COARE computes, with its warm layer and its cool skin, which the catalog
does not hold.

## The surface layer, by a fixed point

The scales u\*, θ\* and q\* and the Obukhov length L depend on each other:
both algorithms iterate. Each step is a formulation of the catalog,
called by its key:

| Step | COARE 3.6 | IFS (CY49R1, Part IV) |
|---|---|---|
| Charnock coefficient, roughness for momentum | `coare36_charnock_coefficient`, `edson2013_roughness_length_momentum` | `ecmwf_ifs_roughness_length_momentum_sea` |
| Roughness for heat and humidity | `coare36_roughness_length_heat`, `coare36_roughness_length_humidity` | `ecmwf_ifs_roughness_length_heat_sea`, `ecmwf_ifs_roughness_length_humidity_sea` |
| Stability | `coare36_obukhov_length`, from the scales | `ecmwf_ifs_bulk_richardson_number` (3.26), then `ecmwf_ifs_obukhov_length_from_bulk_richardson_number` (3.25) |
| Scales | `coare36_friction_velocity`, `coare36_temperature_scale`, `coare36_humidity_scale` | `ecmwf_ifs_transfer_coefficient_momentum`, `_heat`, `_humidity` (3.16 to 3.18), `ecmwf_ifs_friction_velocity` |
| Gustiness of free convection | `coare36_virtual_temperature_flux`, `coare36_convective_gust` | `ecmwf_ifs_virtual_temperature_flux` (3.10), `ecmwf_ifs_free_convection_velocity_scale` (3.20), `ecmwf_ifs_wind_speed_free_convection` (3.19) |
| Viscosity of air | `coare36_kinematic_viscosity_of_air` | in its roughness lengths |

Both add a gustiness to the wind in free convection, from the virtual
temperature flux at the surface: COARE 1.2 w\* with a boundary layer of
600 m, the IFS w\* with 1000 m; these fluxes are of the provisional kind
`KinematicHeatFlux`, pending a QUDT pull request. The gravity is the
normal gravity of WGS 84 at the latitude (`wmo_normal_gravity_wgs84`).

Two steps show how the catalog keeps a formula within its bounds:

- below a 10 m neutral wind of 2.94 m/s, the line of Edson et al. (2013)
  gives a negative Charnock coefficient, beyond the bounds of its kind,
  which nomogram gives as NaN unless asked; COARE takes it, its smooth
  flow term keeping the roughness length positive, and so does the script,
  with `outside="ignore"`, for one measurement;
- equation 3.25 of the IFS is an implicit equation in L, solved at each
  iteration; its root has the sign of Ri_b, and the script narrows the
  search to that side with `search=`, away from the pole at L = 0, where
  the residual is no longer computed meaningfully.

```python
m = measurements()
a = air(m)
by_coare, by_ifs = coare(m, a), ifs(m, a)
z_star = duct_heights(a, by_coare)
length[side] = value(
    "ecmwf_ifs_obukhov_length_from_bulk_richardson_number",
    "m",
    Ri_b=Q_(richardson[side], ONE),
    z_n=z_n[side],
    z_0M=z_0["z_0M"][side],
    z_0H=z_0["z_0H"][side],
    search=search,
)
```

The fixed point over the catalog gives back the outputs of COARE: the
median deviations are 0.02 % on u\*, 0.05 % on the roughness length,
0.6 % on L, 0.8 % on q\* and 0.9 % on θ\* (0.003 K at most). They come
from what the script takes otherwise: the humidity at 17 m, the gravity,
and the skin temperature fixed at its final value.

On the same measurements, the IFS departs from COARE: its roughness
length is twice COARE's (a Charnock coefficient of 0.018, where the line
of Edson et al. gives about 0.011 at 10 m/s), u\* +6 %, L +20 % (less
unstable), θ\* -6 % and q\* -3 %, in medians.

## From the profiles to the duct

The profiles of temperature and humidity of COARE carry the measurements
from 17 m to any height (`coare36_temperature_at_height`,
`coare36_specific_humidity_at_height`), the pressure follows the
hypsometric equation (`wmo_hypsometric_pressure`), the vapour pressure its
definition (`wmo_vapour_pressure_definition`), and P.453 gives N
(`itu_r_p453_refractivity_total_pressure`) and M
(`itu_r_p453_modified_refractivity`), from 0.1 m to 100 m:

```python
profiles = modified_refractivity(m, a, by_coare)
return value(
    "itu_r_p453_modified_refractivity",
    "ppm",
    N=Q_(n, "ppm"),
    h=Q_(HEIGHTS[None, :], "m"),
)
```

The height of the minimum of M runs from 7.7 m to 19.0 m.

## Four ways to the duct height

| Way | Source, in the catalog | What it assumes |
|---|---|---|
| Minimum of M | the profiles of COARE 3.6, P.453 | κ = 0.4 and the stability functions of COARE; 157 = 10⁶/a, an Earth of radius about 6370 km |
| z\* of Fairall et al. (1978), equation 25 | `fairall1978_evaporation_duct_height` | κ = 0.35, α_T = 1.35, φ_T of their appendix B; 0.125 = 0.157 - 0.032 m⁻¹, the critical gradient (the same 157) and the hydrostatic term near sea level |
| z\* of Frederickson et al. (1994), equation 3 | `frederickson1994_evaporation_duct_height` | k = 0.4, no α_T, φ_s; the same 0.125; q\* in g/kg |
| Paulus-Jeske (NOSC TD 1596) | the `paulus1989_*` steps | its bulk Richardson number (wind in knots), profile coefficient and potential refractivity; the measurements at its reference height, 6 m |

Fairall et al. and Frederickson et al. take the scales: those of COARE,
the scale of mixing ratio of Fairall et al. derived from that of specific
humidity (dr = dq/(1 - q)²); and those of the IFS for Fairall et al.
Paulus-Jeske takes the measurements, at 17 and 18 m here, as if at 6 m.
Against the minimum of M, in medians over the 109 measurements:

| Way | Deviation from the minimum of M |
|---|---|
| z\* of Fairall et al., scales of COARE | +11 % |
| z\* of Frederickson et al., scales of COARE | +9 % |
| z\* of Fairall et al., scales of the IFS | +13 % |
| Paulus-Jeske | +65 % (+46 % to +74 %) |

The scales of the two algorithms change the height of Fairall et al. by
about 1 %, less than the ways differ from one another.

![The modified refractivity M along the height for one measurement, its minimum and the duct heights of the four ways; the duct heights along the series of measurements](images/evaporation-duct.png)

The script that computes these values and draws the figure is
[`docs/examples/evaporation_duct.py`](examples/evaporation_duct.py); a
test checks that the code shown here is its own and that this page gives
the values it computes.

## What the chain shows

The catalog holds the alternatives side by side (two algorithms of the
surface layer, four ways to the height), each with its source, its
assumptions and its bounds; a formula appears once, in its own entry,
whatever the chain that calls it; a value beyond the bounds of its kind
is NaN unless asked, which keeps a chain from going on silently.

## References

The sources the formulations of the chain cite, and those of the
formulations and constants they use, followed through the links of the
catalog (`Catalog.uses`) and written by the script:

- Alduchov, O. A.; Eskridge, R. E. (1996). *Improved Magnus form approximation of saturation vapor pressure*. Journal of Applied Meteorology 35, 601-609. <https://doi.org/10.1175/1520-0450(1996)035<0601:IMFAOS>2.0.CO;2>
- Beljaars, A. (1992). *The parametrization of the planetary boundary layer*. ECMWF Meteorological Training Course Lecture Series (May 1992; reprinted 2002). <https://www.ecmwf.int/sites/default/files/elibrary/2002/16959-parametrization-planetary-boundary-layer.pdf>
- Beljaars, A. C. M. (1995). *The parametrization of surface fluxes in large-scale models under free convection*. Quarterly Journal of the Royal Meteorological Society, 121, 255-270. <https://doi.org/10.1002/qj.49712152203>
- Beljaars, A. C. M. and Holtslag, A. A. M. (1991). *Flux parameterization over land surfaces for atmospheric models*. Journal of Applied Meteorology, 30, 327-341. <https://doi.org/10.1175/1520-0450(1991)030<0327:FPOLSF>2.0.CO;2>
- Brutsaert, W. (1982). *Evaporation into the Atmosphere*. D. Reidel, Dordrecht.
- Buck, A. L. (1981). *New equations for computing vapor pressure and enhancement factor*. Journal of Applied Meteorology 20, 1527-1532. <https://doi.org/10.1175/1520-0450(1981)020<1527:NEFCVP>2.0.CO;2>
- Bureau International des Poids et Mesures (2019). *The International System of Units (SI), 9th edition*. BIPM, version 4.01 (June 2026). <https://doi.org/10.59161/AUEZ1291>
- Businger, J. A. (1985). *The marine boundary layer, from air-sea interface to inversion*. NCAR Technical Note NCAR/TN-252+STR, National Center for Atmospheric Research, Boulder. <https://opensky.ucar.edu/system/files/2024-08/technotes_362.pdf>
- ECMWF (2024). *IFS Documentation CY49R1 - Part IV: Physical Processes*. <https://doi.org/10.21957/c731ee1102>
- Edson, J. B., Jampana, V., Weller, R. A., Bigorre, S. P., Plueddemann, A. J., Fairall, C. W., Miller, S. D., Mahrt, L., Vickers, D. and Hersbach, H. (2013). *On the exchange of momentum over the open ocean*. Journal of Physical Oceanography, 43, 1589-1610. <https://doi.org/10.1175/JPO-D-12-0173.1>
- Fairall, C. W., Davidson, K. L., Schacher, G. E. and Houlihan, T. M. (1978). *Evaporation duct height measurements in the Mid-Atlantic: final report*. Naval Postgraduate School, Monterey, California, report NPS61-78-005, 15 August 1978. <https://hdl.handle.net/10945/29858>
- Frederickson, P. A., Davidson, K. L. and Jones, F. K. (1994). *The effect of infrared sea surface temperature measurements on evaporation duct height estimation*. Naval Postgraduate School, Monterey, California, report NPS-MR-94-003, November 1994. <https://hdl.handle.net/10945/28715>
- Holtslag, A. A. M. and De Bruin, H. A. R. (1988). *Applied modeling of the nighttime surface energy balance over land*. Journal of Applied Meteorology, 27, 689-704. <https://doi.org/10.1175/1520-0450(1988)027<0689:AMOTNS>2.0.CO;2>
- ITU-R (2019). *Recommendation ITU-R P.453-14: The radio refractive index: its formula and refractivity data*. <https://www.itu.int/rec/R-REC-P.453-14-201908-I>
- Kramm, G., Amaya, D. J., Foken, T. and Molders, N. (2013). *Hans A. Panofsky's integral similarity function, at fifty*. Atmospheric and Climate Sciences, 3, 581-594. <https://doi.org/10.4236/acs.2013.34061>
- Large, W. G. and Yeager, S. G. (2004). *Diurnal to decadal global forcing for ocean and sea-ice models: the data sets and flux climatologies*. NCAR Technical Note NCAR/TN-460+STR, National Center for Atmospheric Research, Boulder. <https://doi.org/10.5065/D6KK98Q6>
- NOAA Physical Sciences Laboratory (2026). *COARE 3.6 bulk flux algorithm, Python version (coare36vn_zrf_et.py)*. <https://github.com/NOAA-PSL/COARE-algorithm/blob/bd1cac80d2dae454e699f9ef46204dfd88086a71/Python/COARE3.6/coare36vn_zrf_et.py>
- Paulson, C. A. (1970). *The mathematical representation of wind speed and temperature profiles in the unstable atmospheric surface layer*. Journal of Applied Meteorology, 9, 857-861. <https://doi.org/10.1175/1520-0450(1970)009<0857:TMROWS>2.0.CO;2>
- Paulus, R. A. (1989). *Specification for evaporation duct height calculations*. Naval Ocean Systems Center, San Diego, Technical Document 1596, July 1989 (AD-A213 841). <https://archive.org/details/DTIC_ADA213841>
- World Meteorological Organization (2024). *Guide to Instruments and Methods of Observation (WMO-No. 8), Volume I*. <https://doi.org/10.59327/WMO/CIMO/1>
