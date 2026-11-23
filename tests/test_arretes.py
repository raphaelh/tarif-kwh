"""Tempo et EJP au 23 juillet 2012 : barèmes HT recopiés de l'arrêté du 20 juillet 2012 (config/baremes_arretes.json)."""
from datetime import date

import pytest
from conftest import CSV

from tarif_kwh import checks, reconcile, taxes
from tarif_kwh.sources import arretes, cre_opendata

CONFIG = taxes.charger_config()
AUJOURD_HUI = date(2026, 11, 23)
D = date(2012, 7, 23)


@pytest.fixture(scope="module")
def baremes():
    return {g.option: g for g in arretes.collecter()}


@pytest.fixture(scope="module")
def registre():
    hist = {o: {"url": "u", "grilles": cre_opendata.parse_historique(p.read_bytes(), o)} for o, p in CSV.items()}
    return {"taxes_kwh_opendata": reconcile.taxes_kwh_opendata(hist, CONFIG)}


def test_baremes_2012(baremes):
    assert set(baremes) == {"tempo", "ejp"}
    t, e = baremes["tempo"], baremes["ejp"]
    assert t.date_effet == e.date_effet == D
    assert sorted(t.puissances) == [9, 12, 15, 18, 30, 36]
    assert t.puissances[30].abonnement_ht == 361.32
    assert t.puissances[9].prix_ht == {
        "bleu_hc": 0.041, "bleu_hp": 0.053, "blanc_hc": 0.067, "blanc_hp": 0.0835, "rouge_hc": 0.142, "rouge_hp": 0.4052,
    }
    assert sorted(e.puissances) == [9, 12, 15, 18, 36]
    assert e.puissances[36].abonnement_ht == 418.44
    assert e.puissances[9].prix_ht == {"normal": 0.0665, "pointe": 0.4259}
    assert checks.coherence(t) == [] and checks.coherence(e) == []


@pytest.mark.parametrize("option,per,ttc", [("tempo", "bleu_hc", 0.0763), ("tempo", "rouge_hp", 0.5119), ("ejp", "pointe", 0.5366)])
def test_ttc_2012(baremes, registre, option, per, ttc):
    """TTC du kWh : taxes au kWh de l'open data Base/HP/HC du 23 juillet 2012 (2,28 c€), TVA 19,6 % ; pas d'abonnement TTC."""
    g, pb = reconcile.recouper(option, D, {"arrete": baremes[option]}, registre, CONFIG, AUJOURD_HUI, [], [])
    assert pb == []
    assert [s["type"] for s in g["sources"]] == ["arrete"]
    p = g["puissances"]["9"]
    assert p["prix_ttc"][per] == ttc
    assert p["abonnement_ttc"] is None


def test_arrete_redondant_bloque(baremes, registre):
    autre = arretes.parse({"baremes": []})  # aucune grille
    assert autre == []
    obs = {"arrete": baremes["ejp"], "jourtempo": baremes["ejp"]}
    g, pb = reconcile.recouper("ejp", D, obs, registre, CONFIG, AUJOURD_HUI, [], [])
    assert g is None and any("le retirer" in x for x in pb)


def test_bareme_incomplet():
    b = {"option": "ejp", "date_effet": "2012-07-23", "texte": "t", "url": "u",
         "puissances": {"9": {"abonnement_ht": 1, "prix_ceur_kwh": {"normal": 1}}}}
    with pytest.raises(arretes.ParseError):
        arretes.parse({"baremes": [b]})
