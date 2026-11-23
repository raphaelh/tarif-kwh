"""Historique EJP : source Jour Tempo (HT depuis 2023) et CTA calculée par le TURPE."""
import copy
from datetime import date

import pytest
from conftest import ANNEXES, EDF_EJP, EDF_EJP_2025, FIX

from tarif_kwh import reconcile, taxes
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

def test_jourtempo_ejp_depuis_2023(jt):
    """EJP seulement, HT seulement, à partir de février 2023 (avant : TCFE non recalculables)."""
    assert {o for o, _ in jt} == {"ejp"}
    assert min(d for _, d in jt) == date(2023, 2, 1)
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


@pytest.mark.parametrize("option,d", [("ejp", date(2023, 2, 1)), ("ejp", date(2025, 2, 1)), ("ejp", date(2027, 8, 1)), ("tempo", date(2026, 2, 1))])
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
