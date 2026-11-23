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
import json
import re
from datetime import date
from pathlib import Path

from .. import http, taxes
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


CORRECTIONS = Path(__file__).resolve().parents[3] / "config" / "corrections_opendata.json"
TOL_CORRECTION = 0.00011  # €/kWh : en deçà, le TTC publié est juste (arrondi à 4 décimales)


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


def parse_historique(contenu: bytes, option: str) -> list[dict]:
    """Toutes les grilles du CSV (depuis 2012), de la plus ancienne à la plus récente.

    Chaque grille : ``{"date_debut", "date_fin" (dernier jour inclus, ou None pour
    la grille en cours), "puissances": {"<kVA>": {...}}}``. Une puissance sans
    valeur (ex. Tempo 6 kVA avant son ouverture) est omise.
    """
    texte = contenu.decode("utf-8-sig", "replace")
    grilles: dict[tuple, dict] = {}
    for l in csv.DictReader(io.StringIO(texte), delimiter=";"):
        valeurs = [l.get(c, "").strip() for c in ("PART_FIXE_HT", "PART_FIXE_TTC")]
        valeurs += [l.get(c, "").strip() for cols in COLONNES[option].values() for c in cols]
        if not all(valeurs):
            continue
        fin = (l.get("DATE_FIN") or "").strip()
        cle = (parse_date(l["DATE_DEBUT"]), parse_date(fin) if fin else None)
        g = grilles.setdefault(cle, {"date_debut": cle[0].isoformat(), "date_fin": cle[1] and cle[1].isoformat(), "puissances": {}})
        g["puissances"][str(int(l["P_SOUSCRITE"]))] = {
            "abonnement_ht": round(parse_nombre_fr(l["PART_FIXE_HT"]), 2),
            "abonnement_ttc": round(parse_nombre_fr(l["PART_FIXE_TTC"]), 2),
            "prix_ht": {per: round(parse_nombre_fr(l[ht]), 6) for per, (ht, _) in COLONNES[option].items()},
            "prix_ttc": {per: round(parse_nombre_fr(l[ttc]), 6) for per, (_, ttc) in COLONNES[option].items()},
        }
    out = [grilles[k] for k in sorted(grilles)]
    for g in out:
        g["puissances"] = dict(sorted(g["puissances"].items(), key=lambda kv: int(kv[0])))
    debuts = [g["date_debut"] for g in out]
    if len(set(debuts)) != len(debuts):
        raise ParseError(f"{option}: plusieurs grilles commencent à la même date")
    for a, b in zip(out, out[1:]):
        if a["date_fin"] is None or a["date_fin"] >= b["date_debut"]:
            raise ParseError(f"{option}: grilles qui se chevauchent ({a['date_debut']} / {b['date_debut']})")
    return out


def collecter(historique: dict | None = None) -> dict[str, GrilleSource]:
    """Grilles en cours ; si ``historique`` est fourni, y range aussi toutes les grilles par option."""
    out = {}
    for option, fichier in FICHIERS.items():
        url = BASE + fichier
        contenu = http.get(url)
        out[option] = parse_csv(contenu, option, url)
        if historique is not None:
            historique[option] = {"url": url, "grilles": parse_historique(contenu, option)}
    return out


def charger_corrections(path: Path = CORRECTIONS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["corrections"]


def corriger(historique: dict, corrections: list[dict], config_taxes: dict) -> list[str]:
    """Recalcule les TTC au kWh reconnus faux de l'historique (``config/corrections_opendata.json``).

    TTC = (HT + ``taxes_kwh``) × (1 + TVA), pour toutes les puissances de la grille ; la grille
    porte alors ``correction_ttc`` (motif, sources). L'abonnement n'est pas touché, sauf pour une
    correction avec ``bareme`` (barème périmé dans l'open data, voir ``_corriger_bareme``). Une grille
    dont le TTC publié est déjà juste (la CRE a corrigé son fichier) reste telle quelle.
    Renvoie une ligne par grille examinée.
    """
    journal = []
    for c in corrections:
        grilles = {g["date_debut"]: g for g in historique.get(c["option"], {}).get("grilles", [])}
        for d in c["dates_effet"]:
            g = grilles.get(d)
            if g is None:
                journal.append(f"correction {c['option']} {d} : grille absente de l'open data")
                continue
            tva = taxes.tva_energie(date.fromisoformat(d), config_taxes)
            if "bareme" in c:
                journal.append(_corriger_bareme(c, d, g, tva))
                continue
            calc = {
                k: {per: taxes.kwh_ttc(v, c["taxes_kwh"], tva) for per, v in p["prix_ht"].items()}
                for k, p in g["puissances"].items()
            }
            ecart = max(abs(calc[k][per] - p["prix_ttc"][per]) for k, p in g["puissances"].items() for per in p["prix_ttc"])
            if ecart <= TOL_CORRECTION:
                journal.append(f"correction {c['option']} {d} : TTC open data déjà juste, sans effet")
                continue
            for k, p in g["puissances"].items():
                p["prix_ttc"] = calc[k]
            g["correction_ttc"] = {"taxes_kwh": c["taxes_kwh"], "motif": c["motif"], "sources": list(c["sources"])}
            journal.append(f"correction {c['option']} {d} : TTC au kWh recalculé (écart max {ecart:.4f} €/kWh)")
    return journal


def _corriger_bareme(c: dict, d: str, g: dict, tva: float) -> str:
    """Remplace un barème périmé de l'open data (HT, abonnement HT et TTC) par celui de ``c["bareme"]``,
    pour les puissances présentes dans l'open data.

    TTC au kWh = (HT du barème + ``taxes_kwh``) × (1 + TVA). Sans effet si l'open data porte
    déjà ce barème (la CRE a corrigé son fichier).
    """
    bareme = c["bareme"]
    # Le barème couvre toutes les puissances du texte ; l'open data peut en omettre (puissances en extinction)
    manquantes = set(g["puissances"]) - set(bareme)
    if manquantes:
        raise ValueError(f"correction {c['option']} {d} : puissances {sorted(manquantes, key=int)} absentes du barème")
    deja = all(
        abs(p["abonnement_ht"] - bareme[k]["abonnement_ht"]) <= 0.011
        and all(abs(p["prix_ht"][per] - v) <= TOL_CORRECTION / 2 for per, v in bareme[k]["prix_ht"].items())
        for k, p in g["puissances"].items()
    )
    if deja:
        return f"correction {c['option']} {d} : barème open data déjà juste, sans effet"
    for k, p in g["puissances"].items():
        b = bareme[k]
        p["abonnement_ht"], p["abonnement_ttc"] = b["abonnement_ht"], b["abonnement_ttc"]
        p["prix_ht"] = dict(b["prix_ht"])
        p["prix_ttc"] = {per: taxes.kwh_ttc(v, c["taxes_kwh"], tva) for per, v in b["prix_ht"].items()}
    g["correction_ttc"] = {
        "taxes_kwh": c["taxes_kwh"], "bareme": True, "motif": c["motif"], "sources": list(c["sources"]),
    }
    return f"correction {c['option']} {d} : barème remplacé (HT, abonnement, TTC)"
