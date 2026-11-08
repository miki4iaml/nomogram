# Security and compliance

An assessment file for those who approve the use of nomogram on a
laboratory network, in particular one without direct Internet access,
and for the users who prepare that request. State as of 8 November 2026.

| Item | Value |
|---|---|
| Component | nomogram, a Python library of scientific formulas |
| Published version assessed | 0.7.0 (8 November 2026), on PyPI |
| State of development | `develop` branch as of 8 November 2026 |
| Repository | <https://github.com/miki4iaml/nomogram> |
| Licence | BSD-3-Clause (code); CC BY 4.0 and CC0 1.0 (third-party data) |
| Persistent identifier | concept DOI 10.5281/zenodo.23373134 (Zenodo) |
| Vulnerability reporting | GitHub private reporting, see [SECURITY.md](../.github/SECURITY.md) |

## 1. Purpose and method

This document describes:
- how the component behaves at run time;
- how it is developed, checked and published;
- how licences and the rights of sources are respected;
- the regulatory landmarks that apply;
- the known limits, and what remains the user's responsibility;
- the outlook, mapped onto the DevSecOps cycle.

Every statement points to verifiable evidence, at one of four levels:
- **[public]**: anyone can check it, in the repository, on PyPI or in the
  continuous integration logs;
- **[administrator]**: a setting of the GitHub repository, visible to
  its administrator only and declared here by the maintainer;
- **[maintainer]**: a practice declared by the maintainer, with no
  public, verifiable trace to date;
- **[user]**: a check the user carries out.

The document describes a dated state. It is neither a certification,
nor an independent audit, nor legal advice.

**Citing this document**: by its path in the repository at a given
version (the file `docs/security-and-compliance.md` of the tag
`vX.Y.Z`), with the Zenodo DOI of that version. A citation thus points
to a fixed, verifiable text.

## 2. Summary

| Area | Finding |
|---|---|
| Run time | No network access, no subprocess, no telemetry, no file written unless explicitly asked. Works entirely offline. |
| Input data | Data is plain TOML and JSON, read by the standard library; no serialized Python objects. Formulas are read by a whitelist parser, also tested on random texts; `eval`, `sympify` and `parse_expr` are banned from the code by a blocking rule. |
| Dependencies | Three direct dependencies (numpy, pint, sympy), under permissive licences; matplotlib as an option. |
| Approach | DevSecOps principles applied from planning to publication on PyPI, with the security features GitHub offers public repositories (section 12). |
| Development | Protected branches, mandatory review, signed and verified commits, blocking automated checks, code analysis (CodeQL), secret detection. |
| Alerts | 59 Dependabot alerts, all fixed, none on a run-time dependency; 2 CodeQL alerts, in tests, fixed before merging; no secret detected (section 5.5). |
| Publication | Single build, attestations of provenance (SLSA Build Level 2) and of the software bill of materials (SBOM), publication without a stored token, after human approval. |
| Licences and sources | BSD-3-Clause code; third-party data attributed; every formulation is tied to its source, or declared derived by nomogram. |
| Regulation | No personal data processed; free software, not monetised; the right of rights holders to opt out respected. |
| Main limits | A single maintainer; version 0.x; no external audit. |

## 3. The component

nomogram is a Python library (version 3.12 or later) that catalogues
scientific formulas with their units, validity domains and sources, and
evaluates them.

**Run-time dependencies** (package installed without options) [public]:

| Dependency | Version as of 8 November 2026 | Licence |
|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause (and 0BSD, MIT, Zlib, CC0 components) |
| sympy | 1.14.0 | BSD |
| mpmath (required by sympy) | 1.3.0 | BSD |
| pint | 0.26.2 | BSD |
| flexcache, flexparser (required by pint) | 0.3, 0.4 | BSD |
| platformdirs (required by pint) | 4.12.2 | MIT |
| typing_extensions (required by pint) | 4.16.0 | PSF-2.0 |

The `viz` extra adds matplotlib and its own dependencies, for plots
only. `pyproject.toml` declares lowest versions, not pinned ones: see
section 7 for an installation with locked versions.

**Bundled data** [public]: the formula catalog (TOML files) and a frozen
extract of the QUDT 3.5.3 and CF 95 vocabularies
(`src/nomogram/data/semantics.json`), whose origin and licences are
described in [NOTICE.md](../src/nomogram/data/NOTICE.md).

## 4. Run-time behaviour

**Network, processes, files** [public, by reading the code in
`src/nomogram/`]:
- no network access: the package imports no network module; the
  constraint "works on an offline workstation" is one of the project
  rules ([AGENTS.md](../AGENTS.md));
- no subprocess, no system call;
- no telemetry, no data collection;
- no file written, except at the user's explicit request: saving a
  registry of verdicts (`nomogram.relations.record`), at the path given;
  nomogram writes no figure: a plot is a matplotlib figure, which the
  user saves; pint's unit registry is created without a disk cache.

**Data read** [public, by reading the code in `src/nomogram/`]:
- bundled data is plain text, read only, through `importlib.resources`:
  the formula catalog in eight TOML files, read by `tomllib`, and two
  JSON files, read by `json`, both modules of the standard library (the
  extract of QUDT and CF, `semantics.json`, generated by a script, and
  the registry of verdicts, `verifications.json`);
- a personal catalog is a TOML file, and only that: `tomllib` reads it,
  and it goes through the same validation as the bundled catalog; the
  formulas it holds are parsed, never executed (below);
- no serialized Python objects: no `pickle`, `marshal`, `shelve` or
  `joblib`, and no YAML.

**Processing of formulas** [public: `src/nomogram/expression.py`]:
- a formula is written in a restricted Python syntax, parsed by the
  standard `ast` module against a whitelist of operations and functions;
- `eval`, `sympy.sympify` and `sympy.parse_expr` are banned from the
  package and its tests by a rule of the ruff linter (TID251), blocking in
  continuous integration; any exception must be justified in the code and
  visible in review;
- the validated expression is then turned into a numeric function by
  `sympy.lambdify`, which generates and compiles Python code from the
  validated tree: no text supplied by the user is executed as such; its
  variables are renamed with a reserved prefix, so that none shadows a
  name of the generated code;
- limits bound the resources spent reading a formula: at most 2,000
  characters per expression, and at most 1,000 digits for a power or an
  exponential computed exactly;
- a personal catalog supplied by the user (the `extra` parameter of
  `nomogram.catalog.catalog`) goes through the same validated loading.

**Concurrency** [public]: no mutable global state; reference data is
immutable.

## 5. Secure development: practices and checks (DevSecOps approach)

### 5.1 Change management

- **Protected branches** [administrator]: on `develop` and `main`,
  deletion and history rewriting are forbidden; every change goes through
  a pull request, up to date with the target branch; squash merges into
  `develop`, merge commits into `main`.
- **Checks required before merging** [administrator, public results]:
  quality (all the automated checks of section 5.2, strict typing
  included), signatures, and tests on four configurations (Ubuntu and
  Windows, Python 3.12 and 3.13).
- **Code owners' review** [public: [CODEOWNERS](../.github/CODEOWNERS)]:
  changes to the workflows, the scripts, the configuration of the checks
  and the instruction files of coding agents need the maintainer's
  review.
- **Signed and verified commits** [administrator, visible on every
  commit]: required on the protected branches; a continuous integration
  check (`signatures`) also verifies each commit of a pull request, which
  a squash merge would hide.

### 5.2 Automated checks

Run on each contributor's workstation before every commit, then replayed
identically in continuous integration [public:
[.pre-commit-config.yaml](../.pre-commit-config.yaml),
[ci.yml](../.github/workflows/ci.yml)]:
- formatting, static analysis (ruff), strict typing (mypy);
- **secret detection** (gitleaks, private key detection);
- **security analysis of the GitHub Actions workflows** (zizmor);
- **integrity**: refusal of invisible or control characters, of
  unauthorized instruction files of coding agents and of files that must
  stay local ([check_integrity.py](../scripts/check_integrity.py));
- **confidentiality**: refusal of personal or internal data in files and
  messages ([check_anonymity.py](../scripts/check_anonymity.py)), and of
  metadata in images
  ([check_image_metadata.py](../scripts/check_image_metadata.py));
- format of commit messages (Conventional Commits).

**Tests** [public]: 2,803 tests as of 8 November 2026, run on the full,
blocking matrix; branch coverage measured (99 % as of 8 November
2026), with a floor of 80 % required in every configuration.

**Randomized tests of the expression parser** [public:
[test_expression_fuzz.py](../tests/test_expression_fuzz.py)]: random
formulas built from the whitelist, catalog expressions with random
edits, and fragments of Python outside the whitelist. Each text must be
parsed or refused with the parser's own error, never fail otherwise,
and be answered within two seconds; the generator is seeded, so that a
failure can be replayed. They are not coverage-guided fuzzing.

### 5.3 Platform security

- **GitHub Actions pinned by digest** (commit SHA), never by a moving
  tag [public: workflows; administrator: pinning enforced by the
  repository]; only actions from GitHub and verified creators are
  allowed [administrator].
- **Least privilege** [public: workflows; administrator]: read-only
  permissions by default, raised only in the job that needs them;
  workflows cannot approve pull requests.
- **No stored secret**: publication on PyPI and the upload of coverage
  reports (Codecov) authenticate with short-lived OIDC tokens [public:
  workflows].
- **Code analysis**: CodeQL (Python and GitHub Actions) [administrator,
  results in the Security tab].
- **Dependencies**: Dependabot alerts and security updates; grouped
  version updates, proposed no earlier than seven days after their
  release, so that a compromised release is more likely to be caught
  before adoption [public: [dependabot.yml](../.github/dependabot.yml)].
- **Secrets**: secret scanning and push protection [administrator].
- **Two-factor authentication**: GitHub requires it of every account
  that contributes code since March 2023, and PyPI of every account
  since 1 January 2024 [public: their documentation]; the maintainer's
  GitHub account uses an authenticator application [maintainer].
  Publication needs no PyPI password: it goes through Trusted Publishing
  (section 6).
- **Two-factor authentication**: GitHub requires it of every account
  that contributes code since March 2023, and PyPI of every account
  since 1 January 2024 [public: their documentation]; the maintainer's
  GitHub account uses an authenticator application [maintainer].
  Publication needs no PyPI password: it goes through Trusted Publishing
  (section 6).
- **Vulnerabilities**: private reporting enabled, policy published
  [public: [SECURITY.md](../.github/SECURITY.md)].

### 5.4 Coding agents

The project uses coding agents (artificial intelligence assistants).
Every contribution is reviewed and signed by a human, who is accountable
for it. The instruction files of these agents are treated as code:
maintainer's review, integrity check, and contributions from others read
as diffs, never run in an environment where an agent works [public:
[CONTRIBUTING.md](../.github/CONTRIBUTING.md#coding-agents)].

### 5.5 Alerts raised and handled

As of 8 November 2026 [administrator: Security tab; public: the pull
requests cited]:
- **Dependabot alerts**: 59, all fixed, none on a run-time dependency.
  41 concerned Pillow, which matplotlib brings with the `viz` extra; the
  lock file was updated the same day ([#66](https://github.com/miki4iaml/nomogram/pull/66)). 18 concerned virtualenv and
  filelock, which pre-commit brings with the development tools; a
  Dependabot pull request updated them ([#71](https://github.com/miki4iaml/nomogram/pull/71)).
- **Dependabot version updates**: four pull requests, merged ([#5](https://github.com/miki4iaml/nomogram/pull/5), [#71](https://github.com/miki4iaml/nomogram/pull/71),
  [#154](https://github.com/miki4iaml/nomogram/pull/154), [#176](https://github.com/miki4iaml/nomogram/pull/176)), read as diffs since 31 October (section 5.4); the last
  one showed that pytest 9.2 broke a test, fixed first ([#179](https://github.com/miki4iaml/nomogram/pull/179)).
- **CodeQL**: two alerts, both in tests, fixed before their pull request
  was merged: a test variable named like a secret ([#147](https://github.com/miki4iaml/nomogram/pull/147)), an imprecise
  filter of URLs ([#169](https://github.com/miki4iaml/nomogram/pull/169)).
- **Secret scanning**: no alert.

The maintainer keeps a log of the alerts and of how each was handled
[maintainer].

## 6. Publication and provenance

[public: [release.yml](../.github/workflows/release.yml), PyPI, GitHub]
- Version tags (`v*`) are protected against deletion and modification;
  GitHub releases are immutable [administrator].
- Publication is triggered by a version tag, signed by the maintainer.
  The workflow checks that the tag matches the declared version, builds
  the package **once**, checks it (`twine check --strict`) and publishes
  exactly the files built.
- It produces two **signed attestations** (Sigstore): the provenance of
  the build and a software bill of materials (SBOM) in CycloneDX format.
  According to GitHub's documentation, such a provenance attestation
  meets SLSA v1.0 Build Level 2.
- Publication on PyPI goes through **Trusted Publishing** (OIDC, no
  stored token), after **human approval** of the protected `pypi`
  environment, restricted to `v*` tags.
- PyPI shows the provenance attestation of each published file
  (PEP 740); for the wheel and the source archive of version 0.7.0, it
  names the repository `miki4iaml/nomogram`, the workflow `release.yml`
  and the environment `pypi`.
- Each published version is archived on Zenodo, with its own DOI.

**Verification** [user, on a connected workstation]:

```
gh attestation verify nomogram-0.7.0-py3-none-any.whl --repo miki4iaml/nomogram
```

## 7. Installation on a network without Internet access

A suggested procedure, to adapt to local rules [user]:
1. On a connected workstation, download nomogram and its dependencies
   for the target platform:

   ```
   python -m pip download nomogram==0.7.0 --dest packages --only-binary=:all:
   ```

   For a platform or Python version other than the workstation's, add
   `--platform` and `--python-version`.
2. Verify the attestation of nomogram (section 6) and record the SHA-256
   digests of the downloaded files.
3. Transfer the files according to the local procedure, after the
   required antivirus check.
4. On the target workstation, install without network access:

   ```
   python -m pip install --no-index --find-links packages nomogram==0.7.0
   ```

   To lock versions and digests, use a requirements file with hashes
   (`--require-hashes`).
5. nomogram then works entirely offline.

## 8. Licences, citations and rights of sources

- **Code**: BSD-3-Clause. Every source file carries its SPDX licence
  identifier [public].
- **Third-party data** [public: [NOTICE.md](../src/nomogram/data/NOTICE.md),
  `pyproject.toml`]: QUDT (CC BY 4.0, attribution and changes
  described), CF table (CC0 1.0), UCUM codes (notice of Regenstrief
  Institute). The licence expression of the package declares them all
  (`BSD-3-Clause AND CC-BY-4.0 AND CC0-1.0`), and the licence files are
  included in the package.
- **Traceability of formulas** [public: [catalog guide](catalog.md)]:
  every formulation is tied to its source (reference, equation, page),
  with a status: `verified` when the detail was read in the source
  itself, `to-confirm` otherwise, with a note saying what remains to
  check. A formulation nomogram derives itself says so, without a
  citation. Search finds the formulations of a source, or those nomogram
  derived (`search(provenance="derived")`).
- **Citing nomogram**: [CITATION.cff](../CITATION.cff) and the Zenodo DOI
  of each version [public].
- **Rights of source documents** [public: written in
  [CONTRIBUTING.md](../.github/CONTRIBUTING.md#rights-of-sources), binding
  on contributors]:
  - licensed standards (ISO, AFNOR) are never reproduced: only equations
    and constants are cited, never tables or excerpts;
  - no source document is redistributed, neither in the repository nor
    in the package [public, by the content of the repository and the
    package];
  - before a document is processed by a coding agent or another
    automated tool, it is checked for a clause forbidding text and data
    mining or processing by artificial intelligence; a document that
    carries one is not processed that way;
  - protections against robots and paywalls are never circumvented;
  - copyright notices are respected: a formula is cited, the document is
    not reproduced.
- **Personal data**: none collected; automated checks prevent the
  publication of personal or internal data in the repository
  (section 5.2).

## 9. Regulatory landmarks

These landmarks inform the assessment of the institution; they are not
legal advice.

- **Data protection (GDPR)**: nomogram collects, transmits and stores no
  personal data. It therefore carries out no processing within the
  meaning of Regulation (EU) 2016/679; the data a user submits to it
  remain under that user's responsibility.
- **Cyber Resilience Act** (Regulation (EU) 2024/2847): it covers
  products made available on the market, that is supplied in the course
  of a commercial activity (recital 18). Its Article 14 (reporting
  obligations) has applied since 11 September 2026, its other provisions
  apply from 11 December 2027 (Article 71(2)). According to the text:
  - the provision of free and open-source software that is not
    monetised by its manufacturer is not a commercial activity
    (recital 18);
  - the sole act of hosting it on an open repository or a package
    manager does not constitute making it available on the market
    (recital 20);
  - the status of open-source software steward is reserved for legal
    persons (Article 3, point 14).

  nomogram, supplied free of charge by a natural person, therefore falls
  outside these obligations on this reading. A manufacturer that
  integrates nomogram into a product it places on the market, however,
  exercises due diligence on that component (Article 13(5)) and reports
  its vulnerabilities to its maintainer (Article 13(6)). The software
  bill of materials, the attestations and the reporting policy
  ([SECURITY.md](../.github/SECURITY.md)) make that due diligence easier.
  nomogram also applies several practices the regulation expects of
  manufacturers: a vulnerability handling policy, a software bill of
  materials, security updates.
- **Text and data mining**: Directive (EU) 2019/790 (Article 4),
  transposed in France as Article L. 122-5-3 of the Intellectual
  Property Code (code de la propriété intellectuelle), allows rights
  holders to opt out of the mining of their works; under Article
  R. 122-28 of the same code, the opt-out needs no justification and may
  be expressed by any means. Checking documents for a prohibiting clause
  beforehand (section 8) respects that right to opt out.
- **Licences**: the BSD-3-Clause licence allows use, modification and
  redistribution, internal use included, provided the copyright notice
  and the licence are kept; the licences of the dependencies (section 3)
  are all permissive.

## 10. Known limits and open points

- **A single maintainer.** The continuity of the project and the time to
  fix rest on one person; acknowledging a report within seven days is a
  target, not a contractual commitment
  ([SECURITY.md](../.github/SECURITY.md)).
- **Version 0.x.** The public API is not stable yet; only the latest
  published version receives security fixes.
- **No independent audit** of security or code has been carried out.
- **No published standardized assessment** (OpenSSF Scorecard, OpenSSF
  Best Practices badge).
- **SLSA**: Build Level 3 would need an isolated build in a reusable
  workflow; it is not targeted to date.
- **Bit-for-bit reproducibility** of the build not verified.
- **SBOM**: attested on GitHub, it is not published on PyPI. PEP 770
  places it in the wheel (`.dist-info/sboms/`), which the build backend
  used, uv_build, does not offer to date.
- **Dependency versions**: the package declares lowest versions; locking
  versions and digests is the user's responsibility (section 7).
- **Verifying attestations** needs network access; it is therefore done
  on a connected workstation, before the transfer.
- **Generated code**: `sympy.lambdify` compiles Python code from the
  validated expressions. The residual risk is limited by the whitelist
  parser; loading only personal catalogs of known origin is recommended.
- **Randomized tests, not fuzzing**: the expression parser is tested on
  random texts (section 5.2), not by coverage-guided fuzzing.

## 11. Checklist

| # | Check | Status | Where to verify |
|---|---|---|---|
| 1 | Code licence compatible with the intended use | Done (BSD-3-Clause) | [LICENSE](../LICENSE) |
| 2 | Licences of data and dependencies identified | Done | [NOTICE.md](../src/nomogram/data/NOTICE.md), section 3 |
| 3 | No network access or telemetry at run time | Done | Source code, section 4 |
| 4 | No direct execution of supplied text (`eval`) | Done | ruff rule TID251, `pyproject.toml` |
| 5 | No personal data processed | Done | Sections 4 and 9 |
| 6 | Protected branches, review and signed commits | Done | Commit history, section 5.1 |
| 7 | Blocking automated checks and tests | Done | Continuous integration logs |
| 8 | Secret detection, code analysis | Done | `.pre-commit-config.yaml`, Security tab |
| 9 | Pinned actions, least privilege | Done | `.github/workflows/` |
| 10 | Attested publication (SLSA Build Level 2), without a stored token | Done | `release.yml`, PyPI, `gh attestation verify` |
| 11 | Vulnerability reporting policy | Done | [SECURITY.md](../.github/SECURITY.md) |
| 12 | Sources of formulas traced | Done | [Catalog guide](catalog.md), catalog |
| 13 | Rules on the rights of sources written and public | Done | [CONTRIBUTING.md](../.github/CONTRIBUTING.md#rights-of-sources), section 8 |
| 14 | Attestation verified before transfer | User's responsibility | Section 6 |
| 15 | Versions and digests locked at installation | User's responsibility | Section 7 |
| 16 | Personal catalogs of known origin | User's responsibility | Section 10 |
| 17 | Independent audit | To do | — |
| 18 | Published OpenSSF assessment | To do | — |
| 19 | Bit-for-bit reproducibility verified, SLSA Build Level 3 | To do | — |
| 20 | Continuity beyond a single maintainer | To do | — |
| 21 | Randomized testing (fuzzing) of the parser | Partly done: random texts, not coverage-guided | Section 5.2 |
| 22 | Software bill of materials published on PyPI | To do | Section 10 |
| 23 | Two-factor authentication on the accounts that publish | Done | Section 5.3 |

## 12. Outlook and DevSecOps principles

The DevSecOps approach builds security into every stage of the software
life cycle, automates it, and shares responsibility for it between those
who develop the software and those who operate it. nomogram applies it
to the stages it controls, from planning to publication on PyPI, its
only distribution channel to date. Deployment and operation take place
in the user's information system: the project contributes to them
through what it supplies (offline operation, attestations, software bill
of materials, installation procedure), without controlling them.

To that end, the project uses the security features GitHub offers public
repositories free of charge: protection rules for branches and tags,
CodeQL code analysis, secret scanning and push protection, Dependabot
alerts and updates, private vulnerability reporting, protected
environments, OIDC tokens, artifact attestations and immutable releases.

The project will keep following DevSecOps principles and good practices.
Any change to its chain will be described in this document, dated and
versioned with the code. This is the maintainer's intention, not a
contractual commitment.

The following table maps each item of the checklist (section 11) onto a
stage of the DevOps cycle, and onto the corresponding practices of the
NIST SSDF (SP 800-218, version 1.1). An item may belong to several
stages.

| Stage | What nomogram does | Items done | Items to do | User's responsibility | SSDF practices |
|---|---|---|---|---|---|
| Plan | Project rules, offline operation required, dependencies under permissive licences, rights of sources | 1, 2, 12, 13 | 20 | — | PO.1, PO.2, PW.4 |
| Code | Whitelist parser, code owners' review, signed commits, checks before commit | 3, 4, 5, 6, 8 | — | — | PS.1, PW.1, PW.5, PW.7 |
| Build | Pinned actions, least privilege, single build | 9 | 19 | — | PO.3, PO.5, PW.6 |
| Test | Blocking checks and tests on four configurations, randomized tests of the parser, CodeQL | 7, 8, 21 (partly) | 17, 21 | — | PO.4, PW.7, PW.8 |
| Release | Attestations, Trusted Publishing, two-factor authentication, human approval, immutable releases, Zenodo archive | 10, 23 | 22 | — | PS.2, PS.3 |
| Deploy | Offline installation procedure (section 7) | — | — | 14, 15 | PS.2, PW.4 (user side) |
| Operate | Offline operation, with no network, telemetry or personal data | 3, 5 | — | 16 | PW.9 |
| Monitor | Dependabot, CodeQL, private vulnerability reporting, alerts handled and logged (section 5.5) | 11 | 18 | — | RV.1, RV.2 |

Items 1, 12 and 13 (licences, traceability of formulas, rights of
sources) belong to legal compliance and scientific integrity; the SSDF
does not cover them.

**Outlook.** Integrating nomogram into an information system run along
DevOps lines (containers, orchestration, continuous deployment,
centralized secrets management) is up to the institution. The published
attestations and software bill of materials can feed the verification
of components when images are built there. The project publishes no
container image today.

## References

- Scientific Python, SPEC 8, *Securing the Release Process*:
  <https://scientific-python.org/specs/spec-0008/>.
- GitHub, *Using artifact attestations to establish provenance for
  builds* (SLSA v1.0 Build Level 2):
  <https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds>.
- PEP 740, *Index support for digital attestations*.
- PEP 770, *Improving measurability of Python packages with Software
  Bill-of-Materials*.
- GitHub, *Securing your account with two-factor authentication (2FA)*:
  <https://docs.github.com/en/authentication/securing-your-account-with-two-factor-authentication-2fa>.
- PyPI, *2FA Required for PyPI*, 1 January 2024:
  <https://blog.pypi.org/posts/2024-01-01-2fa-enforced/>.
- PEP 770, *Improving measurability of Python packages with Software
  Bill-of-Materials*.
- GitHub, *Securing your account with two-factor authentication (2FA)*:
  <https://docs.github.com/en/authentication/securing-your-account-with-two-factor-authentication-2fa>.
- PyPI, *2FA Required for PyPI*, 1 January 2024:
  <https://blog.pypi.org/posts/2024-01-01-2fa-enforced/>.
- NIST SP 800-218, *Secure Software Development Framework (SSDF)
  Version 1.1*, February 2022: <https://csrc.nist.gov/pubs/sp/800/218/final>.
- Regulation (EU) 2024/2847 (Cyber Resilience Act), OJ L of 20 November
  2024: <http://data.europa.eu/eli/reg/2024/2847/oj>; recitals 18 to 20,
  Articles 3, 13, 14, 24 and 71.
- European Commission, *Cyber Resilience Act — open source*:
  <https://digital-strategy.ec.europa.eu/en/policies/cra-open-source>.
- Regulation (EU) 2016/679 (GDPR); Directive (EU) 2019/790, Article 4;
  French Intellectual Property Code, Articles L. 122-5-3 and R. 122-28.
- Security policy of the project: [SECURITY.md](../.github/SECURITY.md).
- Project rules: [AGENTS.md](../AGENTS.md),
  [CONTRIBUTING.md](../.github/CONTRIBUTING.md), [catalog
  guide](catalog.md).
