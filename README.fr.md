# nomogram

[English](README.md) | **Français**

[![CI](https://github.com/miki4iaml/nomogram/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/miki4iaml/nomogram/actions/workflows/ci.yml)
[![CodeQL](https://github.com/miki4iaml/nomogram/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/miki4iaml/nomogram/actions/workflows/github-code-scanning/codeql)
[![codecov](https://codecov.io/gh/miki4iaml/nomogram/graph/badge.svg?branch=develop)](https://codecov.io/gh/miki4iaml/nomogram)
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fmiki4iaml%2Fnomogram%2Fdevelop%2Fpyproject.toml)](pyproject.toml)
[![License](https://img.shields.io/github/license/miki4iaml/nomogram)](LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196)](https://www.conventionalcommits.org/en/v1.0.0/)

Référentiel de formules scientifiques : notations alternatives selon
les auteurs et les conventions, unités des paramètres (y compris
empiriques), domaines de validité, rendu LaTeX et calcul formel.

En Python pur, fondé sur SymPy, numpy et pint ; il fonctionne sur un
poste déconnecté (aucun moteur en ligne).

> Projet en phase d'initialisation, pas encore publié sur PyPI.

## Installation depuis les sources

```
git clone https://github.com/miki4iaml/nomogram.git
cd nomogram
uv sync
```

Python 3.12 ou plus récent.

## Utilisation

Comparer les formulations de la pression de vapeur saturante à la
référence IAPWS, puis l'humidité absolue qu'elles donnent :

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
table.relative_deviations["sonntag1990_magnus"]  # environ -0,28 % à 20 °C

ha = compose(c.formulations["mass_concentration_ideal_gas"], {"e_s": reference})
ha.evaluate(RH=Q_(100, "percent"), T=Q_(20, "degC")).to("g/m^3")  # 17,29
```

Chaque formulation garde ses unités, son domaine de validité et ses
références ; hors domaine, le résultat vaut NaN sauf demande contraire
(`outside="ignore"`). Le vocabulaire est mis en correspondance dans
[docs/rosetta.md](docs/rosetta.md) (en anglais).

## Contribuer

Voir le [guide de contribution](.github/CONTRIBUTING.fr.md)
(version anglaise de référence : [CONTRIBUTING.md](.github/CONTRIBUTING.md)).

## Licence

[BSD-3-Clause](LICENSE).
