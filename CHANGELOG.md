# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

- Core dependencies: sympy, numpy and pint. The offline constraint now
  rules out online engines rather than dependencies.

### Removed

- The placeholder `nomogram.hello()`.
