# Finding formulations

A formula has many names: its author's, its symbols in each notation,
the name of its quantity in QUDT, CF or a trade, in several languages.
`Catalog.search` finds entries across those names, with wildcards.

```python
from nomogram.catalog import catalog

c = catalog()
c.search("buck*")                                   # every entry, any text
c.search("p453*", "water", section="formulations")
c.search(variable="rho*")                           # ρ in every notation
c.search(symbol="φ", notation="ashrae")             # φ as ASHRAE writes it
c.search(kind="VapourPressure")                     # saturation pressures included
c.search(source="itu_r_p453*", equation="9")
c.used_by("references.itu_r_p453_14")               # everything citing P.453
c.uses("formulations.itu_r_p453_es_water")          # its parts, kinds, source
```

## How a search matches

- A **term** is a shell-style wildcard pattern: `*` (any characters),
  `?` (one character), `[...]` (a set). It is matched against the
  **words** of an entry; every term must match a word.
- Words are compared **without case or accents**: `Équation` is
  `equation`.
- Identifiers are **split and kept whole**: `SaturationVapourPressureOverWater`
  gives *saturation*, *vapour*, *pressure*, *over*, *water*, and itself;
  `itu_r_p453_es_water` gives *itu*, *r*, *p453*, *es*, *water*, and
  itself; `P.453-14` gives *p.453-14*, *p*, *453*, *14*.
- **Symbols** are compared in a normal form: `\rho_{\mathrm{v}}`, `ρ_v`,
  `rho_v` and `rhô_v` are all `rho_v`. Greek letters go by their names
  (English, or French without accents: *rhô*, *khi*); LaTeX font
  commands and braces are dropped; `\varphi` also answers to *phi*.
  `ro` is not a name of ρ: write `rho`, `rhô`, `ρ` or `rh*`. A symbol
  with a space is found whole or by its parts: Dickson's
  `\Sigma m_{\mathrm{B}}` answers to `Σ m_B`, `Σm_B` and `m_B`.
- **Unit and scale symbols** are also kept whole, signs included: `°C`,
  `g/kg` or `%` finds its unit.
- There is no approximate matching: a misspelt word finds nothing, which
  a wildcard can usually fix (`hum*d*`).

## Fields

A field filter applies the same matching to one field. Several words in
a filter must all match within one value of the field: `input="relative
humidity"` needs one input that is a relative humidity, not two inputs
each matching a word.

| Field | Matches |
|---|---|
| `key` | the key of the entry |
| `kind` | the output kind of a formulation, or a quantity kind itself; with `specializations=True` (default), the kinds specializing it as well |
| `output` | the output variable of a formulation: identifier, symbols in every notation, kind (name, label, CF names), description |
| `input` | an input variable, likewise |
| `variable` | any variable, coefficient or constant of a formulation |
| `symbol` | a symbol, as written by a notation; `notation=` restricts the notations (default: all) |
| `notation` | the notation of the symbols (of those `symbol=` matches, if given): a notation of the catalog by its key (`wmo`, `ashrae`), `default` for the identifiers themselves, or the symbols a source uses in a citation, by the source's reference key (`dickson2007`); the full key of such a notation is `<formulation>:<reference>` |
| `source` | a cited reference (key and authors); `equation=` asks for its equation number in the same citation |
| `family` | the family of the entry |
| `keyword` | a keyword of a formulation or a family |

`section=` keeps the entries of one section (a pattern too):
`formulations`, `kinds`, `references`, `constants`, `notations`,
`trade_terms`, `scales`, `relations`, `cross_checks`, `families`, `units`.

## Selections

A search returns a `Selection`, in catalog order, which `&`, `|` and
`-` keep:

- search it again: `c.search(family="water-vapour").search("buck*")`;
- combine selections: `a & b` (in both), `a | b` (in either), `a - b`
  (in `a`, not in `b`);
- `selection.formulations` gives the formulations, for `compare` or a
  plot; `selection.refs` the references `section.key`;
- in a notebook, a selection displays itself as a table, with equations
  when it holds formulations only.

```python
# Formulations built on Buck (1996) that ITU-R P.453 gives
c.used_by("formulations.buck1996") & c.search(source="itu_r_p453*")

# Saturation vapour pressures not from Buck
c.search(output="SaturationVapourPressure*") - c.search(source="buck*")
```

## Links

`uses(entry)` gives the entries an entry refers to (kinds of its
variables, cited references, notations, constants, scales, the
formulations a composition, a relation or a cross-check uses, the
families a family requires); `used_by(entry)` the entries that refer to
it. The links are those the catalog checks for its families
(`Catalog.links`).

## What grows without changing searches

Names come to entries from several sources: identifiers, notations,
QUDT labels, CF standard names, Wikidata items of the links, Greek
letter names. New sources (labels in other languages, a thesaurus of
domains) add names to the same entries: searches keep their form and
find more.
