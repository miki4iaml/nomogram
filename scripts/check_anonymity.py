# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Hook pre-commit : refuse les informations nominatives ou internes.

Deux sources de motifs (expressions régulières, insensibles à la casse) :

- des motifs génériques, versionnés ici, qui ne nomment personne
  (chemins de répertoires personnels) ;
- des motifs personnels (nom civil, domaine, adresse professionnelle…),
  lus dans un fichier hors dépôt pour ne jamais les publier. Chemin par
  défaut : ``~/.config/nomogram/motifs-interdits.txt``, modifiable par la
  variable d'environnement ``NOMOGRAM_MOTIFS_INTERDITS``. Une expression
  par ligne, en UTF-8 ; lignes vides et lignes commençant par ``#``
  ignorées.

Le script ne réussit jamais sans avoir vérifié :

- fichier texte non UTF-8 ou illisible : échec ;
- fichier binaire (contient un octet nul) : recherche dans ses octets
  bruts, ce qui couvre les métadonnées en clair mais pas les contenus
  compressés (docx, PDF compressé…) ;
- chemin du fichier : vérifié comme son contenu ;
- variable d'environnement définie mais fichier de motifs absent,
  illisible ou invalide : échec ;
- ni variable ni fichier par défaut, ou fichier vide : avertissement,
  seuls les motifs génériques s'appliquent.

Avec ``--commit-msg``, le fichier reçu est un message de commit : les
lignes de commentaire et tout ce qui suit la ligne de coupe de
``git commit -v`` sont ignorés, comme Git le fait.

Les correspondances sont signalées par ``fichier:ligne`` seulement, sans
reproduire le texte trouvé ; dans les chemins affichés, les parties
correspondantes sont masquées.
"""

import os
import re
import sys
from pathlib import Path

GENERIC_PATTERNS = (
    # Répertoire personnel Windows : C:\Users\<nom>\ ou C:/Users/<nom>/
    r"\b[A-Za-z]:[\\/](?:Users)[\\/][^\\/\s<]+[\\/]",
    # Répertoire personnel Unix ou macOS : /home/<nom>/, /Users/<nom>/
    r"(?<![\w.])/(?:home|Users)/[^/\s<]+/",
)

ENV_VAR = "NOMOGRAM_MOTIFS_INTERDITS"
DEFAULT_PATTERNS_FILE = Path.home() / ".config" / "nomogram" / "motifs-interdits.txt"

SCISSORS = "# ------------------------ >8 ------------------------"
FINDING = "information nominative ou interne"


class ConfigError(Exception):
    """Fichier de motifs personnels inutilisable."""


def load_personal_patterns() -> list[re.Pattern[str]]:
    """Lit et compile les motifs personnels.

    Renvoie une liste vide, après avertissement, si aucun fichier n'est
    configuré ou s'il ne contient aucun motif. Lève ``ConfigError`` si le
    fichier désigné est absent, illisible ou contient un motif invalide.
    """
    configured = os.environ.get(ENV_VAR)
    path = Path(configured) if configured else DEFAULT_PATTERNS_FILE
    if not path.exists():
        if configured:
            raise ConfigError(f"{ENV_VAR} désigne un fichier absent : {path}")
        warn(f"aucun fichier de motifs personnels ({ENV_VAR} ou {path})")
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"fichier de motifs illisible : {path}") from exc

    patterns = []
    for number, line in enumerate(text.splitlines(), start=1):
        source = line.strip()
        if not source or source.startswith("#"):
            continue
        try:
            patterns.append(re.compile(source, re.IGNORECASE))
        except re.error:
            # Le texte de l'erreur peut citer le motif : on ne le reprend pas.
            raise ConfigError(f"motif invalide ligne {number} de {path}") from None
    if not patterns:
        warn(f"le fichier de motifs personnels est vide : {path}")
    return patterns


def warn(message: str) -> None:
    print(
        f"anonymisation : {message} ; seuls les motifs generiques sont appliques.",
        file=sys.stderr,
    )


def mask(text: str, patterns: list[re.Pattern[str]]) -> str:
    """Masque dans ``text`` les parties qui correspondent à un motif."""
    for pattern in patterns:
        text = pattern.sub("***", text)
    return text


def matches(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def message_lines(text: str) -> list[str]:
    """Lignes d'un message de commit telles que Git les conservera."""
    lines = text.splitlines()
    if SCISSORS in lines:
        lines = lines[: lines.index(SCISSORS)]
    return [line if not line.startswith("#") else "" for line in lines]


def check_file(
    name: str, patterns: list[re.Pattern[str]], *, commit_msg: bool = False
) -> list[str]:
    """Renvoie les signalements pour le fichier ``name`` (vide si conforme)."""
    shown = mask(name, patterns)
    findings = []
    if not commit_msg and matches(name, patterns):
        findings.append(f"{shown}: chemin : {FINDING}")

    try:
        data = Path(name).read_bytes()
    except OSError:
        return [*findings, f"{shown}: illisible, non verifie"]

    if b"\0" in data and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raw = (data.decode("latin-1"), data.decode("utf-8", errors="replace"))
        if any(matches(text, patterns) for text in raw):
            findings.append(f"{shown}: binaire : {FINDING}")
        return findings

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [*findings, f"{shown}: non UTF-8, non verifie"]

    lines = message_lines(text) if commit_msg else text.splitlines()
    findings.extend(
        f"{shown}:{number}: {FINDING}"
        for number, line in enumerate(lines, start=1)
        if matches(line, patterns)
    )
    return findings


def main(argv: list[str]) -> int:
    commit_msg = bool(argv) and argv[0] == "--commit-msg"
    names = argv[1:] if commit_msg else argv
    try:
        personal = load_personal_patterns()
    except ConfigError as exc:
        print(f"anonymisation : {exc}", file=sys.stderr)
        return 2
    patterns = [re.compile(p, re.IGNORECASE) for p in GENERIC_PATTERNS] + personal

    status = 0
    for name in names:
        for finding in check_file(name, patterns, commit_msg=commit_msg):
            print(finding)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
