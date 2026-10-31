<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/banner-dark.svg">
    <img alt="nomogram" src="docs/images/banner-light.svg" width="480">
  </picture>
</p>

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

**Formulas as data, not as code.**

nomogram does not hard-code functions: it catalogs formulas, each one

- **meaningful**: QUDT quantity kinds and units, links to CF and
  Wikidata, its source, its validity domain when stated;
- **checked**: dimensions and units on loading, equivalences proved
  symbolically, values cross-checked against references;
- **ready to use**: compute, compose, invert, plot, and compare with its
  alternatives.

Built for trust, not for speed: to show that a calculation is right, and
where it comes from.

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
IAPWS reference, from 0 to 60 °C and within 1 %; curves stop where a formulation leaves its
stated validity domain, and the figure takes the option set of nomogram's
documentation ([script](docs/examples/saturation_vapour_pressure.py)):

```python
import numpy as np
import nomogram as nomo
from nomogram.units import Q_

catalog = nomo.catalog.catalog()
formulations = catalog.formulations_of("SaturationVapourPressureOverWater")
reference = catalog.formulations["iapws_sr1_86"]
temperatures = Q_(np.linspace(-60, 110, 341), "degC")

table = nomo.comparison.compare(
    formulations, reference, {"ThermodynamicTemperature": temperatures}
)
with nomo.display.display_options(nomo.display.DisplayOptions.DOCUMENTATION):
    nomo.plot.plot_deviations(table, xlim=(0, 60), ylim=(-1.0, 1.0))  # extra viz
```

![Deviation of saturation vapour pressure formulations from IAPWS](docs/images/saturation-vapour-pressure.png)

## Usage

The table holds the values and the relative deviations, by formulation;
values outside a formulation's validity domain are NaN unless asked
otherwise (`outside="ignore"`). Formulations also chain, for instance
the absolute humidity from any saturation vapour pressure formulation:

```python
ha = nomo.comparison.compose(
    catalog.formulations["mass_concentration_ideal_gas"], {"e_s": reference}
)
ha.evaluate(RH=Q_(100, "percent"), T=Q_(20, "degC")).to("g/m^3")  # 17.29
```

`compare` gives each value to the inputs of its quantity kind. A
formulation with several inputs of one kind, such as a scheme
interpolating between two levels (the target pressure p and the
pressures p_1 and p_2 of the levels), compares once some of them are
fixed: `partial` fixes inputs as `functools.partial` fixes arguments,
here the two levels, and leaves a function of p alone, evaluated,
compared and plotted like any formulation
([Humidity between two levels](docs/vertical.md#humidity-between-two-levels)).
It also fixes what is known in advance, such as the levels of a sounding,
and names the curve in legends:

```python
levels = {"p_1": Q_(850, "hPa"), "p_2": Q_(500, "hPa"),
          "T_1": Q_(278, "K"), "T_2": Q_(252, "K")}
in_ln_p = nomo.comparison.partial(
    catalog.formulations["log_pressure_interpolation_temperature"],
    label="T linear in ln p", **levels,
)
in_ln_p.evaluate(p=Q_(700, "hPa")).to("K")  # 268.49
```

Formulations are found by words, wildcards and fields, whatever their
notation ([Finding formulations](docs/search.md)):

```python
catalog.search(variable="rho*")                    # ρ in every notation
catalog.search(kind="VapourPressure", source="buck*")
```

Each formulation keeps its units, validity domain, temperature scale and
references. The vocabulary is mapped in [docs/rosetta.md](docs/rosetta.md);
[How nomogram earns trust](docs/approach.md) explains what is checked and
how, and [Displaying formulas](docs/display.md) shows formulas in notebooks,
Markdown and plots. [Sea water](docs/sea-water.md) shows the salinity
scales and the vapour pressure of sea water, and what its 2 % lowering
changes at the sea surface. [The logo](docs/logo.md) is a working
nomogram.

## Contributing

References to integrate, information or corrections about catalog
entries, new formulas and code are all welcome: see the
[ways to contribute](.github/CONTRIBUTING.md#ways-to-contribute) and
the [catalog guide](docs/catalog.md).

## Data sources

nomogram's units come from QUDT, and so do its quantity kinds, except
those QUDT lacks, which nomogram defines as specializations of QUDT
kinds. nomogram links some kinds to CF standard names, which come, with
their canonical units, from the CF standard name table. The package
bundles a subset of each source:

- QUDT — Quantities, Units, Dimensions and Types, by QUDT.org
  (<https://qudt.org>), release 3.5.2, licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
- the [CF standard name table](https://cfconventions.org/Data/cf-standard-names/95/build/cf-standard-name-table.html),
  version 95, [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/);
- the UCUM codes of the units, as QUDT gives them: © Regenstrief
  Institute, Inc., [UCUM License](https://ucum.org/license).

What nomogram selects, changes and adds is listed in
[NOTICE.md](src/nomogram/data/NOTICE.md).

## License

Code: [BSD-3-Clause](LICENSE). Bundled data: see
[Data sources](#data-sources).
