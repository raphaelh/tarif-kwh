"""Source 6 : barèmes HT recopiés à la main d'arrêtés publiés au JORF (config/baremes_arretes.json).

Pour les dates qu'aucune autre source ne couvre : Tempo et EJP au 23 juillet 2012
(arrêté du 20 juillet 2012 ; l'open data CRE commence à cette date pour la Base et
HP/HC, mais pas pour Tempo ni l'EJP, et Jour Tempo commence en août 2013). Traitée
comme Jour Tempo : source HT, TTC du kWh d'après les taxes de l'open data CRE à la
même date, sans abonnement TTC.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..schema import OPTIONS, GrilleSource, Puissance

SOURCE = "arrete"
FICHIER = Path(__file__).resolve().parents[3] / "config" / "baremes_arretes.json"


class ParseError(ValueError):
    pass


def parse(config: dict) -> list[GrilleSource]:
    grilles = []
    for b in config["baremes"]:
        option = b["option"]
        g = GrilleSource(option, date.fromisoformat(b["date_effet"]), SOURCE, b["url"], meta={"texte": b["texte"]})
        periodes = set(OPTIONS[option].periodes)
        for kva, p in b["puissances"].items():
            if set(p["prix_ceur_kwh"]) != periodes:
                raise ParseError(f"{option} {g.date_effet} {kva} kVA : périodes {sorted(p['prix_ceur_kwh'])}")
            g.puissances[int(kva)] = Puissance(
                abonnement_ht=float(p["abonnement_ht"]),
                prix_ht={k: round(v / 100, 6) for k, v in p["prix_ceur_kwh"].items()},
            )
        grilles.append(g)
    return sorted(grilles, key=lambda g: (g.option, g.date_effet))


def collecter(fichier: Path = FICHIER) -> list[GrilleSource]:
    return parse(json.loads(fichier.read_text(encoding="utf-8")))
