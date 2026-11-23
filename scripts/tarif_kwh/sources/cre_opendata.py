"""Source 3 : open data CRE « Marchés de détail » (CSV Base, HP/HC, Tempo).

Publié avec ~4 semaines de retard mais contient HT ET TTC (abonnement annuel
et kWh) : c'est la source de confirmation. Pas d'EJP.

Les lignes de la grille en cours n'ont pas de DATE_FIN. DATE_DEBUT est au
format JJ/MM/AAAA ; certains outils la relisent à tort en ISO avec jour et mois
inversés (« 2026-01-08 » pour le 1er août 2026) : on corrige ce cas.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from .. import http
from ..schema import GrilleSource, Puissance, parse_nombre_fr

SOURCE = "cre_opendata"
BASE = "https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/"
FICHIERS = {"base": "Option_Base.csv", "hphc": "Option_HPHC.csv", "tempo": "Option_Tempo.csv"}

# colonne CSV -> période (HT, TTC)
COLONNES = {
    "base": {"base": ("PART_VARIABLE_HT", "PART_VARIABLE_TTC")},
    "hphc": {
        "hc": ("PART_VARIABLE_HC_HT", "PART_VARIABLE_HC_TTC"),
        "hp": ("PART_VARIABLE_HP_HT", "PART_VARIABLE_HP_TTC"),
    },
    "tempo": {
        f"{c}_{h}": (f"PART_VARIABLE_{h.upper()}{c.capitalize()}_HT", f"PART_VARIABLE_{h.upper()}{c.capitalize()}_TTC")
        for c in ("bleu", "blanc", "rouge")
        for h in ("hc", "hp")
    },
}


class ParseError(ValueError):
    pass


def parse_date(s: str) -> date:
    s = s.strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, a, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Les grilles TRVE démarrent un 1er du mois : « 2026-01-08 » = 1er août.
        if b != 1 and a == 1:
            a, b = b, a
        return date(y, a, b)
    raise ParseError(f"date illisible : {s!r}")


def parse_csv(contenu: bytes, option: str, url: str = "") -> GrilleSource:
    texte = contenu.decode("utf-8-sig", "replace")
    lignes = list(csv.DictReader(io.StringIO(texte), delimiter=";"))
    courantes = [l for l in lignes if not (l.get("DATE_FIN") or "").strip()]
    if not courantes:
        raise ParseError(f"{option}: aucune ligne sans DATE_FIN")
    dates = {parse_date(l["DATE_DEBUT"]) for l in courantes}
    if len(dates) != 1:
        raise ParseError(f"{option}: plusieurs grilles en cours {sorted(dates)}")
    g = GrilleSource(option, dates.pop(), SOURCE, url)
    for l in courantes:
        kva = int(l["P_SOUSCRITE"])
        p = Puissance(
            abonnement_ht=round(parse_nombre_fr(l["PART_FIXE_HT"]), 2),
            abonnement_ttc=round(parse_nombre_fr(l["PART_FIXE_TTC"]), 2),
        )
        for per, (cht, cttc) in COLONNES[option].items():
            if not l.get(cht, "").strip():
                raise ParseError(f"{option}: valeur manquante {cht} à {kva} kVA")
            p.prix_ht[per] = round(parse_nombre_fr(l[cht]), 6)
            p.prix_ttc[per] = round(parse_nombre_fr(l[cttc]), 6)
        g.puissances[kva] = p
    return g


def collecter() -> dict[str, GrilleSource]:
    out = {}
    for option, fichier in FICHIERS.items():
        url = BASE + fichier
        out[option] = parse_csv(http.get(url), option, url)
    return out
