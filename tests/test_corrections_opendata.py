"""Open data CRE reconnue fausse : TTC Tempo 2022 et barème Base d'août 2015 et d'août 2016, tranchés par les grilles EDF archivées."""
import copy
import json
import re
from datetime import date

import pdfplumber
import pytest
from conftest import CSV, FIX, RACINE, fr

from tarif_kwh import publish, taxes
from tarif_kwh.sources import cre_opendata, edf_grille

CONFIG = taxes.charger_config()
EDF_2022 = {d: FIX / f"edf_grille_tarif_bleu_{d}.pdf" for d in ("2022-02-01", "2022-08-01")}  # captures archive.org


@pytest.fixture(scope="module")
def brut():
    return {o: {"url": "u", "grilles": cre_opendata.parse_historique(p.read_bytes(), o)} for o, p in CSV.items()}


@pytest.fixture(scope="module")
def corrige(brut):
    h = copy.deepcopy(brut)
    journal = cre_opendata.corriger(h, cre_opendata.charger_corrections(), CONFIG)
    assert len(journal) == 4, journal
    assert sum("recalculé" in l for l in journal) == 2 and sum("barème remplacé" in l for l in journal) == 2, journal
    return h


def _grille(hist, option, d):
    return next(g for g in hist[option]["grilles"] if g["date_debut"] == d)


@pytest.mark.parametrize("d", sorted(EDF_2022))
def test_grille_edf_2022_tranche(brut, corrige, d):
    """EDF : TTC = HT open data + 7,63 €/MWh (TCFE 0,6630 + CSPE 0,10 c€) + TVA, pour les trois options.

    Base et HP/HC de l'open data concordent ; Tempo, publié avec 10,9 €/MWh, ne concorde qu'une fois corrigé.
    """
    pdf = EDF_2022[d].read_bytes()
    with pdfplumber.open(EDF_2022[d]) as f:
        texte = " ".join((p.extract_text() or "") for p in f.pages).replace("\n", " ")
    tcfe = fr(re.search(r"TCFE\)?, d.un montant maximum de ([\d,]+) cts", texte).group(1))
    cspe = fr(re.search(r"\(CSPE\), d.un montant de ([\d,]+) cts", texte).group(1))
    taxes_kwh = round((tcfe + cspe) / 100, 6)
    assert taxes_kwh == 0.00763
    edf = edf_grille.parse_grille(pdf)
    for option in ("base", "hphc", "tempo"):
        e = edf[option]
        assert e.date_effet == date.fromisoformat(d)
        for hist, juste in ((brut, option != "tempo"), (corrige, True)):
            od = _grille(hist, option, d)
            for k, p in e.puissances.items():
                if str(k) not in od["puissances"]:
                    continue  # Base 18-36 kVA : en extinction, absentes de l'open data
                q = od["puissances"][str(k)]
                assert {per: taxes.kwh_ttc(v, taxes_kwh, 0.2) for per, v in q["prix_ht"].items()} == p.prix_ttc, (option, k)
                assert (q["prix_ttc"] == p.prix_ttc) is juste, (option, k, q["prix_ttc"], p.prix_ttc)


def test_correction_tempo_2022(brut, corrige):
    for d in EDF_2022:
        g, b = _grille(corrige, "tempo", d), _grille(brut, "tempo", d)
        assert g["correction_ttc"]["taxes_kwh"] == 0.00763
        assert all(s.startswith("https://web.archive.org/") for s in g["correction_ttc"]["sources"])
        assert g["puissances"]["9"]["prix_ttc"]["bleu_hc"] == 0.0862 and b["puissances"]["9"]["prix_ttc"]["bleu_hc"] == 0.0902
        # Abonnement et HT inchangés
        assert {k: (p["abonnement_ht"], p["abonnement_ttc"], p["prix_ht"]) for k, p in g["puissances"].items()} == {
            k: (p["abonnement_ht"], p["abonnement_ttc"], p["prix_ht"]) for k, p in b["puissances"].items()
        }
    # Rien d'autre ne bouge
    for o in brut:
        for g, b in zip(corrige[o]["grilles"], brut[o]["grilles"]):
            if "correction_ttc" not in g:
                assert g == b


def test_correction_sans_effet_si_open_data_juste(corrige):
    """Si la CRE corrige son fichier, la correction ne s'applique plus."""
    h = copy.deepcopy(corrige)
    for g in h["tempo"]["grilles"]:
        g.pop("correction_ttc", None)
    journal = cre_opendata.corriger(h, cre_opendata.charger_corrections(), CONFIG)
    assert all("déjà juste" in l for l in journal) and not any("correction_ttc" in g for g in h["tempo"]["grilles"])


def test_historique_tempo_2022(corrige):
    h = publish.construire_historique(corrige, None, {}, date(2026, 11, 23), None, CONFIG)
    for g in h["options"]["tempo"]["grilles"]:
        corrigee = g["date_debut"] in EDF_2022
        assert ("correction_ttc" in g) is corrigee and g["ttc_estime"] is corrigee, g["date_debut"]
        assert g["statut"] == ("en_vigueur" if corrigee else "confirme")
        if corrigee:
            assert g["prix_ttc"]["rouge_hp"] == 0.5486
    # Hors ligne, les grilles corrigées de l'ancien historique sont gardées telles quelles
    h2 = publish.construire_historique(None, h, {}, date(2026, 11, 23), None, CONFIG)
    assert h2["options"]["tempo"]["grilles"] == h["options"]["tempo"]["grilles"]


def test_corrections_json():
    c = json.loads((RACINE / "config" / "corrections_opendata.json").read_text(encoding="utf-8"))
    for e in c["corrections"]:
        assert e["option"] in {"base", "hphc", "tempo"}
        assert all(date.fromisoformat(d).day == 1 for d in e["dates_effet"])
        assert 0 < e["taxes_kwh"] < 0.1 and e["motif"] and e["sources"]


# --- Base d'août 2015 et d'août 2016 : barème périmé dans l'open data -----------------------------

# Grilles Tarif Bleu EDF archivées (web.archive.org), lues dans les PDF : 6 kVA, abonnement €/an TTC et kWh TTC
EDF_BASE = {"2015-08-01": (88.42, 0.1467), "2016-08-01": (96.50, 0.1449)}
HT_OFFICIEL = {"2015-08-01": (70.44, 0.0932), "2016-08-01": (78.00, 0.0887)}  # arrêté 2015-07-30, CRE 2016-07-13


@pytest.mark.parametrize("d", sorted(EDF_BASE))
def test_correction_bareme_base(brut, corrige, d):
    b, g = _grille(brut, "base", d), _grille(corrige, "base", d)
    p, q = g["puissances"]["6"], b["puissances"]["6"]
    assert (q["abonnement_ht"], q["prix_ht"]["base"]) != HT_OFFICIEL[d]  # open data périmée
    assert (p["abonnement_ht"], p["prix_ht"]["base"]) == HT_OFFICIEL[d]
    assert g["correction_ttc"]["bareme"] is True
    abo, kwh = EDF_BASE[d]
    assert p["abonnement_ttc"] == abo
    # TCFE de la CRE (≈ 0,93 c€) contre 0,957 c€ chez EDF : 0,03 c€ d'écart au plus
    assert abs(p["prix_ttc"]["base"] - kwh) <= 0.00031
    assert p["prix_ttc"]["base"] == taxes.kwh_ttc(p["prix_ht"]["base"], g["correction_ttc"]["taxes_kwh"], 0.20)
    assert set(g["puissances"]) == set(b["puissances"])


def test_correction_bareme_base_2016_egale_grille_edf(corrige):
    """Août 2016 : au centime de la grille EDF (TTC au kWh et abonnement), puissances de l'open data (3 à 15 kVA)."""
    edf = {"3": (56.07, 0.1564), "6": (96.50, 0.1449), "9": (111.35, 0.1462), "15": (199.59, 0.1462)}
    g = _grille(corrige, "base", "2016-08-01")
    for k, (abo, kwh) in edf.items():
        assert (g["puissances"][k]["abonnement_ttc"], g["puissances"][k]["prix_ttc"]["base"]) == (abo, kwh), k


def test_correction_bareme_sans_effet_si_open_data_juste(corrige):
    h = copy.deepcopy(corrige)
    for g in h["base"]["grilles"]:
        g.pop("correction_ttc", None)
    journal = cre_opendata.corriger(h, cre_opendata.charger_corrections(), CONFIG)
    assert sum("barème open data déjà juste" in l for l in journal) == 2
    assert not any("correction_ttc" in g for g in h["base"]["grilles"])


def test_historique_base_janvier_2016_corrige(corrige):
    """La période révisée au 1er janvier 2016 part du barème corrigé : grille EDF de janvier 2016 à 0,03 c€ près."""
    from tarif_kwh import reconcile

    od = reconcile.taxes_kwh_opendata(corrige, CONFIG)
    h = publish.construire_historique(corrige, None, {}, date(2026, 11, 23), None, CONFIG, od)
    g = next(g for g in h["options"]["base"]["grilles"] if g["date_debut"] == "2016-01-01")
    p = g["puissances"]["6"]
    assert p["prix_ht"]["base"] == 0.0932 and p["abonnement_ttc"] == 88.42
    assert abs(p["prix_ttc"]["base"] - 0.1503) <= 0.00031  # EDF au 1er janvier 2016 : 15,03 c€
