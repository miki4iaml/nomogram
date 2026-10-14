# nomogram

**English** | [Français](README.fr.md)

[![CI](https://github.com/miki4iaml/nomogram/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/miki4iaml/nomogram/actions/workflows/ci.yml)
[![CodeQL](https://github.com/miki4iaml/nomogram/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/miki4iaml/nomogram/actions/workflows/github-code-scanning/codeql)
[![codecov](https://codecov.io/gh/miki4iaml/nomogram/graph/badge.svg?branch=develop)](https://codecov.io/gh/miki4iaml/nomogram)
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fmiki4iaml%2Fnomogram%2Fdevelop%2Fpyproject.toml)](pyproject.toml)
[![License](https://img.shields.io/github/license/miki4iaml/nomogram)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23373134.svg)](https://doi.org/10.5281/zenodo.23373134)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196)](https://www.conventionalcommits.org/en/v1.0.0/)

A repository of scientific formulas: alternative notations across
authors and conventions, parameter units (including empirical ones),
validity domains, LaTeX rendering and symbolic computation.

Pure Python, built on SymPy, numpy and pint; it works on an offline
workstation (no online engine).

> Early stage project (alpha).

## Installation

```
pip install nomogram          # core
pip install "nomogram[viz]"   # with plots (matplotlib)
```

## Installation from source

```
git clone https://github.com/miki4iaml/nomogram.git
cd nomogram
uv sync
```

Python 3.12 or later. Plots need the `viz` extra (matplotlib):
`uv sync --extra viz`.

## Example

Every saturation vapour pressure formulation of the catalog against the
IAPWS reference; curves stop where a formulation leaves its stated
validity domain ([script](docs/examples/saturation_vapour_pressure.py)):

```python
import numpy as np
from nomogram.catalog import catalog
from nomogram.comparison import compare
from nomogram.plot import plot_deviations  # extra viz
from nomogram.units import Q_

formulations = catalog().formulations_of("SaturationVapourPressureOverWater")
reference = catalog().formulations["iapws_sr1_86"]
temperatures = Q_(np.linspace(-60, 110, 341), "degC")

table = compare(formulations, reference, {"ThermodynamicTemperature": temperatures})
plot_deviations(table)
```

![Deviation of saturation vapour pressure formulations from IAPWS](https://raw.githubusercontent.com/miki4iaml/nomogram/v0.1.0/docs/images/saturation-vapour-pressure.png)

## Usage

The table holds the values and the relative deviations, by formulation;
values outside a formulation's validity domain are NaN unless asked
otherwise (`outside="ignore"`). Formulations also chain, for instance
the absolute humidity from any saturation vapour pressure formulation:

```python
from nomogram.comparison import compose

ha = compose(catalog().formulations["mass_concentration_ideal_gas"], {"e_s": reference})
ha.evaluate(RH=Q_(100, "percent"), T=Q_(20, "degC")).to("g/m^3")  # 17.29
```

Each formulation keeps its units, validity domain, temperature scale and
references. The vocabulary is mapped in [docs/rosetta.md](docs/rosetta.md);
[How nomogram earns trust](docs/approach.md) explains what is checked and
how.

## Contributing

References to integrate, information or corrections about catalog
entries, new formulas and code are all welcome: see the
[ways to contribute](.github/CONTRIBUTING.md#ways-to-contribute) and
the [catalog guide](docs/catalog.md).

## License

[BSD-3-Clause](LICENSE).
