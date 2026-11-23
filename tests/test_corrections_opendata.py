"""TTC de l'open data CRE reconnus faux : Tempo 2022, tranché par les grilles EDF archivées."""
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
    assert len(journal) == 2 and all("recalculé" in l for l in journal), journal
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
