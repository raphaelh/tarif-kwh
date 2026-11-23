"""Source 5 : historique des TRVE compilé par Jour Tempo (data.gouv.fr, Licence Ouverte).

https://www.data.gouv.fr/datasets/tarifs-reglementes-delectricite-depuis-2014-base-heures-creuses-tempo-ejp-et-textes-officiels

Barèmes HT du Tarif Bleu résidentiel depuis 2013, chaque valeur avec le texte
officiel dont elle vient (arrêté ou décision au JORF, délibération CRE). Il donne
les tarifs réellement appliqués : en 2023 (bouclier tarifaire), ceux des arrêtés
et non les propositions de la CRE.

On ne lit que ce que l'open data CRE n'a pas : l'EJP depuis août 2013, et Tempo
d'août 2013 à juillet 2016 (l'open data Tempo commence au 1er août 2016 ; après,
Jour Tempo ne sert pas pour Tempo, ni comme source ni comme contrôle). Avant février
2023, le TTC comprenait des taxes locales (TCFE) qu'on ne sait pas recalculer : on
reprend les taxes au kWh de l'open data CRE à la même date (voir
``reconcile.taxes_kwh_opendata``), sans abonnement TTC. C'est une source HT, au même
titre que la délibération CRE, recoupée avec elle et avec la grille EDF quand elles
existent.
"""
from __future__ import annotations

import csv
import io
from datetime import date

from .. import http
from ..schema import OPTIONS, GrilleSource, Puissance

SOURCE = "jourtempo"
URL_HISTORIQUE = "https://jourtempo.fr/api/v1/trve-historique.csv"
URL_SOURCES = "https://jourtempo.fr/api/v1/trve-sources.csv"
DATE_MIN = date(2013, 8, 1)
OPTIONS_LUES = ("ejp", "tempo")
# Date d'effet exclue à partir de laquelle l'open data CRE couvre l'option.
DATE_MAX = {"tempo": date(2016, 8, 1)}
COMPOSANTES = {
    "ejp": {"kwh_ejp_normal": "normal", "kwh_ejp_pointe": "pointe"},
    "tempo": {f"kwh_{c}_{h}": f"{c}_{h}" for c in ("bleu", "blanc", "rouge") for h in ("hc", "hp")},
}


class ParseError(ValueError):
    pass


def _lire(contenu: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(contenu.decode("utf-8-sig"))))


def parse(historique: bytes, sources: bytes) -> dict[tuple[str, date], GrilleSource]:
    """Grilles HT par (option, date d'effet). L'URL de chaque grille est celle du texte officiel cité."""
    urls = {r["source_id"]: r["url"] for r in _lire(sources)}
    grilles: dict[tuple[str, date], GrilleSource] = {}
    valeurs: dict[tuple[str, date, int], dict] = {}
    for r in _lire(historique):
        option = r["option"]
        if option not in OPTIONS_LUES or r["ht_ttc"] != "HT":
            continue
        d = date.fromisoformat(r["date_effet"])
        if d < DATE_MIN or (option in DATE_MAX and d >= DATE_MAX[option]):
            continue
        if r["source_id"] not in urls:
            raise ParseError(f"source inconnue {r['source_id']} ({option} {d})")
        cle = (option, d)
        g = grilles.setdefault(cle, GrilleSource(option, d, SOURCE, urls[r["source_id"]]))
        if g.url != urls[r["source_id"]]:
            raise ParseError(f"{option} {d} : plusieurs textes sources")
        g.meta["texte"] = r["source_id"]
        v = valeurs.setdefault((option, d, int(r["puissance_kva"])), {})
        c = r["composante"]
        if c == "abonnement_an":
            if r["unite"] != "eur_an":
                raise ParseError(f"unité inattendue {r['unite']} ({option} {d})")
            v["abonnement_ht"] = float(r["valeur"])
        elif c in COMPOSANTES[option]:
            if r["unite"] != "ceur_kwh":
                raise ParseError(f"unité inattendue {r['unite']} ({option} {d})")
            v.setdefault("prix_ht", {})[COMPOSANTES[option][c]] = round(float(r["valeur"]) / 100, 6)
    for (option, d, kva), v in valeurs.items():
        periodes = set(OPTIONS[option].periodes)
        if "abonnement_ht" not in v or set(v.get("prix_ht", {})) != periodes:
            raise ParseError(f"{option} {d} {kva} kVA : barème incomplet {v}")
        grilles[(option, d)].puissances[kva] = Puissance(abonnement_ht=v["abonnement_ht"], prix_ht=v["prix_ht"])
    return grilles


def collecter() -> list[GrilleSource]:
    g = parse(http.get(URL_HISTORIQUE), http.get(URL_SOURCES))
    return [g[k] for k in sorted(g)]
