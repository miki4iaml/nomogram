# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- The constant `pi` may be written in expressions (Planck's law, the
  Stefan-Boltzmann constant, the Coriolis parameter need it). It is
  rendered `\pi`, and `pi` is a reserved name that no identifier may take.

### Changed

- The data notice credits QUDT in the form its licensing guide suggests.

### Fixed

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

[Unreleased]: https://github.com/miki4iaml/nomogram/compare/v0.3.0...develop
[0.3.0]: https://github.com/miki4iaml/nomogram/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/miki4iaml/nomogram/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/miki4iaml/nomogram/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/miki4iaml/nomogram/releases/tag/v0.1.0
