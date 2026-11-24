"""Page HTML du site Pages (un tableau par option)."""
import json
from html import escape

import pytest

from tarif_kwh import page


def _grille(date_effet, periodes, puissances, **extra):
    return {
        "date_effet": date_effet,
        "statut": "confirme",
        "ttc_estime": False,
        "puissances": {
            str(k): {
                "abonnement_ht": 100.0,
                "abonnement_ttc": abo,
                "prix_ht": {p: 0.1 for p in periodes},
                "prix_ttc": {p: 0.1234 for p in periodes},
            }
            for k, abo in puissances.items()
        },
        **extra,
    }


def _bloc(libelle, periodes, puissances, prochaine=None):
    return {
        "libelle": libelle,
        "periodes": periodes,
        "note": "Note <b>échappée</b>",
        "actuelle": _grille("2026-08-01", periodes, puissances),
        "prochaine": prochaine,
    }


TEMPO = ["bleu_hc", "bleu_hp", "blanc_hc", "blanc_hp", "rouge_hc", "rouge_hp"]
TARIFS = {
    "avertissement": "Projet NON officiel",
    "options": {
        "tempo": _bloc("Tarif Bleu résidentiel - option Tempo", TEMPO, {6: 189.98, 36: 600.0}),
        "ejp": _bloc(
            "Tarif Bleu résidentiel - option EJP", ["normal", "pointe"], {9: None, 12: 300.0},
            prochaine=_grille("2027-02-01", ["normal", "pointe"], {9: 200.0}, statut="propose", ttc_estime=True),
        ),
    },
}


def test_page_un_tableau_par_option(tmp_path):
    (tmp_path / "tarifs.json").write_text(json.dumps(TARIFS), encoding="utf-8")
    etat = {"options": {"ejp": {"publication": "bloquee"}}, "derniere_verification": "2026-11-23T17:17:00+00:00"}
    (tmp_path / "etat.json").write_text(json.dumps(etat), encoding="utf-8")
    page.ecrire_index(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert html.count('<section id="') == 2
    tempo, ejp = html.split('<section id="tempo">')[1].split('<section id="ejp">')
    # Tempo : en-tête à deux niveaux (couleur, puis HC/HP), TTC puis HT
    assert tempo.count("<table>") == 2
    assert "Jours rouges" in tempo and tempo.count(">HP</th>") == 6
    assert "En vigueur depuis le 1er août 2026" in tempo
    assert "15,83" in tempo and "189,98" in tempo and "0,1234" in tempo  # mois calculé, virgule décimale
    assert '<tr><th scope="row">6 kVA</th>' in tempo.split('<tr><th scope="row">36 kVA</th>')[0]  # tri numérique
    # EJP : publication bloquée signalée, abonnement inconnu, prochaine grille
    assert "Publication bloquée" in ejp and "Publication bloquée" not in tempo
    assert "<td class=\"num\">—</td><td class=\"num\">—</td>" in ejp
    assert "Prochaine grille, à partir du 1er février 2027" in ejp and "TTC calculé" in ejp
    assert "Pointe mobile" in ejp
    assert "<b>" not in html and "Note &lt;b&gt;échappée&lt;/b&gt;" in html
    assert "23 novembre 2026 à 17:17 UTC" in html


def test_page_mensuel_egal_annuel_sur_douze(tmp_path):
    """Le mensuel EDF (arrondi, ici 30,69) n'est pas affiché : annuel ÷ 12 (369,49 / 12 = 30,79)."""
    tarifs = json.loads(json.dumps(TARIFS))
    p = tarifs["options"]["tempo"]["actuelle"]["puissances"]["6"]
    p["abonnement_ttc"], p["abonnement_ttc_mensuel"] = 369.49, 30.69
    ejp9 = tarifs["options"]["ejp"]["actuelle"]["puissances"]["9"]
    ejp9["abonnement_ttc_mensuel"] = 19.52  # annuel inconnu : mensuel EDF à défaut
    (tmp_path / "tarifs.json").write_text(json.dumps(tarifs), encoding="utf-8")
    page.ecrire_index(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "30,79" in html and "30,69" not in html
    assert '<td class="num">19,52</td><td class="num">—</td>' in html
    assert html.count("annuel ÷ 12") == 3  # une note par grille TTC (tempo, ejp, ejp prochaine)


@pytest.mark.parametrize("code,sources,attendu", [
    ("ejp", ["cre_deliberation", "jourtempo", "edf_grille"],
     "Grille en vigueur, recoupée avec la grille EDF (l'EJP ne figure pas dans l'open data CRE)."),
    ("ejp", ["cre_deliberation"], "Grille en vigueur (l'EJP ne figure pas dans l'open data CRE)."),
    ("tempo", ["cre_deliberation", "edf_grille"], "Grille en vigueur (non encore recoupée par l'open data CRE)."),
])
def test_page_statut_en_vigueur(code, sources, attendu):
    g = _grille("2026-08-01", ["normal", "pointe"], {9: 234.24}, statut="en_vigueur",
                sources=[{"type": s, "url": "u"} for s in sources])
    html = page._grille(code, "En vigueur depuis le {}", g, ["normal", "pointe"])
    assert escape(attendu) in html


def test_page_sans_etat(tmp_path):
    (tmp_path / "tarifs.json").write_text(json.dumps(TARIFS), encoding="utf-8")
    page.ecrire_index(tmp_path)
    assert "Dernière vérification" not in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_page_icones_et_apercu(tmp_path):
    """Favicon, icône d'accueil et aperçu des liens : chaque fichier cité existe dans docs/img."""
    import pathlib
    import re

    (tmp_path / "tarifs.json").write_text(json.dumps(TARIFS), encoding="utf-8")
    (tmp_path / "etat.json").write_text(json.dumps({"options": {}}), encoding="utf-8")
    page.ecrire_index(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<link rel="icon" href="img/favicon.ico"' in html
    assert '<meta property="og:image" content="https://raphaelh.github.io/tarif-kwh/img/social.png">' in html
    img = pathlib.Path(__file__).parents[1] / "docs" / "img"
    cites = set(re.findall(r'href="img/([^"]+)"', html)) | {"social.png"}
    assert cites and all((img / f).is_file() for f in cites)
    manifeste = json.loads((img / "site.webmanifest").read_text(encoding="utf-8"))
    assert all((img / i["src"]).is_file() for i in manifeste["icons"])
