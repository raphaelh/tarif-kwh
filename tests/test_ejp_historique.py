"""Historique EJP : source Jour Tempo (HT depuis 2013), taxes d'avant 2023 et CTA calculée par le TURPE."""
import copy
from datetime import date

import pytest
from conftest import ANNEXES, EDF_EJP, EDF_EJP_2025, FIX

from tarif_kwh import publish, reconcile, taxes
from tarif_kwh.reconcile import grille_to_dict
from tarif_kwh.sources import cre_deliberation, edf_grille, jourtempo

JT_HIST = FIX / "jourtempo_trve-historique.csv"
JT_SOURCES = FIX / "jourtempo_trve-sources.csv"
EDF_EJP_2023 = FIX / "edf_grille_ejp_2023-02-01.pdf"  # capture archive.org
CONFIG = taxes.charger_config()
KVAS = (9, 12, 15, 18, 36)


@pytest.fixture(scope="module")
def jt():
    return jourtempo.parse(JT_HIST.read_bytes(), JT_SOURCES.read_bytes())


@pytest.fixture(scope="module")
def ejp_cre():
    return {d: cre_deliberation.parse_annexe_b(p.read_bytes(), p.name)["ejp"] for d, p in ANNEXES.items()}


# --- Jour Tempo ----------------------------------------------------------------------

def test_jourtempo_ejp_depuis_2013(jt):
    """EJP seulement, HT seulement, depuis août 2013."""
    assert {o for o, _ in jt} == {"ejp"}
    assert min(d for _, d in jt) == date(2013, 8, 1)
    # Délibération CRE n° 2017-166, tableau « TARIF BLEU - OPTION EJP RESIDENTIEL »
    g = jt[("ejp", date(2017, 8, 1))]
    assert g.puissances[9].abonnement_ht == 93.72 and g.puissances[36].abonnement_ht == 210.36
    assert g.puissances[9].prix_ht == {"normal": 0.0845, "pointe": 0.2793}
    g = jt[("ejp", date(2023, 2, 1))]
    assert sorted(g.puissances) == list(KVAS)
    assert g.puissances[9].abonnement_ht == 145.56
    assert g.puissances[9].prix_ht == {"normal": 0.1078, "pointe": 1.2279}
    assert g.url == "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000047074589"  # arrêté du 30 janvier 2023
    assert g.meta["texte"] == "jorf_arrete_2023-01-30"


@pytest.mark.parametrize("d", sorted(ANNEXES))
def test_jourtempo_egal_deliberation_cre(jt, ejp_cre, d):
    cre, j = ejp_cre[d], jt[("ejp", date.fromisoformat(d))]
    assert {k: (p.abonnement_ht, p.prix_ht) for k, p in cre.puissances.items()} == {
        k: (p.abonnement_ht, p.prix_ht) for k, p in j.puissances.items()
    }


def test_jourtempo_2023_egal_grille_edf(jt):
    """Février 2023 (bouclier) : HT de l'arrêté + accise 0,1 c€ + TVA = TTC de la grille EDF archivée."""
    edf = edf_grille.parse_grille_ejp(EDF_EJP_2023.read_bytes())["ejp"]
    assert edf.date_effet == date(2023, 2, 1)
    assert edf.meta["accise_eur_kwh"] == 0.001  # « … (CSPE)1, d'un montant de 0,10 cts »
    for k, p in jt[("ejp", date(2023, 2, 1))].puissances.items():
        assert {per: taxes.kwh_ttc(v, 0.001, 0.20) for per, v in p.prix_ht.items()} == edf.puissances[k].prix_ttc


def test_jourtempo_bareme_incomplet():
    lignes = JT_HIST.read_text().splitlines()
    sans = [l for l in lignes if not l.startswith("2023-02-01,ejp,12,kwh_ejp_pointe")]
    with pytest.raises(jourtempo.ParseError, match="incomplet"):
        jourtempo.parse("\n".join(sans).encode(), JT_SOURCES.read_bytes())


def test_jourtempo_source_inconnue():
    with pytest.raises(jourtempo.ParseError, match="source inconnue"):
        jourtempo.parse(JT_HIST.read_bytes(), b"source_id,type,titre,date,numero,url,consulte_le\n")


def test_recoupement_jourtempo_contredit_cre(jt, ejp_cre):
    j = copy.deepcopy(jt[("ejp", date(2026, 8, 1))])
    j.puissances[9].prix_ht["pointe"] = 0.33
    obs = {"cre_deliberation": ejp_cre["2026-08-01"], "jourtempo": j}
    g, pb = reconcile.recouper("ejp", date(2026, 8, 1), obs, {}, CONFIG, date(2026, 11, 23))
    assert g is None and any("Jour Tempo" in m for m in pb)


def test_recoupement_jourtempo_seul_2023(jt):
    """Août 2023 : arrêté seul (pas de délibération appliquée, pas de grille EDF archivée)."""
    g, pb = reconcile.recouper("ejp", date(2023, 8, 1), {"jourtempo": jt[("ejp", date(2023, 8, 1))]}, {}, CONFIG, date(2026, 11, 23))
    assert pb == []
    assert g["statut"] == "en_vigueur" and g["ttc_estime"] is True
    assert g["puissances"]["9"]["prix_ttc"] == {"normal": 0.1518, "pointe": 1.4958}


# --- Avant 2023 : taxes au kWh de l'open data CRE ------------------------------------------

def _hist_opendata(corrige: bool) -> dict:
    from conftest import CSV

    from tarif_kwh.sources import cre_opendata

    hist = {o: {"url": "u", "grilles": cre_opendata.parse_historique(p.read_bytes(), o)} for o, p in CSV.items()}
    if corrige:  # comme collect.py
        cre_opendata.corriger(hist, cre_opendata.charger_corrections(), CONFIG)
    return hist


@pytest.fixture(scope="module")
def taxes_od():
    """Taxes au kWh de l'open data, Tempo 2022 corrigé (config/corrections_opendata.json)."""
    return reconcile.taxes_kwh_opendata(_hist_opendata(True), CONFIG)


@pytest.fixture(scope="module")
def taxes_od_brut():
    """Taxes au kWh de l'open data telle que publiée par la CRE (Tempo 2022 faux)."""
    return reconcile.taxes_kwh_opendata(_hist_opendata(False), CONFIG)


def test_taxes_kwh_opendata(taxes_od, taxes_od_brut):
    """CSPE + TCFE de la CRE par date : cohérentes entre options de 2013 à 2022, une fois Tempo 2022 corrigé."""
    assert max(taxes_od) < "2023-02-01"
    assert taxes_od["2013-08-01"]["valeur"] == 0.02278  # TVA 19,6 % avant 2014
    assert taxes_od["2021-08-01"]["valeur"] == 0.03245
    for d, t in taxes_od.items():
        assert t["ecart"] <= reconcile.TOL_TAXES_OPTIONS, d
        assert (taxes_od_brut[d]["ecart"] > reconcile.TOL_TAXES_OPTIONS) == d.startswith("2022"), d
    # Open data brute, 2022 : Base et HP/HC à 7,6 €/MWh, Tempo à 10,9 €/MWh
    assert taxes_od_brut["2022-02-01"]["options"]["base"] == 0.0076
    assert taxes_od_brut["2022-02-01"]["options"]["tempo"] == 0.01093
    # Corrigée d'après les grilles EDF 2022 : 7,6 €/MWh partout
    for d in ("2022-02-01", "2022-08-01"):
        assert taxes_od[d]["valeur"] == 0.00763  # = TCFE 0,6630 + CSPE 0,10 c€ des grilles EDF 2022
        assert all(abs(v - 0.0076) <= 0.0001 for v in taxes_od[d]["options"].values()), taxes_od[d]  # arrondi


def test_recoupement_avant_2023(jt, taxes_od):
    """Août 2021 : TTC au kWh = (HT + taxes CRE) × 1,2, abonnement TTC inconnu."""
    r = {"taxes_kwh_opendata": taxes_od}
    g, pb = reconcile.recouper("ejp", date(2021, 8, 1), {"jourtempo": jt[("ejp", date(2021, 8, 1))]}, r, CONFIG, date(2026, 11, 23))
    assert pb == []
    assert g["ttc_estime"] is True and g["statut"] == "en_vigueur"
    assert g["prix_ttc"] == {"normal": 0.1498, "pointe": 0.3741}
    assert all(p["abonnement_ttc"] is None and p["abonnement_ht"] for p in g["puissances"].values())
    assert "open data CRE du 2021-08-01" in g["taxes"]["accise_source"]
    # Août 2013 : TVA 19,6 %
    g, pb = reconcile.recouper("ejp", date(2013, 8, 1), {"jourtempo": jt[("ejp", date(2013, 8, 1))]}, r, CONFIG, date(2026, 11, 23))
    assert pb == [] and g["taxes"]["tva_energie"] == 0.196
    assert g["prix_ttc"] == {"normal": taxes.kwh_ttc(0.0673, 0.02278, 0.196), "pointe": taxes.kwh_ttc(0.4313, 0.02278, 0.196)}


def test_recoupement_avant_2023_rejete(jt, taxes_od_brut):
    """Taxes incohérentes entre options (2022 sans correction) et date sans open data : grille rejetée."""
    obs = {"jourtempo": jt[("ejp", date(2022, 2, 1))]}
    g, pb = reconcile.recouper("ejp", date(2022, 2, 1), obs, {"taxes_kwh_opendata": taxes_od_brut}, CONFIG, date(2026, 11, 23))
    assert g is None and "incohérentes" in pb[0]
    g, pb = reconcile.recouper("ejp", date(2022, 2, 1), obs, {}, CONFIG, date(2026, 11, 23))
    assert g is None and "aucune grille open data" in pb[0]


def test_historique_2022(jt, taxes_od):
    """Tempo 2022 corrigé : les taxes de l'EJP 2022 sont connues (7,63 €/MWh).

    Février 2022 reste bloqué par le contrôle de variation (pointe 27,93 -> 77,72 c€ HT, +178 %)
    tant qu'il n'est pas validé dans config/validations.json ; une fois validé, plus de trou.
    """
    dates = [date(2021, 8, 1), date(2022, 2, 1), date(2022, 8, 1), date(2023, 2, 1)]
    r = {
        "taxes_kwh_opendata": taxes_od,
        "grilles": {"ejp": {d.isoformat(): {"jourtempo": grille_to_dict(jt[("ejp", d)])} for d in dates}},
    }
    g23 = edf_grille.parse_grille_ejp(EDF_EJP_2023.read_bytes())["ejp"]
    r["grilles"]["ejp"]["2023-02-01"]["edf_grille"] = grille_to_dict(g23)
    ok, pb, _ = publish.grilles_validees("ejp", r, CONFIG, date(2026, 11, 23), [], set())
    assert sorted(pb) == ["2022-02-01"] and "variation > 40%" in pb["2022-02-01"][0]
    ok, pb, _ = publish.grilles_validees("ejp", r, CONFIG, date(2026, 11, 23), [], {("ejp", "2022-02-01")})
    assert sorted(ok) == [d.isoformat() for d in dates] and pb == {}
    for d in ("2022-02-01", "2022-08-01"):
        g = ok[d]
        assert g["ttc_estime"] is True and "open data CRE du " + d in g["taxes"]["accise_source"]
        assert g["prix_ttc"] == {"normal": taxes.kwh_ttc(0.0993, 0.00763, 0.2), "pointe": taxes.kwh_ttc(0.7772, 0.00763, 0.2)}
    h = publish.construire_historique(None, None, {"ejp": ok}, date(2026, 11, 23), {"ejp": set(r["grilles"]["ejp"])}, CONFIG)
    # (février 2023 est ensuite révisé à chaque changement de taxe de config/taxes.json)
    assert [(g["date_debut"], g["date_fin"]) for g in h["options"]["ejp"]["grilles"]][:4] == [
        ("2021-08-01", "2022-01-31"), ("2022-02-01", "2022-07-31"), ("2022-08-01", "2023-01-31"), ("2023-02-01", "2023-07-31"),
    ]


# --- Avant 2023 : révision du TTC au 1er janvier ---------------------------------------------

@pytest.fixture(scope="module")
def od_hist():
    """Open data CRE, Tempo 2022 corrigé."""
    return _hist_opendata(True)


def test_taxes_annuelles(taxes_od):
    """Première grille de chaque année."""
    a = publish.taxes_annuelles(taxes_od)
    assert a[2014] == ("2014-11-01", 0.02585) and a[2019] == ("2019-06-01", taxes_od["2019-06-01"]["valeur"])
    assert a[2022] == ("2022-02-01", 0.00763)


def test_revisions_janvier(od_hist, taxes_od):
    """CSPE +3 €/MWh en 2014, 2015 et 2016 (et TVA 20 % en 2014) : une période au 1er janvier ; rien ensuite."""
    h = publish.construire_historique(od_hist, None, {}, date(2026, 11, 23), None, CONFIG, taxes_od)
    rev = {
        o: [(g["date_debut"], g["date_fin"]) for g in b["grilles"] if "revision_ttc" in g and g["date_debut"] < "2023-02"]
        for o, b in h["options"].items()
    }
    attendu = [("2014-01-01", "2014-10-31"), ("2015-01-01", "2015-07-31"), ("2016-01-01", "2016-07-31")]
    assert rev["base"] == rev["hphc"] == attendu + [("2023-01-01", "2023-01-31")]
    assert rev["tempo"] == [("2023-01-01", "2023-01-31")]  # open data Tempo depuis août 2016
    base = {g["date_debut"]: g for g in h["options"]["base"]["grilles"]}
    assert base["2013-08-01"]["date_fin"] == "2013-12-31"
    g = base["2014-01-01"]
    assert g["ttc_estime"] is True and g["statut"] == "confirme"
    assert "TVA" in g["revision_ttc"]["motifs"][1]
    for k, p in g["puissances"].items():
        assert p["prix_ht"] == base["2013-08-01"]["puissances"][k]["prix_ht"]
        assert p["abonnement_ttc"] == base["2013-08-01"]["puissances"][k]["abonnement_ttc"]
        assert p["prix_ttc"] == {per: taxes.kwh_ttc(v, 0.02585, 0.20) for per, v in p["prix_ht"].items()}
    # Janvier 2022 : pas de révision (baisse au 1er février, avec la grille suivante)
    assert base["2021-08-01"]["date_fin"] == "2022-01-31"
    # Janvier 2023 : TCCFE dans l'accise, 1 €/MWh pour toutes les options
    for o in ("base", "hphc", "tempo"):
        g = next(g for g in h["options"][o]["grilles"] if g["date_debut"] == "2023-01-01")
        assert g["date_fin"] == "2023-01-31" and g["ttc_estime"] is True
        assert "2023-01-01" in g["revision_ttc"]["date"]
        for p in g["puissances"].values():
            assert p["prix_ttc"] == {per: taxes.kwh_ttc(v, 0.001, 0.20) for per, v in p["prix_ht"].items()}
    # Relu hors ligne (open data non téléchargé), l'historique ne se duplique pas
    h2 = publish.construire_historique(None, {"options": h["options"]}, {}, date(2026, 11, 23), None, CONFIG, taxes_od)
    assert h2["options"] == h["options"]


def test_turpe_ignore_avant_2023(jt):
    """Avant 2023, l'abonnement TTC est inconnu par construction : pas d'issue TURPE."""
    r = {"grilles": {"ejp": {"2021-08-01": {"jourtempo": grille_to_dict(jt[("ejp", date(2021, 8, 1))])}}}}
    assert reconcile.ejp_hors_turpe(r, CONFIG) == []


# --- CTA calculée par le TURPE ----------------------------------------------------------

@pytest.mark.parametrize("d,fixture", [("2025-08-01", EDF_EJP_2025), ("2026-08-01", EDF_EJP)])
def test_cta_turpe_redonne_grille_edf(ejp_cre, d, fixture):
    """Taux de CTA × (gestion + comptage + CU4 × kVA) redonne l'abonnement EDF au centime."""
    edf = edf_grille.parse_grille_ejp(fixture.read_bytes())["ejp"]
    tva = taxes.tva(date.fromisoformat(d), CONFIG, "tva_abonnement")
    for k in KVAS:
        cta, _ = taxes.cta_turpe("ejp", date.fromisoformat(d), k, CONFIG)
        ttc = taxes.abonnement_ttc(ejp_cre[d].puissances[k].abonnement_ht, cta, tva)
        assert round(ttc / 12 + 1e-9, 2) == edf.puissances[k].abonnement_ttc_mensuel, k


def test_cta_turpe_2023_redonne_grille_edf_fevrier_2024():
    """TURPE du 1er août 2023 (reporté jusqu'au 31 octobre 2024), TVA 5,5 % : grille EDF de février 2024 au centime."""
    from conftest import ANNEXE_2024, EDF_EJP_2024

    cre = cre_deliberation.parse_annexe_b(ANNEXE_2024.read_bytes(), "u", date(2024, 2, 1))["ejp"]
    edf = edf_grille.parse_grille_ejp(EDF_EJP_2024.read_bytes())["ejp"]
    for k in KVAS:
        cta, src = taxes.cta_turpe("ejp", date(2024, 2, 1), k, CONFIG)
        ttc = taxes.abonnement_ttc(cre.puissances[k].abonnement_ht, cta, 0.055)
        assert round(ttc / 12 + 1e-9, 2) == edf.puissances[k].abonnement_ttc_mensuel, k
    assert "2023-137" in src


@pytest.mark.parametrize("d,fixture,delib", [
    ("2024-11-01", FIX / "edf_grille_ejp_2024-11-01.pdf", "2024-122"),  # capture archive.org
    ("2025-02-01", FIX / "edf_grille_ejp_2025-02-01.pdf", "2025-08"),   # capture archive.org
])
def test_cta_turpe_novembre_2024_fevrier_2025_redonne_grille_edf(jt, d, fixture, delib):
    """TURPE 6 du 1er novembre 2024 et du 1er février 2025, TVA 5,5 % : grilles EDF au centime.
    En novembre 2024, seule la CTA change : le HT est celui de février 2024."""
    de = date.fromisoformat(d)
    edf = edf_grille.parse_grille_ejp(fixture.read_bytes())["ejp"]
    assert edf.date_effet == de
    ht = jt[("ejp", date(2024, 2, 1) if de.month == 11 else de)]
    for k in KVAS:
        cta, src = taxes.cta_turpe("ejp", de, k, CONFIG)
        ttc = taxes.abonnement_ttc(ht.puissances[k].abonnement_ht, cta, 0.055)
        assert round(ttc / 12 + 1e-9, 2) == edf.puissances[k].abonnement_ttc_mensuel, k
    assert delib in src


# Grilles EDF EJP d'avant le TURPE 6, en €/mois (annuel ÷ 12), recopiées par picbleu.fr
# (article « tarif EDF EJP ») ; ses tableaux de février 2023 et février 2024 sont identiques
# aux grilles EDF archivées. Aucune grille EDF EJP de cette époque n'est archivée.
EDF_EJP_TURPE_5 = {
    "2018-08-01": (129.36, 148.68, 168.00, 187.20, 303.00),
    "2019-08-01": (140.52, 162.24, 183.96, 205.56, 336.84),
    "2020-08-01": (152.16, 176.28, 200.16, 224.04, 371.28),
}


@pytest.mark.parametrize("d,delib", [("2018-08-01", "2018-148"), ("2019-08-01", "2019-138"), ("2020-08-01", "2020-095")])
def test_cta_turpe_5_cu_redonne_grilles_edf(jt, d, delib):
    """TURPE 5 bis, CTA 27,04 %, tarif CU (et non CU4) : grilles EDF EJP au centime."""
    de = date.fromisoformat(d)
    for k, annuel in zip(KVAS, EDF_EJP_TURPE_5[d]):
        cta, src = taxes.cta_turpe("ejp", de, k, CONFIG)
        ttc = taxes.abonnement_ttc(jt[("ejp", de)].puissances[k].abonnement_ht, cta, 0.055)
        assert round(ttc / 12 + 1e-9, 2) == round(annuel / 12, 2), k
        assert "27.04%" in src and "+ CU ×" in src and delib in src


def test_cta_turpe_aout_2022_cu4_redonne_grille_edf_fevrier_2023(jt):
    """TURPE 6 du 1er août 2022 en CU4 : grille EDF de février 2023 au centime (en CU, 1 à 4 €/an de trop)."""
    edf = edf_grille.parse_grille_ejp(EDF_EJP_2023.read_bytes())["ejp"]
    de = date(2023, 2, 1)
    for k in KVAS:
        cta, src = taxes.cta_turpe("ejp", de, k, CONFIG)
        ttc = taxes.abonnement_ttc(jt[("ejp", de)].puissances[k].abonnement_ht, cta, 0.055)
        assert round(ttc / 12 + 1e-9, 2) == edf.puissances[k].abonnement_ttc_mensuel, k
    assert "2022-158" in src and "CU4" in src


def test_cta_turpe_une_seule_formule_par_periode():
    cfg = copy.deepcopy(CONFIG)
    cfg["turpe_part_fixe"][0]["soutirage_fixe_cu4"] = 1.0
    with pytest.raises(ValueError):
        taxes.cta_turpe("ejp", date.fromisoformat(cfg["turpe_part_fixe"][0]["debut"]), 9, cfg)


def test_historique_revision_novembre_2024(jt):
    """TURPE du 1er novembre 2024 sans nouveau barème : l'historique EJP ouvre une période
    au TTC recalculé, qui redonne la grille EDF du 1er novembre 2024 au centime."""
    from conftest import EDF_EJP_2024

    r = {"grilles": {"ejp": {}}}
    for d in ("2024-02-01", "2025-02-01"):
        r["grilles"]["ejp"][d] = {"jourtempo": grille_to_dict(jt[("ejp", date.fromisoformat(d))])}
    r["grilles"]["ejp"]["2024-02-01"]["edf_grille"] = grille_to_dict(
        edf_grille.parse_grille_ejp(EDF_EJP_2024.read_bytes())["ejp"])
    jour = date(2026, 11, 23)
    validees = {"ejp": publish.grilles_validees("ejp", r, CONFIG, jour, [])[0]}
    h = publish.construire_historique(None, None, validees, jour, {"ejp": set(r["grilles"]["ejp"])}, CONFIG)
    g = h["options"]["ejp"]["grilles"]
    assert [(x["date_debut"], x["date_fin"], x["ttc_estime"]) for x in g[:3]] == [
        ("2024-02-01", "2024-10-31", False), ("2024-11-01", "2025-01-31", True), ("2025-02-01", "2025-07-31", True)]
    fev, nov = g[0], g[1]
    assert nov["prix_ttc"] == fev["prix_ttc"] and nov["sources"] == fev["sources"]
    assert "2024-122" in nov["revision_ttc"]["motifs"][0] and "revision_ttc" not in fev
    edf = edf_grille.parse_grille_ejp((FIX / "edf_grille_ejp_2024-11-01.pdf").read_bytes())["ejp"]
    for k in KVAS:
        assert nov["puissances"][str(k)]["abonnement_ht"] == fev["puissances"][str(k)]["abonnement_ht"]
        assert round(nov["puissances"][str(k)]["abonnement_ttc"] / 12 + 1e-9, 2) == edf.puissances[k].abonnement_ttc_mensuel, k
    # sans configuration des taxes : pas de période révisée
    sans = publish.construire_historique(None, None, validees, jour, {"ejp": set(r["grilles"]["ejp"])})
    assert [x["date_debut"] for x in sans["options"]["ejp"]["grilles"]] == ["2024-02-01", "2025-02-01"]


def test_cta_turpe_aout_2023(jt):
    """Août 2023 : arrêté seul, pas de grille EDF archivée ; abonnement calculé."""
    g, pb = reconcile.recouper("ejp", date(2023, 8, 1), {"jourtempo": jt[("ejp", date(2023, 8, 1))]}, {}, CONFIG, date(2026, 11, 23))
    assert pb == []
    assert {k: p["abonnement_ttc_mensuel"] for k, p in g["puissances"].items()} == {
        "9": 15.63, "12": 18.6, "15": 21.62, "18": 24.55, "36": 42.96,
    }
    assert "21.93%" in g["taxes"]["cta_calculee"]


def test_cta_turpe_fevrier_2026(ejp_cre):
    """Pas de grille EDF archivée : le calcul donne les montants de la grille EDF de février 2026
    (19,20 / 22,71 / 26,27 / 29,74 / 51,31 €/mois, recopiés par plusieurs comparateurs)."""
    d = date(2026, 2, 1)
    mensuel = {
        k: round(taxes.abonnement_ttc(ejp_cre["2026-02-01"].puissances[k].abonnement_ht,
                                      taxes.cta_turpe("ejp", d, k, CONFIG)[0], 0.20) / 12 + 1e-9, 2)
        for k in KVAS
    }
    assert mensuel == {9: 19.20, 12: 22.71, 15: 26.27, 18: 29.74, 36: 51.31}


@pytest.mark.parametrize("option,d", [
    ("ejp", date(2018, 7, 31)), ("ejp", date(2021, 8, 1)), ("ejp", date(2022, 7, 31)),
    ("ejp", date(2027, 8, 1)), ("tempo", date(2026, 2, 1)),
])
def test_cta_turpe_hors_perimetre(option, d):
    assert taxes.cta_turpe(option, d, 9, CONFIG) is None


def test_recoupement_ejp_fevrier_2026_abonnement_calcule(jt, ejp_cre):
    obs = {"cre_deliberation": ejp_cre["2026-02-01"], "jourtempo": jt[("ejp", date(2026, 2, 1))]}
    g, pb = reconcile.recouper("ejp", date(2026, 2, 1), obs, {}, CONFIG, date(2026, 11, 23))
    assert pb == []
    assert g["ttc_estime"] is True
    assert g["puissances"]["9"]["abonnement_ttc"] == 230.43
    assert g["puissances"]["9"]["abonnement_ttc_mensuel"] == 19.20
    assert "CU4" in g["taxes"]["cta_calculee"] and "15.00%" in g["taxes"]["cta_calculee"]
    assert [s["type"] for s in g["sources"]] == ["cre_deliberation", "jourtempo"]


def test_amorcage_accepte_grille_jourtempo(monkeypatch):
    import collect

    g23 = edf_grille.parse_grille_ejp(EDF_EJP_2023.read_bytes())["ejp"]
    monkeypatch.setattr(edf_grille, "collecter_captures_ejp", lambda: ([g23], []))
    registre = {"grilles": {"ejp": {"2023-02-01": {"jourtempo": {}}}}}
    collect.amorcer_captures_ejp(registre)
    assert "edf_grille" in registre["grilles"]["ejp"]["2023-02-01"]
    assert registre["accise_observee"] == {"2023-02-01": 0.001}


# --- Garde-fous : configuration TURPE périmée ----------------------------------------------

@pytest.fixture(scope="module")
def registre_ejp(ejp_cre):
    """Registre EJP réel d'août 2025 et août 2026 : délibération CRE + grille EDF."""
    grilles = {}
    for d, fixture in (("2025-08-01", EDF_EJP_2025), ("2026-08-01", EDF_EJP)):
        edf = edf_grille.parse_grille_ejp(fixture.read_bytes())["ejp"]
        grilles[d] = {
            "cre_deliberation": reconcile.grille_to_dict(ejp_cre[d]),
            "edf_grille": reconcile.grille_to_dict(edf),
        }
    grilles["2026-02-01"] = {"cre_deliberation": reconcile.grille_to_dict(ejp_cre["2026-02-01"])}
    return {"grilles": {"ejp": grilles}}


def test_turpe_a_jour_aucune_alerte(registre_ejp):
    assert reconcile.ejp_hors_turpe(registre_ejp, CONFIG) == []
    assert reconcile.ecarts_abonnement_ejp(registre_ejp, CONFIG) == []


def test_turpe_nouvelle_grille_hors_periode(registre_ejp):
    """Grille du 1er août 2027 proposée par la CRE, TURPE 2027 pas encore ajouté : signalée."""
    r = copy.deepcopy(registre_ejp)
    g = copy.deepcopy(r["grilles"]["ejp"]["2026-08-01"]["cre_deliberation"])
    g["date_effet"] = "2027-08-01"
    r["grilles"]["ejp"]["2027-08-01"] = {"cre_deliberation": g}
    pb = reconcile.ejp_hors_turpe(r, CONFIG)
    assert len(pb) == 1 and "2027-08-01" in pb[0] and "2027-07-31" in pb[0]


def test_turpe_periode_oubliee_meme_avec_grille_edf(registre_ejp):
    """TURPE d'août 2026 non ajouté : signalé même si la grille EDF donne l'abonnement."""
    cfg = copy.deepcopy(CONFIG)
    cfg["turpe_part_fixe"] = [p for p in cfg["turpe_part_fixe"] if p["debut"] != "2026-08-01"]
    pb = reconcile.ejp_hors_turpe(registre_ejp, cfg)
    assert len(pb) == 1 and "2026-08-01" in pb[0]


def test_turpe_trou_historique(registre_ejp, ejp_cre):
    """Février 2025 (période TURPE retirée) : silencieux avec la grille EDF, signalé sans elle."""
    cfg = copy.deepcopy(CONFIG)
    cfg["turpe_part_fixe"] = [p for p in cfg["turpe_part_fixe"] if p["debut"] != "2025-02-01"]
    r = copy.deepcopy(registre_ejp)
    g = copy.deepcopy(r["grilles"]["ejp"]["2025-08-01"]["cre_deliberation"])
    g["date_effet"] = "2025-02-01"
    r["grilles"]["ejp"]["2025-02-01"] = {"cre_deliberation": g, "edf_grille": {"puissances": {}}}
    assert reconcile.ejp_hors_turpe(r, cfg) == []
    del r["grilles"]["ejp"]["2025-02-01"]["edf_grille"]
    pb = reconcile.ejp_hors_turpe(r, cfg)
    assert len(pb) == 1 and "2025-02-01" in pb[0] and "pas de grille EDF" in pb[0]


def test_taux_cta_non_reporte(registre_ejp):
    """Passage de la CTA à 15 % (février 2026) non reporté : la grille EDF d'août 2026 diverge."""
    cfg = copy.deepcopy(CONFIG)
    cfg["cta_taux"] = [t for t in cfg["cta_taux"] if t["debut"] != "2026-02-01"]
    pb = reconcile.ecarts_abonnement_ejp(registre_ejp, cfg)
    assert {e.split(",")[0] for e in pb} == {"grille EJP du 2026-08-01"}
    assert len(pb) == len(KVAS)


def test_turpe_faux_detecte(registre_ejp):
    """Coefficient CU4 mal recopié (10,24 au lieu de 10,42) : écart sur la grille EDF d'août 2026."""
    cfg = copy.deepcopy(CONFIG)
    next(p for p in cfg["turpe_part_fixe"] if p["debut"] == "2026-08-01")["soutirage_fixe_cu4"] = 10.24
    pb = reconcile.ecarts_abonnement_ejp(registre_ejp, cfg)
    assert pb and all("2026-08-01" in e for e in pb)
    assert any("36 kVA" in e for e in pb)


def test_collecte_ouvre_les_issues_turpe(monkeypatch, tmp_path, registre_ejp):
    """main() hors ligne : une grille hors période ouvre l'issue TURPE."""
    import json

    import collect
    from tarif_kwh import issues

    r = copy.deepcopy(registre_ejp)
    g = copy.deepcopy(r["grilles"]["ejp"]["2026-08-01"]["cre_deliberation"])
    g["date_effet"] = "2027-08-01"
    r["grilles"]["ejp"]["2027-08-01"] = {"cre_deliberation": g}
    reg = tmp_path / "registre.json"
    reg.write_text(json.dumps(r), encoding="utf-8")
    monkeypatch.setattr(collect, "REGISTRE", reg)
    monkeypatch.setattr(collect, "DOCS", tmp_path / "docs")
    titres = []
    monkeypatch.setattr(issues, "alerter", lambda titre, corps: titres.append((titre, corps)))
    monkeypatch.setattr("sys.argv", ["collect.py", "--hors-ligne", "--date", "2026-11-23"])
    collect.main()
    turpe = [c for t, c in titres if t.startswith("TURPE à ajouter")]
    assert len(turpe) == 1 and "2027-08-01" in turpe[0] and "soutirage_fixe_cu4" in turpe[0]
