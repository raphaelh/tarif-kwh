"""Lecture des sources réelles (PDF/CSV/HTML enregistrés dans tests/fixtures)."""
from datetime import date
from urllib.parse import quote

import pytest
from conftest import CSV, EDF, EDF_EJP, EDF_EJP_2025, FIX, fr, lignes_csv

from tarif_kwh import taxes
from tarif_kwh.sources import cre_deliberation, cre_opendata, edf_grille

TEMPO_TTC_2026_08 = {
    "bleu_hc": 0.1356, "bleu_hp": 0.1654,
    "blanc_hc": 0.1536, "blanc_hp": 0.1921,
    "rouge_hc": 0.1615, "rouge_hp": 0.7295,
}


# --- délibérations CRE ---------------------------------------------------------

@pytest.mark.parametrize("d", ["2025-08-01", "2026-02-01", "2026-08-01"])
def test_annexe_b_dates_et_options(annexes, d):
    g = annexes[d]
    assert set(g) == {"base", "hphc", "tempo", "ejp"}
    for gr in g.values():
        assert gr.date_effet == date.fromisoformat(d)
    assert sorted(g["tempo"].puissances) == [6, 9, 12, 15, 18, 24, 30, 36]
    assert sorted(g["ejp"].puissances) == [9, 12, 15, 18, 36]
    assert sorted(g["base"].puissances) == [3, 6, 9, 12, 15, 18, 24, 30, 36]


def test_tempo_2026_08_ht_et_ttc(annexes):
    t = annexes["2026-08-01"]["tempo"]
    assert t.puissances[6].prix_ht == {
        "bleu_hc": 0.0824, "bleu_hp": 0.1072, "blanc_hc": 0.0974,
        "blanc_hp": 0.1295, "rouge_hc": 0.104, "rouge_hp": 0.5773,
    }
    # HT CRE + accise 3,062 c€/kWh + TVA 20 % = TTC attendu
    for kva, p in t.puissances.items():
        ttc = {k: taxes.kwh_ttc(v, 0.03062, 0.20) for k, v in p.prix_ht.items()}
        assert ttc == TEMPO_TTC_2026_08, kva


def test_tranche_24_30_eclatee(annexes):
    """Les annexes 2025-08 et 2026-02 regroupent 24 et 30 kVA sur une ligne « 24-30 »."""
    t = annexes["2026-02-01"]["tempo"]
    assert t.puissances[24].abonnement_ht == t.puissances[30].abonnement_ht == 396.0


@pytest.mark.parametrize(
    "d,csvdate",
    [("2025-08-01", "01/08/2025"), ("2026-02-01", "01/02/2026"), ("2026-08-01", "01/08/2026")],
)
@pytest.mark.parametrize("option", ["base", "hphc", "tempo"])
def test_annexe_b_egale_open_data_cre(annexes, d, csvdate, option):
    """HT de la délibération = HT de l'open data CRE, pour chaque puissance publiée."""
    lignes = lignes_csv(option, csvdate)
    assert lignes, f"pas de lignes {csvdate} dans le CSV {option}"
    g = annexes[d][option]
    cols = cre_opendata.COLONNES[option]
    for kva, l in lignes.items():
        p = g.puissances[kva]
        assert p.abonnement_ht == pytest.approx(fr(l["PART_FIXE_HT"]), abs=0.005), kva
        for per, (cht, _) in cols.items():
            assert p.prix_ht[per] == pytest.approx(fr(l[cht]), abs=1e-6), (kva, per)


@pytest.mark.parametrize("d,accise", [("2025-08-01", 0.02998), ("2026-02-01", 0.03085), ("2026-08-01", 0.03062)])
@pytest.mark.parametrize("option", ["base", "hphc", "tempo"])
def test_ttc_calcule_egale_open_data(annexes, d, accise, option):
    """(HT + accise) × 1,2 redonne le TTC de l'open data CRE au 1/10000 près."""
    jj, mm, aa = d[8:], d[5:7], d[:4]
    lignes = lignes_csv(option, f"{jj}/{mm}/{aa}")
    for kva, l in lignes.items():
        for per, (_, cttc) in cre_opendata.COLONNES[option].items():
            calc = taxes.kwh_ttc(annexes[d][option].puissances[kva].prix_ht[per], accise, 0.20)
            assert calc == pytest.approx(fr(l[cttc]), abs=0.00011), (kva, per)


def test_base_prix_depend_de_la_puissance(annexes):
    b = annexes["2026-08-01"]["base"]
    assert b.puissances[6].prix_ht["base"] == 0.1361
    assert b.puissances[9].prix_ht["base"] == 0.1348


def test_ejp(annexes):
    e = annexes["2026-08-01"]["ejp"]
    assert e.puissances[9].abonnement_ht == 175.20
    assert e.puissances[9].prix_ht == {"normal": 0.1185, "pointe": 0.3297}


def test_annexe_illisible():
    with pytest.raises(Exception):
        cre_deliberation.parse_annexe_b(b"%PDF-1.4 pas un vrai pdf")


def test_decouverte_liens():
    liste = (FIX / "cre_page_trve.html").read_text()
    pages = cre_deliberation.liens_deliberations_trve(liste)
    assert any("1er-fevrier-2026" in p for p in pages)
    assert all(p.startswith("https://www.cre.fr/documents/deliberations/") for p in pages)
    page = (FIX / "cre_deliberation_2025-06-19.html").read_text()
    assert cre_deliberation.liens_annexe_b(page, pages[0]) == [
        "https://www.cre.fr/fileadmin/Documents/Deliberations/2025/250619_2025-155_Proposition_TRVE_inf_36_annexe_B.pdf"
    ]


# --- grille EDF ------------------------------------------------------------------

def test_grille_edf():
    g = edf_grille.parse_grille(EDF.read_bytes())
    assert set(g) == {"base", "hphc", "tempo"}
    t = g["tempo"]
    assert t.date_effet == date(2026, 8, 1)
    assert t.meta["accise_eur_kwh"] == 0.03062
    for p in t.puissances.values():
        assert p.prix_ttc == TEMPO_TTC_2026_08
    assert t.puissances[6].abonnement_ttc_mensuel == 15.80
    assert g["hphc"].puissances[3].prix_ttc == {"hp": 0.2142, "hc": 0.1589}
    assert g["base"].puissances[3].prix_ttc == {"base": 0.2001}
    assert g["base"].puissances[36].prix_ttc == {"base": 0.1985}
    assert sorted(g["base"].puissances) == sorted(g["hphc"].puissances) == [3, 6, 9, 12, 15, 18, 24, 30, 36]


def test_grille_edf_ejp():
    g = edf_grille.parse_grille_ejp(EDF_EJP.read_bytes())
    assert set(g) == {"ejp"}
    e = g["ejp"]
    assert e.date_effet == date(2026, 8, 1)
    assert e.meta["accise_eur_kwh"] == 0.03062
    assert {k: p.abonnement_ttc_mensuel for k, p in e.puissances.items()} == {
        9: 19.52, 12: 23.14, 15: 26.81, 18: 30.37, 36: 52.60,
    }
    for p in e.puissances.values():
        assert p.prix_ttc == {"normal": 0.1789, "pointe": 0.4324}


def test_grille_edf_ejp_2025():
    """Mise en page de l'année précédente (capture archive.org) : même lecture."""
    e = edf_grille.parse_grille_ejp(EDF_EJP_2025.read_bytes())["ejp"]
    assert e.date_effet == date(2025, 8, 1)
    assert e.meta["accise_eur_kwh"] == 0.02998
    assert e.puissances[9].abonnement_ttc_mensuel == 19.32
    assert e.puissances[36].prix_ttc == {"normal": 0.1418, "pointe": 1.0867}


def test_grille_edf_ejp_refuse_autre_grille():
    with pytest.raises(edf_grille.ParseError):
        edf_grille.parse_grille_ejp(EDF.read_bytes())


def test_ejp_ttc_edf_egal_ht_cre_plus_taxes(annexes):
    """kWh : TTC EDF = HT CRE + accise + TVA ; abonnement : TTC EDF > HT CRE (CTA + TVA)."""
    cre = annexes["2026-08-01"]["ejp"]
    edf = edf_grille.parse_grille_ejp(EDF_EJP.read_bytes())["ejp"]
    assert sorted(cre.puissances) == sorted(edf.puissances)
    for k, p in cre.puissances.items():
        q = edf.puissances[k]
        assert {per: taxes.kwh_ttc(v, 0.03062, 0.20) for per, v in p.prix_ht.items()} == q.prix_ttc
        cta = q.abonnement_ttc_mensuel * 12 / 1.2 - p.abonnement_ht
        assert 15 < cta < 70, (k, cta)


def test_recoupement_ejp_abonnement_ttc_officiel(annexes):
    from tarif_kwh import reconcile

    obs = {
        "cre_deliberation": annexes["2026-08-01"]["ejp"],
        "edf_grille": edf_grille.parse_grille_ejp(EDF_EJP.read_bytes())["ejp"],
    }
    g, pb = reconcile.recouper("ejp", date(2026, 8, 1), obs, {}, taxes.charger_config(), date(2026, 11, 23))
    assert pb == []
    assert g["ttc_estime"] is False
    assert g["puissances"]["9"]["abonnement_ttc"] == 234.24
    assert g["puissances"]["9"]["abonnement_ttc_mensuel"] == 19.52


# --- open data CRE -------------------------------------------------------------

def test_date_inversee():
    assert cre_opendata.parse_date("01/08/2026") == date(2026, 8, 1)
    assert cre_opendata.parse_date("2026-01-08") == date(2026, 8, 1)  # jour/mois inversés
    assert cre_opendata.parse_date("2026-02-01") == date(2026, 2, 1)


@pytest.mark.parametrize("option", ["base", "hphc", "tempo"])
def test_open_data_grille_en_cours(option):
    g = cre_opendata.parse_csv(CSV[option].read_bytes(), option)
    assert g.date_effet == date(2026, 8, 1)  # lignes sans DATE_FIN
    if option == "tempo":
        assert g.puissances[6].prix_ttc == TEMPO_TTC_2026_08
    if option == "hphc":
        assert g.puissances[6].prix_ttc == {"hc": 0.1589, "hp": 0.2142}
        assert g.puissances[6].abonnement_ttc == 190.81



# --- grille EDF lue sur web.archive.org (EDF refuse les serveurs de GitHub) --------

CAPTURES = {edf_grille.URL: ("20260801093110", EDF), edf_grille.URL_EJP: ("20260801134207", EDF_EJP)}


def faux_archive(appels, absents=()):
    def faux_get(url, **kw):
        appels.append(url)
        for doc, (ts, fichier) in CAPTURES.items():
            if url.startswith(edf_grille.CDX) and quote(doc, safe="") in url:
                return b'[["timestamp"]]' if doc in absents else f'[["timestamp"],["{ts}"]]'.encode()
            if url == edf_grille.url_capture(ts, doc):
                return fichier.read_bytes()
        raise AssertionError(f"URL inattendue : {url}")
    return faux_get


def test_edf_copie_archive(monkeypatch):
    from tarif_kwh import http

    appels = []
    monkeypatch.setattr(http, "get", faux_archive(appels))
    g = edf_grille.collecter()
    assert set(g) == {"base", "hphc", "tempo", "ejp"}
    t = g["tempo"]
    assert t.url == edf_grille.URL
    assert t.meta["copie_archive"] == "https://web.archive.org/web/20260801093110id_/" + edf_grille.URL
    assert t.puissances[6].prix_ttc == TEMPO_TTC_2026_08
    assert g["ejp"].url == edf_grille.URL_EJP
    assert g["ejp"].meta["copie_archive"] == "https://web.archive.org/web/20260801134207id_/" + edf_grille.URL_EJP
    assert g["ejp"].puissances[9].abonnement_ttc_mensuel == 19.52
    assert edf_grille.URL not in appels and edf_grille.URL_EJP not in appels  # EDF jamais sollicité
    assert not any("/save/" in u for u in appels)  # aucune capture demandée


def test_edf_un_document_sans_capture(monkeypatch):
    from tarif_kwh import http

    monkeypatch.setattr(http, "get", faux_archive([], absents=(edf_grille.URL_EJP,)))
    assert set(edf_grille.collecter()) == {"base", "hphc", "tempo"}


def test_edf_un_document_illisible(monkeypatch):
    from tarif_kwh import http

    faux = faux_archive([])

    def get(url, **kw):
        if url == edf_grille.url_capture("20260801134207", edf_grille.URL_EJP):
            return b"%PDF-1.4 pas un vrai pdf"
        return faux(url, **kw)

    monkeypatch.setattr(http, "get", get)
    assert set(edf_grille.collecter()) == {"base", "hphc", "tempo"}


def test_edf_sans_capture(monkeypatch):
    from tarif_kwh import http

    monkeypatch.setattr(http, "get", lambda url, **kw: b'[["timestamp"]]')
    assert edf_grille.collecter() == {}
