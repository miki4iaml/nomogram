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
  syntax: numbers, declared identifiers, `+ - * / **`, parentheses and
  the functions `exp`, `ln`, `log10` and `sqrt`. LaTeX, numeric
  functions and symbolic results all derive from it.
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
(`water-vapour`, `moist-air`, `radio`), and **aggregates** holding no entry, only
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
| `[formulations.<key>]` | `label`, `expression`, `fixed_units`, `output`, `inputs` | `coefficients`, `constants`, `domains`, `citations`, `note`, `matches`, `keywords` |
| `[formulations.<key>]`, composed | `label`, `composition` (`outer`, `inner`, optional `bind`) | `output`, `citations`, `note`, `matches`, `keywords` |
| `[constants.<key>]` | `identifier`, `value`, `unit`, `description`, `reference` | `matches` |
| `[kinds.<Name>]` | `label`, `specialization_of` (a QUDT kind) | `description`, `matches`, `scale_type` (`ratio`, `interval`) |
| `[notations.<key>]` | `label`, `symbols` (identifier to LaTeX) | `reference` |
| `[trade_terms.<key>]` | `term`, `language`, `meanings` | `matches` |
| `[scales.<key>]` | `label`, `kinds` (quantity kinds it applies to) | `reference_scale`, `unit`, `differences` (`[reference value, reference value - value]` pairs), `reference` |
| `[relations.<key>]` | `kind` (`equivalent`, `approximates`), `subject`, `object`, `citation` | `accuracy`, `at`, `bounds`, `given`, `scale`, `note` |

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
  `{ theta = "t" }`. Inputs of the same identifier in several parts are
  one input: same kind, unit and scale, or the entry is refused.
- The entry writes no `expression`, `fixed_units`, `inputs`,
  `coefficients`, `constants` nor `domains`: the inner expressions are
  substituted into the outer one, and the result is an ordinary
  formulation (LaTeX, inversion, units of coefficients, signature). It is
  fixed-units when a part is; a quantity equation then keeps its value
  in its output unit through a factor.
- Coefficients and constants are those of the parts; one identifier for
  two coefficients, or for two different constants, is refused.
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
the first examples. Each applies to quantity kinds (`kinds`); each kind
has one reference scale, on which inputs are taken and results given
(`its90` for temperatures). Another scale of the same kinds names its
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
outside nomogram). A kind missing from QUDT can be
declared in `[kinds]` as a specialization of a QUDT kind; it takes the
scale type of its parent unless `scale_type` says otherwise (a quantity
with a conventional origin is on an interval scale even under a
ratio-scale parent; it is then never a difference). A missing
QUDT kind or unit is added to the extraction script
(`scripts/extract_semantics.py`), which is a code contribution.

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
the same quantity kind; nomogram verifies it
(`nomogram.relations.verify`), but never invents one. A deviation
nomogram computes without a source is an observation
(`nomogram.comparison.compare`), not a relation.

```toml
[relations.ae96_aekr_gg46]
kind = "approximates"                 # or "equivalent"
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
- **`scale`**: `"convert"` (default) evaluates with conversion of
  temperature scales; `"ignore"` compares the formulas as given, as many
  sources did.

Verification runs in the tests and on demand, not when the catalog is
loaded, which only checks the structure. A relation lives in the family
of its subject, which must require the families of its formulations and
of its citation.

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

`check` loads the file with the bundled families (as a personal catalog
when it is not one of them), then reports, for each of its
formulations, those of the same form (coefficients aside) and the
maximum relative deviation **observed** against every formulation of the
same kind, on the domain where both are valid. These are observations:
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
