# Contribuer à nomogram

[English](CONTRIBUTING.md) | **Français**

> Traduction de [CONTRIBUTING.md](CONTRIBUTING.md) ; en cas d'écart,
> la version anglaise fait foi.

Merci de votre intérêt. Ce guide décrit l'installation, les contrôles,
les commandes, le circuit d'une contribution, la publication d'une
version et les raisons des décisions arrêtées. Les règles de code et
d'architecture
sont dans [AGENTS.md](../AGENTS.md), qui s'applique aux humains comme
aux agents de codage.

## Comment contribuer

De la plus légère à la plus engagée ; toutes sont bienvenues.

1. **Signaler une référence à intégrer.** Une citation, un DOI ou un
   lien suffit : la référence est lue, vérifiée et saisie pour vous.
   [Ouvrir une issue « Reference to integrate »](https://github.com/miki4iaml/nomogram/issues/new?template=reference_proposal.yml).
2. **Apporter un complément d'information ou signaler un problème sur
   une entrée du catalogue** : un coefficient, un domaine de validité,
   une attribution, une échelle de température, une notation, la
   vérification d'une référence encore marquée `to-confirm`.
   [Ouvrir une issue « Catalog entry »](https://github.com/miki4iaml/nomogram/issues/new?template=catalog_entry.yml).
3. **Proposer une formule**, soit par une issue (le LaTeX convient,
   [ouvrir une issue « Formula proposal »](https://github.com/miki4iaml/nomogram/issues/new?template=formula_proposal.yml)),
   soit directement au format du catalogue par une pull request : voir
   [Writing a catalog entry](../docs/catalog.md) (en anglais).
4. **Contribuer au code** : installation, contrôles et parcours
   ci-dessous.

Quelle que soit la voie, une formule entre au catalogue avec sa source,
ses unités et son domaine de validité ; un détail n'est marqué
`verified` qu'une fois lu dans la source elle-même.

## Droits des sources

Une formule se cite ; le document qui la donne garde ses propres droits.
Ces règles engagent tout contributeur, quel que soit l'outil employé :

- **Les normes sous licence** (ISO, AFNOR…) ne sont jamais reproduites :
  le catalogue cite leurs équations et leurs constantes, jamais leurs
  tableaux ni leurs extraits.
- **Aucun document source n'est redistribué**, ni dans le dépôt ni dans
  le paquet : une référence donne son titre, son DOI ou son lien.
- **Fouille de textes et de données** : avant qu'un document soit traité
  par un agent de codage ou un autre outil automatique, vérifier qu'il ne
  porte pas de clause interdisant la fouille de textes et de données ou
  le traitement par une intelligence artificielle ; un document qui en
  porte une n'est pas traité ainsi.
- **Les protections contre les robots et les accès payants ne sont
  jamais contournées.**
- **Les mentions de droit d'auteur sont respectées** : une formule se
  cite, une citation reste brève et dans ce que la mention permet, le
  document n'est pas reproduit.

## Prérequis

- Python 3.12 ou plus récent.
- [uv](https://docs.astral.sh/uv/). Il est indispensable : les hooks
  ruff, mypy et pytest passent par `uv run --frozen`, pour utiliser
  exactement les versions figées dans `uv.lock` (une seule source de
  version, en local comme en CI). Sans uv, ces hooks échouent.
- Une clé de signature des commits (voir plus bas).

## Installation

```
uv sync --all-extras
uv run pre-commit install
```

La première commande installe aussi les extras optionnels (`viz`),
couverts par les tests. La seconde commande installe les hooks aux trois stades (pre-commit,
commit-msg, pre-push).

## Contrôles locaux

| Stade | Contrôles |
|---|---|
| pre-commit | hygiène des fichiers (espaces, fin de fichier, fins de ligne LF, BOM, YAML, TOML, conflits, gros fichiers), clé privée, refus de commit direct sur `main` et `develop`, `ruff check --fix` et `ruff format`, codespell (orthographe), zizmor (audit de sécurité des workflows), gitleaks, nbstripout, anonymisation, métadonnées des images, caractères cachés et fichiers locaux |
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

Elle crée `~/.config/anonymity/deny-patterns.txt` (sous
`$XDG_CONFIG_HOME` s'il est défini), avec un mode d'emploi et des
exemples commentés. Complétez-le avec ce que vous voulez garder privé.
Sans ce fichier, le hook avertit et n'applique que les motifs
génériques.

**Une seule liste pour tous vos dépôts.** Les noms appartiennent à
l'outil, pas à ce projet : tout dépôt qui utilise ce hook lit le même
fichier, et vous ne tenez votre liste qu'une fois. Pour ajouter des
motifs propres à un projet (noms de code d'un client, nom d'un autre
compte que vous gardez séparé), donnez à la variable d'environnement
`ANONYMITY_DENY_PATTERNS` plusieurs fichiers, séparés comme dans `PATH`
(`;` sous Windows, `:` ailleurs), par exemple
`~/.config/anonymity/deny-patterns.txt;~/.config/anonymity/client.txt`.
Chaque fichier listé doit exister : une faute de frappe fait échouer le
hook au lieu d'être ignorée en silence.

**Des motifs pour ce seul dépôt.** La variable d'environnement vaut pour
tous les dépôts. Pour ajouter une liste à ce dépôt seulement, écrivez
son chemin dans `.git/anonymity-deny-patterns` (dans le dossier git,
donc jamais commité) : un chemin par ligne, absolu ou relatif à la
racine du dépôt, par exemple `../mes-notes-privees/motifs-nomogram.txt`.
Les mêmes règles s'appliquent : le fichier doit exister et rester hors
du dépôt.

**Votre dossier personnel.** Un dossier `_priv/` à la racine du dépôt
est ignoré par git : rangez-y vos notes, analyses ou fichiers
d'assistant, et sauvegardez-les comme vous l'entendez. N'y mettez jamais
de fichier de motifs : un fichier de motifs doit rester hors du dépôt.

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
ligne : une copie partielle qui ne la contient pas n'est pas détectée.

**Images et PDF.** Une image ne porte aucune métadonnée : le hook
`scripts/check_image_metadata.py` refuse texte, EXIF (avec le lieu de
prise d'une photographie), XMP, IPTC, commentaires, horodatages et
profils de couleur, et tout bloc qu'il ne connaît pas, en PNG, JPEG,
GIF, WebP et SVG ; les autres formats sont refusés comme non vérifiés.
Le message nomme le bloc, jamais son contenu. Un PDF garde ses
métadonnées (les auteurs officiels d'une référence) : le hook
d'anonymisation les fouille, décompressées quand elles sont dans un
flux compressé.

**Ce que le hook ne couvre pas.** Les contenus compressés (docx, pages
d'un PDF), l'historique déjà poussé, les noms de branches et
d'étiquettes, et tout ce qui se saisit directement sur GitHub : titres
et descriptions de PR, issues, commentaires. Relisez-les avant de
publier. Le hook peut aussi être sauté en local
(`git commit --no-verify`) : la CI applique alors toujours les motifs
génériques et le contrôle de la ligne repère, mais jamais vos motifs
personnels, qui restent sur votre poste par conception.

## Commandes

```
uv sync --all-extras                       # environnement
uv run pytest                              # tests
uv run coverage run -m pytest && uv run coverage report   # couverture
uv run ruff check --fix && uv run ruff format
uv run mypy                                # typage strict
uv run --isolated --python 3.13 --all-extras pytest   # reproduire la CI
uv run --isolated --resolution lowest-direct --all-extras pytest   # versions minimales
```

`--isolated` compte pour les deux dernières commandes : sans lui,
`uv run` reverrouille `uv.lock` avec la résolution demandée et remplace
le `.venv` du projet.

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

## Publier une version

Pour le mainteneur, dans cet ordre :

1. Pour une version mineure, une PR préalable réextrait `semantics.json`
   depuis les dernières versions officielles de QUDT et de CF
   (`scripts/extract_semantics.py`), chacune enregistrée avec sa version ;
   les versions de correctif gardent l'extrait. Un genre ou une unité
   qu'une nouvelle version de QUDT définit remplace le genre ou l'unité
   local dans la même PR, avec une entrée au CHANGELOG. La même PR
   vérifie la PR de chaque genre provisoire (`LOCAL_KINDS`) : fusionnée et
   publiée, le genre de QUDT le remplace, sous son nom et sa définition,
   avec une entrée « Changed » qui nomme les deux ; fermée sans fusion, le
   genre est retiré ou repris ; encore ouverte, il reste.
2. PR vers `develop` (squash) : version dans `pyproject.toml` et
   `CITATION.cff`, section `[Unreleased]` du `CHANGELOG.md` devenue
   `[x.y.z] - date`, titre `chore: release x.y.z`. La même PR met à
   jour `docs/security-and-compliance.md` : la date, la version évaluée,
   les versions des dépendances, le nombre de tests et la couverture,
   les alertes traitées, la liste de contrôle.
3. PR `develop` → `main`, fusionnée par un commit de fusion (seule
   exception au squash : `main` doit garder l'historique exact de
   `develop`, sinon les deux branches divergent à chaque version).
4. Avant le tag, vérifier localement : `uv build` puis
   `uvx --from twine twine check --strict dist/*`.
5. Tag signé `vx.y.z` sur `main`, puis publication d'une release GitHub
   depuis ce tag, ses notes étant la section du `CHANGELOG.md` de la
   version, liens rendus absolus : `python scripts/absolute_links.py
   rewrite --repo miki4iaml/nomogram --ref vx.y.z notes.md`. Le workflow
   de publication (`.github/workflows/release.yml`) vérifie que le tag
   correspond à la version du projet, rend absolus les liens du README au
   tag (PyPI l'affiche hors du dépôt), construit une seule fois, vérifie
   qu'aucun lien relatif ne reste, atteste la provenance de la
   construction et la SBOM CycloneDX, et publie exactement ces fichiers
   sur PyPI par Trusted Publishing (OIDC, aucun jeton stocké), après
   approbation de l'environnement protégé `pypi`.
6. Vérifier : `gh attestation verify <wheel> --repo miki4iaml/nomogram`.

Répétition : lancer le workflow de publication à la main
(`workflow_dispatch`). Il publie une version unique `x.y.z.devN` sur
TestPyPI sans créer de release. Ne jamais publier une release GitHub
pour essayer : chaque release publiée archive aussi un DOI Zenodo
permanent.

## Décisions arrêtées

Les décisions qu'[AGENTS.md](../AGENTS.md) énonce en une ligne, avec
leurs raisons.

- **Matrice de CI** : complète et bloquante, Ubuntu et Windows × Python
  3.12 et 3.13. La portabilité et `requires-python >=3.12` sont des
  promesses faites aux utilisateurs du paquet ; une cellule non
  bloquante finit ignorée, et la promesse n'est plus vérifiée. Ce choix
  découle du profil du paquet — Python pur, dépendances légères, publics
  variés —, qui rend l'intégration peu coûteuse et la portabilité
  réellement importante. Ne pas aligner cette matrice sur celle d'un
  dépôt plus lourd par souci d'uniformité : le profil du paquet décide.
- **Signatures des contributeurs** : une fusion par squash produit un
  commit signé par GitHub, qui masque les commits de la PR ; le job de
  CI `signatures` exige donc que chacun d'eux soit signé et vérifié.
- **`.vscode` versionné en partie** : `settings.json`, `extensions.json`
  et `tasks.json` sont partagés (ruff et mypy de l'environnement,
  extensions recommandées et indésirables, tâche « Quality gates ») ; le
  reste du dossier reste local. L'interpréteur n'est pas fixé :
  l'extension Python trouve `.venv` seule. Ne pas réintroduire
  `python.defaultInterpreterPath` pointant vers un dossier : l'extension
  Python le résout pour elle seule, mais le passe tel quel aux extensions
  ruff et mypy, qui ne parviennent pas à le lancer. Un chemin
  d'exécutable dépendrait du système.
- **mypy au pre-push** : recouvrement voulu avec la CI, pour que les
  échecs surviennent sur le poste plutôt qu'après la poussée. Surveiller
  le temps de poussée.
- **Couverture** : couverture des branches mesurée par coverage.py (sans
  pytest-cov) ; un plancher de 80 % est imposé dans chaque cellule de la
  matrice de tests de la CI, la cible courante (recommandation usuelle
  de Codecov ; le guide de Google juge 75 % louable, 90 % exemplaire).
  Le hook de pre-push lance pytest seul, pour rester rapide ; la CI fait
  foi pour la couverture.

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

Les fichiers d'instructions des agents de codage se relisent comme du
code. AGENTS.md est le seul suivi, à la racine : le hook
`check-integrity` refuse un AGENTS.md dans un sous-dossier, les fichiers
d'instructions des autres outils (`GEMINI.md`, `.cursorrules`,
`.github/copilot-instructions.md`…), les fichiers qui restent locaux
(`CLAUDE.md`, `.claude/`, `.mcp.json`) et les caractères cachés (largeur
nulle, bidirectionnels, étiquettes, sélecteurs de variante, caractères de
contrôle). Un mainteneur lit une PR d'un tiers comme un diff, sur GitHub
ou avec `gh pr diff`, et ne l'extrait jamais dans un arbre de travail où
tourne un agent de codage : l'agent chargerait les instructions qu'elle
apporte. `.github/CODEOWNERS` liste les chemins dont les modifications
demandent la relecture du mainteneur.

## Licence

En contribuant, vous acceptez que votre contribution soit publiée sous
la licence [BSD-3-Clause](../LICENSE) du projet.
