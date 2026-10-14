# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Humidity mixing ratio r = epsilon e / (p - e) and specific humidity
  q = r / (1 + r) (ASHRAE 2017, through PsychroLib), with the constant
  epsilon = 0.621945 and its source; composed with any saturation vapour
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

[Unreleased]: https://github.com/miki4iaml/nomogram/compare/v0.1.1...develop
[0.1.1]: https://github.com/miki4iaml/nomogram/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/miki4iaml/nomogram/releases/tag/v0.1.0
