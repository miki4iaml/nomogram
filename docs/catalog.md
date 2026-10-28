# Writing a catalog entry

The formula catalog is hand-written TOML in
[`src/nomogram/data/catalog/`](../src/nomogram/data/catalog/). Every
file is read and **validated when the package loads it**: a typo, an
unknown unit or an undeclared identifier stops the load with a message
naming the faulty entry. This page describes the format; the vocabulary
is explained in [rosetta.md](rosetta.md).

You do not need to write TOML to contribute: a reference or a formula
can also be proposed through an issue (see the
[contributing guide](../.github/CONTRIBUTING.md#ways-to-contribute)).

## Principles

- **A formula is written once**, as an expression in restricted Python
  syntax: numbers, declared identifiers, `+ - * / **`, parentheses, the
  functions `exp`, `ln`, `log10`, `sqrt`, `sin` and `cos`, the constant
  `pi` (a reserved name, which no identifier may take), and a
  [piecewise definition](#piecewise-definitions). LaTeX, numeric
  functions and symbolic results all derive from it. An angle in the
  argument of `sin` or `cos` is in radians: a variable in degrees there
  is refused, since pint counts the degree as a pure number worth
  pi/180 (a latitude given in degrees is converted when evaluated).
- **Everything is traced to a source.** A reference is `verified` only
  when the detail was **read in the source itself**; anything else is
  `to-confirm`, with a note saying what remains to check. A formula
  quoted by a review is entered as quoted, and the review is cited too.
- **Disagreements are recorded, not smoothed over.** When secondary
  sources differ (a constant, a year, an attribution), say so in the
  note.
- **Validity domains are objective only**: physical, or stated by the
  author or the cited publication with their criterion. A domain suited
  to one application is the user's business.

## A complete example

```toml
[references.alduchov_eskridge1996]
authors = "Alduchov, O. A.; Eskridge, R. E."
year = 1996
title = "Improved Magnus form approximation of saturation vapor pressure"
container = "Journal of Applied Meteorology 35, 601-609"
url = "https://www.osti.gov/servlets/purl/548871"
status = "verified"                       # read in the source
note = "Read in the report version: Table II (formulas), Table III (errors)."

[formulations.alduchov_eskridge1996]
label = "Magnus form, Alduchov and Eskridge (1996) AEKR coefficients"
expression = "C * exp(A * t / (B + t))"
fixed_units = true                        # coefficients only hold in these units
output = { identifier = "e_s", kind = "SaturationVapourPressureOverWater", unit = "HectoPA", description = "Saturation vapour pressure over water" }
inputs = [
  { identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "Celsius temperature" },
]
coefficients = { A = 17.625, B = 243.04, C = 6.1094 }

[[formulations.alduchov_eskridge1996.citations]]   # a source that gives the formula
reference = "alduchov_eskridge1996"

[[formulations.alduchov_eskridge1996.citations.domains]]   # stated by that source
bounds = { t = [-40.0, 50.0] }
criterion = "Maximum relative error 0.384 % against GG46, WE76 and SO90 (Table III)."
```

## Families

Each file of the catalog is a **family**, declared by a `[catalog]`
header:

```toml
[catalog]
name = "moist-air"
label = "Humidity of moist air"
format = 2                       # version of the catalog format
requires = ["water-vapour"]      # families it depends on
keywords = ["humidity", "psychrometrics"]
```

Families are layered: a **core** without dependency (conventional
scales, notation conventions), **pure** families holding one domain
(`water-vapour`, `moist-air`, `atmosphere`, `radio`, `sea-water`), and **aggregates** holding no entry, only
`requires` (`humidity`). An entry belongs to the family of its file:
nothing is written in the entry itself. `catalog()` loads every family;
`catalog("water-vapour")` loads one family with the families it requires.

Checked when loading:

- requires name loaded families and form no cycle;
- an entry refers only to its own family and to the families it requires
  (references, quantity kinds, scales, notations, constants), and every
  required family is used: the message names the entry and proposes the
  exact list;
- the format is the current one.

`python -m nomogram.catalog describe FILE` prints the header a file
needs, its requires computed from its entries.

`keywords` (on a family or a formulation) are free words for discovery,
several per entry; unlike the family, they decide nothing.

**Personal catalogs** extend the bundled ones without touching the
repository: `catalog(extra=["mylab.toml"])`. A personal family has a
header like any other; its keys start with its name and a colon, quoted
in TOML (`[formulations."mylab:corrected_buck"]`), and the bundled
families it requires are loaded with it. It is checked like the bundled
ones.

## Sections

All sections are optional; a key may be defined in one file only.

| Section | Required fields | Optional fields |
|---|---|---|
| `[catalog]` (one per file) | `name`, `format` | `label`, `requires`, `matches`, `keywords` |
| `[references.<key>]` | `authors`, `title`, `status` (`verified`, `to-confirm`) | `year`, `container`, `doi`, `url`, `note`, `matches` |
| `[formulations.<key>]` | `label`, `expression`, `fixed_units`, `output`, `inputs` | `coefficients`, `constants`, `domains`, `citations`, `note`, `matches`, `keywords`, `nature`, `conditions`, `assumptions` |
| `[formulations.<key>]`, composed | `label`, `composition` (`outer`, `inner`, optional `bind`) | `output`, `citations`, `note`, `matches`, `keywords` |
| `[formulations.<key>]`, calling others | `label`, `expression`, `calls`, `fixed_units`, `output`, `inputs` | `coefficients`, `constants`, `domains`, `citations`, `note`, `matches`, `keywords`, `conditions` |
| `[constants.<key>]` | `identifier`, `value`, `unit`, `description`, `reference` | `nature`, `uncertainty`, `conditions`, `definition`, `constants`, `tolerance`, `note`, `matches` |
| `[kinds.<Name>]` | `label`, `specialization_of` (a QUDT kind, or a kind of the catalog in any family loaded) | `description`, `matches`, `scale_type` (`ratio`, `interval`), `cf_standard_names` (from the frozen CF subset, with a canonical unit of the kind's dimension) |
| `[notations.<key>]` | `label`, `symbols` (identifier to LaTeX) | `reference` |
| `[trade_terms.<key>]` | `term`, `language`, `meanings` | `matches` |
| `[scales.<key>]` | `label`, `kinds` (quantity kinds it applies to, and their specializations) | `reference_scale`, `unit`, `differences` (`[reference value, reference value - value]` pairs) or `conversion` (expression of `x`) with `base` and `bounds`, `convertible`, `reference`, `symbol` (short name, `"ITS-90"`), `subscript` (marks a quantity on the scale in axis labels, `"90"`), `cf_standard_names` (from the frozen CF subset), `note` |
| `[relations.<key>]` | `kind` (`equivalent`, `approximates`, `proportional`), `subject`, `object` | `citation` (required for `approximates`; without it, the relation is computed by nomogram), `accuracy`, `at`, `bounds`, `given`, `scale`, `note` |
| `[cross_checks.<key>]` | `implementation`, `version`, `checked` (date), `cases` (`formulation`, `inputs`, `value`) | `url`, `note`; per case `call`, `rtol` |

### Formulations

- **`output` and `inputs`** are variables: `identifier` (used in the
  expression), `kind` (a quantity kind), `unit` (a QUDT unit name) and
  `description`. The unit must apply to the kind.
- **`fixed_units`**: `true` when the coefficients only hold in the
  declared units (most empirical fits, such as the Magnus form). Inputs
  are then converted to the declared unit and scale before evaluation;
  coefficients are never converted. `false` for a quantity equation,
  whose dimensional homogeneity is checked at load.
- **`coefficients`**: a number, or a table
  `{ value, unit, unit_basis, note }` when the unit or a remark matters.
  See [units of coefficients](#units-of-coefficients).
- **`constants`**: keys of `[constants]` entries (physical constants with
  their source, such as the gas constant of water vapour).
- **`domains`**: physical domains only: `bounds` (closed intervals per
  input identifier, in the input's unit), and optionally `criterion` and
  `reference`. A domain stated by a source belongs to its citation.
- **`citations`**: the sources that give the formula; see
  [citations](#citations).
- **Conventional scale** (VIM 1.29, such as the temperature scales
  ITS-90 and IPTS-68): a scale stated by a source goes in its citation.
  An input may carry a scale nomogram infers: `scale` (`its90`,
  `ipts68`) with `scale_basis` `inferred-from-date` (the scale in force
  at publication; weak, scales took years to be applied) or
  `inferred-from-numbers` (evidence given in the note). The scale must
  apply to the input's kind.
- Every declared identifier must be used by the expression, and every
  identifier of the expression must be declared.

### Piecewise definitions

A formula given by pieces, one expression per interval of an input, is
written with `piecewise((expression, condition), ...)`:

```toml
expression = "piecewise((0, T <= T_ice), (((T - T_ice) / (T_0 - T_ice)) ** 2, T_ice < T < T_0), (1, T >= T_0))"
```

- **A piecewise definition cuts the range of one input into intervals.**
  Each condition is a comparison (`<`, `<=`, `>`, `>=`) or two chained in
  one direction, bounding the same input for every branch; the bounds are
  numbers, coefficients or constants. No `and`, `or` or `True`: where no
  condition holds, the formulation gives NaN. Loading refuses intervals
  that overlap, are empty, or bound two inputs.
- Conditions are kept as written (a last condition is not turned into
  "otherwise"), and are in the units and on the scale of the input, like
  the expression. Bounds take the unit of their input (T_ice in K when T
  is); in a quantity equation, a bound has a unit, so it is a coefficient
  with a declared unit or a constant, never a bare number, and every
  branch gives the same unit.
- The formula is rendered on one line, in a left brace
  (`\left\{0 \;\mathrm{if}\; T \leq T_{\mathrm{ice}},\; ...\right.`), the
  same string for LaTeX, Markdown and matplotlib's mathtext, which has no
  `cases` environment.
- In a composition, the conditions bound inputs of the composed
  formulation: a condition on a value an inner part computes is refused.
- **Inversion has a limit:** a piecewise definition is inverted branch by
  branch **only if each branch is strictly monotonic on its interval**
  (nomogram checks it on samples), has a closed form, and the images of
  the intervals do not overlap; the inverse is then piecewise too, its
  conditions being those images. A constant branch, such as the 0 and 1
  of a mixed-phase fraction, has no inverse. Otherwise the inverse is
  numerical (see
  [the approach](approach.md#6-derived-formulations-are-checked-both-ways)).

### Composed formulations

A formula is written once. When a source gives a formula built from
others, the entry says so instead of copying them: ITU-R P.453
equation 9 is its enhancement factor times the Buck (1996) equation.

```toml
[formulations.itu_r_p453_es_water]
label = "Saturation vapour pressure over water in moist air (ITU-R P.453)"
composition = { outer = "saturation_vapour_pressure_in_moist_air", inner = { EF = "itu_r_p453_ef_water", e_s = "buck1996" } }
output = { identifier = "e_ws", kind = "SaturationVapourPressureOverWaterInMoistAir", unit = "HectoPA", description = "Saturation vapour pressure over water in moist air" }

[[formulations.itu_r_p453_es_water.citations]]
reference = "itu_r_p453_14"
equation = "9"
notation = { C = "a", A = "b", B = "c", D = "d", e_ws = "e_s", p = "P" }

[[formulations.itu_r_p453_es_water.citations.domains]]
bounds = { t = [-40.0, 50.0] }
```

- **`composition`**: `outer` is the formulation evaluated last; `inner`
  gives, for some of its inputs, the formulation computing them. Each
  inner output must be of the input's kind or a specialization of it,
  in the same unit.
- **`bind`** (optional) renames inputs of inner formulations, for example
  `{ theta = "t" }`. A table under the identifier an inner formulation
  computes renames the inputs of that part only, so that one formulation
  may compute two inputs at different arguments, such as a potential
  temperature at two levels:
  `bind = { theta_1 = { T = "T_1", p = "p_1" }, theta_2 = { T = "T_2", p = "p_2" } }`.
  Inputs of the same identifier in several parts are one input: same
  kind and unit, and same scale, or the entry is refused.
- **Conventional scales**: an inner output feeds an input on the same
  scale. A part on no scale at all, such as an interpolation or a
  definition, feeds an input on any: its inputs of a kind the scale
  applies to take that scale, so that evaluation brings them onto it. An
  input on no scale, met with the same input on a scale in another part,
  takes that scale.
- The entry writes no `expression`, `fixed_units`, `inputs`,
  `coefficients`, `constants` nor `domains`: the inner expressions are
  substituted into the outer one, and the result is an ordinary
  formulation (LaTeX, inversion, units of coefficients, signature). It is
  fixed-units when a part is; a quantity equation then keeps its value
  in its output unit through a factor.
- Coefficients and constants are those of the parts; one identifier for
  two coefficients, or for two different constants, is refused. A part
  reached twice, directly and inside another part (the total molality of
  Dickson et al. 2007, in the exponent and in the osmotic coefficient),
  is one part: its coefficients count once.
- Units of coefficients are inferred on the composed expression, each
  inner part keeping the unit of its output: an intermediate quantity
  fixes the units of the coefficients around it.
- **Validity domains**: a composed formulation is never more permissive
  than the chain of its parts. At evaluation, the domains of each part
  apply to the values it receives, intermediate values included: a bound
  on the vapour pressure an inner part computes is a bound on that
  part's inputs, whatever its shape. One exception: a domain stated by a
  source of the composed formulation itself (ITU-R P.453 for its
  equation 9) replaces the domains the sources of the parts state, since
  that source speaks of the composed formula. Physical domains of the
  parts always apply. `python -m nomogram.catalog check` points out
  where such a stated domain goes beyond those stated for the parts:
  the disagreement is shown, never smoothed. Physical domains on inputs
  carried unchanged are also listed in `physical_domains`.
- **`output`** (optional) narrows the output to a specialization of the
  outer formulation's kind, in the same unit.
- A composition may use another one; a cycle is refused. Parts come from
  the family or the families it requires. A composition identical to a
  written formulation is refused, like any duplicate.
- The formulation's `derivation` records the method `"composition"`, the
  outer formulation and the parts; the legend of a single formula says
  what it is composed of.

### Formulations calling others

When a source evaluates one formula at several arguments, the entry calls
that formulation in its expression, as the source writes it. WMO-No. 8
equation 4.B.11 takes the saturation vapour pressure in moist air at the
dew point and at the air temperature:

```toml
[formulations.wmo_relative_humidity_from_dew_point]
label = "Relative humidity with respect to water, from the dew point, WMO Guide (CIMO)"
expression = "100 * e_w(p=p, t=t_d) / e_w(p=p, t=t)"
calls = { e_w = "wmo_es_water_moist_air" }
fixed_units = true
output = { identifier = "RH", kind = "RelativeHumidity", unit = "PERCENT", description = "Relative humidity with respect to water" }
inputs = [
  { identifier = "t_d", kind = "DewPointTemperature", unit = "DEG_C", description = "Dew point temperature" },
  { identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "Air temperature" },
  { identifier = "p", kind = "Pressure", unit = "HectoPA", description = "Pressure of moist air" },
]
```

- **`calls`** gives the formulations called, by the name the expression
  uses. That name is neither a function, `pi` nor `piecewise`, nor an
  identifier of the entry, and every formulation declared is called.
- **A call names its arguments** by the identifiers of the inputs of the
  formulation called, even when it has only one: `e_w(t=t_d)`. Every
  input is given once, and each argument is an input of the entry, not
  a number, an expression nor another call. A call stands anywhere in the
  expression but in a `piecewise` definition, where the domains of the
  formulation called would hold in every branch: such an entry is defined
  by branches.
- **An argument has the kind of the input it feeds, or a specialization
  of it**, in the same unit. A point at which a formula is evaluated is
  the exception: a dew or frost point, a wet- or ice-bulb temperature
  may feed a Celsius or a thermodynamic temperature, still in the same
  unit. A temperature difference never
  feeds a temperature.
- **An input takes the conventional scale of the inputs it feeds**. One
  that feeds inputs on two scales is refused, and so is one that states
  a scale other than that of the input it feeds.
- **A result on another scale than the reference** (a dew point on
  IPTS-68) makes the entry state that scale for its own output, in its
  citation, so that evaluation converts the result back.
- **`fixed_units`** is written by the entry; it is `true` as soon as a
  formulation called holds only in its declared units.
- **Identifiers stay free.** nomogram renames for the computation:
  - the coefficients of each formulation called take their name as
    written, qualified by the formulation that defines them
    (`A__sonntag1990_magnus`), however it is reached (through a
    composition, branches or another call), so that those of two
    formulations never meet, and two calls of one formulation share them;
  - a constant keeps its identifier when it is the same constant
    everywhere; one of the same identifier but another constant (the
    epsilon of another source) takes a name qualified by its key
    (`epsilon__epsilon_ashrae2017`).

  The display keeps the name as written, with its owner. `__` is kept
  for these names: the entry's own identifiers may not contain it.
- **Validity domains**: those of each formulation called apply to the
  values each call receives (t_d and t above, each against −45 to 60 °C).
  Those the entry states apply as well; they never replace them.
- **Nothing is removed.** A factor common to two calls (the enhancement
  factor above, the coefficient C of the Magnus form) may simplify away
  from the computation; the inputs written stay inputs (p above), and the
  coefficients stay listed.
- The expression shown is the one written, with its calls,
  `e_w(p, t_d)`; `Formulation.written_expression` holds it, with each call
  kept as an opaque function, and `sympy_expression` the developed one,
  for the computation. The `derivation` records the method `"calls"`,
  the first formulation called as its `source`, and each call with its
  formulation (two identical calls count once); the legend lists the
  calls.
- A formulation called may be composed, defined by branches, or call
  others itself; formulations calling each other, directly or not, are
  refused.
- A formulation calling others takes part in `uses` and `used_by`, its
  inputs in `search(input=...)` (a search for a dew point input finds
  it), and the coefficients it calls in `search(symbol=...)`, by the name
  they are written with.

### Definitions, identities and derived formulations

A formulation may be a definition, true by definition, or an identity,
an exact consequence of definitions, rather than a fit or a model. It
says so with `nature`, and is cited, as any formulation, to a text that
prints it:

```toml
[formulations.latent_heat_fusion_identity]
label = "Specific latent heat of fusion, as that of sublimation minus that of vaporization"
nature = "identity"
expression = "L_s - L_v"
fixed_units = false
conditions = "Both latent heats at the same temperature, the specific enthalpy of each phase depending on temperature only (Bechtold, equation 39)."
...
[[formulations.latent_heat_fusion_identity.citations]]
reference = "bechtold2015"
equation = "40"
```

- **`nature`**: `"definition"` or `"identity"`; absent for a formula a
  source fits or models. A definition or an identity has no empirical
  coefficient and no domain stated by a source. It is a quantity
  equation, or a numerical value equation when its source prints it so
  (the relative humidity of WMO-No. 8, 100 e'/e'_w in %).
- **`conditions`**: under which it holds, as stated (the same
  temperature); a written formulation or one calling others may have
  them, a composition or a formulation by branches does not. The legend
  shows them.
- **Derived by nomogram**: a composition, a formulation by branches or
  one calling others, without a citation of its own, is derived by
  nomogram from formulations that are cited. The latent heat of fusion of
  the IFS, which the IFS does not print, is the identity above composed
  with its latent heats of sublimation and vaporization:

  ```toml
  [formulations.ecmwf_ifs_latent_heat_fusion]
  label = "Specific latent heat of fusion, linear in temperature, from the latent heats of the ECMWF IFS"
  composition = { outer = "latent_heat_fusion_identity", inner = { L_s = "ecmwf_ifs_latent_heat_sublimation", L_v = "ecmwf_ifs_latent_heat_vaporization" } }
  ```

  Its provenance is its derivation, never a citation:
  `Formulation.derived` is true, the legend says that no source prints
  it, and the indicators count such formulations. Cite a printed source
  whenever one gives the formula; derive only when none does.
- `search(nature="identity")` finds the identities,
  `search(provenance="derived")` the formulations derived by nomogram,
  `search(provenance="cited")` those a source gives.

### Assumptions

A formula holds under assumptions its source does not always state: an
ideal gas, constant specific heats, the saturation vapour pressure of
pure water rather than of moist air, a former Kelvin temperature. They
are written, never turned into a validity domain without a criterion:

```toml
[formulations.mass_concentration_ideal_gas]
...
assumptions = [
  { text = "Water vapour is an ideal gas: rho_v = e / (R_v T).", status = "deduced" },
]

[[formulations.ecmwf_ifs_latent_heat_vaporization.citations]]
reference = "ecmwf_ifs_cy49r1"
assumptions = ["The specific heat of liquid water is taken as constant, its value holding at the triple point (section 12.5, p. 246)."]
```

- An assumption the source states belongs to its citation, as a list of
  texts: its status is *stated*.
- Any other goes on the formulation, with its `status`:
  `"stated-by-other"` (stated about the formula by another source, whose
  `reference` is given), `"deduced"` (from the form of the formula, its
  coefficients or its kinds) or `"suspected"` (to be checked).
- `Formulation.assumptions` gives them all, stated first, then those of
  the parts and branches of a formulation built from others, which holds
  under them too, each once; the legend lists them with their status;
  `search(assumption="ideal gas*")` finds the formulations that assume an
  ideal gas. The source an assumption refers to is linked to the
  formulation (`uses`, `used_by`) and found by `search(source=...)`.

### Formulations by branches

When the pieces of a [piecewise definition](#piecewise-definitions) are
formulations that make sense alone, with their own sources, validity
domains and accuracy, the formulation refers to them instead of copying
their expressions:

```toml
[formulations.psychrolib_saturation_pressure]
label = "Saturation pressure of water vapour over ice, then over water"
branches = [
  { formulation = "hyland_wexler1983_ice", where = "T <= 273.16" },
  { formulation = "hyland_wexler1983", where = "T > 273.16" },
]
output = { identifier = "p_ws", kind = "VapourPressure", unit = "PA", description = "Saturation pressure" }
```

- **`branches`**: at least two `{ formulation, where }` tables; `where` is
  the condition of a piecewise definition, an interval of one input, the
  same for every branch. The expression is the piecewise definition the
  branches make, written by the catalog; `expression`, `inputs`,
  `coefficients`, `constants`, `domains` and `fixed_units` come from the
  branches and are not written.
- **`output`** is required: its kind is that of every branch or one they
  specialize (over ice, over water: a vapour pressure), in their unit.
  Branches give values on one scale, and are all numerical value
  equations or all quantity equations.
- Inputs are shared by identifier, alike in kind, unit and scale.
  Coefficients and constants are gathered; one formulation may serve two
  branches, but two formulations may not give a coefficient the same name.
- **Validity domains**: those of each branch apply where its condition
  holds. A domain stated by a source of the formulation replaces those
  the sources of the branches state, as for a composition; physical
  domains of the branches always apply.
- The formulation's `derivation` records the method `"branches"` and the
  formulation used under each condition; the legend of a single formula
  lists them. `uses` and `used_by` link the formulation and its branches.

### Citations

A formula is written once; each source that gives it is a citation, a
table of `[[formulations.<key>.citations]]`, with what that source
states:

- `reference` (required): key of a `[references]` entry;
- `equation`: the equation number in the source, as printed;
- `notation`: the symbols the source uses, coefficients included, as a
  table identifier to LaTeX (`{ C = "a", A = "b" }`), or the key of a
  `[notations]` convention (`"wmo"`);
- `units`: units the source states for coefficients
  (`{ T_c = "K", p_c = "PA" }`);
- `scales`: conventional scales the source states for inputs
  (`{ T = "its90" }`);
- `accuracy`: the accuracy the source claims, as stated;
- `assumptions`: the assumptions the source states for the formula,
  as a list of texts (see [assumptions](#assumptions));
- `note`;
- `domains`: validity domains the source states, as
  `[[formulations.<key>.citations.domains]]` tables with `bounds` and
  `criterion`.

A source cited for a domain or a unit must be one of the citations: the
link is never implicit. **By default, domains of different citations
combine by union** (a value is inside if one source says so); the
domains of one citation apply together, and physical domains always
apply.

### Conventional scales

A conventional reference scale (VIM 1.29) is a quantity-value scale
defined by formal agreement; the international temperature scales are
the first examples. Each applies to quantity kinds (`kinds`) and to
their specializations, never to a difference; each kind has one
reference scale, specializations included, on which inputs are taken and
results given (`its90` for temperatures). Another scale of the same kinds names its
reference (`reference_scale`) and gives the conversion as a table of
`[reference value, reference value - value]` pairs, in a declared
`unit`, values increasing:

```toml
[scales.ipts68]
label = "International Practical Temperature Scale of 1968 (IPTS-68)"
kinds = ["ThermodynamicTemperature", "CelsiusTemperature", "DewPointTemperature"]
reference_scale = "its90"
unit = "DEG_C"
differences = [[-190.0, 0.008], [-180.0, 0.008]]   # extract of Table 6 of the ITS-90 text
```

A conversion may instead be an expression of `x`, the value on the
scale, giving the value on its `base` (the reference scale by default),
both in `unit`; `bounds` give the values where it holds (NaN beyond),
and a chain holds where each of its steps does. Chains end on the
reference scale, and each relation is written once:

```toml
[scales.pss78]
label = "Practical Salinity Scale 1978 (PSS-78)"
kinds = ["SeaWaterSalinity"]
reference_scale = "reference_salinity2008"
unit = "UNITLESS"                       # S_P is a number: S_P = 35
conversion = "35.16504 / 35 * x / 1000" # TEOS-10 eq. 2.4.1, S_R in 1
bounds = [2.0, 42.0]                    # the limits of PSS-78
cf_standard_names = [{ name = "sea_water_practical_salinity", relation = "close", verified = 2026-10-26 }]

[scales.cox1967]
label = "Cox salinity (JPOTS 1966, S = 1.80655 Cl)"
kinds = ["SeaWaterSalinity"]
reference_scale = "reference_salinity2008"
unit = "PERMILLE"
conversion = "35.16504 / 35 * x"       # TEOS-10 A.4, no bounds

[scales.knudsen1901]
label = "Knudsen salinity (Knudsen 1901, S = 0.030 + 1.805 Cl)"
kinds = ["SeaWaterSalinity"]
reference_scale = "reference_salinity2008"
base = "cox1967"                        # Knudsen, then Cox, then S_R
unit = "PERMILLE"
conversion = "(x - 0.03) * 1.80655 / 1.805"
note = "Derived; sources disagree (TEOS-10 A.4, Lewis and Perkin 1981)."
```

- The inverse comes from SymPy when it is unique, and otherwise by
  fixed-point iteration (conversions are close to the identity).
- A scale whose conversion needs data nomogram does not hold declares
  `convertible = false` (Absolute Salinity: its anomaly depends on the
  location); a formulation on it is evaluated with `scale="ignore"`,
  values as given, and refuses a conversion otherwise.
- Several conversions may join the same two scales: IPTS-68 by the table
  of the ITS-90 text (`ipts68`) or by the linear relation of Saunders
  (1990) that oceanographic algorithms take (`ipts68_saunders1990`).
- `symbol` and `subscript` name the scale in axis labels; CF standard
  names (`cf_standard_names`, checked against the frozen CF subset, where
  the extraction script lists them in `SCALE_CF_NAMES`) and the `note`
  (disagreements between sources) are searchable.
- A composition checks that an inner output and the outer input share
  their scale, and a composed formulation keeps the scale of the outer
  output; an inverse takes its input on the scale of the source's
  output.
- A citation may state the scale of the output too
  (`scales = { S = "knudsen1901" }`): the result is converted back to the
  reference scale. A scale declared on the output of an entry defined by
  branches is the one its branches give.
- A scale of numbers (unit `UNITLESS`, Practical Salinity) takes inputs
  without unit: S_P = 35 is no ratio, and 35 per mille would read it a
  thousand times too large.

### Quantity kinds and units

Kinds and units come from the bundled QUDT subset (see
[rosetta.md](rosetta.md)): kinds such as `ThermodynamicTemperature`,
`CelsiusTemperature`, `RelativeHumidity`, `VapourPressure`,
`MassConcentrationOfWaterVapour`; units such as `K`, `DEG_C`, `PA`,
`HectoPA`, `GM-PER-M3`, `PERCENT`, and for radio refractivity
`RefractiveIndex`, `DimensionlessRatio` (units `UNITLESS`, `PERCENT`,
`PPM`), `Height` (above the surface) and `Altitude` (above the geoid),
both in `M` or `KiloM`. An altitude and a height never feed each other:
a height above the surface is h = z - z_s (`height_above_surface`), with
the altitude z_s of the surface given by the user (a terrain model is
outside nomogram). The vertical coordinates (geopotential height,
pressure altitude, ellipsoidal height...) and their kinds are described
in [vertical.md](vertical.md). A kind missing from QUDT can be
declared in `[kinds]` as a specialization of a QUDT kind; it takes the
scale type of its parent unless `scale_type` says otherwise (a quantity
with a conventional origin is on an interval scale even under a
ratio-scale parent; it is then never a difference). Its CF standard
names, when CF has an equivalent, come from the frozen CF subset, where
the extraction script keeps them (`LOCAL_KIND_CF_NAMES`); a search by a
CF name finds the kind and the formulations that compute it, and
`input=` those that take it as input.

CF standard names are links to an external vocabulary, like Wikidata
items: each carries its SKOS relation and the date it was checked, and
becomes an `ExternalMatch` whose target is the name in the NERC
Vocabulary Server (`nomogram.semantics.CF_NAMESPACE`, which publishes the
CF table as SKOS concepts). `QuantityKind.cf_standard_names` and
`ConventionalScale.cf_standard_names` give the names alone.

```toml
cf_standard_names = [{ name = "virtual_temperature", relation = "exact", verified = 2026-10-26 }]
```

- `relation` is `exact`, `close`, `broad` or `narrow`, read from the
  catalog's object to the CF name: `air_temperature` is *narrow* for the
  thermodynamic temperature (the temperature of air only), a CF salinity
  name is *close* for a salinity scale (it names the quantity on the
  scale).
- A bare name, as format 2 writes it (`cf_standard_names =
  ["virtual_temperature"]`), is read as an exact match, checked on the
  date the frozen CF subset was extracted. A missing
QUDT kind or unit is added to the extraction script
(`scripts/extract_semantics.py`), which is a code contribution.

### Physical constants

A constant is one value from one source: two sources giving different
values make two entries (`epsilon_ashrae2017`, `epsilon_ecmwf_ifs`), and a
formulation lists the one it uses.

```toml
[constants.R_v_iapws95]
identifier = "R_v"
value = 461.51805
unit = "J-PER-KiloGM-K"
description = "Specific gas constant of water vapour"
reference = "iapws95"
nature = "conventional"
```

- `nature` says how the value is known; every constant of the bundled
  catalog states it:
  - `exact`: fixed by definition, without uncertainty, as the defining
    constants of the SI (SI Brochure, 2.2) and the constants derived from
    them alone (QUDT `exactConstant`, CODATA "exact");
  - `conventional`: attributed by agreement for a given purpose (VIM
    2.12), such as the standard acceleration of free fall, or a value a
    source adopts for its formulas;
  - `measured`: a measurement result (VIM 2.10), such as a CODATA value.
- `uncertainty` is the standard uncertainty the source gives, in the unit
  of the constant; an exact constant has none.
- `conditions` says what the value depends on, if anything (a latent
  heat at 0 degC).
- `value` is a number, or decimal text when trailing zeros are
  significant: `value = "287.0500"` keeps the digits the source prints,
  which a number loses whatever its notation (`287.0500` and
  `2.870500e2` are both read as 287.05).

A constant the source defines by a formula of other constants carries
that formula; the value used stays the one printed, and the catalog
checks that the two agree:

```toml
[constants.epsilon_ecmwf_ifs]
identifier = "epsilon"
value = 0.621981
unit = "UNITLESS"
description = "Ratio of the molar masses of water and dry air, R_d / R_v of the ECMWF IFS"
reference = "ecmwf_ifs_cy49r1"
nature = "conventional"
definition = "R_d / R_v"
constants = ["R_d_ecmwf_ifs", "R_v_ecmwf_ifs"]
```

- `definition` uses the identifiers of the constants listed in
  `constants`, each one used, and gives the unit of the constant.
- The formula is evaluated exactly (pi exact) on the values the
  components print, and on their unrounded values (the definition of a
  component that has one), since a source may derive a constant from
  either: the ECMWF IFS derives R_d = R / M_d from the unrounded
  R = N k, then c_pd = 7/2 R_d from the printed R_d. The printed value
  agrees with one of the two results: within the uncertainty the source
  gives; as a truncation for an exact constant (less than one unit of its
  last digit below: CODATA's sigma); otherwise rounded to half a unit of
  its last digit. Write the value as text when its trailing zeros count.
- A source that departs from its own formula is entered as it prints:
  `tolerance` (in the unit of the constant) says how far, and `note`, which
  is then required, says by how much and why.
- Constants cannot define each other in a cycle; a constant using a
  constant of another family requires that family.

### External links

`matches` link an entry to an external vocabulary (Wikidata, ...):

```toml
matches = [
  { target = "http://www.wikidata.org/entity/Q2387102", relation = "broad", verified = 2026-10-14 },
]
```

`relation` is a SKOS relation (`exact`, `close`, `broad`, `narrow`) and
`verified` the date the link was last checked.


## Relations

A relation records what a **source states** between two formulations of
the same quantity kind, which nomogram verifies
(`nomogram.relations.verify`), or, without a citation, an equivalence or
a proportionality that nomogram computes and proves. A deviation
nomogram computes without a source is an observation
(`nomogram.comparison.compare`), not a relation.

```toml
[relations.ae96_aekr_gg46]
kind = "approximates"                 # or "equivalent", "proportional"
subject = "alduchov_eskridge1996"
object = "goff1957"
citation = "alduchov_eskridge1996"    # the source that states it
accuracy = 0.384                      # maximum relative deviation, in percent
at = { t = -30.0 }                    # where the source places the maximum
bounds = { t = [-40.0, 50.0] }        # every input of the subject
scale = "ignore"                      # formulas compared as given
note = "Table III, r_g."
```

- **`approximates`**: the deviation is checked on a grid of `bounds`,
  refined around its best points. Verdict: *reproduced* (equal at the
  precision published), *held* (smaller) or *exceeded* (larger), with
  the value and place found. A check on points, not a proof, reliable
  with one to three inputs and an estimate beyond: see
  [what a verdict on a stated relation guarantees](relation-verdicts.md).
- **`equivalent`**: proved with SymPy, coefficients as exact rationals,
  the object's inputs replaced as `given` says (`given = { P_d = "P - e" }`).
  Verdict: *proven*, *refuted* (with a numerical counterexample) or
  *unproven*.
- **`proportional`**: the subject equals the object times a constant
  factor. Proved on the ratio, simplified to a constant (*proven*), or
  sampled on `bounds`, which every input of the subject needs: *held*
  when moving a printed coefficient within its rounding takes its
  variation away, *refuted* otherwise. Outputs on an interval scale (°C)
  have no ratio: such a proportionality is refused. The verdict gives the factor, the coefficients it
  is the ratio of (a coefficient of the object brought into the output
  unit of the subject: 611.21 Pa is 6.1121 hPa), whether the two are
  equal to the printed precision,
  and whether a shift or a factor of a temperature or a salinity would
  explain it (a matter of scale; a factor of an input the object is
  proportional to cannot tell). An equivalence is a proportionality of
  factor 1 (`RelationKind.broader`).
- **Computed by nomogram**: an equivalence or a proportionality without
  a `citation` is one nomogram computes; its verdict proves it or holds
  it, and searching for "computed by nomogram" finds it. An approximation
  always cites its source.
- **Units**: the object is brought into the units of the subject by an
  exact factor (a result in Pa compared with one in hPa, an input in hPa
  fed by one in Pa). A conversion with an offset is stated in **`given`**,
  whose expressions are taken as written: `given = { t = "T - 273.16" }`
  feeds a Celsius temperature from a kelvin one, with 0 degC at 273.16 K
  as Murray writes it; a bare identifier in another unit is refused.
- A claim that cannot be checked as it stands is *unverified*, with the
  reason: an equivalence between formulations on different scales under
  `scale = "convert"`, an approximation evaluable at no point of its
  bounds.
- **`scale`**: `"convert"` (default) evaluates with conversion of
  conventional scales; `"ignore"` compares the formulas as given, as many
  sources did. An equivalence is proved on the expressions as written, so
  under `"convert"` it needs both formulations on the same scale.

Verification runs in the tests and on demand, not when the catalog is
loaded, which only checks the structure. A relation lives in the family
of its subject, which must require the families of its formulations and
of its citation.

## Cross-checks against other implementations

A cross-check records values of formulations computed once with another
implementation (software outside nomogram, never a dependency), with its
version and the date of the check. It is an observation, never a source:
it shows that two implementations of the same printed equation agree on
the points tried, not that the equation is right.

```toml
[cross_checks.itu_rpy_p453]
implementation = "ITU-Rpy"
version = "master commit f739993 (version string 0.4.0, unreleased)"
url = "https://github.com/inigodelportillo/ITU-Rpy"
checked = 2026-10-21
note = "Its wet term is called with a Celsius temperature (ITU-Rpy issue 115)."

[[cross_checks.itu_rpy_p453.cases]]
formulation = "itu_r_p453_refractivity_dry"
inputs = { P_d = 1000.0, T = 293.15 }     # in the units of its inputs
value = 264.71089885724035                # in the unit of its output
call = "dry_term_radio_refractivity(1000.0, 293.15)"
```

- **`inputs`**: a value for every input of the formulation, in its
  units; the formulation is evaluated as written (no scale conversion, no
  validity domain), as an implementation of the printed equation does.
- **`value`**: what the other implementation gives, written with all its
  digits (`repr`); **`call`** says how it was obtained, workarounds
  included.
- **`rtol`**: relative tolerance, 1e-12 by default; larger when the value
  went through a transformation (a refractivity from a refractive index,
  `(n - 1) * 1e6`, loses digits).
- The tests compute every case again (`nomogram.relations.replay`), so a
  change of a formulation cannot silently depart from what an
  independent implementation gave; `python -m nomogram.catalog verify`
  lists the cross-checks with the verdicts.

## Units of coefficients

Every coefficient has a unit, declared or inferred from the expression
(`nomogram.dimensions`). In `C * exp(A * t / (B + t))`, B takes the unit
of t, A is a pure number and C takes the unit of the result: none needs
declaring, and the legend shows them as inferred by nomogram.

- **Declare a unit only when the source states it, or when the
  expression does not determine it.** A unit the source gives (read in
  the source, as for any `verified` detail) goes in that source's
  citation: `units = { T_c = "K" }`. A unit you add while writing the
  entry is declared on the coefficient, with `unit_basis = "added"` and a
  `note` saying why. A unit the expression determines is not added:
  inference gives it.
- **An incomplete formulation is refused.** If the expression does not
  determine a unit (two coefficients tied only by their product, a
  pressure read inside a logarithm), the load stops and says which; add
  declarations until the inference succeeds.
- **An inconsistent formulation is refused.** A declared unit that
  contradicts the expression stops the load, with the part of the
  expression where the conflict appears. Adding declarations never fixes
  it: find the error (a unit, the transcription of the expression, or the
  source itself, in which case the disagreement is recorded in a note).

The legend of a single formulation shows each origin: unit from the
source, added by nomogram, or inferred by nomogram.

## Checking an entry locally

```
uv sync --all-extras
uv run pytest
```

The tests load the whole catalog. Before adding a file, two commands help:

```
uv run python -m nomogram.catalog describe my_family.toml   # the header it needs
uv run python -m nomogram.catalog check my_family.toml      # a report on its formulations
```

After adding or changing a relation, refresh the registry of verdicts
(see [what a verdict on a stated relation guarantees](relation-verdicts.md#recorded-verdicts)):

```
uv run python -m nomogram.catalog verify --record
```

To see how far the catalog covers the design goals (formulations with a
validity domain, inputs with their conventional scale, references
checked against the source, links to CF and Wikidata...):

```
uv run python -m nomogram.catalog stats
```

`check` loads the file with the bundled families (as a personal catalog
when it is not one of them), then reports, for each of its
formulations, those of the same form (coefficients aside) and the
maximum relative deviation **observed** against every formulation of the
same kind, on the domain where both are valid. Inputs are taken on the
reference scale of their kind, as in an evaluation: the domain an input
on a conventional scale is stated on is converted to the reference scale
first, leaving out the values that do not convert. These are observations:
only a relation with a citation states an approximation or an
equivalence. A pair that comes out numerically identical deserves a
look: an equivalence to state, or the same formulation written twice.

**A formulation already in the catalog is not entered again.** Two
writings of one formulation (same quantity kinds and units, same
expression once inputs are renamed, same coefficients as exact
decimals) are refused when loading, with the key of the existing one:
add a **citation** to it instead, with the source's notation, equation
number and statements.

To use a new entry in Python before adding it, load it with the bundled
families:

```python
from nomogram.catalog import catalog
from nomogram.units import Q_

mine = catalog(extra=["my_family.toml"])  # keys start with "my_family:"
mine.formulations["my_family:my_key"].evaluate(t=Q_(20, "degC"))
```

Add a test against a **published value** (a table of the source, a
reference formulation), never against the formula itself.
