"""Page HTML du site Pages (un tableau par option)."""
import json

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


def test_page_sans_etat(tmp_path):
    (tmp_path / "tarifs.json").write_text(json.dumps(TARIFS), encoding="utf-8")
    page.ecrire_index(tmp_path)
    assert "Dernière vérification" not in (tmp_path / "index.html").read_text(encoding="utf-8")
