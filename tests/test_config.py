"""Validité des fichiers de configuration édités à la main (ex. dans l'éditeur web GitHub)."""
import json
from datetime import date

import pytest
from conftest import RACINE

TAXES = json.loads((RACINE / "config" / "taxes.json").read_text(encoding="utf-8"))
BORNES = {"accise_eur_kwh": (0.0005, 0.1),  # 0,1 c€/kWh sous le bouclier tarifaire (2022-2024)
          "tva_energie": (0.0, 0.3), "tva_abonnement": (0.0, 0.3)}


@pytest.mark.parametrize("cle", sorted(BORNES))
def test_taxes_json(cle):
    serie = TAXES[cle]
    assert serie, f"{cle} vide"
    debuts = []
    for e in serie:
        assert {"debut", "valeur"} <= set(e), f"{cle}: champ manquant dans {e}"
        debuts.append(date.fromisoformat(e["debut"]))  # AAAA-MM-JJ
        lo, hi = BORNES[cle]
        assert isinstance(e["valeur"], (int, float)) and lo <= e["valeur"] <= hi, (
            f"{cle} {e['debut']}: {e['valeur']} hors de [{lo}, {hi}] "
            "(accise en €/kWh : 30,62 €/MWh s'écrit 0.03062)"
        )
    assert debuts == sorted(debuts) and len(set(debuts)) == len(debuts), f"{cle}: dates non croissantes ou en double"


def test_validations_json():
    v = json.loads((RACINE / "config" / "validations.json").read_text(encoding="utf-8"))
    for e in v["validations"]:
        date.fromisoformat(e["date_effet"])
        assert e["option"] in {"base", "hphc", "tempo", "ejp"}


def test_sources_json():
    s = json.loads((RACINE / "config" / "sources.json").read_text(encoding="utf-8"))
    assert all(u.startswith("https://www.cre.fr/") for u in s["annexes_b_connues"])
    for a in s.get("annexes_b_anciennes", []):
        assert a["url"].startswith("https://www.cre.fr/") and a["url"].lower().endswith(".pdf")
        d = date.fromisoformat(a["date_effet"])
        assert d.day == 1, a
        # Propositions CRE non appliquées (bouclier tarifaire 2023, report de novembre 2024)
        assert d.isoformat() not in {"2023-02-01", "2023-08-01", "2024-11-01"}, a
