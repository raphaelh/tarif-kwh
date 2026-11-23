"""Recoupement, statuts, blocages et publication, à partir des sources réelles."""
import copy
import io
import json
import tarfile
from datetime import date, datetime, timedelta, timezone

import pytest
from conftest import ANNEXES, CSV, EDF

from tarif_kwh import checks, publish, taxes
from tarif_kwh.reconcile import grille_to_dict
from tarif_kwh.sources import cre_deliberation, cre_opendata, edf_grille, jorf

T0 = datetime(2026, 11, 23, tzinfo=timezone.utc)


def registre_avec(*, delibs=("2026-02-01", "2026-08-01"), edf=True, opendata=True):
    r = {"grilles": {}}

    def add(g):
        r["grilles"].setdefault(g.option, {}).setdefault(g.date_effet.isoformat(), {})[g.source] = grille_to_dict(g)

    for d in delibs:
        for g in cre_deliberation.parse_annexe_b(ANNEXES[d].read_bytes(), ANNEXES[d].name).values():
            add(g)
    if edf:
        for g in edf_grille.parse_grille(EDF.read_bytes()).values():
            add(g)
    if opendata:
        for o, p in CSV.items():
            add(cre_opendata.parse_csv(p.read_bytes(), o, p.name))
    return r


@pytest.fixture
def cfg():
    return taxes.charger_config()


def lire(docs, nom):
    return json.loads((docs / nom).read_text())


def test_publication_complete(tmp_path, cfg):
    etat = publish.publier(tmp_path, registre_avec(), cfg, date(2026, 11, 23), [], T0)
    assert {o: e["publication"] for o, e in etat.items()} == dict.fromkeys(("base", "hphc", "tempo", "ejp"), "ok")
    t = lire(tmp_path, "tempo.json")
    a = t["actuelle"]
    assert a["date_effet"] == "2026-08-01" and a["statut"] == "confirme" and not a["ttc_estime"]
    assert a["prix_ttc"] == {
        "bleu_hc": 0.1356, "bleu_hp": 0.1654, "blanc_hc": 0.1536,
        "blanc_hp": 0.1921, "rouge_hc": 0.1615, "rouge_hp": 0.7295,
    }
    assert t["prochaine"] is None
    assert t["plages_horaires"]["hc"] == "22:00-06:00"
    assert {s["type"] for s in a["sources"]} == {"cre_deliberation", "edf_grille", "cre_opendata"}
    # Base : prix différent selon la puissance -> pas de prix commun au niveau grille
    b = lire(tmp_path, "base.json")["actuelle"]
    assert "prix_ttc" not in b
    assert b["puissances"]["6"]["prix_ttc"] == {"base": 0.2001}
    assert b["puissances"]["36"]["prix_ttc"] == {"base": 0.1985}  # absent du CSV : vient d'EDF
    # EJP : délibération seule, date atteinte -> en vigueur
    e = lire(tmp_path, "ejp.json")["actuelle"]
    assert e["statut"] == "en_vigueur" and e["ttc_estime"]
    glob = lire(tmp_path, "tarifs.json")
    assert set(glob["options"]) == {"base", "hphc", "tempo", "ejp"}
    assert "NON officiel" in glob["avertissement"]


def test_hphc_confirme(tmp_path, cfg):
    publish.publier(tmp_path, registre_avec(), cfg, date(2026, 11, 23), [], T0)
    h = lire(tmp_path, "hphc.json")["actuelle"]
    assert h["statut"] == "confirme"
    assert h["prix_ttc"] == {"hp": 0.2142, "hc": 0.1589}
    assert h["puissances"]["6"]["abonnement_ttc"] == 190.81
    assert h["puissances"]["6"]["abonnement_ttc_mensuel"] == 15.86


def test_grille_proposee_avant_entree_en_vigueur(tmp_path, cfg):
    """Le 20/07/2026 : seule la délibération du 15/07 est connue -> prochaine = propose."""
    cfg_sans_aout = copy.deepcopy(cfg)
    cfg_sans_aout["accise_eur_kwh"] = [a for a in cfg["accise_eur_kwh"] if a["debut"] < "2026-08-01"]
    r = registre_avec(edf=False, opendata=False)
    publish.publier(tmp_path, r, cfg_sans_aout, date(2026, 7, 20), [], T0)
    t = lire(tmp_path, "tempo.json")
    assert t["actuelle"]["date_effet"] == "2026-02-01"
    p = t["prochaine"]
    assert p["date_effet"] == "2026-08-01" and p["statut"] == "propose" and p["ttc_estime"]
    assert p["prix_ht"]["rouge_hp"] == 0.5773
    # TTC estimé avec l'accise connue (30,85 €/MWh) : proche du réel (72,95 c€) sans l'égaler
    assert p["prix_ttc"]["rouge_hp"] == pytest.approx(0.7295, abs=0.001)
    # Le jour J, la grille proposée devient l'actuelle
    publish.publier(tmp_path, r, cfg_sans_aout, date(2026, 8, 1), [], T0)
    a = lire(tmp_path, "tempo.json")["actuelle"]
    assert a["date_effet"] == "2026-08-01"
    assert a["statut"] == "en_vigueur" and a["ttc_estime"]  # date atteinte, sans texte au JORF


def test_abonnement_estime_proche_du_reel(tmp_path, cfg):
    """Abonnement TTC estimé (CTA de la grille précédente) à moins de 2 % du réel."""
    # open data 2026-08 connu ; grille suivante proposée avec les mêmes HT
    r = registre_avec(edf=False, opendata=True)
    reel = r["grilles"]["tempo"]["2026-08-01"]["cre_opendata"]["puissances"]["6"]["abonnement_ttc"]
    d = copy.deepcopy(r["grilles"]["tempo"]["2026-08-01"]["cre_deliberation"])
    d["date_effet"] = "2027-02-01"
    r["grilles"]["tempo"]["2027-02-01"] = {"cre_deliberation": d}
    publish.publier(tmp_path, r, cfg, date(2027, 1, 20), [], T0)
    p = lire(tmp_path, "tempo.json")["prochaine"]
    assert p["statut"] == "propose" and p["ttc_estime"]
    assert p["puissances"]["6"]["abonnement_ttc"] == pytest.approx(reel, rel=0.02)
    assert "cta_deduite_de" in p["taxes"]


def test_desaccord_bloque_et_conserve_l_ancien(tmp_path, cfg):
    publish.publier(tmp_path, registre_avec(), cfg, date(2026, 11, 23), [], T0)
    avant = (tmp_path / "tempo.json").read_text()
    r = registre_avec()
    r["grilles"]["tempo"]["2026-08-01"]["edf_grille"]["puissances"]["6"]["prix_ttc"]["rouge_hp"] = 0.7395
    etat = publish.publier(tmp_path, r, cfg, date(2026, 11, 23), [], T0)
    assert etat["tempo"]["publication"] == "bloquee"
    assert any("rouge_hp" in p for p in etat["tempo"]["problemes"])
    assert (tmp_path / "tempo.json").read_text() == avant  # rien de nouveau publié
    assert etat["hphc"]["publication"] == "ok"  # les autres options ne sont pas touchées
    assert lire(tmp_path, "etat.json")["options"]["tempo"]["publication"] == "bloquee"


def test_desaccord_ht_cre_vs_open_data(tmp_path, cfg):
    r = registre_avec()
    r["grilles"]["hphc"]["2026-08-01"]["cre_deliberation"]["puissances"]["9"]["prix_ht"]["hc"] = 0.1019
    etat = publish.publier(tmp_path, r, cfg, date(2026, 11, 23), [], T0)
    assert etat["hphc"]["publication"] == "bloquee"
    assert not (tmp_path / "hphc.json").exists()


def test_variation_forte_source_unique(tmp_path, cfg):
    r = registre_avec(edf=False, opendata=False)
    d = copy.deepcopy(r["grilles"]["ejp"]["2026-08-01"]["cre_deliberation"])
    d["date_effet"] = "2027-02-01"
    for p in d["puissances"].values():
        p["prix_ht"]["pointe"] = 3.297  # virgule décalée
    r["grilles"]["ejp"]["2027-02-01"] = {"cre_deliberation": d}
    etat = publish.publier(tmp_path, r, cfg, date(2027, 1, 20), [], T0)
    assert etat["ejp"]["publication"] == "bloquee"
    # ... sauf validation manuelle
    bloc, pb, _ = publish.evaluer_option("ejp", r, cfg, date(2027, 1, 20), [], {("ejp", "2027-02-01")})
    assert not pb or all("bornes" in x for x in pb)  # 3,297 €/kWh dépasse de toute façon les bornes


def test_variation_forte_validee(tmp_path, cfg):
    r = registre_avec(edf=False, opendata=False)
    d = copy.deepcopy(r["grilles"]["ejp"]["2026-08-01"]["cre_deliberation"])
    d["date_effet"] = "2027-02-01"
    for p in d["puissances"].values():
        p["prix_ht"]["pointe"] = 0.6  # +82 %
    r["grilles"]["ejp"]["2027-02-01"] = {"cre_deliberation": d}
    bloc, pb, _ = publish.evaluer_option("ejp", r, cfg, date(2027, 1, 20), [], set())
    assert bloc is None and any("variation" in x for x in pb)
    bloc, pb, _ = publish.evaluer_option("ejp", r, cfg, date(2027, 1, 20), [], {("ejp", "2027-02-01")})
    assert bloc and bloc["prochaine"]["prix_ht"]["pointe"] == 0.6


def test_alerte_jorf_maintient_ejp_propose(tmp_path, cfg):
    alerte = [{"titre": "Arrêté relatif aux tarifs réglementés de vente de l'électricité",
               "date_publication": "2026-07-30", "url": "https://www.legifrance.gouv.fr/jorf/id/X"}]
    publish.publier(tmp_path, registre_avec(), cfg, date(2026, 11, 23), alerte, T0)
    e = lire(tmp_path, "ejp.json")["actuelle"]
    assert e["statut"] == "propose" and e["alertes"]


def test_horodatage_stable(tmp_path, cfg):
    r = registre_avec()
    publish.publier(tmp_path, r, cfg, date(2026, 11, 23), [], T0)
    publish.publier(tmp_path, r, cfg, date(2026, 11, 24), [], datetime(2026, 11, 24, tzinfo=timezone.utc))
    assert lire(tmp_path, "tempo.json")["mis_a_jour_le"].startswith("2026-11-23")


# --- contrôles unitaires ---------------------------------------------------------

def _tempo():
    return cre_deliberation.parse_annexe_b(ANNEXES["2026-08-01"].read_bytes())["tempo"]


def test_controle_rouge_hp_max():
    g = _tempo()
    g.puissances[6].prix_ht["blanc_hp"] = 0.60
    assert any("rouge HP" in p for p in checks.coherence(g))


def test_controle_hp_sup_hc():
    g = cre_deliberation.parse_annexe_b(ANNEXES["2026-08-01"].read_bytes())["hphc"]
    g.puissances[6].prix_ht["hc"] = 0.20
    assert any("HP" in p for p in checks.coherence(g))


def test_controle_nombre_de_valeurs():
    g = _tempo()
    del g.puissances[6].prix_ht["rouge_hc"]
    assert checks.coherence(g)
    g = _tempo()
    for k in (6, 9, 12):
        del g.puissances[k]
    assert any("puissances" in p for p in checks.coherence(g))


def test_controle_grilles_reelles_ok(annexes):
    for gr in annexes.values():
        for g in gr.values():
            assert checks.coherence(g) == []


# --- JORF ----------------------------------------------------------------------

def _archive(titres):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for i, t in enumerate(titres):
            nature = "LOI" if t.startswith("LOI") else "ARRETE"
            xml = (f"<TEXTE_VERSION><META><META_COMMUN><ID>JORFTEXT{i}</ID><NATURE>{nature}</NATURE></META_COMMUN>"
                   f"<META_SPEC><META_TEXTE_CHRONICLE><CID>JORFTEXT{i}</CID><DATE_PUBLI>2026-07-31</DATE_PUBLI>"
                   f"</META_TEXTE_CHRONICLE><META_TEXTE_VERSION><TITREFULL>{t}</TITREFULL></META_TEXTE_VERSION>"
                   "</META_SPEC></META></TEXTE_VERSION>").encode()
            info = tarfile.TarInfo(f"x/jorf/global/texte/version/JORF/TEXT/00/{i}.xml")
            info.size = len(xml)
            tar.addfile(info, io.BytesIO(xml))
    return buf.getvalue()


def test_jorf_detection():
    a = _archive([
        "Arrêté du 30 juillet 2026 relatif aux tarifs réglementés de vente de l'électricité",
        "Arrêté relatif aux captures accidentelles de dauphins",
    ])
    t = jorf.textes_pertinents(a)
    assert len(t) == 1 and t[0]["url"].endswith("JORFTEXT0")


def test_jorf_index():
    html = '<a href="JORF_20261121-010907.tar.gz">x</a><a href="JORF_20261120-222218.tar.gz">y</a>'
    assert [a for a, _ in jorf.lister_archives(html)] == ["JORF_20261120-222218.tar.gz", "JORF_20261121-010907.tar.gz"]


# --- accise appliquée vs config/taxes.json -----------------------------------------

def test_accise_conforme(cfg):
    from tarif_kwh import reconcile

    r = registre_avec()
    assert reconcile.accises_appliquees(r, cfg)["2026-08-01"] == (0.03062, "grille EDF")
    assert reconcile.ecarts_accise(r, cfg) == []
    # Sans la grille EDF : accise déduite de l'open data CRE
    r = registre_avec(edf=False)
    v, src = reconcile.accises_appliquees(r, cfg)["2026-08-01"]
    assert v == pytest.approx(0.03062, abs=0.0001) and "open data" in src
    assert reconcile.ecarts_accise(r, cfg) == []


def test_accise_oubliee_dans_la_config(cfg):
    """Changement d'accise non reporté (ex. 1er août 2026) : signalé."""
    from tarif_kwh import reconcile

    cfg2 = copy.deepcopy(cfg)
    cfg2["accise_eur_kwh"] = [a for a in cfg["accise_eur_kwh"] if a["debut"] != "2026-08-01"]
    ecarts = reconcile.ecarts_accise(registre_avec(), cfg2)
    assert len(ecarts) == 1 and "0.03062" in ecarts[0] and "0.03085" in ecarts[0]


@pytest.mark.parametrize("titre,attendu", [
    ("LOI n° 2026-1290 du 30 décembre 2026 de finances pour 2027", True),
    ("LOI n° 2026-801 du 12 juillet 2026 de finances rectificative pour 2026", True),
    ("Arrêté du 28 juillet 2026 fixant les tarifs de l'accise sur l'électricité", True),
    ("Décret relatif aux accises sur les énergies", True),
    ("Arrêté relatif aux tarifs réglementés de vente de l'électricité", False),  # TRVE, pas taxes
    ("Arrêté relatif aux accises sur les alcools et boissons alcooliques", None),
    ("Décret relatif aux captures accidentelles de dauphins", None),
])
def test_jorf_motifs(titre, attendu):
    nature = "LOI" if titre.startswith("LOI") else "ARRETE"
    if attendu is None:
        assert not jorf.pertinent(titre, nature)
    else:
        assert jorf.pertinent(titre, nature) and jorf.concerne_les_taxes(titre, nature) is attendu


def test_jorf_decret_d_application_ignore():
    titre = ("Décret n° 2026-1073 du 19 novembre 2026 pris pour l'application de l'article 17 "
             "de la loi n° 2026-103 du 19 février 2026 de finances pour 2026")
    assert not jorf.pertinent(titre, "DECRET")


def test_jorf_anciens_textes_ignores():
    a = _archive(["LOI n° 2026-1290 du 30 décembre 2026 de finances pour 2027"])  # publié le 2026-07-31
    assert jorf.textes_pertinents(a, date(2026, 7, 20))
    assert jorf.textes_pertinents(a, date(2026, 8, 5)) == []


# --- historique.json -------------------------------------------------------------

def historique_opendata():
    return {o: {"url": p.name, "grilles": cre_opendata.parse_historique(p.read_bytes(), o)} for o, p in CSV.items()}


def test_historique_depuis_2012(tmp_path, cfg):
    publish.publier(tmp_path, registre_avec(), cfg, date(2026, 11, 23), [], T0, historique_opendata())
    h = lire(tmp_path, "historique.json")["options"]
    base = h["base"]["grilles"]
    assert base[0]["date_debut"] == "2012-07-23" and base[0]["date_fin"] == "2013-07-31"
    assert base[0]["puissances"]["6"]["prix_ttc"] == {"base": 0.1263}
    assert base[-1]["date_debut"] == "2026-08-01" and base[-1]["date_fin"] is None
    # périodes contiguës, sans trou ni chevauchement
    for o in ("base", "hphc", "tempo"):
        g = h[o]["grilles"]
        for a, b in zip(g, g[1:]):
            assert date.fromisoformat(a["date_fin"]) + timedelta(days=1) == date.fromisoformat(b["date_debut"])
    tempo = h["tempo"]["grilles"]
    assert tempo[0]["date_debut"] == "2016-08-01" and "6" not in tempo[0]["puissances"]  # pas de 6 kVA en 2016
    assert tempo[-1]["prix_ttc"]["rouge_hp"] == 0.7295 and tempo[-1]["statut"] == "confirme"
    # EJP absent de l'open data : seulement les grilles recoupées du registre
    assert [g["date_debut"] for g in h["ejp"]["grilles"]] == ["2026-02-01", "2026-08-01"]
    assert h["ejp"]["grilles"][0]["date_fin"] == "2026-07-31"


def test_historique_complete_l_open_data_en_retard(tmp_path, cfg):
    """Nouvelle grille en vigueur, pas encore dans l'open data : elle clôt la dernière grille CRE."""
    od = historique_opendata()
    for o in od:  # open data « d'avant » : la grille du 1er août n'y est pas encore
        od[o]["grilles"] = od[o]["grilles"][:-1]
        od[o]["grilles"][-1]["date_fin"] = None
    r = registre_avec(opendata=False)
    publish.publier(tmp_path, r, cfg, date(2026, 8, 10), [], T0, od)
    g = lire(tmp_path, "historique.json")["options"]["tempo"]["grilles"]
    assert g[-2]["date_debut"] == "2026-02-01" and g[-2]["date_fin"] == "2026-07-31"
    assert g[-2]["sources"] == [{"type": "cre_opendata", "url": CSV["tempo"].name}]
    assert g[-1]["date_debut"] == "2026-08-01" and g[-1]["date_fin"] is None
    assert g[-1]["statut"] == "en_vigueur" and "abonnement_ttc_mensuel" not in g[-1]["puissances"]["6"]


def test_historique_conserve_sans_telechargement(tmp_path, cfg):
    r = registre_avec()
    publish.publier(tmp_path, r, cfg, date(2026, 11, 23), [], T0, historique_opendata())
    avant = lire(tmp_path, "historique.json")
    publish.publier(tmp_path, r, cfg, date(2026, 11, 24), [], datetime(2026, 11, 24, tzinfo=timezone.utc))
    assert lire(tmp_path, "historique.json") == avant  # même contenu, même horodatage


def test_historique_chevauchement_refuse():
    contenu = CSV["base"].read_bytes().replace(b"01/08/2013;31/10/2014", b"01/07/2013;31/10/2014")
    with pytest.raises(cre_opendata.ParseError):
        cre_opendata.parse_historique(contenu, "base")


def test_historique_grille_rejetee_laisse_un_trou(tmp_path, cfg):
    """Une grille rejetée (variation forte, source unique) ne prolonge pas la précédente."""
    r = registre_avec(edf=False, opendata=False)
    fevrier = r["grilles"]["ejp"]["2026-02-01"]["cre_deliberation"]
    for p in fevrier["puissances"].values():
        p["prix_ht"]["pointe"] *= 3  # la grille d'août varie alors de -67 % : rejetée
    publish.publier(tmp_path, r, cfg, date(2026, 11, 23), [], T0, historique_opendata())
    g = lire(tmp_path, "historique.json")["options"]["ejp"]["grilles"]
    assert [(x["date_debut"], x["date_fin"]) for x in g] == [("2026-02-01", "2026-07-31")]


def test_restructuration_ejp_fevrier_2026_validee(tmp_path, cfg):
    """Pointe EJP -71 % au 01/02/2026 (vraie refonte CRE) : validée dans config/validations.json."""
    r = registre_avec(delibs=("2025-08-01", "2026-02-01", "2026-08-01"), edf=False, opendata=False)
    ok, pb, _ = publish.grilles_validees("ejp", r, cfg, date(2026, 11, 23), [], set())
    assert "2026-02-01" in pb  # sans validation : rejetée
    ok, pb, rem = publish.grilles_validees("ejp", r, cfg, date(2026, 11, 23), [])  # validations du dépôt
    assert not pb and list(ok) == ["2025-08-01", "2026-02-01", "2026-08-01"]
    assert any("validée à la main" in x for x in rem)
    assert ok["2026-02-01"]["prix_ht"] == {"normal": 0.1176, "pointe": 0.2558}
    publish.publier(tmp_path, r, cfg, date(2026, 11, 23), [], T0, historique_opendata())
    g = lire(tmp_path, "historique.json")["options"]["ejp"]["grilles"]
    assert [(x["date_debut"], x["date_fin"]) for x in g] == [
        ("2025-08-01", "2026-01-31"), ("2026-02-01", "2026-07-31"), ("2026-08-01", None)]
