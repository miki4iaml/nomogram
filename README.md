# nomogram

**English** | [Français](README.fr.md)

[![CI](https://github.com/miki4iaml/nomogram/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/miki4iaml/nomogram/actions/workflows/ci.yml)
[![CodeQL](https://github.com/miki4iaml/nomogram/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/miki4iaml/nomogram/actions/workflows/github-code-scanning/codeql)
[![codecov](https://codecov.io/gh/miki4iaml/nomogram/graph/badge.svg?branch=develop)](https://codecov.io/gh/miki4iaml/nomogram)
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fmiki4iaml%2Fnomogram%2Fdevelop%2Fpyproject.toml)](pyproject.toml)
[![License](https://img.shields.io/github/license/miki4iaml/nomogram)](LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196)](https://www.conventionalcommits.org/en/v1.0.0/)

A repository of scientific formulas: alternative notations across
authors and conventions, parameter units (including empirical ones),
validity domains, LaTeX rendering and symbolic computation.

Pure Python, built on SymPy, numpy and pint; it works on an offline
workstation (no online engine).

> Early stage project, not yet published on PyPI.

## Installation from source

```
git clone https://github.com/miki4iaml/nomogram.git
cd nomogram
uv sync
```

Python 3.12 or later.

## Usage

Compare the saturation vapour pressure formulations against the IAPWS
reference, then the absolute humidity they give:

```python
import numpy as np
from nomogram.catalog import catalog
from nomogram.comparison import compare, compose
from nomogram.units import Q_

c = catalog()
reference = c.formulations["iapws_sr1_86"]
saturation = c.formulations_of("SaturationVapourPressureOverWater")
grid = {"ThermodynamicTemperature": Q_(np.linspace(0.01, 40, 5), "degC")}

table = compare(saturation, reference, grid)
table.relative_deviations["sonntag1990_magnus"]  # about -0.28 % at 20 degC

ha = compose(c.formulations["mass_concentration_ideal_gas"], {"e_s": reference})
ha.evaluate(RH=Q_(100, "percent"), T=Q_(20, "degC")).to("g/m^3")  # 17.29
```

Each formulation keeps its units, validity domain and references; outside
its domain the result is NaN unless asked otherwise (`outside="ignore"`).
The vocabulary is mapped in [docs/rosetta.md](docs/rosetta.md).

## Contributing

See the [contributing guide](.github/CONTRIBUTING.md).

## License

[BSD-3-Clause](LICENSE).
