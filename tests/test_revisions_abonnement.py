"""Abonnement TTC révisé par le TURPE en 2014 (config/revisions_abonnement.json) : TURPE 4 au 1er janvier,
indexé au 1er août, sans nouveau barème TRVE. La CTA (27,04 % de la part fixe du TURPE) change."""
from datetime import date

import pytest
from conftest import CSV, FIX

from tarif_kwh import publish, reconcile, taxes
from tarif_kwh.reconcile import grille_to_dict
from tarif_kwh.sources import cre_opendata, jourtempo

CONFIG = taxes.charger_config()
CONF = taxes.charger_revisions_abonnement()
T3, T4, T4_AOUT, T15, T16, T17 = CONF["periodes"]
AUJOURD_HUI = date(2026, 11, 23)
ARCHIVEES = {a["date"]: a for a in reconcile.charger_grilles_edf_archivees()}
TOL = 0.011  # €/an : EDF et la CRE arrondissent parfois la CTA différemment

# Grille Tarif Bleu EDF « en vigueur à compter du 1er février 2014 » (web.archive.org, 24/02/2014),
# abonnements annuels TTC des options Base et Heures creuses.
EDF_FEVRIER_2014 = {
    "base": {3: 52.11, 6: 84.56, 9: 111.95, 12: 172.62, 15: 198.04, 18: 227.77, 24: 484.73, 30: 598.95, 36: 693.80},
    "hphc": {6: 90.98, 9: 121.90, 12: 197.78, 15: 229.23, 18: 257.91, 24: 541.06, 30: 639.46, 36: 735.83},
}


@pytest.fixture(scope="module")
def od_hist():
    hist = {o: {"url": "u", "grilles": cre_opendata.parse_historique(p.read_bytes(), o)} for o, p in CSV.items()}
    cre_opendata.corriger(hist, cre_opendata.charger_corrections(), CONFIG)
    return hist


@pytest.fixture(scope="module")
def od(od_hist):
    return {o: {g["date_debut"]: g for g in b["grilles"]} for o, b in od_hist.items()}


@pytest.fixture(scope="module")
def jt():
    g = jourtempo.parse((FIX / "jourtempo_trve-historique.csv").read_bytes(), (FIX / "jourtempo_trve-sources.csv").read_bytes())
    return {d.isoformat(): v for (o, d), v in g.items() if o == "tempo"}


def _abo(option, kva, ht, periode):
    return taxes.abonnement_ttc_turpe(option, kva, ht, periode, CONF)


def test_turpe3_redonne_aout_2013(od, jt):
    """Référence : la règle (CU pour la Base et au-delà de 18 kVA, MU sinon) redonne l'open data et EDF d'août 2013."""
    for o in ("base", "hphc"):
        for k, p in od[o]["2013-08-01"]["puissances"].items():
            assert _abo(o, int(k), p["abonnement_ht"], T3) == p["abonnement_ttc"], (o, k)
    for k, e in ARCHIVEES["2013-08-01"]["puissances"].items():
        assert abs(_abo("tempo", int(k), jt["2013-08-01"].puissances[int(k)].abonnement_ht, T3) - e["abonnement_ttc"]) <= TOL, k


def test_turpe4_redonne_grille_edf_fevrier_2014(od, jt):
    """Même barème HT qu'en août 2013, CTA du TURPE 4 : abonnements de la grille EDF de février 2014."""
    for o, abos in EDF_FEVRIER_2014.items():
        ht = od[o]["2013-08-01"]["puissances"]
        for kva, v in abos.items():
            if str(kva) in ht:  # Base 18 à 36 kVA en extinction : absente de l'open data
                assert abs(_abo(o, kva, ht[str(kva)]["abonnement_ht"], T4) - v) <= TOL, (o, kva)
    for k, e in ARCHIVEES["2014-02-01"]["puissances"].items():
        assert abs(_abo("tempo", int(k), jt["2013-08-01"].puissances[int(k)].abonnement_ht, T4) - e["abonnement_ttc"]) <= TOL, k


def test_turpe4_aout_2014_redonne_novembre_2014(od, jt):
    """TURPE indexé au 1er août 2014 : abonnements de l'open data de novembre 2014 et de la grille EDF de janvier 2015."""
    for o in ("base", "hphc"):
        for k, p in od[o]["2014-11-01"]["puissances"].items():
            assert abs(_abo(o, int(k), p["abonnement_ht"], T4_AOUT) - p["abonnement_ttc"]) <= TOL, (o, k)
    for k, e in ARCHIVEES["2015-01-01"]["puissances"].items():
        assert abs(_abo("tempo", int(k), jt["2014-11-01"].puissances[int(k)].abonnement_ht, T4_AOUT) - e["abonnement_ttc"]) <= TOL, k


# Grille Tarif Bleu EDF du 1er août 2015 (web.archive.org), abonnements annuels TTC Base et Heures creuses.
EDF_AOUT_2015 = {
    "base": {3: 54.45, 6: 88.42, 9: 117.20, 12: 180.11, 15: 206.57, 18: 237.59, 24: 505.49, 30: 624.69, 36: 723.39},
    "hphc": {6: 94.46, 9: 126.52, 12: 204.77, 15: 237.26, 18: 266.84, 24: 560.18, 30: 661.91, 36: 761.37},
}


def test_turpe_aout_2015_redonne_grille_edf(od, jt):
    """TURPE au 1er août 2015 : abonnements de la grille EDF d'août 2015 ; l'open data HP/HC garde la CTA d'août 2014."""
    for o, abos in EDF_AOUT_2015.items():
        ht = od[o]["2015-08-01"]["puissances"]
        for kva, v in abos.items():
            if str(kva) in ht:
                assert abs(_abo(o, kva, ht[str(kva)]["abonnement_ht"], T15) - v) <= TOL, (o, kva)
    for k, e in ARCHIVEES["2015-08-01"]["puissances"].items():
        assert abs(_abo("tempo", int(k), jt["2015-08-01"].puissances[int(k)].abonnement_ht, T15) - e["abonnement_ttc"]) <= TOL, k
    for k, p in od["hphc"]["2015-08-01"]["puissances"].items():  # open data HP/HC : CTA du TURPE d'août 2014
        assert p["abonnement_ttc"] == _abo("hphc", int(k), p["abonnement_ht"], T4_AOUT), k
        assert p["abonnement_ttc"] < EDF_AOUT_2015["hphc"][int(k)] - 0.02, k


def test_historique_aout_2015(historique):
    """HP/HC corrigé d'août 2015 à juillet 2016 (révision de janvier 2016 comprise) ; Base et Tempo intacts."""
    h, _, _ = historique
    hphc = _periodes(h, "hphc")
    for d in ("2015-08-01", "2016-01-01"):
        g = hphc[d]
        assert g["revision_abonnement"]["date"] == "2015-08-01" and g["revision_abonnement"]["sources"] == [T15["url"]]
        assert g["ttc_estime"] is True and g["statut"] == "en_vigueur"
        assert g["puissances"]["9"]["abonnement_ttc"] == 126.52
        for k, p in g["puissances"].items():
            assert abs(p["abonnement_ttc"] - EDF_AOUT_2015["hphc"][int(k)]) <= TOL, k
    assert hphc["2015-08-01"]["date_fin"] == "2015-12-31"
    assert hphc["2016-08-01"]["revision_abonnement"]["date"] == "2016-08-01"
    for o in ("base", "tempo"):
        for d in ("2015-08-01", "2016-01-01", "2016-08-01"):
            assert "revision_abonnement" not in _periodes(h, o)[d], (o, d)


# Grille Tarif Bleu EDF annuelle « applicable au 1er août 2016 » (web.archive.org, 18/10/2016) : dernière grille
# EDF à imprimer l'abonnement annuel ; ensuite, seulement le mensuel, qui ne permet pas un contrôle au centime.
EDF_AOUT_2016 = {
    "base": {6: 96.50, 9: 111.35, 12: 172.78, 15: 199.59},
    "hphc": {6: 100.51, 9: 117.50, 12: 183.25, 15: 212.05, 18: 239.84, 24: 495.65, 30: 599.74, 36: 703.07},
    "tempo": {9: 116.24, 12: 181.98, 15: 210.02, 18: 237.05, 30: 597.21, 36: 700.80},
}


def test_turpe_aout_2016_redonne_grille_edf(od):
    """TURPE au 1er août 2016 : grille EDF annuelle d'août 2016 ; l'open data HP/HC garde la CTA de novembre 2014."""
    for o, abos in EDF_AOUT_2016.items():
        ht = od[o]["2016-08-01"]["puissances"]
        for kva, v in abos.items():
            assert abs(_abo(o, kva, ht[str(kva)]["abonnement_ht"], T16) - v) <= TOL, (o, kva)
    for k, p in od["hphc"]["2016-08-01"]["puissances"].items():
        assert p["abonnement_ttc"] == _abo("hphc", int(k), p["abonnement_ht"], T4_AOUT), k
        assert p["abonnement_ttc"] < EDF_AOUT_2016["hphc"][int(k)] - 0.1, k


def test_historique_aout_2016(historique):
    """HP/HC d'août 2016 à juillet 2017 corrigé ; la grille d'août 2017 (TURPE 5) n'est pas touchée."""
    h, _, _ = historique
    hphc = _periodes(h, "hphc")
    g = hphc["2016-08-01"]
    assert g["date_fin"] == "2017-07-31" and g["statut"] == "en_vigueur" and g["ttc_estime"] is True
    assert g["revision_abonnement"]["sources"] == [T16["url"]]
    for k, p in g["puissances"].items():
        assert abs(p["abonnement_ttc"] - EDF_AOUT_2016["hphc"][int(k)]) <= TOL, k
    assert "revision_abonnement" not in hphc["2017-08-01"]


def _periodes(h, option):
    return {g["date_debut"]: g for g in h["options"][option]["grilles"]}


@pytest.fixture(scope="module")
def historique(od_hist, jt):
    taxes_od = reconcile.taxes_kwh_opendata(od_hist, CONFIG)
    dates = ("2013-08-01", "2014-11-01", "2015-08-01")
    r = {"taxes_kwh_opendata": taxes_od, "grilles": {"tempo": {d: {"jourtempo": grille_to_dict(jt[d])} for d in dates}}}
    ok, pb, _ = publish.grilles_validees("tempo", r, CONFIG, AUJOURD_HUI, [], set())
    assert pb == {}
    args = ({"tempo": ok}, AUJOURD_HUI, {"tempo": set(dates)}, CONFIG, taxes_od, CONF)
    h = publish.construire_historique(od_hist, None, *args)
    return h, publish.construire_historique(None, {"options": h["options"]}, *args), od_hist


@pytest.mark.parametrize("option", ["base", "hphc", "tempo"])
def test_historique_2014(historique, option):
    h, _, _ = historique
    g = _periodes(h, option)
    assert [(d, g[d]["date_fin"]) for d in ("2013-08-01", "2014-01-01", "2014-08-01", "2014-11-01")] == [
        ("2013-08-01", "2013-12-31"), ("2014-01-01", "2014-07-31"), ("2014-08-01", "2014-10-31"), ("2014-11-01", "2014-12-31"),
    ]
    assert "revision_abonnement" not in g["2013-08-01"] and "revision_abonnement" not in g["2014-11-01"]
    for d, per in (("2014-01-01", T4), ("2014-08-01", T4_AOUT)):
        assert g[d]["revision_abonnement"]["date"] == d and g[d]["revision_abonnement"]["sources"] == [per["url"]]
        assert g[d]["ttc_estime"] is True and g[d]["statut"] == "en_vigueur"
        for k, p in g[d]["puissances"].items():
            if p["abonnement_ttc"] is not None:
                assert p["abonnement_ttc"] == _abo(option, int(k), p["abonnement_ht"], per)
            # même barème HT et même TTC au kWh que la période précédente de 2014
            assert p["prix_ht"] == g["2013-08-01"]["puissances"][k]["prix_ht"]
        assert g["2014-08-01"]["puissances"][k]["prix_ttc"] == g["2014-01-01"]["puissances"][k]["prix_ttc"]
    assert g["2014-08-01"]["revision_ttc"]["date"] == "2014-08-01"


def test_historique_valeurs(historique):
    h, _, _ = historique
    assert _periodes(h, "base")["2014-01-01"]["puissances"]["6"]["abonnement_ttc"] == 84.56  # août 2013 : 84,05
    assert _periodes(h, "base")["2014-08-01"]["puissances"]["6"]["abonnement_ttc"] == 84.46
    tempo = _periodes(h, "tempo")
    assert tempo["2014-01-01"]["puissances"]["9"]["abonnement_ttc"] == 121.02  # EDF : 121,01
    assert "24" not in tempo["2014-01-01"]["puissances"]  # pas de Tempo 24 kVA avant août 2026
    assert tempo["2014-11-01"]["puissances"]["9"]["abonnement_ttc"] == 125.98  # grille EDF, inchangée


def test_open_data_intacte_et_relecture_stable(historique):
    """La révision ne modifie pas l'open data lue, et l'historique relu hors ligne est identique."""
    h, h2, od_hist = historique
    base = {g["date_debut"]: g for g in od_hist["base"]["grilles"]}
    assert "2014-01-01" not in base  # janvier 2014 : période révisée par publish (CSPE, TVA), pas une grille open data
    assert base["2013-08-01"]["puissances"]["6"]["abonnement_ttc"] == 84.05
    assert h2["options"] == h["options"]


def test_sans_configuration_rien(od_hist):
    h = publish.construire_historique(od_hist, None, {}, AUJOURD_HUI, None, CONFIG)
    assert not any("revision_abonnement" in g for b in h["options"].values() for g in b["grilles"])


def test_turpe5_aout_2017(od):
    """TURPE 5 (gestion provisoire) : open data HP/HC et Tempo d'août 2017 au centime ; la Base garde la CTA d'août 2016."""
    for o in ("hphc", "tempo"):
        for k, p in od[o]["2017-08-01"]["puissances"].items():
            assert p["abonnement_ttc"] == _abo(o, int(k), p["abonnement_ht"], T17), (o, k)
    for k, p in od["base"]["2017-08-01"]["puissances"].items():
        assert p["abonnement_ttc"] == _abo("base", int(k), p["abonnement_ht"], T16), k
        assert p["abonnement_ttc"] != _abo("base", int(k), p["abonnement_ht"], T17), k


def test_historique_aout_2017(historique, od):
    """Base d'août 2017 à janvier 2018 révisée (TURPE 5) ; HP/HC, Tempo et la Base de février 2018 intacts."""
    h, _, _ = historique
    base = _periodes(h, "base")
    g = base["2017-08-01"]
    assert g["revision_abonnement"]["date"] == "2017-08-01" and g["revision_abonnement"]["sources"] == [T17["url"]]
    assert g["statut"] == "en_vigueur" and g["ttc_estime"] is True
    assert {k: p["abonnement_ttc"] for k, p in g["puissances"].items()} == {
        "3": 67.03, "6": 100.73, "9": 118.74, "12": 137.12, "15": 155.63,
    }
    assert g["date_fin"] == "2018-01-31" and "revision_abonnement" not in base["2018-02-01"]
    for o in ("hphc", "tempo"):
        assert "revision_abonnement" not in _periodes(h, o)["2017-08-01"], o
