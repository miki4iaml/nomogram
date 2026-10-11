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
