# Contribuer à nomogram

[English](CONTRIBUTING.md) | **Français**

> Traduction de [CONTRIBUTING.md](CONTRIBUTING.md) ; en cas d'écart,
> la version anglaise fait foi.

Merci de votre intérêt. Ce guide décrit l'installation, les contrôles
et le circuit d'une contribution. Les règles de code et d'architecture
sont dans [AGENTS.md](../AGENTS.md), qui s'applique aux humains comme
aux agents de codage.

## Prérequis

- Python 3.12 ou plus récent.
- [uv](https://docs.astral.sh/uv/). Il est indispensable : les hooks
  ruff, mypy et pytest passent par `uv run --frozen`, pour utiliser
  exactement les versions figées dans `uv.lock` (une seule source de
  version, en local comme en CI). Sans uv, ces hooks échouent.
- Une clé de signature des commits (voir plus bas).

## Installation

```
uv sync
uv run pre-commit install
```

La seconde commande installe les hooks aux trois stades (pre-commit,
commit-msg, pre-push).

## Contrôles locaux

| Stade | Contrôles |
|---|---|
| pre-commit | hygiène des fichiers (espaces, fin de fichier, fins de ligne LF, BOM, YAML, TOML, conflits, gros fichiers), clé privée, refus de commit direct sur `main` et `develop`, `ruff check --fix` et `ruff format`, gitleaks, nbstripout, anonymisation |
| commit-msg | anonymisation du message, Conventional Commits, sujet sans accent |
| pre-push | mypy strict, pytest |

Dans VS Code, la tâche « Portes de qualité » enchaîne ruff check,
ruff format --check, mypy et pytest.

### Anonymisation

Le hook `scripts/check_anonymity.py` refuse les informations
nominatives ou internes, dans le contenu comme dans les chemins. Il
applique des motifs génériques, versionnés, et vos motifs personnels
(nom civil, domaine de messagerie, organisation…), lus dans un fichier
hors dépôt pour ne jamais être publiés :

- `~/.config/nomogram/motifs-interdits.txt` par défaut, ou le chemin
  donné par la variable d'environnement `NOMOGRAM_MOTIFS_INTERDITS` ;
- une expression régulière par ligne, en UTF-8, insensible à la casse ;
  lignes vides et commentaires `#` ignorés ;
- pas de normalisation Unicode : prévoir les variantes avec et sans
  accent, et échapper les points (`exemple\.fr`).

Sans ce fichier, le hook avertit et n'applique que les motifs
génériques. Le hook ne recopie jamais un motif dans ses messages.

## Circuit d'une contribution

1. Créer une branche depuis `develop` (branche par défaut), par
   exemple `feature/formules-humidite`.
2. Commits signés, au format Conventional Commits, sujet sans accent :
   `feat: ajout de la formule de Magnus`.
3. PR vers `develop`. Le titre de la PR suit le même format : il
   devient le message du commit à la fusion par squash.
4. La CI doit être verte. Contrôles exigés :
   - `qualite` : les hooks ci-dessus, sur tout le dépôt ;
   - `tests` : Ubuntu et Windows × Python 3.12 et 3.13 ;
   - `signatures` : chaque commit de la PR est signé et vérifié.
5. La branche doit être à jour avec `develop` avant fusion.

### Signer ses commits

Avec une clé SSH (la plus simple) :

```
git config gpg.format ssh
git config user.signingkey ~/.ssh/ma_cle.pub
git config commit.gpgsign true
```

Puis enregistrer la clé publique sur GitHub comme *Signing key*
(Settings → SSH and GPG keys). Le badge « Verified » doit apparaître
sur vos commits. Une clé GPG convient aussi.

## Agents de codage

Ce projet utilise des agents de codage ; toute contribution est relue
et signée par un contributeur humain. Aucune mention d'outil n'est
ajoutée aux commits ni aux PR : la signature humaine engage le
contributeur, quel que soit l'outil employé.

## Licence

En contribuant, vous acceptez que votre contribution soit publiée sous
la licence [BSD-3-Clause](../LICENSE) du projet.
