# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Family `atmosphere`: the vertical coordinates, each a quantity kind
  defined after a text in force (CF standard names, WMO-No. 8 2024, the
  IFS documentation, and for aviation the SERA regulation, which takes
  over the ICAO definitions). Geopotential, geopotential height and the
  thickness of a layer, pressure altitude, ellipsoidal and geoid heights,
  the lapse rate (-dT/dz) and the vertical temperature gradient (dT/dz)
  as siblings, surface and mean-sea-level pressures, QNH and QFE. Kinds
  that differ by metres never feed each other (a geopotential height
  never feeds an altitude). Trade terms give what each community means
  by geopotential, altitude, height, elevation, pressure altitude and
  flight level. The surface altitude and the height above the surface
  move to this family, which `radio` now requires. Guide
  `docs/vertical.md`.
- The standard acceleration of free fall, g_n = 9.80665 m s-2 (3rd CGPM,
  1901), a conventional constant.
- From one vertical coordinate to another: the geopotential height from
  the geopotential (WMO-No. 8, 12.12); between geometric altitude and
  geopotential height with the radius of the U.S. Standard Atmosphere
  (ITU-R P.835-7, 1a and 1b) and with the spherical Earth of the IFS
  (ERA5); for a GPS radiosonde, from the geometric height and the
  latitude on WGS 84 (WMO-No. 8, 12.15 and 12.16), composed of a normal
  gravity, an effective radius and the generic form of 12.13 and 12.15;
  the normal gravity of the Smithsonian tables (12.14). Kind
  `GeodeticLatitude` (CF `latitude`, broader).
- The hydrostatic atmosphere: the hypsometric equation with the mean
  virtual temperature of the layer, in the pressure form of WMO-No. 8
  (12.17) and the geopotential form of the IFS (Part III, 2.20); the
  pressure in a layer of constant temperature gradient and in an
  isothermal layer (U.S. Standard Atmosphere 1976, 33a and 33b, with its
  constants R* and M0); the reduction of a station pressure to sea level
  in the two forms of WMO-No. 8 (3.2 and 3.1), with the gas constant of
  dry air it gives; the dry adiabatic gradient (Bechtold 2015, 38, with
  its g = 9.81 m s-2). The assumptions each source states are recorded.
- The reference atmosphere of ITU-R P.835-7, temperature (2a-2g) and
  pressure (3a-3g) against the geopotential height up to 84.852 km'; each
  pressure layer written as the general form of the U.S. Standard
  Atmosphere with its values as coefficients. The pressure altitude by
  inversion of that pressure (numerical: the source's layers meet with
  small jumps), and the NWS formula in feet.
- Functions `sin` and `cos` in expressions. An angle in their argument
  is in radians: a variable in degrees there is refused, pint counting
  the degree as a pure number.
- From QUDT 3.5.2: the kinds `Length`, `AccelerationOfGravity`,
  `TemperatureGradient`, `Velocity` and `Speed` (with the CF names of the
  wind), and the units m s-2, m2 s-2 (added to `SpecificEnergy`, CF's
  unit of the geopotential), K m-1 and ft.

### Changed

- An inversion no longer waits for SymPy to check the closed forms it
  finds, which nomogram checks numerically anyway: the dew point of
  MetPy's saturation vapour pressure is found in 4 s rather than 24 s.

### Fixed

- On PyPI, the links and images of the README lead to the files of the
  release; relative, they led nowhere. The release workflow makes them
  absolute, at the release's tag, before building, and checks the built
  description (`scripts/absolute_links.py`); the README of the repository
  keeps its relative links, its figure included.

## [0.4.0] - 2026-10-28

### Added

- Pre-commit hook `check-image-metadata`: an image carries no metadata
  (text, EXIF and its geolocation, XMP, IPTC, comments, timestamps,
  colour profiles), PNG, JPEG, GIF, WebP and SVG read, other formats
  refused as not checked. The anonymity hook searches the metadata of
  PDF files, decompressed when compressed, which keep their authors.
- README section "Data sources": the QUDT, CF and UCUM material bundled
  in the package, with its versions and licenses. `CITATION.cff` and
  `.zenodo.json` reference QUDT and the CF standard name table.
- The data notice credits the UCUM codes of the units (Regenstrief
  Institute, UCUM License 1.1), which QUDT identifies as third-party
  material.
- Search by unit: `Catalog.search(unit=...)` finds what works in a unit,
  named by its QUDT name, symbol, UCUM code, label or pint expression
  (`unit="hPa"` is `unit="HectoPA"`). Formulations link to the units of
  their variables, constants and declared coefficients, constants and
  scales to theirs, so `uses` and `used_by` reach units.
- The URL of a reference or a cross-check can be searched, whole or with
  wildcards (`*archive.org*`).
- Formulations link to their Wikidata items, with their SKOS relation and
  the date they were checked: the Goff-Gratch equations over water and
  ice (Q3433288, broader), the five Buck correlations (Q4787919, the
  group, broader) and Tetens (1930) (Q28231917, close). A search by item
  finds them (`search("Q4787919")`).
- Design goals, stated in AGENTS.md: alternatives side by side; validity,
  scale and sources stated, never invented; open, machine-readable data;
  one source for every output; links to shared vocabularies. `python -m
  nomogram.catalog stats` (and `nomogram.catalog.stats`) prints the
  indicators of how far the catalog covers them, such as formulations
  with a validity domain or quantity kinds with a CF standard name.
- The constant `pi` may be written in expressions (Planck's law, the
  Stefan-Boltzmann constant, the Coriolis parameter need it). It is
  rendered `\pi`, and `pi` is a reserved name that no identifier may take.
- Piecewise definitions in expressions, `piecewise((expression,
  condition), ...)`: each condition is an interval of one input (a
  comparison, or two chained in one direction), the same input for every
  branch, and the formulation gives NaN where none holds. Loading checks
  the intervals (one input, no overlap, none empty) and the units: bounds
  take the unit of their input, and a quantity equation is checked by
  pint branch by branch. The formula is rendered on one line in a left
  brace, one string for LaTeX, Markdown and mathtext. A power or a
  quotient applies to the whole definition, whose conditions stay as
  written (1 / e_s, for a saturation pressure by branches). It is
  inverted branch by branch when each branch is strictly monotonic on its
  interval, the inverse taking the images of the intervals as conditions,
  numerically otherwise (a constant branch, for one). An equivalence between piecewise definitions is proved
  branch by branch when their conditions agree, and checked on samples
  otherwise; in a composition, conditions bound inputs of the composed
  formulation.
- Formulations by branches: a catalog entry with `branches = [{
  formulation, where }, ...]` takes the pieces of its piecewise definition
  from formulations of the catalog, which keep their own sources and
  domains. Its expression, inputs, coefficients and constants come from
  the branches; the domains of each branch apply where its condition
  holds, unless a source of the formulation states its own. `uses` and
  `used_by` link the formulation and its branches, and the legend of a
  single formula lists them (`nomogram.model.Branch`, `Formulation.branches`,
  derivation method `"branches"`).
- Quantity kind `SaturationVapourPressure` (Wikidata Q2387102, close):
  over water or over ice, as a formulation states, or over each on one
  side of a temperature. Formulation `psychrolib_saturation_pressure`, the
  saturation pressure of PsychroLib: Hyland and Wexler over ice up to the
  triple point, over water above, by branches. Unlike ASHRAE, which
  switches at the freezing point and leaves a step of 0.06 Pa, the two
  branches meet. A cross-check reproduces PsychroLib on six temperatures
  around the switch.
- Units of physical constants, from QUDT 3.5.2: J/K, J·s, m/s, mol⁻¹,
  J/(mol·K), W/(m²·K⁴), kg/mol and J/kg. QUDT writes `/mol`; nomogram
  writes mol⁻¹, as the SI Brochure does.
- A logo, drawn by code (`scripts/make_logo.py`): NOMO, whose N is a
  working nomogram, then a sphere of linked nodes, M and a globe. Light
  and dark variants, a banner with the word "nomogram", an icon and a
  favicon ([docs/logo.md](docs/logo.md)).
- The figures that `plot_values` and `plot_deviations` create are
  signed with the logo, at the right edge, on the line of the x-axis
  label (`signature=False` leaves it out). A figure given through `ax` is
  never signed. `nomogram.plot.sign` signs any figure; the signature is a
  vector artist, which `remove()` takes off.
- Quantity kind `SpecificEnergy` (QUDT, Wikidata Q3023293), in J/kg.
- A formulation may call others in its expression, each at its own
  arguments, as sources write them: `expression = "100 * e_w(p=p, t=t_d) /
  e_w(p=p, t=t)"` with `calls = { e_w = "..." }`. Arguments are named and
  checked (kind, unit, scale); the domains of each formulation called
  apply to each call; coefficients, and constants in conflict, are
  renamed for the computation, so that two formulations never meet, and
  found by the name they are written with. The relative humidity from
  the dew point of WMO-No. 8 (4.B.11) is the first such entry.
- Units of coefficients are inferred through every level of a
  composition of compositions.
- The specific latent heats of vaporization and sublimation of the
  ECMWF IFS, linear in temperature (CY49R1, equations 12.1 and 12.2),
  with the triple point temperature T_0 of the IFS and the quantity kind
  `SpecificLatentHeat` (that of QUDT, ahead of its release), specialized
  for vaporization and sublimation.
- The other formulas of WMO-No. 8, Annex 4.A that need no solver: the
  mixing ratio, specific humidity and vapour concentration from masses
  and a volume (4.A.1 to 4.A.3), the mole fraction of water vapour from
  amounts of substance and from the mixing ratio (4.A.4, 4.A.5), the
  vapour pressure from the mole fraction (4.A.6, proven equivalent to its
  form in the mixing ratio), the saturation vapour pressures of moist air
  from the saturation mixing ratios (4.A.9, 4.A.10), and the relative
  humidity from the mixing ratios (4.A.16), which is not 100 r / r_w. The
  WMO's bound of 0.5 % on e'_w = e_w (4.A.11) is an assumption stated by
  another source where e = RH e_s. The QUDT quantity kinds Mass, Volume,
  AmountOfSubstance and MoleFraction, and the local ones
  MoleFractionOfWaterVapour, SaturationMixingRatioOverWater and
  SaturationMixingRatioOverIce.
- Three definitions of WMO-No. 8, Annex 4.A: the vapour pressure of
  moist air e' = r p / (0.62198 + r) (4.A.6), and the relative humidities
  with respect to water and to ice (4.A.15, 4.A.17), with their conditions;
  the quantity kind `RelativeHumidityWithRespectToIce`. A definition may
  be a numerical value equation when its source prints it so.
- Proportionalities: a relation may state that a formulation equals
  another times a constant factor. nomogram proves it, or holds it to the
  printed precision of the coefficients, and says what the factor is the
  ratio of, whether the two are equal to the printed precision, and
  whether a shift or a factor of a temperature or a salinity would explain
  it (a factor is left aside for an input the object is proportional to,
  where it cannot tell). An equivalence or a proportionality without a
  citation is computed by nomogram. A `given` expression may convert a
  unit. Murray (1967) is Tetens (1930) in kelvins, to the printed
  precision.
- Assumptions: a citation lists those its source states; a formulation
  notes the others with their status (stated by another source, deduced,
  suspected). The legend shows them and `search(assumption=...)` finds
  them. First ones: the constant specific heats of the IFS and Ambaum
  latent heats, the ideal gas and the enhancement factor left out where
  e = RH e_s, the 0 degC at 273.16 K of Goff and Gratch and Murray.
- `docs/rosetta.md` maps the terms of nomogram to MathModDB and Wikidata
  (defining formulas, symbols tied to quantities, sources, approximations),
  with only the correspondences checked in MathModDB 2.0.0 and Wikidata.
- Definitions and identities: a formulation may be true by definition
  or an exact consequence of definitions (`nature`), with the conditions
  under which it holds (`conditions`). The latent heat of fusion as that
  of sublimation minus that of vaporization is the first, cited to
  Bechtold (2015, equation 40) and Ambaum (2020).
- Formulations derived by nomogram: a composition, branches or calls
  without a citation of their own are derived (`Formulation.derived`),
  said so in the legend, counted by the indicators, and found by
  `search(provenance="derived")`. The latent heat of fusion of the ECMWF
  IFS, which the IFS does not print, is derived from its latent heats.
- The specific latent heats of vaporization and of melting of Ambaum
  (2020), linear in temperature, with the units and the 0-100 degC
  range the article states, and the quantity kind
  `SpecificLatentHeatOfFusion`.
- Formulations of WMO-No. 8 (2024), Annex 4.B:
  - the enhancement factor f(p) (4.B.5);
  - the saturation vapour pressures over water and over ice in moist air,
    as compositions of f(p) with 4.B.1 and 4.B.3 (4.B.2, 4.B.4);
  - the relative humidity with respect to water (4.B.10);
  - the dew point (4.B.6), with the enhancement factor as an input or
    taken from 4.B.5.
- The submodules are attributes of the package, imported the first time
  they are used (PEP 562): `import nomogram as nomo`, then `nomo.catalog`,
  `nomo.comparison`, `nomo.plot`... `import nomogram` stays light, and type
  checkers see each submodule.
- A dew point may be given in K as well as in degC. QUDT has one kind for
  it, CF writes it in K and empirical formulas in degC, so
  `DewPointTemperature` takes units with and without an offset, an
  exception to the scale rule declared in the extraction script.
- Physical constants state their nature: `exact` (a defining constant of the
  SI, or one derived from them alone), `conventional` (attributed by
  agreement, VIM 2.12) or `measured` (VIM 2.10), with an optional standard
  uncertainty and the conditions the value holds in. A value may be written
  as decimal text (`"287.0500"`) to keep the digits the source prints.
  `nature` is optional in a catalog file, so files written for 0.3 still
  load; every bundled constant states it. A search finds constants by
  nature and conditions.
- A constant may carry the formula its source defines it by, from other
  constants (`definition`, `constants`). The value used stays the one
  printed; loading checks it in exact arithmetic, against the formula
  computed from the printed and from the unrounded values of its
  components: within the uncertainty given, as a truncation for an exact
  constant, else to half a unit of its last digit, or within a
  `tolerance` explained in a `note` when the source departs from its own
  formula. `uses` and `used_by` link a constant to its components.
- Physical constants of the SI and of the ECMWF IFS, each linked to
  Wikidata where an item exists:
  - in `core`, the defining constants c, h, k and N_A (SI Brochure, 9th
    edition, table 1), and the molar gas constant R = N_A k and the
    Stefan-Boltzmann constant derived from them (CODATA 2022);
  - in `moist-air`, the constants of the IFS (CY49R1, Part IV, chapter
    12): c, h, k and N (the CODATA 1986 values), sigma, R = N k, the molar
    masses and gas constants of dry air and water vapour, the specific
    heats of dry air, water vapour, liquid water and ice, and the latent
    heats of vaporisation and sublimation at the triple point, each
    derived constant with its definition.
- Atmospheric thermodynamics of Bechtold (2015), the ECMWF training
  notes: the virtual temperature, defined from the density of moist air
  (23) and computed from the specific humidity or the mixing ratio (25,
  the two forms proven equivalent) or with the coefficient 0.608, equal to
  (1 - epsilon) / epsilon to the printed precision; the potential
  temperature of dry air (28) and of moist air (35), the virtual potential
  temperature (36, printed with p and p0 swapped) and the reversible
  equivalent potential temperature (46), with their stated and deduced
  assumptions; the specific humidity and the mixing ratio from the vapour
  pressure (Table 1) and the mixing ratio from the specific humidity (22);
  the saturation vapour pressure over water from Clausius-Clapeyron with a
  constant latent heat (53), and the Magnus form in kelvins (54), Buck
  (1981) with C = 6.112 hPa, proven proportional to it. The local quantity
  kinds VirtualTemperature, PotentialTemperature,
  VirtualPotentialTemperature, EquivalentPotentialTemperature,
  DensityOfMoistAir and MassRatioOfTotalWaterToDryGas, linked to Wikidata
  where an item exists, and the QUDT kinds Density and MassRatio. The
  conversion q = r / (1 + r) is marked as an identity.
- A quantity kind declared by the catalog may carry CF standard names,
  from the frozen CF subset, like a conventional scale; a search by the
  name finds it and its formulations. The virtual, potential and
  equivalent potential temperatures and the density of moist air carry
  theirs (`virtual_temperature`, `air_potential_temperature`,
  `air_equivalent_potential_temperature`, `air_density`), as do the mole
  fraction of water vapour, sea water salinity and the surface altitude
  (`mole_fraction_of_water_vapor_in_air`, `sea_water_salinity`,
  `surface_altitude`). `Altitude` also carries the close name
  `height_above_mean_sea_level`, mean sea level being what the geoid
  approximates.
- The end of WMO-No. 8, Annex 4.B: the frost point (4.B.7), with the
  enhancement factor as an input or from 4.B.5, and the Assmann
  psychrometer with a wet or an ice bulb (4.B.8, 4.B.9), with its
  condition. The relative humidity with respect to ice from the frost
  point, which the guide gives over water only (4.B.11), is derived by
  nomogram from 4.B.4. The QUDT kinds Temperature and WetBulbTemperature
  (CF `wet_bulb_temperature`), and the local kinds FrostPointTemperature
  and IceBulbTemperature, siblings of the dew point and of the wet bulb
  rather than specializations: a frost point never feeds a dew point
  input. A frost point, a wet- or an ice-bulb temperature may be the point
  at which a called formulation is evaluated, as a dew point may. A
  formulation calling others may state its conditions.
- The trade term "relative humidity" and its three meanings: the ratio of
  mole fractions (CCT, WMO-No. 8 4.A.15), the ratio of the partial
  pressure to the saturation vapour pressure of pure water (IUPAC,
  textbooks), both of kind `RelativeHumidity`, and the ratio of the mixing
  ratio to its saturation value, of the QUDT kind
  `RelativeMassRatioOfVapour` (ISO 80000), which TEOS-10 calls the WMO
  definition (3.40.2) and which WMO-No. 8 (2024) does not use. That ratio
  is a formulation of its own, distinct from the WMO relative humidity in
  mixing ratios (4.A.16).
- The general psychrometric formulae of WMO-No. 8 (4.1, 4.2), for a
  given psychrometer coefficient and the saturation vapour pressure at the
  bulb temperature; and the air temperature from the thermodynamic
  wet-bulb and ice-bulb temperatures, for ideal gases with constant
  specific heats (4.A.19, 4.A.21, whose printed c_p is read as c_pa). The
  QUDT kinds InverseTemperature and SpecificHeatCapacityAtConstantPressure,
  the unit K⁻¹, and the local kind PsychrometerCoefficient.
- The saturation vapour pressure of Ambaum (2020), the Clausius-Clapeyron
  equation integrated with a latent heat linear in temperature: over water
  (equation 13, with the latent heat of equation 15), over ice (equation
  17), and its constant latent heat approximation (equation 16). Ambaum
  prints no latent heat of sublimation at the triple point: it is his
  L_0 + L_m0, borne out by the IAPWS sublimation curve to 0.1 % from -40
  to 0 degC. The reference moves to `core`, shared by two families.
- Two implementations as formulations, each cross-checked against it:
  - MetPy 1.7.1: its saturation vapour pressure over water, the form of
    Ambaum (2020) equation 13 with MetPy's constants rather than those
    Ambaum recommends, and its psychrometric vapour pressure, with the
    constants of MetPy; cross-checked with its doctests;
  - ASHRAE (2017), through PsychroLib: the mixing ratio from a wet bulb
    above freezing (equation 33) and below, covered with ice (equation
    35); cross-checked with PsychroLib. Equation 33 is WMO-No. 8 4.A.19
    solved for the mixing ratio.

  The units kJ/kg and kJ/(kg·K), which specific energies now take too.
- The saturation vapour pressures of the ECMWF IFS over water and over
  ice (CY49R1, Part IV, equations 12.9 and 12.10), cross-checked with
  earthkit-meteo 1.2.1, and the Magnus form of Bechtold (2015) over ice
  (equation 54). Computed by nomogram and proven: the IFS formula over
  water is Buck (1981) in kelvins, 0 degC written 273.16 K, and the Magnus
  forms of Bechtold round its e_0 (6.112 hPa rather than 611.21 Pa).
- `plot_deviations` and `plot_values` take properties of the axes as
  keyword arguments (`ylim=(-1, 1)`, `title`...), set once the curves are
  drawn; limits given to `plot_deviations` make the curves beyond them off
  scale, each legend entry saying how far it goes. The example of the
  README zooms in on 0 to 60 degC and 1 %.
- The display options `axis_detail` and `legend_detail` set,
  independently, how much the axes and the legend of a plot say:
  `"short"` gives the symbol and unit on an axis, and the first citation
  of each formulation in the legend (`Bechtold (2015), eq. 54`), in two
  columns beyond ten curves; `"standard"` (default) the names and
  labels; `"full"` adds a second line: the scale of an axis, the full
  label of the reference, the first citation of each formulation.
- Option sets for figures: the display option `off_scale_notes` says
  whether the legend entry of a curve off scale tells how far it goes,
  and the preset `DisplayOptions.DOCUMENTATION` (full axes, short legend
  entries, no off-scale notes) gives the figures of nomogram's
  documentation, the README's included. `plot_deviations` and
  `plot_values` take a set for one call (`options=`), as `render` does.
  An x range given to `plot_deviations` (`xlim`) narrows what its y axis
  holds to the points shown.

### Changed

- CF standard names are links like Wikidata items: each carries its SKOS
  relation and the date it was checked, as an `ExternalMatch` in the
  `matches` of a kind or a scale, whose target is the name in the NERC
  Vocabulary Server (`nomogram.semantics.CF_NAMESPACE`).
  `cf_standard_names` still gives the names alone, and `QuantityKind` and
  `ConventionalScale` are built with their links. The catalog writes them
  as tables (`{ name, relation, verified }`); a bare name, as format 2
  writes it, is an exact match. `air_temperature` and `air_pressure` are
  narrow matches of the temperatures and of the pressure (air only),
  `height_above_mean_sea_level` a close match of the altitude, the CF
  salinity names close matches of the salinity scales.
- `plot_deviations` draws off scale a curve whose largest deviation
  exceeds those of all the others by more than three times, so that it
  no longer flattens them: the curve leaves the axis, and its legend
  entry says how far it goes. `off_scale=False` holds every curve. Its
  y axis names the reference by its source (`IAPWS (1992)`) rather than
  by its full label.
- `plot_values` plots on a logarithmic scale values that are all
  positive and span more than two decades; `yscale` chooses.

- A relation between formulations working in different units is verified
  on the expressions brought into the units of the subject by an exact
  factor (a result in Pa against one in hPa, an input in hPa fed by one in
  Pa), instead of being refused when the catalog is loaded. A conversion
  with an offset (degC fed by K) is still stated in `given`: its origin,
  273.15 or 273.16 K, is the source's choice. A proportionality names a
  coefficient of the object in the output unit of the subject.

- A reciprocal unit is written with a negative exponent, as the SI
  Brochure writes it (K⁻¹, K⁻², hPa⁻¹), instead of 1/K.
- A conventional scale applies to the specializations of the kinds it
  lists, never to a difference (`ConventionalScale.applies_to`); the
  temperature scales list `Temperature`, so they apply to every
  temperature point, the frost point included.
- The README opens with the logo and says what nomogram is: formulas as
  data, not as code, each one meaningful, checked and ready to use. Its
  examples use `import nomogram as nomo`.
- `SaturationVapourPressureOverWater` and `SaturationVapourPressureOverIce`
  specialize `SaturationVapourPressure`, itself a vapour pressure: they
  still feed any vapour pressure input, and a search of the new kind with
  its specializations finds every saturation pressure of pure water, over
  water or over ice (those in moist air and over sea water are found
  through `VapourPressure`).
- Practical Salinity is a number, as CF (canonical unit 1) and TEOS-10
  write it: the scale `pss78` and the salinity inputs of COARE 3.6, Weiss
  and Price (1980) and Dickson et al. (2007) are unitless instead of per
  mille (S_P = 35). With the default evaluation nothing changes: the
  Reference Salinity given, in g/kg, per mille or as a fraction, is
  converted. Knudsen and Cox salinities, mass ratios, stay in per mille.
  A value taken as given (`scale="ignore"`) is written as its scale writes
  it, or `ScaleConversionError` is raised: S_P without a unit (in per
  mille or g/kg it would be read a thousand times smaller), a Knudsen or
  Cox salinity with its unit (a bare number would be read as a fraction).
  A comparison taken as given that mixes both kinds of scale therefore
  fails instead of misreading one.
- The data notice credits QUDT in the form its licensing guide suggests.

### Fixed

- Documentation and search:
  - `search(provenance=...)` takes a third value, `uncited`, for the
    formulations nomogram writes without a source (a usual approximation
    or a definition), which neither `cited` nor `derived` reached;
  - the note of a constant is searched;
  - the examples of `Catalog.search` give what they show again, and a
    test runs them;
  - the documentation follows the code on conditions (not on
    compositions nor branches), on relations (`proportional`, a citation
    only required for approximations), on searching by a CF name
    (`input=` for the formulations taking the kind), on the inverses
    tested, and in `docs/rosetta.md` on the saturation vapour pressure
    and the temperature points taking units with and without an offset.
- Catalog, checked against its sources:
  - the relative humidity with respect to ice specialized the relative
    humidity, which QUDT defines with respect to water: it fed the inputs
    paired with the saturation over water (+21 % on e at -20 degC). It is
    now their sibling under the QUDT kind `RelativePartialPressure`
    (p/p_sat over either phase), added to the bundled subset;
  - the readings of a psychrometer, which WMO-No. 8 says are not the
    thermodynamic wet-bulb and ice-bulb temperatures, have kinds of their
    own, `PsychrometerWetBulbTemperature` and
    `PsychrometerIceBulbTemperature` (4.B.8, 4.B.9, 4.1, 4.2 and MetPy);
    `WetBulbTemperature` and `IceBulbTemperature` are the thermodynamic
    ones (4.A.19, 4.A.21, ASHRAE);
  - the effect of the enhancement factor is quoted around 1000 hPa, where
    4.B.5 holds, not at 300 hPa;
  - the unit K of B in the IFS saturation formulas is printed by the IFS
    (a4, section 7.2.1): stated, not added; the unit of Bechtold's 0.608,
    printed bare, is inferred, not stated;
  - the temperatures of Ambaum (2020) are on ITS-90 from the article
    itself (p. 4255), not from its date;
  - page ranges and wordings of notes (WMO-No. 8, Bechtold, the
    triple-point pressure of IAPWS R14-08, saturation over water with
    dissolved air);
  - a formulation built from others holds under the assumptions of its
    parts and branches, which its legend lists and `search(assumption=)`
    finds; the source an assumption refers to is linked and found by
    `search(source=)`;
  - `docs/rosetta.md` lists the meanings of "relative humidity" and of
    "wet-bulb temperature".
- Robustness of the loader and of the expression parser:
  - a short expression such as `9 ** 9 ** 9` made the parser compute a
    number of hundreds of millions of digits: a power of two numbers
    beyond 1000 digits is refused; deep nesting and an infinite literal
    (`1e309`) are refused with an `ExpressionError`;
  - `FUNCTIONS` and `CONSTANTS` of `nomogram.expression` are read-only;
  - a branch condition containing `), (` added a piece no branch gives:
    one condition is expected;
  - a local kind may specialize a kind of the catalog written after it,
    in another family; a cycle of specializations is refused;
  - a CF standard name of a local kind must have a canonical unit of the
    kind's dimension;
  - a constant written as decimal text beyond the float range is
    refused; an expression that calls others may start with a space;
  - the indicator "formulations with a validity domain" counts domains
    reached through parts and branches at any depth (26 of 120, not 22);
  - a unit outside the catalog is written as a product with negative
    exponents (g·K·hPa⁻¹·m⁻³, never a chain of solidi), an exponent that
    is not whole after a caret (‰^1.5).
- Figures:
  - a short legend entry or the deviation axis named a later source when
    the first is personal: the formulation keeps its label; a body keeps
    its whole name (IOC, SCOR and IAPSO, not IOC);
  - the figures `plot_values` and `plot_deviations` create take the
    tight layout, so labels of two lines stay on them;
  - a legend takes two columns only when all its short entries are short
    (none kept on a collision, none off scale);
  - on axes given through `ax`, the off-scale limits and the automatic
    logarithmic scale are left to the caller, who may have drawn there;
  - a curve equal to the reference to rounding no longer sends another
    off scale;
  - a dew point plotted in kelvins is T_d, not t_d;
  - a figure saved with `bbox_inches="tight"` keeps the whole signature;
  - a deviation plot without a curve draws no empty legend.
- Scales and units:
  - an input in per mille on PSS-78, which became a scale of numbers in
    this version, loaded and was read 1000 times too large: a scale of
    numbers now takes inputs without unit (a personal catalog written
    for 0.3 with `unit = "PERMILLE"` on `pss78` writes `UNITLESS`);
  - the relative deviation of values in °C (the WMO dew and frost
    points) depended on the Celsius origin: it is computed in kelvins;
  - a temperature difference no longer feeds a temperature point, though
    QUDT makes it a temperature, and no longer inherits a conventional
    scale;
  - a formulation called with its result on another scale than the
    reference (IPTS-68) makes the caller state that scale, so that the
    result is converted back, instead of returning it unconverted;
  - a bound of a piecewise definition in another unit than its input (Pa
    for hPa, K for °C) is refused, since conditions compare numbers;
    arithmetic on Celsius temperatures in a quantity equation is refused
    with a catalog error;
  - a scale declared on the output of an entry defined by branches must
    be the one its branches give, instead of being dropped;
  - scales follow specializations when a derived scale is checked
    against its reference, and a kind has one reference scale,
    specializations included;
  - `plot_values` never puts temperatures in °C on a logarithmic scale.
- Verification of proportionalities (the method moves to version 3,
  and every recorded verdict is recomputed; the verdicts of the bundled
  catalog keep their status):
  - the rounding of a coefficient is half a unit of its last significant
    digit in any notation: a coefficient below 10⁻⁴ hid 0.5, so that
    formulations far from proportional were held;
  - a ratio is held only when moving one coefficient within its rounding
    takes its variation away, not as soon as that coefficient could move
    the ratio as much; the same holds for equality to the printed
    precision;
  - points where a side is negative are compared by their ratio, instead
    of being dropped, or of failing when all were; a ratio that changes
    sign is refuted, the share of the samples compared is given, and a
    proportionality between outputs in °C is refused;
  - a factor is the ratio of two coefficients only within their printed
    rounding, never of two equal ones; a sampled factor is the median
    of a ratio that varies, not a constant deviation;
  - a shift or a factor of an input is put down to a conventional scale
    only within what the catalog's scales give over the bounds (a shift
    of 0.7 °C was);
  - the signature of a formulation includes the units of its
    coefficients and constants, and the fingerprint of a verdict the
    keys of the formulations, the names of their coefficients and the
    scales applying to the inputs, so that no recorded verdict outlives
    what it was computed for;
  - proofs read the decimal numbers of expressions and of `given` as
    exact rationals (`parse_expression(..., exact=True)`, new): with
    SymPy 1.13, the lowest version supported, 273.15 written in a
    formula and in `given = { t = "T - 273.15" }` did not cancel, and an
    equivalence stayed unproven.
- Ten references had no DOI although they have one: Alduchov and
  Eskridge (1996), Bolton (1980), Buck (1981), Lewis and Perkin (1981),
  Marti and Mauersberger (1993), Murphy and Koop (2005), Murray (1967),
  Wagner and Pruß (1993), Wagner et al. (2011), and the IFS
  documentation CY49R1, Part IV (`10.21957/c731ee1102`, ECMWF). Each was
  checked against Crossref or DataCite and resolved at doi.org.
- The closed-form inverse of a quantity equation in kelvins, asked in
  degC (`dew_point`), subtracted a unitless 273.15 from a result in
  kelvins, which gave wrong values. A quantity equation now keeps the
  unit of the solved variable, which pint converts.
- Murray (1967), over water and over ice, is Tetens (1930) rewritten in
  kelvins, with 0 degC written 273.16 K: its T_0 was described as the
  triple point. Likewise, the 273.16 K of Goff and Gratch over ice is
  their 0 degC, not the triple point.
- `Catalog.uses` and `used_by` failed with an obscure error when given a
  formulation. They now take a formulation of the catalog as well as its
  reference `formulations.<key>` or a search entry, and refuse any other
  object with a clear message.
- A product of units written by pint takes the middle dot of the
  catalog symbols (`Pa·s`, as in `J/(kg·K)`), whatever its version:
  pint writes a dot operator from 0.25 and a middle dot before.
- The closed-form inverse of a formulation in degC, solved in K, writes
  T = t + T0 with T0 = 273.15 K. It wrote t - T0 with T0 = -273.15 K:
  the values were right, the expression misleading.
- The report of `check` took the domains of inputs on a conventional
  scale, stated on that scale, as values of the reference scale on which
  it evaluates. They are now converted to the reference scale first,
  leaving out the values that do not convert: Weiss and Price (1980),
  stated valid up to 313 K on IPTS-48, which converts up to 30 degC only,
  are compared with Dickson et al. (2007) on the whole common domain
  instead of three quarters of it. `ConventionalScale.interval_to_reference`
  carries an interval of a scale to its reference scale.
- `epsilon_ecmwf_ifs` is the value the IFS documentation prints, 0.621981
  (CY49R1, Part IV, section 7.5.2), instead of the ratio R_d / R_v
  computed by nomogram (0.6219808); it carries that ratio as its
  definition.
- The 0.6 % (k = 2) uncertainty of the WMO Magnus form over water was
  attributed to the WMO guide, which states none (WMO-No. 8, 2024,
  Annex 4.B). It is now cited from the WMO ET-QTC training unit that
  states it, beside the guide's own wording. The Magnus form over ice
  cites the guide (4.B.3) and gains its stated domain, -65 to 0 degC.
- `docs/rosetta.md` and two docstrings presented QUDT's `isDeltaQuantity`,
  set on no quantity kind, as a gap. By design it belongs to the quantity
  in its context (`qudt:Quantity`), the unit staying the same.
- A search by the CF name `air_temperature` missed the formulations taking
  a Celsius temperature (Magnus, Tetens, Buck...). CF names a temperature
  by its medium and allows `degC`, so the name is now linked to
  `CelsiusTemperature` too.
- A DOI searched whole found nothing, since it was split at its slashes
  and brackets (`10.1016/0304-4203(80)90024-9`). DOIs are now also kept
  whole, bare or as their `https://doi.org/` address. A word written
  exactly as a search term matches it even when the term holds wildcard
  signs (`[0]` in an address).

## [0.3.0] - 2026-10-21

### Added

- Conventional scales converted by an expression of `x` (`conversion`),
  possibly through another scale (`base`), within `bounds`; scales
  nomogram cannot convert (`convertible = false`, raising
  `ScaleConversionError` unless values are taken as given); CF standard
  names and a note on scales, searchable. A citation may state the scale
  of the output. Compositions check the scales of their pieces; an
  inverse takes its input on the scale of the source's output. A value
  beyond the bounds of a conversion follows `outside=` like a value
  outside a domain (NaN, `OutOfDomainError` with `"raise"`, a warning
  with `"warn"`); `evaluate` refuses an unknown `scale`, `outside` or
  `basis`.
- Guide `docs/sea-water.md`: salinity on conventional scales, the
  vapour pressures of sea water against TEOS-10, and the 2 % at the sea
  surface (the equivalent cooling of Beljaars 1998, found again by
  inversion, and the radio refractivity at the surface).
- In `sea-water`, the vapour pressure of sea water of Dickson et al.
  (2007): the total molality of dissolved species and the osmotic
  coefficient of sea water (QUDT kinds `MolalityOfSolute` and
  `OsmoticCoefficient`, unit mol/kg), composed with IAPWS SR1-86, which
  gains Dickson et al. as a citation. Cross-check of Weiss and Price
  (1980) and Dickson et al. (2007) against pySeaFlux 2.2.1.
- In `sea-water`, the vapour pressure of sea water. Kinds
  `SaturationVapourPressureOverSeaWater`, `RelativeVapourPressureOfSeaWater`
  and `SaturationSpecificHumidityOverSeaWater`, with
  `SaturationSpecificHumidity` in `moist-air`. The relative vapour
  pressure after Witting (1908, through Sverdrup et al. 1942 and Robinson
  1954), Sverdrup et al. (1942, on the Knudsen scale), Robinson (1954),
  Raoult's law (Sharqawy et al. 2010, adopted by the ITTC with Absolute
  Salinity), Nayar et al. (2016) and COARE 3.6; the vapour pressures of
  Millero and Leung (1976) and of Weiss and Price (1980); the ITTC vapour
  pressure, composed with IAPWS SR1-86; the 2 % salinity effect on the
  surface humidity (IFS, Beljaars 1998, Fairall et al. 1996). The family
  now requires `moist-air`.
- Temperature scales of oceanography: IPTS-68 through the linear
  conversion of Saunders (1990), t68 = 1.00024 t90, and IPTS-48 through
  Fofonoff and Bryden (1975).
- Family `sea-water`: kinds `SeaWaterSalinity` and `Chlorinity`, the
  salinity scales (Reference Salinity, PSS-78, Cox, Knudsen, Absolute
  Salinity) with their conversions and CF names (added to the frozen CF
  subset), and the formulations of Knudsen and of JPOTS giving salinity
  from chlorinity. QUDT kind `MassFraction`, units per mille, mmHg and
  atm.
- `Comparison.scale`: how the formulations compared took their inputs;
  after `scale="ignore"`, plot labels mark no conventional scale.
- Axis labels in three styles, display option `axis_labels`: `"si"`
  (default), the quotient of the quantity by its unit with the
  conventional scale as a subscript of the symbol, as the SI Brochure
  writes them (`Celsius temperature t₉₀/°C`); `"explicit"`
  (`Celsius temperature - t [°C] {ITS-90}`); `"simple"`
  (`Celsius temperature t [°C]`). `nomogram.display.axis_label` and
  `reference_scale`; conventional scales gain a short name (`symbol`)
  and a `subscript`, searchable.
- Search (`Catalog.search`, `nomogram.search`): one index of every entry
  of the catalog (formulations, kinds, references, constants, notations,
  trade terms, scales, relations, cross-checks, families, units); terms
  are shell-style wildcards matched against words, without case or
  accents, identifiers split at CamelCase and underscores; symbols in a
  normal form (`\rho_{\mathrm{v}}`, `ρ_v`, `rhô_v` are `rho_v`); field
  filters `key`, `kind` (with its specializations), `output`, `input`,
  `variable`, `symbol` with `notation`, `source` with `equation`,
  `family`, `keyword`; a symbol is found as its notation writes it,
  a unit or a scale by its symbol, the symbols of a citation by its
  reference (`notation="dickson2007"`). Results are `Selection`s, in
  catalog order, searched again or combined with `&`, `|` and `-`,
  displayed as tables in notebooks.
  `Catalog.uses` and `Catalog.used_by` follow the links between entries
  (`Catalog.links`, with the kinds and scales a composed formulation
  takes from its parts), in catalog order. Guide: `docs/search.md`.
- Family `radio` (ITU-R P.453-14, read on the PDF): refractive index
  from the refractivity (eq. 1), radio refractivity (eq. 2), its dry and
  wet terms (eq. 3, 4), the form with the total pressure (eq. 6) with the
  equivalence stated by P.453 and proven by SymPy, the approximate form
  (eq. 7) with its stated domain and criterion, the reference profile
  and the surface refractivity (eq. 11, 12), the modified refractivity
  (eq. 17), and the height above the surface h = z - z_s. Kinds
  `RadioRefractivity`, its dry and wet terms, `ModifiedRadioRefractivity`
  (interval scale), `SurfaceAltitude`.
- In `moist-air`: P.453 equations 8 (vapour pressure from the relative
  humidity in percent and the saturation vapour pressure in moist air)
  and 10 (from the water vapour density); kinds `DryAirPressure` and
  `SaturationVapourPressureInMoistAir`, parent of the saturation vapour
  pressures over water and over ice in moist air.
- Cross-checks against other implementations (catalog section
  `[cross_checks]`, `nomogram.model.CrossCheck` and `CheckCase`): values
  of formulations computed once with outside software, with its version
  and the date of the check; `nomogram.relations.replay` computes them
  again (the tests do it for every case), and
  `python -m nomogram.catalog verify` lists them. First one: ITU-R P.453
  against ITU-Rpy, 16 cases, all agreeing.
- An equivalence between formulations is refused when they do not work
  in the same units, since its proof compares the expressions as written.
  `docs/relation-verdicts.md` works through the equivalence of P.453
  equations 2 and 6.
- QUDT kind `Altitude` (CF `altitude`), on an interval scale with
  multiplicative units: the extraction script gains `offset_units` for
  scales whose zero is a reference surface rather than a unit.
- Composed formulations in the catalog (`composition = { outer, inner,
  bind }`): the inner expressions are substituted into the outer one,
  which gives an ordinary formulation (LaTeX, inversion, units of
  coefficients, signature) with its own citations. Inputs, coefficients
  and constants come from the parts and must agree; cycles and
  duplicates are refused. A composition is never more permissive than
  the chain of its parts: their domains apply to the values each part
  receives, intermediate values included, unless a source of the
  composed formulation states its own domain, which then replaces those
  stated for the parts (physical domains always apply); `check` points
  out a stated domain beyond those of the parts. `Formulation.parts`
  (`Part`) holds the parts; `Derivation` records the method
  `"composition"` and its `parts`; the legend of a single formula says
  what it is composed of.
- ITU-R P.453-14 equation 9 in the `moist-air` family: enhancement
  factors over water and over ice (`itu_r_p453_ef_water`,
  `itu_r_p453_ef_ice`), and the saturation vapour pressures in moist air
  (`itu_r_p453_es_water`, `itu_r_p453_es_ice`) composed from them and
  the Buck (1996) equations, with the domains P.453 states. Kinds
  `EnhancementFactor`, `SaturationVapourPressureOverWaterInMoistAir`,
  `SaturationVapourPressureOverIceInMoistAir`.
- Semantics for radio refractivity: QUDT kinds `RefractiveIndex`,
  `DimensionlessRatio` and `Height` (CF `height`), units `PPM`
  (displayed `ppm`, as ITU-R P.453 writes it), `M` and `KiloM`.
- A kind declared in a catalog may set `scale_type` (`ratio`,
  `interval`); it otherwise takes that of its parent.
- Registry of verdicts (`src/nomogram/data/catalog/verifications.json`,
  generated): each verdict on a relation is filed under a SHA-256
  fingerprint of everything it depends on (relation, signatures of its
  formulations, scales, budget, version of the method `VERIFIER`).
  `nomogram.relations.verdict` reads it when the fingerprint matches;
  `record` and `python -m nomogram.catalog verify --record` compute only
  what is missing and drop stale entries; a test recomputes every
  verdict and compares it with the registry.
- `docs/relation-verdicts.md`: examples of what SymPy proves, leaves
  unproven or refutes, and the registry of verdicts.
- Signatures of formulations (`nomogram.relations.signature`): equal
  for two writings of one formulation (inputs renamed canonically,
  coefficients as exact rationals); the catalog refuses a formulation
  identical to another, naming it so that a citation is added instead.
  `form` leaves coefficients aside (the Magnus forms share one).
- `python -m nomogram.catalog check FILE` (`check`, and
  `nomogram.relations.report`): for each formulation of a file, those of
  the same form and the maximum relative deviation observed against every
  formulation of the same kind on their common domain; numerically
  identical pairs are pointed out, pairs that cannot be compared (a scale
  without conversion, no finite point) are named. Observations, never
  relations.
- Relations between formulations (`nomogram.model.Relation`, catalog
  section `[relations]`): what a source states, equivalence (possibly
  given substitutions between inputs) or approximation (maximum relative
  deviation over a domain, with where it lies), with its citation and
  whether formulas are compared with scale conversion or as given.
  `nomogram.relations.verify` proves equivalences with SymPy (proven,
  refuted with a counterexample, or unproven), results compared in their
  output unit, and checks approximations on a grid refined around its
  best points (reproduced, held or exceeded, the share of the grid where
  both are finite stated), inputs matched by identifier then by kind; a
  claim that cannot be checked as it stands is unverified (an
  equivalence across scales under conversion, an approximation finite
  nowhere);
  `Catalog.relations`. `docs/relation-verdicts.md` says what each verdict
  guarantees: reliable with one to three inputs, an estimate beyond.
- The maximum relative errors of Alduchov and Eskridge (1996, Table III)
  for five Magnus forms against GG46 (triple-point form) and SO90, and
  between GG46 and SO90: ten of twelve reproduced to the third decimal
  with the formulas compared as given; Sonntag's Magnus coefficients
  (SA90) give 0.610 % and 0.315 % where the table gives 0.597 % and
  0.328 %.
- Catalog families (`nomogram.catalog.Family`): each file declares a
  `[catalog]` header (name, format, requires, keywords, `matches`);
  `catalog("water-vapour")` loads one family with those it requires,
  `catalog()` still loads everything; `Catalog.families`;
  `Formulation.family` (from the file) and `Formulation.keywords`.
  Checked when loading: requires known and without cycle, entries
  referring only to their family and its requires, every required family
  used. `python -m nomogram.catalog describe FILE` prints the header a
  file needs. Personal catalogs: `catalog(extra=[path])`, keys prefixed
  with the family name; `load_catalog` accepts paths.
- Citations (`nomogram.model.Citation`): a formulation is written once,
  and each source that gives it is a citation recording what that source
  states (equation number, notation, units of coefficients, validity
  domains, accuracy, temperature scales). `Formulation.citations`;
  `Formulation.references` and `Formulation.domains` are derived from
  them. A citation's notation is the source's own symbols or a
  convention of the catalog. `CoefficientUnit.citation` names the source
  of a stated unit.
- `nomogram.dimensions.infer_units` (and `Formulation.coefficient_units`):
  the unit of each coefficient, declared or inferred by dimensional
  analysis of the expression tree (B of the Magnus form in °C, C in hPa,
  a2 of Sonntag's formulation in 1/K). Local propagation runs first and
  records the part of the expression each unit follows from; linear
  algebra settles the rest. Formulations with fixed units are read as
  numerical value equations where needed (T/K in ln(T)).
- The catalog checks at load that every coefficient has a unit, declared
  or inferred, and that declared units agree with the expression; a
  conflict names the part of the expression where it appears.
- Declared units of coefficients say where they come from
  (`unit_basis`: `"stated"` by the source, or `"added"` when the entry
  was written, with a note); `CoefficientUnit.origin` is `"stated"`,
  `"added"` or `"inferred"`, and the legend of a single formulation reads
  "from the source", "added by nomogram" or "inferred by nomogram". The
  catalog guide states the rule for contributors.
- The Markdown legend of a single formulation gives the unit of every
  coefficient and its origin (from the source, added or inferred by
  nomogram), and the units the
  coefficients of a formulation with fixed units hold for; tables and
  plot labels do not show origins. Renderings and tables have a short
  `repr`.
- `nomogram.display`: `render` displays a formulation as LaTeX, as a
  matplotlib label and as Markdown with the meaning and unit of each
  symbol; `table` puts several formulations side by side (equation,
  validity domains, references); `symbol` labels a variable for a plot.
  Renderings and tables display themselves in Jupyter notebooks
  (`_repr_markdown_`, and `_repr_latex_` for a formulation), without
  importing IPython. Guide: `docs/display.md`.
- Display options (`DisplayOptions`): multiplication sign, decimal
  separator, upright symbols, coefficients as values; set for one call,
  as a reusable set, or for a block (`display_options`, a context
  variable as `numpy.printoptions`).
- `nomogram.expression.LATEX_COMMANDS`: the LaTeX commands nomogram
  emits, common to MathJax, KaTeX and matplotlib's mathtext; every
  formula of the catalog is checked against it, and notation symbols
  outside it are refused when the catalog is loaded.

### Changed

- Compositions: a part reached twice, directly and inside another part,
  is one part, its coefficients counted once; the units of coefficients
  are inferred with each inner part keeping the unit of its output.
- The symbol of the unit one is 1, as in the SI Brochure, rather than
  QUDT's `一` (a deliberate QUDT choice, qudt/qudt-public-repo#712);
  displays still leave it unwritten. Unit symbols follow the SI Brochure,
  departures from QUDT being declared in the extraction script.
- Plot axes and `display.symbol` labels follow `axis_labels` (SI form
  by default, instead of a unit in brackets). A temperature axis names
  the temperature its values are: in °C a Celsius temperature t, in K or
  °R a thermodynamic temperature T, in °F a temperature (it said
  "Thermodynamic Temperature [°C]"). The y axis of `plot_values` gains
  the name of the output kind, the x axis a symbol (in the notation
  given); names are in sentence case, units take the catalog's symbols.
  The deviation axis reads "Relative deviation from ... δ/%".
- `Derivation.solved_for` is optional (`None` for a composition), and
  `Derivation` gains `parts`.
- The bundled catalog is split into families: `core` (conventional
  scales, notations), `water-vapour` (saturation vapour pressure),
  `moist-air` (humidity quantities) and the aggregate `humidity`; no
  value changes.
- Conventional reference scales (VIM 1.29): `TemperatureScale` becomes
  `ConventionalScale`, for any quantity kinds, with one reference scale
  per kind (ITS-90 for temperatures) and a conversion table to it
  (`from_reference`, `to_reference` replace `from_its90`, `to_its90`).
  `Variable.scale` replaces `Variable.temperature_scale` and
  `Catalog.scales` replaces `Catalog.temperature_scales`. Catalog format:
  `[scales.<key>]` with `kinds`, and for a derived scale
  `reference_scale`, `unit` and `differences`; inputs take `scale`
  instead of `temperature_scale`. No value changes.
- Catalog format: `[[formulations.<key>.citations]]` replaces
  `references` and `accuracy`; domains, units of coefficients and
  temperature scales stated by a source move into its citation; the
  formulation keeps physical domains (without `basis`), units added by
  nomogram and scales nomogram infers. `Formulation` takes
  `physical_domains` and `citations` instead of `domains`, `accuracy`
  and `references`. Domains stated by different sources combine by union
  by default (inside if one source says so); within a citation they
  apply together, as do physical domains. The catalog was converted
  without changing any value; the range of the Goff-Gratch equation,
  attributed to Gibbins (1990) without citing it, now comes with that
  citation.
- Catalog: the declared units of coefficients that the expression
  determines were removed (Murray, Goff 1957, Marti and Mauersberger,
  and the reference temperatures of Goff-Gratch), since Vömel, the
  source read, gives these coefficients as bare numbers; they are now
  inferred. The units stated by the IAPWS releases are kept as stated,
  and the two reference pressures of Goff-Gratch, read inside a
  logarithm, as added.
- Default typography of `Formulation.latex()`: every product shows ×
  (RH can no longer be read as R × H), a power of ten always with ×
  whatever the multiplication sign chosen, and descriptive subscripts are
  upright, as in ISO 80000-2 (`e_{\mathrm{s}}` instead of `e_{s}`).
  `DisplayOptions.SYMPY` gives the former rendering.

### Fixed

- Notes of the catalog checked again against their sources: the
  Goff-Gratch equation over water is not the form Alduchov and Eskridge
  (1996) print (their GG45, with the opposite sign in the last exponent,
  which they report more than 5 % from GG46): the disagreement is
  recorded; Buck's (1981) formulas over ice come from Vömel only.

## [0.2.0] - 2026-10-14

### Added

- Saturation vapour pressure over ice (new quantity kind
  `SaturationVapourPressureOverIce`): the IAPWS sublimation equation
  R14-08(2011) as reference, read in the release (range 50 to 273.16 K,
  ITS-90; reproduces its Table 3), and the formulations quoted by Vömel:
  Goff-Gratch, Hyland and Wexler (ITS-90, inferred from numbers), WMO
  Guide Magnus form, Murray, Buck (1981 and 1996), Marti and
  Mauersberger, Murphy and Koop, Sonntag. Their deviations from IAPWS
  are tested, and so is the frost point obtained with `invert`.
- Humidity mixing ratio r = epsilon e / (p - e) and specific humidity
  q = r / (1 + r) (ASHRAE 2017, through PsychroLib), with the constant
  epsilon = 0.621945 and its source (ASHRAE); the values of the ECMWF
  IFS (0.6219808, R_d/R_v) and of MetPy (0.6219569, M_w/M_d) are recorded
  too, each read in its source; composed with any saturation vapour
  pressure formulation they give r and q at saturation, or from (T, RH,
  p). Checked against PsychroLib and against ASHRAE's Table 2 (the ideal
  gas formula stays 0.4 to 0.6 % below it).
- `compose` lets a result feed an input of a more general kind
  (`feeds`): a saturation vapour pressure is a vapour pressure, never the
  reverse.
- `docs/approach.md`, "How nomogram earns trust": sources read and their
  status, checks against published values, comparison with a reference,
  units and temperature scales, objective validity domains, derived
  formulations checked both ways (f^-1(f(t)) = t and f(f^-1(e)) = e), and
  the limits of the tests; linked from both READMEs.
- `nomogram.inversion`: `invert` turns a formulation of one input around;
  SymPy finds the closed form when there is one (after taking
  logarithms: the Magnus form gives the classical dew point formula
  t_d = B ln(e/C) / (A - ln(e/C)), Buck's quadratic forms get their
  right branch picked automatically), otherwise the inverse is solved by
  vectorised bisection. The derived formulation records its origin
  (`Derivation`), carries the validity domains through the function and
  returns temperatures on ITS-90. `dew_point` inverts any saturation
  vapour pressure formulation; with `vapour_pressure_from_relative_humidity`
  (e = RH e_s, new catalog entry) it composes into t_d = f(T, RH).
- Quantity kinds `DewPointTemperature` (interval scale, degC; CF
  `dew_point_temperature`), never matched with the air temperature, and
  `Pressure` (CF `air_pressure`), extracted from QUDT 3.5.2.
- Zenodo DOI (all versions: 10.5281/zenodo.23373134): badge in the README,
  `doi` in `CITATION.cff`.

## [0.1.1] - 2026-10-14

### Fixed

- The dimensional check of quantity equations no longer divides by zero
  when inputs cancel out (p - e): probe values are distinct.
- Archive metadata for Zenodo (`.zenodo.json`): the creator is declared by
  name (the alias), which Zenodo requires; the 0.1.0 release could not be
  archived for lack of it.

## [0.1.0] - 2026-10-14

First release.

### Added

- Core dependencies: sympy, numpy and pint (at least 0.24.4); matplotlib
  in the optional `viz` extra. Works on an offline workstation: no
  online engine at run time.
- License expression `BSD-3-Clause AND CC-BY-4.0 AND CC0-1.0`: the
  package ships QUDT data (CC BY 4.0, attribution in
  `src/nomogram/data/NOTICE.md`) and CF data (CC0 1.0).
- Package skeleton, pure Python, `requires-python >= 3.12`, typed
  (`py.typed`).
- BSD-3-Clause license, declared through SPDX (PEP 639 metadata and
  per-file headers).
- Local checks with pre-commit: formatting and lint (ruff), secrets
  (gitleaks), anonymity, Conventional Commits, strict typing (mypy) and
  tests on push.
- Continuous integration: quality checks, complete blocking test matrix
  (Ubuntu and Windows × Python 3.12 and 3.13), commit signature check
  on pull requests; Dependabot for actions and dependencies.
- Contributor documentation: `AGENTS.md`, contributing guide (English
  and French), security policy, code of conduct, issue and pull request
  templates, citation file.
- Tooling aligned with the Scientific Python development guide:
  spelling check (codespell) and workflow security audit (zizmor) as
  hooks, extra ruff rule families, strict pytest configuration with
  warnings as errors, extra mypy checks, grouped Dependabot updates
  with a 7-day cooldown, manual CI trigger, documented `sp-repo-review`
  exceptions.
- Branch coverage measured with coverage.py, with an 80 % floor
  enforced in every cell of the CI test matrix.
- Anonymity hook: tool-level names, not tied to the project
  (`ANONYMITY_DENY_PATTERNS`, `~/.config/anonymity/deny-patterns.txt`,
  `$XDG_CONFIG_HOME` honored), so that one personal list serves every
  repository; several patterns files allowed (`os.pathsep`), each
  required to exist; guided setup (`--init` creates a commented starter
  patterns file); the patterns file protects itself (refused inside
  the repository, found from any subdirectory, marker line rejected in
  any committed file, even in CI); non-printable characters
  neutralized in displayed names and paths; beginner-friendly
  documentation of its purpose, usage and limits.
- Anonymity hook: project-specific patterns files declared for one
  clone only in `.git/anonymity-deny-patterns` (never committed), with
  the same checks as the other lists.
- `_priv/` folder ignored at the repository root, for each
  contributor's personal material.
- Coverage reports uploaded to Codecov from every CI matrix cell
  (OIDC, no stored token; one flag per OS and Python version),
  informational only; Codecov badge in both README files.
- Release workflow: triggered by a published GitHub release (PyPI,
  after approval of a protected environment) or manually (rehearsal on
  TestPyPI with a unique development version); single build, metadata
  check, SLSA build provenance and CycloneDX SBOM attestations, Trusted
  Publishing with PEP 740 attestations, no stored token.
- `nomogram.units`: nomogram's own pint registry (`ureg`, `Q_`),
  `convert` (also accepts quantities from other pint registries, such as
  MetPy's), `is_offset_unit`, `ScaleType` (ratio or interval scale).
- `nomogram.expression`: formulas written once in restricted Python
  syntax, parsed safely (whitelist, no `eval`) into SymPy expressions;
  LaTeX per notation (`to_latex`, with `\exp` written explicitly since
  `e` denotes the vapour pressure); cached numeric functions vectorised
  with numpy (`compile_numeric`).
- `nomogram.__version__`, read from the package metadata.
- Vocabulary reference (`docs/rosetta.md`): nomogram's concepts mapped
  to QUDT, the SI and VIM, pint, SymPy, CF standard names and OM, with
  ambiguous trade terms (absolute and specific humidity) and the
  inconsistencies found in QUDT 3.5.2.
- `nomogram.semantics`: quantity kinds, unit definitions and CF standard
  names from bundled subsets of QUDT 3.5.2 and the CF standard name
  table 95 (`semantic_catalog`), with scale type and point/difference
  typing of each kind, applicable units checked against pint, and
  links to Wikidata as `ExternalMatch` (SKOS relation, date of last
  verification).
- `scripts/extract_semantics.py`: development tool regenerating the
  bundled subsets (rdflib, development dependency only).
- `nomogram.model`: formulations with their variables (quantity kind and
  unit), empirical coefficients, physical constants, objective validity
  domains (physical or stated by the source, with criterion and
  reference), references with a verification status, notations and
  ambiguous trade terms. `Formulation.evaluate` converts pint inputs to
  the unit and scale of the formula (coefficients are never converted),
  is vectorised, and returns NaN outside the validity domains by default
  (or warns, raises, or ignores them on request).
- `nomogram.catalog`: hand-written TOML catalog, validated when loaded
  (declared and used identifiers, units applicable to kinds, references,
  dimensional homogeneity of quantity equations, unknown keys refused);
  kinds defined by nomogram, such as the saturation vapour pressure over
  water; first entries: Sonntag (1990) and the mass concentration of
  water vapour from the ideal gas law.
- Saturation vapour pressure over water: IAPWS SR1-86(1992) as the
  reference, Sonntag (1990), the Magnus forms of Sonntag (1990), Alduchov
  and Eskridge (1996, AEKR) and Buck (1981), the Buck (1981) equation,
  Tetens (1930) and Hyland and Wexler (1983); each with its references
  and verification status, stated domains and published accuracy.
- `nomogram.comparison`: `compare` (values and relative deviations from a
  reference formulation, vectorised) and `compose` (feeding formulations
  into another, for HA = f(T, RH)); Celsius and thermodynamic
  temperatures match the same input, a temperature difference never
  does.
- Further saturation vapour pressure formulations, as quoted by Vömel's
  review of saturation vapour pressure formulations: Bolton (1980),
  Murray (1967), Buck (1996), the Goff-Gratch equation (Smithsonian
  Tables form, steam point 373.16 K, range -50 to 102 degC) and the
  Goff (1957) triple point form. Conflicting attributions between
  secondary sources are recorded (Sonntag 1990 or 1994; Goff 1957 or
  GG46).
- Temperature scales: each temperature input of a formulation records
  the scale it was fitted on (ITS-90 or IPTS-68) and how it is known:
  stated by the source, inferred from the publication date only (weak:
  new scales took years to be applied), or inferred from numerical
  evidence. `evaluate`,
  `compare` and `compose` take ITS-90 inputs and convert them to that
  scale by default (`scale="convert"`; `"ignore"` to disable), from the
  table of t90 - t68 of the ITS-90 text. Hyland and Wexler's
  coefficients, as given by ASHRAE (2017), behave as ITS-90: scale ITS-90
  inferred from numbers.
- `nomogram.plot` (extra `viz`, matplotlib, imported lazily):
  `plot_deviations` (relative deviation from the reference, in %) and
  `plot_values` (y-axis symbol in a chosen notation); values outside
  validity domains show as gaps. Every formulation of the catalog, in
  every notation, is checked to render in matplotlib's mathtext.
- Ways to contribute (contributing guide, en and fr): reference to
  integrate, information or problem about a catalog entry, formula
  proposal, code; new issue templates for the first two, catalog guide
  `docs/catalog.md` (writing a catalog entry).
- README example: every saturation vapour pressure formulation against
  IAPWS, with its script (`docs/examples/`), run by the tests.
- `Comparison` keeps the formulations compared (labels, output variable).
- Expressions accept `log10`, written `\log_{10}` in LaTeX.
- README: usage example.

[Unreleased]: https://github.com/miki4iaml/nomogram/compare/v0.4.0...develop
[0.4.0]: https://github.com/miki4iaml/nomogram/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/miki4iaml/nomogram/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/miki4iaml/nomogram/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/miki4iaml/nomogram/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/miki4iaml/nomogram/releases/tag/v0.1.0
