# AGENTS.md — nomogram

Rules shared by all contributors and their coding agents, whatever the
tool. The practical guide (setup, hooks, pull request workflow) is in
[.github/CONTRIBUTING.md](.github/CONTRIBUTING.md).

## Project

`nomogram` is a repository of scientific formulas. It references
formulas and manages their alternative notations (by author,
publication, domain convention), the units of their parameters —
including empirical ones —, their validity domains, their LaTeX
rendering and their use in symbolic computation.

Reference use case: list the alternative formulations of air humidity
HA = f(T, RH), compare them, plot them.

Structural constraint: the core must stay installable on an offline
workstation, with no heavy dependency.

## Architecture and invariants

- Pure Python core. `sympy` and `matplotlib` are extras (`[symbolic]`,
  `[plot]`), never imported when the package loads: lazy import inside
  the functions that need them, with an explicit message if the extra
  is missing.
- Reference data is immutable: frozen structures (`frozen=True`), no
  mutation after construction.
- No mutable global state. The package must be safe in concurrent
  contexts; parallelism is the caller's business.
- Caching (`functools.lru_cache`) for symbolic → numeric conversions,
  which are costly and deterministic.
- Explicit public API (`__all__`). Only the public API is covered by
  semantic versioning.

## Conventions

- Language: English for everything versioned (code, docstrings,
  documentation, commits, pull requests). French translations:
  `README.fr.md`, `.github/CONTRIBUTING.fr.md`, and later the
  documentation; the English version is authoritative.
- Branches: `main` (released versions), `develop` (default branch,
  integration), and work branches prefixed with their Conventional
  Commits type (`feature/`, `fix/`, `docs/`, `ci/`, `chore/`…). Never
  commit directly to `main` or `develop`: always a branch, then a pull
  request against `develop`.
- Merges into `develop` are squash merges only; the pull request title
  becomes the commit message.
- Commit messages and pull request titles: Conventional Commits
  v1.0.0, optional scope, ASCII-only subject.
- Commits signed and verified by GitHub, required on every pull
  request.
- Versions: `0.x` until a `1.0.0` whose scope is still to be defined.
  Version declared only in `pyproject.toml`, read through
  `importlib.metadata`. Git tags prefixed with `v`.
- `requires-python = ">=3.12"`. Development on 3.12.
- Documentation: Sphinx, NumPy-style docstrings. A strict build will
  be a blocking CI check.
- License BSD-3-Clause. Every source file starts with:
  ```
  # SPDX-FileCopyrightText: 2026 Miki
  # SPDX-License-Identifier: BSD-3-Clause
  ```

## Releasing

1. Pull request against `develop` (squash): version bump in
   `pyproject.toml` and `CITATION.cff`, `[Unreleased]` section of
   `CHANGELOG.md` turned into `[x.y.z] - date`, titled
   `chore: release x.y.z`.
2. Pull request `develop` → `main`, merged with a merge commit (the
   only exception to squash: `main` must hold the exact history of
   `develop`, otherwise both branches diverge at every release).
3. Signed tag `vx.y.z` on `main`, then a GitHub release, which will
   trigger the PyPI publication through OIDC trusted publishing.

## Security

No safety rule is bypassed, including during project bootstrap.

- GitHub Actions pinned by commit SHA, never by a moving tag; the
  repository enforces it. Dependabot keeps the pins up to date.
- Workflow permissions read-only by default; elevated only in the job
  that needs it.
- No secret in the repository, no stored token: PyPI publication
  through OIDC trusted publishing.
- Local checks (pre-commit hooks): formatting, lint, secrets and
  anonymity before each commit; typing and tests on push. CI replays
  the same checks.
- Nothing personal or internal in what is published: no legal name,
  no internal path, no work email address, no customer name.

## Working rules

- Propose a plan before any change touching more than two files.
- No new dependency without explicit approval.
- No public function without a test.
- Every user-visible change adds an entry under `[Unreleased]` in
  `CHANGELOG.md` (Keep a Changelog format).
- No new file at the repository root unless necessary.
- Portability: `pathlib`, explicit UTF-8 encoding on every file open,
  no hard-coded shell command, `importlib.resources` for embedded
  data.
- No tool attribution in commit messages or pull request descriptions
  (no Co-Authored-By, no "Generated with …"); the policy on coding
  agents is in CONTRIBUTING.
- Propose before executing anything hard to reverse or
  outward-facing.
- Verify before asserting: a version or a tool behavior can be
  checked.
- Challenge a false premise rather than answering beside the point.

## Settled decisions

- **CI matrix**: complete and blocking, Ubuntu and Windows × Python
  3.12 and 3.13. Portability and `requires-python >=3.12` are promises
  made to the package's users; a non-blocking cell ends up ignored and
  the promise stops being checked. This choice follows from the
  package profile — pure Python, light dependencies, diverse target
  audiences — which makes integration cheap and portability a real
  concern. Do not align this matrix with that of a heavier repository
  for the sake of uniformity: the package profile decides.
- **Contributor signatures**: a squash merge produces a commit signed
  by GitHub, which hides the commits of the pull request; the
  `signatures` CI job therefore requires each of them to be signed and
  verified.
- **`.vscode` partly versioned**: `settings.json`, `extensions.json`
  and `tasks.json` are shared (ruff and mypy from the environment,
  recommended and unwanted extensions, "Quality gates" task); the
  rest of the folder stays local. The interpreter is not set: the
  Python extension discovers `.venv` on its own. Do not reintroduce
  `python.defaultInterpreterPath` pointing to a folder: the Python
  extension resolves it for itself only, but passes it raw to the ruff
  and mypy extensions, which fail to launch it. An executable path
  would be OS-specific.
- **mypy at pre-push**: deliberate overlap with CI, so that failures
  happen locally rather than after the push. Keep an eye on push time.

## Commands

```
uv sync                                    # environment
uv run pytest                              # tests
uv run ruff check --fix && uv run ruff format
uv run mypy                                # strict typing
uv run --python 3.13 pytest                # reproduce CI
uv run --resolution lowest-direct pytest   # lower bounds
```
