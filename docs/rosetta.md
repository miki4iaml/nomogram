# Rosetta stone: the vocabulary of nomogram

nomogram reuses established vocabularies rather than inventing its own.
This page maps each concept it handles to the terms used by
[QUDT](https://qudt.org/) (the reference vocabulary), the metrology
texts it rests on (SI Brochure, VIM), its dependencies (pint, SymPy)
and the domain vocabularies it bridges (CF standard names, OM). Where
nomogram departs from QUDT, the reason is given.

Versions read: QUDT 3.5.2, CF standard name table 95, SI Brochure 9th
edition, VIM3 (JCGM 200:2012), pint 0.26, SymPy 1.14.

## Main table

| nomogram term | QUDT | SI / VIM | pint | SymPy | CF / OM | Notes |
|---|---|---|---|---|---|---|
| quantity kind | `qudt:QuantityKind` | kind of quantity (VIM 1.2) | none | none | CF standard name (narrower); OM `Quantity` subclasses | `nomogram.semantics.QuantityKind`, with nomogram's scale type and point/difference typing. Two quantities of the same dimension need not be of the same kind (VIM 1.2): pint cannot tell a Celsius temperature from a temperature difference, hence QUDT kinds. |
| specialization | `qudt:specializationOf` | — | none | none | — | How nomogram defines kinds QUDT lacks, e.g. saturation vapour pressure over water as a specialization of `VapourPressure`. Such kinds have `origin = "nomogram"` and no IRI yet; their local names are stable, to become the end of persistent IRIs (w3id.org) once nomogram has documentation online. |
| quantity | `qudt:Quantity` | quantity (VIM 1.1): a property of a phenomenon, body or substance | none | none | OM `Quantity` | The property itself ("the temperature of this air"), not a number. Never a class name in nomogram, to avoid the clash with pint's `Quantity`. |
| quantity value | `qudt:QuantityValue` (`numericValue` + `unit`) | quantity value (VIM 1.19) | `pint.Quantity` (`magnitude` + `units`) | none | OM `Measure` | nomogram keeps pint's name `quantity` for parameters holding a pint object, and says "quantity value" in prose when the distinction matters. |
| unit | `qudt:Unit` | measurement unit (VIM 1.9) | `pint.Unit` | `sympy.physics.units` (not used) | CF canonical units (UDUNITS strings) | pint is the only unit engine; QUDT units are mapped to pint strings and checked by dimension. |
| dimension | `qudt:QuantityKindDimensionVector` (`hasDimensionVector`) | quantity dimension (VIM 1.7) | `dimensionality` | none | — | Same notion; QUDT adds dimension `D` (dimensionless ratio) to tell ratios apart. |
| unit registry | `qudt:SystemOfUnits` (partly) | system of units (VIM 1.13) | `pint.UnitRegistry` | — | — | nomogram owns one private registry, `nomogram.units.ureg`, created once and never modified. |
| offset unit | unit with `qudt:conversionOffset` ≠ 0 (`unit:DEG_C`: multiplier 1, offset 273.15) | none: the SI says the degree Celsius equals the kelvin in magnitude; the *quantity* Celsius temperature is offset (SI Brochure 2.3.1) | non-multiplicative unit (`degC`, `degF`) | — | OM: a scale defined by an offset from another | QUDT and pint put the offset in the unit, the SI puts it in the quantity. nomogram follows pint for computation and the SI for meaning: `is_offset_unit` tells which units express points of an interval scale. |
| conventional scale | `qudt:Scale` (class only: no instance in the QUDT 3.5.2 vocabularies used) | conventional reference scale (VIM 1.29), for example the International Temperature Scale (ITS-90), formerly IPTS-68, IPTS-48, ITS-27 | none | — | CF names salinity by scale (`sea_water_practical_salinity`, `sea_water_knudsen_salinity`...) | `nomogram.model.ConventionalScale`: a quantity-value scale defined by formal agreement, for given quantity kinds, with one reference scale per kind (ITS-90 for temperatures, Reference Salinity for salinity) and a conversion to it: a table, or an expression of the value, possibly through another scale (Knudsen salinity, then Cox salinity, then Reference Salinity); a scale may hold no conversion (Absolute Salinity, whose anomaly depends on the location). Not QUDT's `ScaleType` (ratio, interval), which is the level of measurement. The scale a formulation was fitted on is stated by the source, inferred from the publication date only (weak: ITS-90 itself took years to be applied) or inferred from numerical evidence. Inputs are taken on ITS-90 and converted before evaluation (table of t90 − t68 from the ITS-90 text); a formulation fitted to formulas on several scales gets none. Neither QUDT nor pint models it, though it shifts saturation vapour pressure by up to 0.09 % between 0 and 100 °C. |
| scale type | `qudt:ScaleType`: `RatioScale`, `IntervalScale`, `OrdinalScale`, `NominalScale` | quantity-value scale (VIM 1.27); ordinal scale (VIM 1.28) | none | — | OM `Scale` | `nomogram.units.ScaleType` keeps only ratio and interval, the two the formulas need. The four types come from Stevens (1946). |
| point / difference | `qudt:isDeltaQuantity`, a boolean of `qudt:Quantity` (the quantity in its context), not of the kind; the unit stays the same | — | `degC` versus `delta_degC` | — | OM `Point` versus `Measure` | A Celsius temperature is a point; the difference of two points is a difference, expressed in `delta_degC` or `K`. pint refuses to add two points. In a formula each input or output is a point or a difference by definition, so nomogram types it on the variable's kind (`TemperatureDifference`); a nomogram variable plays the role of a `qudt:Quantity`. |
| identifier | none (`qudt:QuantityKind` IRIs identify kinds, not variables) | — | — | name of a `sympy.Symbol` | — | The semantic name of a variable in a formula (`t`, `RH`, `e_s`), stable across notations. |
| symbol | `qudt:symbol`, `qudt:latexSymbol`, `qudt:altSymbol` | quantity symbol (ISO 80000-1) | unit symbol only | `sympy.Symbol` is a *variable*, not a glyph | — | Ambiguous across vocabularies. In nomogram's prose, "symbol" means the glyph (QUDT sense); the SymPy object is always called "SymPy symbol". |
| notation | none (one `latexSymbol` per kind, plus `altSymbol`) | — | — | `symbol_names` of the LaTeX printer | — | A mapping from identifiers to LaTeX symbols, one per author or convention (WMO, ASHRAE...). QUDT has no concept of competing notations: nomogram adds it. |
| citation | none (`dcterms:source`, `qudt:informativeReference` on kinds and units) | — | — | — | — | `nomogram.model.Citation`: one appearance of a formulation in a source, with what the source states (equation number, notation, units, validity domains, accuracy, conventional scales of the inputs and of the output). A formulation is written once and cited by each source that gives it; domains of different citations combine by union by default. |
| family | none | — | — | — | — | `nomogram.catalog.Family`: one file of the catalog, with the families it requires. A core without dependency, pure families (one domain), aggregates (requires only). Names are nomogram's own; links to the subject vocabularies of each domain (GCMD Science Keywords, PhySH, IEC 60050) go in `matches`, as for quantity kinds. |
| relation | none | — | — | — | — | `nomogram.model.Relation`: what a source states between two formulations, equivalence, proportionality or approximation, or an equivalence or a proportionality nomogram computes and proves, without a citation (maximum relative deviation over a domain), with its citation; verified by `nomogram.relations.verify` (proven, refuted or unproven; reproduced, held or exceeded; unverified when it cannot be checked as it stands). A deviation nomogram computes without a source is an observation, never a relation. |
| rendering | — | — | — | printer settings (`mul_symbol`, `decimal_separator`, `symbol_names`) | — | `nomogram.display.Rendering`: one formulation displayed in one notation with given `DisplayOptions` (typography). The notation says *which* symbols; the options say *how* they are set (multiplication sign, upright subscripts...). |
| expression | `qudt:expression`, `qudt:latexDefinition`, `qudt:mathMLdefinition` | quantity equation (VIM 1.22) | — | `sympy.Expr` | — | Written once in restricted Python syntax; LaTeX and MathML are derived, never stored. |
| piecewise definition | none | — | — | `sympy.Piecewise` (subclassed, never evaluated: conditions kept as written, a power applied to the whole) | — | `piecewise((expression, condition), ...)` in an expression: each condition an interval of one input, the same for every branch; NaN where none holds. Rendered on one line in a left brace (mathtext has no `cases` environment). Inverted branch by branch when each branch is strictly monotonic on its interval. A catalog entry with `branches` takes its pieces from other formulations (`nomogram.model.Branch`), whose domains apply where their conditions hold. |
| formulation | none | — | — | — | — | `nomogram.model.Formulation`: one author's way of computing a quantity kind (Magnus-Tetens, Sonntag 1990...). The alternative formulations of a kind are what nomogram compares; they are grouped by the kind they compute. |
| fixed units | none | numerical value equation (VIM 1.25), as opposed to a quantity equation (VIM 1.22) | — | — | — | `Formulation.fixed_units`: the coefficients only hold in the declared units. They are never converted; inputs are converted to the declared unit and scale first (a Fahrenheit point becomes a Celsius point), since with offset scales a formula's result depends on the scale it is written in. The VIM terms are not widely used, hence the plainer name. Quantity equations have their dimensional homogeneity checked when the catalog is loaded. |
| coefficient | none | — | — | — | — | Empirical parameter of one formulation (the A, B, C of the Magnus form). Not a physical constant: it has a source and a validity domain. Its unit is declared, or inferred by dimensional analysis (`nomogram.dimensions.infer_units`). |
| physical constant | `qudt:PhysicalConstant`, `qudt:ConstantValue` | — | pint constants (`R`, `k`...) | `sympy.physics.constants` (not used) | — | Constants with a metrological status (specific gas constant of water vapour). nomogram keeps their source (IAPWS-95, CODATA) because values differ between sources. |
| nature of a constant | `qudt:exactConstant` (a boolean); `qudt:standardUncertainty` | defining constant, whose numerical value has no uncertainty (SI Brochure, 2.2); conventional quantity value (VIM 2.12); measured quantity value (VIM 2.10) | none | none | — | `nomogram.model.ConstantNature`: `exact` (a defining constant of the SI, or one derived from them alone: CODATA "exact"), `conventional` (attributed by agreement: g_n, or a value a source adopts) or `measured`. QUDT's boolean says only whether a constant is exact; the VIM separates the two other cases. `PhysicalConstant.uncertainty` is the standard uncertainty the source gives. |
| validity domain | none | — | — | assumptions (`real=True`, `positive=True`) only | — | `nomogram.model.ValidityDomain`. Objective domains only: *physical* (where the physics holds) or *stated* by the author or the cited publication, each with its criterion (maximum deviation or uncertainty against a reference) and its source. A domain suited to an application is the user's business. Behaviour outside is a parameter of `evaluate` (NaN by default). No vocabulary covers it; nomogram defines it. |
| reference | `qudt:Citation`; `qudt:informativeReference`, `qudt:isoNormativeReference` | — | — | — | — | `nomogram.model.Reference`: bibliographic source of a formulation, constant, domain or notation, with a verification status (`verified` or `to-confirm`). The DOI takes precedence over any other identifier. |
| derivation, inversion | none | — | — | `sympy.solve` | — | `nomogram.inversion.invert`: a formulation of one input, inverted. A closed form found by SymPy (after taking logarithms) becomes a formulation with its own expression and LaTeX, branch by branch for a piecewise definition whose branches are strictly monotonic on their intervals; otherwise the inverse is solved numerically. `Derivation` records the source and the method; validity domains are carried through the function, and temperatures return to ITS-90. |
| definition, identity | `qudt:latexDefinition` (the definition of a quantity kind, as LaTeX text: `$x = m/m_d$`) | quantity equation (VIM 1.22), by which a quantity is defined (VIM 1.12, examples: v = dr/dt) | — | — | — | `FormulationNature`: a formulation true by definition, or an exact consequence of definitions, cited to a text that prints it; it has no empirical coefficient nor stated domain. It is the *defining formula* that MathModDB (P989) and Wikidata (P2534) give a quantity, each symbol tied to a quantity, here evaluable, with units, and cited; QUDT keeps it as text only. A formulation derived by nomogram (`Formulation.derived`) is a composition, branches or calls without a citation of their own: its provenance is its `Derivation`. |
| assumption | none | — | — | — | — | `Assumption`: what a formulation assumes, stated by its source (in the citation), stated by another source, deduced from its form, or suspected; never turned into a validity domain without a criterion. |
| comparison, composition | none | — | — | `sympy.Expr.subs` | — | `nomogram.comparison`: `compare` gives the relative deviation of formulations of one kind from a reference; `compose` feeds formulations into another, numerically. A composed catalog entry (`composition`) substitutes the expressions of its parts and is an ordinary formulation, with `Derivation` method `"composition"`. An entry may also call formulations in its expression, each at its own arguments (`calls`, `Derivation` method `"calls"`), as a Modelica function call names its arguments. Inputs are matched by quantity kind; the Celsius and thermodynamic temperatures express one state (t = T − 273.15 K) and match the same input, a temperature difference never does. In a composition, a result may feed an input of a more general kind (`specializationOf`): a saturation vapour pressure feeds a vapour pressure input, never the reverse. |
| search, selection, link | none | — | — | — | — | `Catalog.search`: shell-style wildcards matched against the words of every entry (names, symbols in every notation, labels, CF names), without case or accents; field filters; a `Selection` searched again or combined (`&`, `|`, `-`). `uses` / `used_by` follow the links between entries (`Catalog.links`). See [search.md](search.md). |
| cross-check | none | — | — | — | — | `[cross_checks]` in the catalog: values of formulations computed once by another implementation, with its version and the date; replayed by the tests (`nomogram.relations.replay`). An observation that two implementations of a printed equation agree on given points, never a source nor a proof. |
| trade term | none | — | — | — | — | `nomogram.model.TradeTerm`: a term whose meaning depends on the trade (absolute humidity), recorded as a label pointing to unambiguous kinds, never as a kind. |
| CF standard name | none | — | — | — | CF standard name, with canonical units | The geoscience name of a variable in a data file (`air_temperature`). Linked to a QUDT kind; one kind may have several CF names, and one CF name may name several kinds that differ only by their scale (`air_temperature`: thermodynamic and Celsius temperatures, since CF allows `degC`). A CF name on a kind that says nothing of the medium is a search aid, not a statement about the medium: `input="air_temperature"` also finds sea-water formulations. |
| external match | `qudt:wikidataMatch`, `qudt:siExactMatch`, `qudt:ucumCode`, `qudt:udunitsCode`; SKOS `exactMatch`, `closeMatch`, `broadMatch`, `narrowMatch` | BIPM SI Reference Point | — | — | — | `nomogram.semantics.ExternalMatch`: target, SKOS relation, date of last verification. See "External links". |
| unit definition | `qudt:Unit` with `conversionMultiplier`, `conversionOffset` | — | the pint expression it maps to | — | — | `nomogram.semantics.UnitDefinition`: the QUDT record of a unit. Named after Wikidata's description of P2968 ("unit of measure definition according to QUDT") to avoid a clash with `pint.Unit`. |

## Reference case: humidity of air

| Variable | QUDT kind | Wikidata | CF standard name | pint unit |
|---|---|---|---|---|
| thermodynamic temperature T | `ThermodynamicTemperature` | Q264647 | `air_temperature` | `K` |
| Celsius temperature t | `CelsiusTemperature` | Q74758530 | `air_temperature` (in `degC`) | `degC` |
| temperature difference | `TemperatureDifference` | — | — | `delta_degC`, `K` |
| dew point temperature T_d | `DewPointTemperature` | — | `dew_point_temperature` | `degC`, `K` |
| air pressure p | `Pressure` | Q39552 | `air_pressure` | `hPa` |
| relative humidity RH | `RelativeHumidity` | Q2499617 | `relative_humidity` | `percent`, `1` |
| vapour pressure e | `VapourPressure` | — | `water_vapor_partial_pressure_in_air` | `hPa` |
| saturation vapour pressure e_s | nomogram kind, specialization of `VapourPressure` | — | none | `hPa` |
| absolute humidity (mass concentration of water vapour) | `MassConcentrationOfWaterVapour` | Q76378808 | `mass_concentration_of_water_vapor_in_air` | `g/m³` |
| humidity mixing ratio | `MassRatioOfWaterVapourToDryGas` | Q17232415 | `humidity_mixing_ratio` | `g/kg` |
| specific humidity | `SpecificHumidity` | — | `specific_humidity` | `g/kg` |
| specific energy | `SpecificEnergy` | Q3023293 | none | `J/kg` |

## Ambiguous trade terms

Some terms mean different quantities in different communities. nomogram
records the term as a label, never as a kind, and points to the
unambiguous kinds.

| Term | Meaning | Community | Kind (QUDT / ISO 80000-5) | Typical unit | Sources |
|---|---|---|---|---|---|
| absolute humidity | mass of water vapour per volume of moist air (the mixture) | meteorology, physics | `MassConcentrationOfWaterVapour`, v = m/V | g/m³ | AMS Glossary (*vapor density*); ISO 80000-5 as quoted by QUDT; IEC Electropedia |
| absolute humidity | mass of water vapour per mass of dry air | chemical engineering, HVAC, the French term for absolute humidity on psychrometric charts | `MassRatioOfWaterVapourToDryGas`, x = m/m_d | g/kg | Çengel and Boles, *Thermodynamics*, ch. 14; French HVAC teaching material; QUDT's own description of `AbsoluteHumidity` |
| specific humidity | mass of water vapour per mass of moist air | meteorology (CF, NOAA), ASHRAE (γ) | `SpecificHumidity`, q = m/(m + m_d) | g/kg | CF table 95; ASHRAE Handbook — Fundamentals, ch. 1 |
| specific humidity | mass of water vapour per mass of dry air | engineering textbooks (Çengel: "absolute or specific humidity") | `MassRatioOfWaterVapourToDryGas` | g/kg | Çengel and Boles |

The two meanings of "absolute humidity" differ in dimension (L⁻³M
versus dimensionless), so mixing them is not a small numerical error.
British Standard BS 1339-1:2002 deprecates the term in favour of
"volumetric humidity". No source was found defining absolute humidity
per volume of *dry* air.

Symbols collide as well as terms. ITU-R P.453-14 writes h for an
altitude in its equation 11 (the reference profile, N_0 being
extrapolated to sea level) and for a height above ground in its equation
17 (figure 12). nomogram keeps the identifiers apart (z, z_s, h, with
distinct kinds) and gives each source its own symbols in the notation of
its citation.

Over sea water, "about 98 %" is said of three close quantities: the
vapour pressure of sea water relative to pure water at the same
temperature (`RelativeVapourPressureOfSeaWater`), the activity of water
in sea water, which equals the relative fugacity of sea air (TEOS-10
Manual, eq. 3.40.11), and the relative humidity of air in equilibrium
with sea water. They are not the same quantity. The 0.98 of flux
algorithms is applied to the saturation specific humidity (IFS, Beljaars
1998, Fairall et al. 1996) or to the saturation vapour pressure (COARE
code); since q is not linear in e, the two differ slightly.

## QUDT findings

Found while reading QUDT 3.5.2; documented here, not worked around
silently.

1. `quantitykind:VaporPressure` is deprecated since QUDT 3.2.0 and
   replaced by `quantitykind:VapourPressure`. nomogram uses the latter.
2. `quantitykind:AbsoluteHumidity` (a specialization of `Density`)
   describes both meanings of the term in its description, and its
   `latexDefinition` is not consistent. nomogram uses
   `MassConcentrationOfWaterVapour` instead: defined by ISO 80000-5,
   matched to Wikidata, consistent with the CF name.
3. `quantitykind:MassConcentrationOfWaterVapour` has the symbol `v`
   but its `latexDefinition` writes `w = m/V`.
4. The description of `quantitykind:SpecificHumidity` (mass of water
   vapour per mass of moist air) says it is commonly written ω in
   psychrometrics; in psychrometrics ω or W denotes the mixing ratio,
   a different quantity.
5. `qudt:isDeltaQuantity` is a boolean of `qudt:Quantity`, not of
   `qudt:QuantityKind`, by design: whether a value is a difference
   belongs to the quantity in its context, and the unit stays the same
   ([QUDT wiki](https://github.com/qudt/qudt-public-repo/wiki/Support-for-measures-of-absolute-values-and-for-intervals-(differences))).
   QUDT also has a `TemperatureDifference` kind. In nomogram the context
   is the formula, so the point/difference typing sits on the kinds of
   its variables and on pint's units; a nomogram variable maps to a
   `qudt:Quantity`.
6. There is no kind for the saturation vapour pressure. nomogram
   defines one as a specialization of `VapourPressure`, the mechanism
   QUDT itself uses.
7. The `latexSymbol` of `ThermodynamicTemperature` is `\Theta`, the
   symbol of the *dimension*, not the usual quantity symbol T. One
   reason why nomogram keeps LaTeX symbols in notations rather than in
   the reference data.
8. Units are declared for general kinds (`qudt:unitForQuantityKind`):
   `unit:DEG_C` for `Temperature`, no unit for `VapourPressure`.
   nomogram makes a unit applicable to a kind when it is declared for
   that kind or one it specializes, then keeps offset units for
   interval-scale kinds only. Without that rule, QUDT would make the
   degree Celsius a unit of the thermodynamic temperature. The dew point
   is the exception: QUDT has one kind for it, where the air temperature
   has two, and CF gives it in K while empirical formulas give it in
   degC, so `DewPointTemperature` takes both (`offset_units="any"`).
9. `MassRatioOfWaterVapourToDryGas` specializes no kind, so the mass
   ratio units (g/kg) do not reach it; `RelativeHumidity` and
   `SpecificHumidity` have no unit 1, CF's canonical unit for both.
   nomogram adds these units and lists them as `added_units`.
10. `qudt:wikidataMatch` is a plain annotation, not a SKOS mapping
    property, so its precision is unknown: nomogram imports it as a
    close match. Its description announces IRIs of the form
    `https://www.wikidata.org/wiki/Q…`; the data uses
    `http://www.wikidata.org/entity/Q…`.
11. The symbol of `unit:UNITLESS` is `一`, a CJK ideograph, chosen
    deliberately ([qudt-public-repo#712](https://github.com/qudt/qudt-public-repo/issues/712),
    where `1` and `-` were proposed). The SI Brochure gives the unit one
    the symbol 1, "rarely explicitly written" (9th ed., 2.3.3 and 5.4.7).
    nomogram follows the SI: `1` in its data, an override declared in the
    extraction script (`SYMBOLS`), and no symbol in its displays.
12. The symbol of `unit:PPM` is `PPM`; the SI Brochure (5.4.7) and ITU-R
    P.453 write `ppm`, as UCUM does (`[ppm]`). nomogram displays `ppm`, an
    override declared with its reason in the extraction script
    (`SYMBOLS`).
13. `quantitykind:RefractiveIndex` and `quantitykind:DimensionlessRatio`
    specialize no kind: dimensionless kinds share no common parent in
    QUDT. nomogram uses `DimensionlessRatio` as the parent of the
    dimensionless kinds it defines.
14. The description of `quantitykind:Altitude` says that altitude or
    height "is defined based on the context in which it is used"; CF is
    precise (`altitude`: above the geoid; `height`: above the surface;
    also `surface_altitude`, `height_above_mean_sea_level`,
    `height_above_reference_ellipsoid`). nomogram follows CF. An altitude
    is on an interval scale (its zero is a reference surface) yet in
    metres: the extraction marks it so (`offset_units=False`), the
    reference surface rather than the unit setting the zero.
15. QUDT also has `quantitykind:ElevationRelativeToNAP`, an elevation
    relative to the Dutch datum: the reference surface is part of the
    meaning of the quantity.
16. QUDT has no kind for the salinity or the chlorinity of sea water;
    `quantitykind:MassFraction` has no per mille or g/kg unit (QUDT 3.5.2
    gives it FRACTION, PERCENT, UNITLESS and IU-PER-MilliGM), although CF writes
    salinities in 1e-3 and g kg-1 (nomogram adds them). `unit:PSU` has a
    conversion multiplier of 0, the value QUDT gives units without a
    multiplicative conversion (decibel, Beaufort...): Practical Salinity
    is a number defined by a conductivity ratio (Millero 1993, "What is
    PSU?"), and QUDT's own description calls the unit "formally incorrect
    and strongly discouraged". nomogram writes Practical Salinity without
    a unit, as CF (canonical unit 1) and TEOS-10 do, and the Knudsen and
    Cox salinities, mass ratios, in per mille.

CF table 95 names salinities by their scale: `sea_water_knudsen_salinity`,
`sea_water_cox_salinity`, `sea_water_practical_salinity`,
`sea_water_reference_salinity`, `sea_water_absolute_salinity` and
`sea_water_preformed_salinity`, with `sea_water_salinity` for the
unqualified quantity. nomogram keeps one kind, `SeaWaterSalinity`, and
puts these names on its conventional scales.

CF table 95 has no standard name for the saturation vapour pressure
either, and its `relative_humidity` entry has an empty description (it
does not say whether saturation is over water or over ice).

## Wikidata findings

Read on 14 October 2026.

- Wikidata has two items for absolute humidity in its meteorological
  sense: *absolute humidity* (Q1048298) and *mass concentration of
  water vapour* (Q76378808). QUDT links the second one only.
- Items for the formulations are thin: *Tetens equation* (Q28231917)
  carries one statement, *saturation vapor pressure* (Q2387102) has
  neither a defining formula (P2534) nor a QUDT identifier (P8393).
- *Arden Buck equation* (Q4787919) is described as a group of
  correlations: Buck 1981 and Buck 1996 are narrower than it, which is
  why links carry a relation.

## External links

A link from a nomogram object to an external vocabulary is an
`ExternalMatch`: target IRI, SKOS relation (exact, close, broad,
narrow) and the date it was last verified. A link belongs to the object
it identifies and is never copied elsewhere: a variable of a formula
has no Wikidata link of its own, it inherits the link of its quantity
kind (the model of Wikidata's P7235 *in defining formula* with its
qualifier P9758 *symbol represents*).

## Sources

- QUDT 3.5.2, <https://github.com/qudt/qudt-public-repo/releases> (CC BY 4.0).
- BIPM, *The International System of Units*, 9th edition, section 2.3.1,
  doi:10.59161/AUEZ1291.
- JCGM 200:2012, *International vocabulary of metrology* (VIM3),
  <https://jcgm.bipm.org/vim/en/>.
- pint, *Temperature conversion*,
  <https://pint.readthedocs.io/en/stable/user/nonmult.html>.
- SymPy, *Printing*, <https://docs.sympy.org/latest/modules/printing.html>.
- CF standard name table, version 95,
  <https://cfconventions.org/Data/cf-standard-names/95/build/cf-standard-name-table.html>.
- Rijgersberg, H., van Assem, M., Top, J. (2013). Ontology of units of
  Measure and related concepts. *Semantic Web* 4(1),
  doi:10.3233/SW-2012-0069.
- Stevens, S. S. (1946). On the theory of scales of measurement.
  *Science* 103(2684), 677–680, doi:10.1126/science.103.2684.677.
- American Meteorological Society, *Glossary of Meteorology*, "vapor
  density", <https://glossary.ametsoc.org/wiki/Absolute_humidity>.
- Çengel, Y. A., Boles, M. A. *Thermodynamics: An Engineering
  Approach*, chapter 14, "Gas–vapor mixtures and air-conditioning".
- ASHRAE, *Handbook — Fundamentals*, chapter 1, "Psychrometrics".
