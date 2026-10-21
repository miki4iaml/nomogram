# nomogram

[English](README.md) | **Français**

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

Référentiel de formules scientifiques : notations alternatives selon
les auteurs et les conventions, unités des paramètres (y compris
empiriques), domaines de validité, rendu LaTeX et calcul formel.

En Python pur, fondé sur SymPy, numpy et pint ; il fonctionne sur un
poste déconnecté (aucun moteur en ligne).

> Projet à un stade précoce (alpha).

## Installation

```
pip install nomogram          # cœur
pip install "nomogram[viz]"   # avec les tracés (matplotlib)
```

## Installation depuis les sources

```
git clone https://github.com/miki4iaml/nomogram.git
cd nomogram
uv sync
```

Python 3.12 ou plus récent. Les tracés demandent l'extra `viz`
(matplotlib) : `uv sync --extra viz`.

## Exemple

Toutes les formulations de la pression de vapeur saturante du catalogue
comparées à la référence IAPWS ; les courbes s'arrêtent là où une
formulation sort de son domaine de validité déclaré
([script](docs/examples/saturation_vapour_pressure.py)) :

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

![Écart des formulations de la pression de vapeur saturante à IAPWS](https://raw.githubusercontent.com/miki4iaml/nomogram/v0.1.0/docs/images/saturation-vapour-pressure.png)

## Utilisation

La table contient les valeurs et les écarts relatifs, par formulation ;
hors du domaine de validité d'une formulation, les valeurs valent NaN
sauf demande contraire (`outside="ignore"`). Les formulations se
composent aussi, par exemple l'humidité absolue à partir de n'importe
quelle formulation de la pression de vapeur saturante :

```python
from nomogram.comparison import compose

ha = compose(catalog().formulations["mass_concentration_ideal_gas"], {"e_s": reference})
ha.evaluate(RH=Q_(100, "percent"), T=Q_(20, "degC")).to("g/m^3")  # 17,29
```

Les formulations se retrouvent par mots, jokers et champs, quelle que
soit leur notation ([Finding formulations](docs/search.md), en anglais) :

```python
catalog().search(variable="rho*")                    # ρ dans toutes les notations
catalog().search(kind="VapourPressure", source="buck*")
```

Chaque formulation garde ses unités, son domaine de validité, son
échelle de température et ses références. Le vocabulaire est mis en
correspondance dans [docs/rosetta.md](docs/rosetta.md) (en anglais) ; la
page [How nomogram earns trust](docs/approach.md) (en anglais) explique ce
qui est vérifié, et comment, et [Displaying formulas](docs/display.md) (en
anglais) montre l'affichage des formules dans un notebook, en Markdown et
sur un graphique. [Sea water](docs/sea-water.md) (en anglais) présente les
échelles de salinité et la pression de vapeur de l'eau de mer, et ce que
son abaissement de 2 % change à la surface de la mer.

## Contribuer

Références à intégrer, compléments ou corrections sur les entrées du
catalogue, nouvelles formules et code sont tous bienvenus : voir
[comment contribuer](.github/CONTRIBUTING.fr.md#comment-contribuer)
(version anglaise de référence : [CONTRIBUTING.md](.github/CONTRIBUTING.md))
et le [guide du catalogue](docs/catalog.md) (en anglais).

## Licence

[BSD-3-Clause](LICENSE).
