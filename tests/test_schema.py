"""Les JSON publiés respectent docs/schema.json (contrat avec Jeedom, Domoticz, scripts…)."""
import copy
import json
from datetime import date

import pytest
from conftest import RACINE
from jsonschema import Draft202012Validator, FormatChecker
from test_pipeline import T0, registre_avec

from tarif_kwh import publish, taxes
from tarif_kwh.schema import SCHEMA_VERSION

DOCS = RACINE / "docs"
SCHEMA = json.loads((DOCS / "schema.json").read_text(encoding="utf-8"))
FICHIERS = {
    "tarifs.json": "fichier_tarifs",
    "historique.json": "fichier_historique",
    "etat.json": "fichier_etat",
    **{f"{o}.json": "fichier_option" for o in ("base", "hphc", "tempo", "ejp")},
}


def erreurs(data, definition=None):
    schema = SCHEMA if definition is None else {"$ref": f"#/$defs/{definition}", "$defs": SCHEMA["$defs"]}
    v = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(data)]


def test_schema_valide():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$defs"]["schema_version"]["const"] == SCHEMA_VERSION


@pytest.mark.parametrize("nom", sorted(FICHIERS))
def test_fichiers_publies_conformes(nom):
    data = json.loads((DOCS / nom).read_text(encoding="utf-8"))
    assert erreurs(data) == []
    assert erreurs(data, FICHIERS[nom]) == []


def _verifier_dossier(docs):
    for nom, definition in FICHIERS.items():
        f = docs / nom
        if f.exists():
            assert erreurs(json.loads(f.read_text(encoding="utf-8")), definition) == [], nom


def test_sorties_du_collecteur_conformes(tmp_path):
    """Grille confirmée, grille proposée (prochaine, TTC estimé) et option bloquée."""
    cfg = taxes.charger_config()
    publish.publier(tmp_path / "a", registre_avec(), cfg, date(2026, 11, 23), [], T0)
    _verifier_dossier(tmp_path / "a")

    r = registre_avec(edf=False, opendata=True)
    for option in ("tempo", "hphc"):
        d = copy.deepcopy(r["grilles"][option]["2026-08-01"]["cre_deliberation"])
        d["date_effet"] = "2027-02-01"
        r["grilles"][option]["2027-02-01"] = {"cre_deliberation": d}
    jorf = [{"titre": "Loi de finances pour 2027", "date_publication": "2026-12-30", "nature": "LOI",
             "url": "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000000000001"}]
    publish.publier(tmp_path / "b", r, cfg, date(2027, 1, 20), jorf, T0)
    assert json.loads((tmp_path / "b" / "tempo.json").read_text())["prochaine"]["statut"] == "propose"
    _verifier_dossier(tmp_path / "b")

    r = registre_avec()
    r["grilles"]["tempo"]["2026-08-01"]["edf_grille"]["puissances"]["6"]["prix_ttc"]["rouge_hp"] = 0.7395
    publish.publier(tmp_path / "a", r, cfg, date(2026, 11, 23), [], T0)
    assert json.loads((tmp_path / "a" / "etat.json").read_text())["options"]["tempo"]["publication"] == "bloquee"
    _verifier_dossier(tmp_path / "a")


def test_schema_rejette_les_erreurs():
    t = json.loads((DOCS / "tempo.json").read_text(encoding="utf-8"))

    def modifie(f):
        x = copy.deepcopy(t)
        f(x)
        return erreurs(x, "fichier_option")

    assert modifie(lambda x: x["actuelle"]["prix_ttc"].update(vert_hp=0.1))  # période d'une autre option
    assert modifie(lambda x: x["actuelle"]["prix_ttc"].pop("rouge_hp"))
    assert modifie(lambda x: x["actuelle"].update(statut="ok"))
    assert modifie(lambda x: x.update(schema_version=2))
    assert modifie(lambda x: x["actuelle"]["puissances"].update({"7": x["actuelle"]["puissances"]["6"]}))
    assert modifie(lambda x: x["actuelle"].update(date_effet="01/08/2026"))
    # Champ ajouté : accepté sans changer de version (compatibilité ascendante)
    assert not modifie(lambda x: x.update(champ_futur=1))
