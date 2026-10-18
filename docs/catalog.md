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

## Sections

All sections are optional; a key may be defined in one file only.

| Section | Required fields | Optional fields |
|---|---|---|
| `[references.<key>]` | `authors`, `title`, `status` (`verified`, `to-confirm`) | `year`, `container`, `doi`, `url`, `note`, `matches` |
| `[formulations.<key>]` | `label`, `expression`, `fixed_units`, `output`, `inputs` | `coefficients`, `constants`, `domains`, `citations`, `note`, `matches` |
| `[constants.<key>]` | `identifier`, `value`, `unit`, `description`, `reference` | `matches` |
| `[kinds.<Name>]` | `label`, `specialization_of` (a QUDT kind) | `description`, `matches` |
| `[notations.<key>]` | `label`, `symbols` (identifier to LaTeX) | `reference` |
| `[trade_terms.<key>]` | `term`, `language`, `meanings` | `matches` |
| `[scales.<key>]` | `label`, `kinds` (quantity kinds it applies to) | `reference_scale`, `unit`, `differences` (`[reference value, reference value - value]` pairs), `reference` |

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
`HectoPA`, `GM-PER-M3`, `PERCENT`. A kind missing from QUDT can be
declared in `[kinds]` as a specialization of a QUDT kind. A missing
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

The tests load the whole catalog. To try a new entry before adding it,
load it together with the bundled files (it may use their kinds and
references):

```python
from importlib.resources import files
from pathlib import Path

from nomogram.catalog import load_catalog
from nomogram.units import Q_

bundled = [
    entry.read_text(encoding="utf-8")
    for entry in (files("nomogram") / "data" / "catalog").iterdir()
    if entry.name.endswith(".toml")
]
mine = Path("my_entry.toml").read_text(encoding="utf-8")
catalog = load_catalog([*bundled, mine])
catalog.formulations["my_key"].evaluate(t=Q_(20, "degC"))
```

Add a test against a **published value** (a table of the source, a
reference formulation), never against the formula itself.
