from datetime import date

from tarif_kwh import calendrier


def reg(*dates):
    return {"grilles": {"tempo": {d: {} for d in dates}}}


def test_fenetres():
    assert calendrier.echeance_surveillee(date(2026, 11, 23)) is None
    assert calendrier.echeance_surveillee(date(2027, 1, 24)) is None
    assert calendrier.echeance_surveillee(date(2027, 1, 25)) == date(2027, 2, 1)
    assert calendrier.echeance_surveillee(date(2027, 3, 18)) == date(2027, 2, 1)
    assert calendrier.echeance_surveillee(date(2027, 3, 19)) is None
    assert calendrier.echeance_surveillee(date(2027, 7, 26)) == date(2027, 8, 1)


def test_deliberation_trouvee():
    r = reg("2026-08-01", "2027-02-01")
    assert calendrier.deliberation_manquante(r, date(2027, 1, 26)) is None
    assert calendrier.deliberation_manquante(r, date(2026, 11, 23)) is None


def test_deliberation_manquante():
    r = reg("2026-08-01")
    msg = calendrier.deliberation_manquante(r, date(2027, 1, 26))
    assert msg and "01/02/2027" in msg and "annexes_b_connues" in msg
    # toujours signalée après la date d'effet
    assert calendrier.deliberation_manquante(r, date(2027, 2, 10))


def test_registre_reel_aujourd_hui():
    """Le 23/11/2026, la grille du 01/08/2026 est connue et aucune échéance n'est surveillée."""
    import json
    from conftest import RACINE
    r = json.loads((RACINE / "data" / "registre.json").read_text())
    assert calendrier.deliberation_manquante(r, date(2026, 11, 23)) is None
    assert calendrier.deliberation_manquante(r, date(2026, 8, 10)) is None
