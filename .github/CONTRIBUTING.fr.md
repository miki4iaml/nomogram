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
| pre-commit | hygiène des fichiers (espaces, fin de fichier, fins de ligne LF, BOM, YAML, TOML, conflits, gros fichiers), clé privée, refus de commit direct sur `main` et `develop`, `ruff check --fix` et `ruff format`, codespell (orthographe), zizmor (audit de sécurité des workflows), gitleaks, nbstripout, anonymisation |
| commit-msg | anonymisation du message, Conventional Commits, sujet sans accent |
| pre-push | mypy strict, pytest |

Dans VS Code, la tâche « Quality gates » enchaîne ruff check,
ruff format --check, mypy et pytest.

### Anonymisation

Inutile d'être expert pour rester anonyme ici : une commande suffit à
la mise en place, et le hook vérifie ensuite chaque commit pour vous.

**Pourquoi.** Des informations personnelles fuient plus facilement
qu'on ne le croit dans un dépôt public : votre répertoire personnel
dans un chemin copié d'un terminal ou d'une sortie de notebook, le
domaine de messagerie de votre employeur, le nom de code d'un projet,
votre nom civil dans un commentaire ou dans les métadonnées d'un
fichier. Une fois poussées, elles restent dans l'historique.

**Fonctionnement.** Le hook `scripts/check_anonymity.py` refuse un
commit quand le contenu d'un fichier, son chemin ou le message de
commit correspond à un *motif interdit*. Il applique :

- des motifs génériques, versionnés ici (chemins de répertoires
  personnels) ;
- vos motifs personnels, lus dans un fichier situé **hors** du dépôt,
  pour que la liste elle-même ne soit jamais publiée.

Le hook signale seulement `fichier:ligne` et n'affiche jamais un motif.

**Mise en place en une commande** (depuis la racine du dépôt) :

```
uv run python scripts/check_anonymity.py --init
```

Elle crée `~/.config/nomogram/deny-patterns.txt` (ou le chemin donné
par la variable d'environnement `NOMOGRAM_DENY_PATTERNS`), avec un mode
d'emploi et des exemples commentés. Complétez-le avec ce que vous
voulez garder privé. Sans ce fichier, le hook avertit et n'applique que
les motifs génériques.

**Bien écrire ses motifs.** Une expression régulière par ligne,
insensible à la casse ; lignes vides et commentaires `#` ignorés.

- `\b` marque une frontière de mot : `\bdoe\b` trouve « Doe » mais pas
  « Doerr ».
- Échappez les points : `exemple\.fr` (un point seul vaut n'importe
  quel caractère).
- Pas de normalisation Unicode : prévoyez les variantes avec et sans
  accent, par exemple `h[eé]l[eè]ne`.
- N'y mettez pas votre pseudonyme public s'il figure volontairement
  dans le dépôt (auteur, adresses) : tous les commits seraient refusés.
- Évitez les quantificateurs imbriqués comme `(a+)+` : ils peuvent
  bloquer le hook.

**La liste se protège elle-même.** Un fichier de motifs situé dans le
dépôt est refusé. Le fichier créé par `--init` commence par une ligne
repère, et tout fichier qui la contient est refusé, même en CI : une
copie de votre liste ne peut pas être commitée par erreur. Gardez cette
ligne.

**Ce que le hook ne couvre pas.** Les contenus compressés (docx, PDF
compressé), l'historique déjà poussé, les noms de branches et
d'étiquettes, et tout ce qui se saisit directement sur GitHub : titres
et descriptions de PR, issues, commentaires. Relisez-les avant de
publier.

## Circuit d'une contribution

1. Créer une branche depuis `develop` (branche par défaut), par
   exemple `feature/formules-humidite`.
2. Commits signés, au format Conventional Commits, sujet sans accent :
   `feat: ajout de la formule de Magnus`.
3. PR vers `develop`. Le titre de la PR suit le même format : il
   devient le message du commit à la fusion par squash.
4. La CI doit être verte. Contrôles exigés :
   - `quality` : les hooks ci-dessus, sur tout le dépôt ;
   - `tests` : Ubuntu et Windows × Python 3.12 et 3.13, avec un plancher
     de couverture des branches à 80 % ;
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

## Sécurité

Ne signalez jamais une vulnérabilité dans une issue publique : suivez
la [politique de sécurité](SECURITY.md), qui passe par le signalement
privé de vulnérabilités de GitHub.

## Code de conduite

Ce projet applique le [Contributor Covenant](CODE_OF_CONDUCT.md). En
participant, vous vous engagez à le respecter.

## Agents de codage

Ce projet utilise des agents de codage ; toute contribution est relue
et signée par un contributeur humain. Aucune mention d'outil n'est
ajoutée aux commits ni aux PR : la signature humaine engage le
contributeur, quel que soit l'outil employé.

## Licence

En contribuant, vous acceptez que votre contribution soit publiée sous
la licence [BSD-3-Clause](../LICENSE) du projet.
