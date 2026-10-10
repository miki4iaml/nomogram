import nomogram


def test_hello() -> None:
    assert nomogram.hello() == "Hello from nomogram!"


# Essai negatif de la CI, a retirer.
ERREUR_VOLONTAIRE: int = "essai negatif"
