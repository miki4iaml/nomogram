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
| temperature scale | none (no ITS-90 in QUDT 3.5.2) | International Temperature Scale (ITS-90), formerly IPTS-68, IPTS-48, ITS-27 | none | — | — | `nomogram.model.TemperatureScale`: the scale a formulation was fitted on, stated by the source or inferred from the scale in force at publication. Inputs are taken on ITS-90 and converted before evaluation (table of t90 − t68 from the ITS-90 text); a formulation fitted to formulas on several scales gets none. Neither QUDT nor pint models it, though it shifts saturation vapour pressure by up to 0.09 % between 0 and 100 °C. |
| scale type | `qudt:ScaleType`: `RatioScale`, `IntervalScale`, `OrdinalScale`, `NominalScale` | quantity-value scale (VIM 1.27); ordinal scale (VIM 1.28) | none | — | OM `Scale` | `nomogram.units.ScaleType` keeps only ratio and interval, the two the formulas need. The four types come from Stevens (1946). |
| point / difference | `qudt:isDeltaQuantity` (schema only, see findings) | — | `degC` versus `delta_degC` | — | OM `Point` versus `Measure` | A Celsius temperature is a point; the difference of two points is a difference, expressed in `delta_degC` or `K`. pint refuses to add two points. |
| identifier | none (`qudt:QuantityKind` IRIs identify kinds, not variables) | — | — | name of a `sympy.Symbol` | — | The semantic name of a variable in a formula (`t`, `RH`, `e_s`), stable across notations. |
| symbol | `qudt:symbol`, `qudt:latexSymbol`, `qudt:altSymbol` | quantity symbol (ISO 80000-1) | unit symbol only | `sympy.Symbol` is a *variable*, not a glyph | — | Ambiguous across vocabularies. In nomogram's prose, "symbol" means the glyph (QUDT sense); the SymPy object is always called "SymPy symbol". |
| notation | none (one `latexSymbol` per kind, plus `altSymbol`) | — | — | `symbol_names` of the LaTeX printer | — | A mapping from identifiers to LaTeX symbols, one per author or convention (WMO, ASHRAE...). QUDT has no concept of competing notations: nomogram adds it. |
| expression | `qudt:expression`, `qudt:latexDefinition`, `qudt:mathMLdefinition` | quantity equation (VIM 1.22) | — | `sympy.Expr` | — | Written once in restricted Python syntax; LaTeX and MathML are derived, never stored. |
| formulation | none | — | — | — | — | `nomogram.model.Formulation`: one author's way of computing a quantity kind (Magnus-Tetens, Sonntag 1990...). The alternative formulations of a kind are what nomogram compares; they are grouped by the kind they compute. |
| fixed units | none | numerical value equation (VIM 1.25), as opposed to a quantity equation (VIM 1.22) | — | — | — | `Formulation.fixed_units`: the coefficients only hold in the declared units. They are never converted; inputs are converted to the declared unit and scale first (a Fahrenheit point becomes a Celsius point), since with offset scales a formula's result depends on the scale it is written in. The VIM terms are not widely used, hence the plainer name. Quantity equations have their dimensional homogeneity checked when the catalog is loaded. |
| coefficient | none | — | — | — | — | Empirical parameter of one formulation (the A, B, C of the Magnus form). Not a physical constant: it has a source and a validity domain. |
| physical constant | `qudt:PhysicalConstant`, `qudt:ConstantValue` | — | pint constants (`R`, `k`...) | `sympy.physics.constants` (not used) | — | Constants with a metrological status (specific gas constant of water vapour). nomogram keeps their source (IAPWS-95, CODATA) because values differ between sources. |
| validity domain | none | — | — | assumptions (`real=True`, `positive=True`) only | — | `nomogram.model.ValidityDomain`. Objective domains only: *physical* (where the physics holds) or *stated* by the author or the cited publication, each with its criterion (maximum deviation or uncertainty against a reference) and its source. A domain suited to an application is the user's business. Behaviour outside is a parameter of `evaluate` (NaN by default). No vocabulary covers it; nomogram defines it. |
| reference | `qudt:Citation`; `qudt:informativeReference`, `qudt:isoNormativeReference` | — | — | — | — | `nomogram.model.Reference`: bibliographic source of a formulation, constant, domain or notation, with a verification status (`verified` or `to-confirm`). The DOI takes precedence over any other identifier. |
| comparison, composition | none | — | — | — | — | `nomogram.comparison`: `compare` gives the relative deviation of formulations of one kind from a reference; `compose` feeds formulations into another. Inputs are matched by quantity kind; the Celsius and thermodynamic temperatures express one state (t = T − 273.15 K) and match the same input, a temperature difference never does. |
| trade term | none | — | — | — | — | `nomogram.model.TradeTerm`: a term whose meaning depends on the trade (absolute humidity), recorded as a label pointing to unambiguous kinds, never as a kind. |
| CF standard name | none | — | — | — | CF standard name, with canonical units | The geoscience name of a variable in a data file (`air_temperature`). Linked to a QUDT kind; one kind may have several CF names. |
| external match | `qudt:wikidataMatch`, `qudt:siExactMatch`, `qudt:ucumCode`, `qudt:udunitsCode`; SKOS `exactMatch`, `closeMatch`, `broadMatch`, `narrowMatch` | BIPM SI Reference Point | — | — | — | `nomogram.semantics.ExternalMatch`: target, SKOS relation, date of last verification. See "External links". |
| unit definition | `qudt:Unit` with `conversionMultiplier`, `conversionOffset` | — | the pint expression it maps to | — | — | `nomogram.semantics.UnitDefinition`: the QUDT record of a unit. Named after Wikidata's description of P2968 ("unit of measure definition according to QUDT") to avoid a clash with `pint.Unit`. |

## Reference case: humidity of air

| Variable | QUDT kind | Wikidata | CF standard name | pint unit |
|---|---|---|---|---|
| thermodynamic temperature T | `ThermodynamicTemperature` | Q264647 | `air_temperature` | `K` |
| Celsius temperature t | `CelsiusTemperature` | Q74758530 | `air_temperature` (in `degC`) | `degC` |
| temperature difference | `TemperatureDifference` | — | — | `delta_degC`, `K` |
| relative humidity RH | `RelativeHumidity` | Q2499617 | `relative_humidity` | `percent`, `1` |
| vapour pressure e | `VapourPressure` | — | `water_vapor_partial_pressure_in_air` | `hPa` |
| saturation vapour pressure e_s | nomogram kind, specialization of `VapourPressure` | — | none | `hPa` |
| absolute humidity (mass concentration of water vapour) | `MassConcentrationOfWaterVapour` | Q76378808 | `mass_concentration_of_water_vapor_in_air` | `g/m³` |
| humidity mixing ratio | `MassRatioOfWaterVapourToDryGas` | Q17232415 | `humidity_mixing_ratio` | `g/kg` |
| specific humidity | `SpecificHumidity` | — | `specific_humidity` | `g/kg` |

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
5. `qudt:isDeltaQuantity` exists in the schema but is set on no kind,
   not even `TemperatureDifference`. The distinction between points and
   differences therefore comes from pint and OM, not from QUDT data.
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
   degree Celsius a unit of the thermodynamic temperature.
9. `MassRatioOfWaterVapourToDryGas` specializes no kind, so the mass
   ratio units (g/kg) do not reach it; `RelativeHumidity` and
   `SpecificHumidity` have no unit 1, CF's canonical unit for both.
   nomogram adds these units and lists them as `added_units`.
10. `qudt:wikidataMatch` is a plain annotation, not a SKOS mapping
    property, so its precision is unknown: nomogram imports it as a
    close match. Its description announces IRIs of the form
    `https://www.wikidata.org/wiki/Q…`; the data uses
    `http://www.wikidata.org/entity/Q…`.
11. The symbol of `unit:UNITLESS` is `一`, a CJK ideograph.

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
