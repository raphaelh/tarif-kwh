"""Tempo d'août 2013 à juillet 2016, avant l'open data CRE : barème HT de Jour Tempo (arrêtés),
contrôlé par les grilles Tarif Bleu EDF archivées (config/grilles_edf_archivees.json)."""
import copy
from datetime import date

import pytest
from conftest import CSV, FIX

from tarif_kwh import publish, reconcile, taxes
from tarif_kwh.reconcile import grille_to_dict
from tarif_kwh.sources import cre_opendata, jourtempo

CONFIG = taxes.charger_config()
AUJOURD_HUI = date(2026, 11, 23)
BAREMES = ("2013-08-01", "2014-11-01", "2015-08-01")
ARCHIVEES = reconcile.charger_grilles_edf_archivees()


@pytest.fixture(scope="module")
def jt():
    g = jourtempo.parse((FIX / "jourtempo_trve-historique.csv").read_bytes(), (FIX / "jourtempo_trve-sources.csv").read_bytes())
    return {d.isoformat(): v for (o, d), v in g.items() if o == "tempo"}


@pytest.fixture(scope="module")
def od_hist():
    hist = {o: {"url": "u", "grilles": cre_opendata.parse_historique(p.read_bytes(), o)} for o, p in CSV.items()}
    cre_opendata.corriger(hist, cre_opendata.charger_corrections(), CONFIG)
    return hist


@pytest.fixture(scope="module")
def registre(jt, od_hist):
    return {
        "taxes_kwh_opendata": reconcile.taxes_kwh_opendata(od_hist, CONFIG),
        "grilles": {"tempo": {d: {"jourtempo": grille_to_dict(jt[d])} for d in BAREMES}},
    }


def _recouper(jt, registre, d, archivees=None):
    return reconcile.recouper(
        "tempo", date.fromisoformat(d), {"jourtempo": jt[d]}, registre, CONFIG, AUJOURD_HUI, [], archivees
    )


def test_jourtempo_bareme_2013(jt):
    """Arrêté du 26 juillet 2013 : 9 à 36 kVA, six prix HT."""
    g = jt["2013-08-01"]
    assert sorted(g.puissances) == [9, 12, 15, 18, 24, 30, 36]
    assert g.puissances[9].abonnement_ht == 96.6
    assert g.puissances[9].prix_ht == {
        "bleu_hc": 0.044, "bleu_hp": 0.0576, "blanc_hc": 0.0719, "blanc_hp": 0.0907, "rouge_hc": 0.1525, "rouge_hp": 0.4401,
    }
    assert g.meta["texte"] == "jorf_arrete_2013-07-26"


def test_grilles_edf_archivees():
    """Cinq grilles EDF de 2013 à 2016, 9 à 36 kVA sauf 24 kVA ; coquille de janvier 2015 corrigée."""
    assert [a["date"] for a in ARCHIVEES] == ["2013-08-01", "2014-02-01", "2015-01-01", "2015-08-01", "2016-01-01"]
    for a in ARCHIVEES:
        assert a["option"] == "tempo" and a["source"].startswith("https://web.archive.org/")
        assert sorted(a["puissances"], key=int) == ["9", "12", "15", "18", "30", "36"]
    jan15 = ARCHIVEES[2]
    assert jan15["puissances"]["36"]["prix_ttc"]["blanc_hc"] == jan15["puissances"]["9"]["prix_ttc"]["blanc_hc"] == 0.1255
    assert "15,55" in jan15["coquilles"][0]


@pytest.mark.parametrize("d", BAREMES)
def test_bareme_concorde_avec_grilles_edf(jt, registre, d):
    """Chaque barème Jour Tempo redonne au centime le TTC des grilles EDF de sa période."""
    g, pb = _recouper(jt, registre, d)
    assert pb == []
    assert g["statut"] == "en_vigueur" and g["ttc_estime"] is True
    attendues = {"2013-08-01": ["2013-08-01", "2014-02-01"], "2014-11-01": ["2015-01-01"], "2015-08-01": ["2015-08-01", "2016-01-01"]}[d]
    assert g["taxes"]["grilles_edf_archivees"] == attendues
    assert [s["type"] for s in g["sources"]] == ["jourtempo"] + ["edf_grille"] * len(attendues)
    # Abonnement TTC : première grille EDF de la période ; 24 kVA absent des grilles EDF
    premiere = next(a for a in ARCHIVEES if a["date"] == attendues[0])
    for k, p in g["puissances"].items():
        e = premiere["puissances"].get(k)
        assert p["abonnement_ttc"] == (e["abonnement_ttc"] if e else None), k
    # TTC au kWh : HT + taxes de l'open data CRE à la même date (comme l'EJP)
    t = registre["taxes_kwh_opendata"][d]["valeur"]
    tva = 0.196 if d < "2014" else 0.2
    assert g["prix_ttc"] == {per: taxes.kwh_ttc(v, t, tva) for per, v in g["prix_ht"].items()}


def test_abonnement_2013(jt, registre):
    g, _ = _recouper(jt, registre, "2013-08-01")
    assert g["puissances"]["9"]["abonnement_ttc"] == 121.94 and g["puissances"]["9"]["abonnement_ht"] == 96.6
    assert g["puissances"]["9"]["abonnement_ttc_mensuel"] == round(121.94 / 12, 2)
    assert g["taxes"]["abonnement_ttc_de"] == "grille EDF archivée du 2013-08-01"


def test_coquille_non_corrigee_rejette(jt, registre):
    """Avec le 15,55 c€ imprimé par EDF, la grille de novembre 2014 serait rejetée."""
    archivees = copy.deepcopy(ARCHIVEES)
    archivees[2]["puissances"]["36"]["prix_ttc"]["blanc_hc"] = 0.1555
    g, pb = _recouper(jt, registre, "2014-11-01", archivees)
    assert g is None and any("36 kVA blanc_hc : TTC EDF 0.1555" in m for m in pb)


def test_taxes_trop_loin_de_l_open_data_rejette(jt, registre):
    """Un barème HT décalé de 0,1 c€ partout reste cohérent entre périodes, mais pas avec les taxes de la CRE."""
    archivees = copy.deepcopy(ARCHIVEES)
    for p in archivees[0]["puissances"].values():
        p["prix_ttc"] = {per: round(v + 0.0012, 4) for per, v in p["prix_ttc"].items()}
    g, pb = _recouper(jt, registre, "2013-08-01", archivees)
    assert g is None and any("open data CRE 0.02278" in m for m in pb)


def test_sans_grille_edf_abonnement_inconnu(jt, registre):
    g, pb = _recouper(jt, registre, "2014-11-01", [])
    assert pb == [] and all(p["abonnement_ttc"] is None for p in g["puissances"].values())
    assert [s["type"] for s in g["sources"]] == ["jourtempo"]


def test_historique_tempo_depuis_2013(jt, registre, od_hist):
    """Tempo commence en août 2013, révisé chaque 1er janvier, sans trou jusqu'à l'open data (août 2016)."""
    ok, pb, _ = publish.grilles_validees("tempo", registre, CONFIG, AUJOURD_HUI, [], set())
    assert pb == {} and sorted(ok) == list(BAREMES)
    h = publish.construire_historique(
        od_hist, None, {"tempo": ok}, AUJOURD_HUI, {"tempo": set(BAREMES)}, CONFIG, registre["taxes_kwh_opendata"]
    )
    grilles = h["options"]["tempo"]["grilles"]
    assert [(g["date_debut"], g["date_fin"]) for g in grilles][:7] == [
        ("2013-08-01", "2013-12-31"), ("2014-01-01", "2014-10-31"), ("2014-11-01", "2014-12-31"),
        ("2015-01-01", "2015-07-31"), ("2015-08-01", "2015-12-31"), ("2016-01-01", "2016-07-31"),
        ("2016-08-01", "2017-07-31"),
    ]
    assert [s["type"] for s in grilles[6]["sources"]] == ["cre_opendata"]
    # Révisions de janvier : TTC au kWh à moins de 0,05 c€ des grilles EDF de la même année
    # (taxes de l'open data CRE, TCFE comprises, au lieu de celles d'EDF)
    for g, a in ((grilles[1], ARCHIVEES[1]), (grilles[3], ARCHIVEES[2]), (grilles[5], ARCHIVEES[4])):
        assert "revision_ttc" in g
        for k, e in a["puissances"].items():
            for per, v in e["prix_ttc"].items():
                assert abs(g["puissances"][k]["prix_ttc"][per] - v) <= 0.0005, (g["date_debut"], k, per)
    # Janvier 2016 : au centime
    for k, e in ARCHIVEES[4]["puissances"].items():
        for per, v in e["prix_ttc"].items():
            assert abs(grilles[5]["puissances"][k]["prix_ttc"][per] - v) <= reconcile.TOL_KWH
    # Relu hors ligne : identique
    h2 = publish.construire_historique(
        None, {"options": h["options"]}, {"tempo": ok}, AUJOURD_HUI, {"tempo": set(BAREMES)}, CONFIG, registre["taxes_kwh_opendata"]
    )
    assert h2["options"]["tempo"] == h["options"]["tempo"]
