"""Hook pre-commit : refuse les informations nominatives ou internes.

Deux sources de motifs (expressions régulières, insensibles à la casse) :

- des motifs génériques, versionnés ici, qui ne nomment personne
  (chemins de répertoires personnels) ;
- des motifs personnels (nom civil, domaine, adresse professionnelle…),
  lus dans un fichier hors dépôt pour ne jamais les publier. Chemin par
  défaut : ``~/.config/nomogram/motifs-interdits.txt``, modifiable par la
  variable d'environnement ``NOMOGRAM_MOTIFS_INTERDITS``. Une expression
  par ligne ; lignes vides et lignes commençant par ``#`` ignorées.

Si le fichier personnel est absent, seuls les motifs génériques
s'appliquent et un avertissement est émis.

Les correspondances sont signalées par ``fichier:ligne`` seulement, sans
reproduire le texte trouvé.
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


def load_personal_patterns() -> list[str] | None:
    """Lit les motifs personnels ; renvoie None si le fichier est absent."""
    path = Path(os.environ.get(ENV_VAR) or DEFAULT_PATTERNS_FILE)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def find_matches(path: Path, patterns: list[re.Pattern[str]]) -> list[int]:
    """Renvoie les numéros de ligne de ``path`` où un motif correspond."""
    data = path.read_bytes()
    if b"\0" in data:
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return []
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if any(p.search(line) for p in patterns)
    ]


def main(argv: list[str]) -> int:
    personal = load_personal_patterns()
    if personal is None:
        print(
            f"anonymisation : aucun fichier de motifs personnels "
            f"(variable {ENV_VAR} ou {DEFAULT_PATTERNS_FILE}) ; "
            "seuls les motifs generiques sont appliques.",
            file=sys.stderr,
        )
        personal = []
    try:
        patterns = [
            re.compile(p, re.IGNORECASE) for p in (*GENERIC_PATTERNS, *personal)
        ]
    except re.error as exc:
        print(f"anonymisation : motif invalide ({exc})", file=sys.stderr)
        return 2

    status = 0
    for name in argv:
        for number in find_matches(Path(name), patterns):
            print(f"{name}:{number}: information nominative ou interne")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
