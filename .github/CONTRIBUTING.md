# Contributing to nomogram

**English** | [Français](CONTRIBUTING.fr.md)

Thank you for your interest. This guide covers setup, checks and the
path of a contribution. Coding and architecture rules live in
[AGENTS.md](../AGENTS.md), which applies to humans and coding agents
alike.

## Prerequisites

- Python 3.12 or later.
- [uv](https://docs.astral.sh/uv/). It is required: the ruff, mypy and
  pytest hooks run through `uv run --frozen`, so they use exactly the
  versions locked in `uv.lock` (a single source of versions, locally
  and in CI). Without uv, these hooks fail.
- A commit signing key (see below).

## Setup

```
uv sync
uv run pre-commit install
```

The second command installs the hooks at all three stages
(pre-commit, commit-msg, pre-push).

## Local checks

| Stage | Checks |
|---|---|
| pre-commit | file hygiene (whitespace, end of file, LF line endings, BOM, YAML, TOML, merge conflicts, large files), private keys, no direct commit to `main` or `develop`, `ruff check --fix` and `ruff format`, gitleaks, nbstripout, anonymity |
| commit-msg | anonymity of the message, Conventional Commits, ASCII-only subject |
| pre-push | strict mypy, pytest |

In VS Code, the "Quality gates" task runs ruff
check, ruff format --check, mypy and pytest in sequence.

### Anonymity

The `scripts/check_anonymity.py` hook rejects personal or internal
information, in file contents and in paths. It applies generic
patterns, versioned in the repository, and your personal patterns
(legal name, email domain, organization…), read from a file outside
the repository so they are never published:

- `~/.config/nomogram/deny-patterns.txt` by default, or the path
  given by the `NOMOGRAM_DENY_PATTERNS` environment variable;
- one regular expression per line, UTF-8, case-insensitive; blank
  lines and `#` comments are ignored;
- no Unicode normalization: list accented and unaccented variants,
  and escape dots (`example\.org`).

Without this file, the hook warns and applies the generic patterns
only. The hook never echoes a pattern in its messages.

## Contribution workflow

1. Create a branch from `develop` (the default branch), prefixed with
   its Conventional Commits type, for example `feature/humidity`.
2. Signed commits, Conventional Commits format, ASCII-only subject:
   `feat: add the Magnus formula`.
3. Open a pull request against `develop`. Its title follows the same
   format: it becomes the commit message on squash merge.
4. CI must be green. Required checks:
   - `quality`: the hooks above, on the whole repository;
   - `tests`: Ubuntu and Windows × Python 3.12 and 3.13;
   - `signatures`: every commit of the pull request is signed and
     verified.
5. The branch must be up to date with `develop` before merging.

### Signing commits

With an SSH key (the simplest option):

```
git config gpg.format ssh
git config user.signingkey ~/.ssh/my_key.pub
git config commit.gpgsign true
```

Then add the public key to GitHub as a *Signing key*
(Settings → SSH and GPG keys). Your commits should show the
"Verified" badge. A GPG key works too.

## Coding agents

This project uses coding agents; every contribution is reviewed and
signed by a human contributor. No tool attribution is added to commits
or pull requests: the human signature commits the contributor,
whatever the tool used.

## License

By contributing, you agree that your contribution is published under
the project's [BSD-3-Clause](../LICENSE) license.
