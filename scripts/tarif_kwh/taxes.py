"""Calcul du TTC à partir du HT.

kWh TTC        = (HT + accise) × (1 + TVA énergie)
abonnement TTC = (HT + CTA) × (1 + TVA abonnement)

La CTA dépend de la part fixe du tarif d'acheminement (TURPE), propre à chaque
option et puissance, et change chaque 1er août : on la déduit de la dernière
grille officielle connue (open data CRE). Pour l'EJP, absente de l'open data,
on la calcule : taux de CTA × part fixe du TURPE (composantes de gestion et de
comptage + soutirage fixe × puissance, tarif CU jusqu'en juillet 2022 puis CU4),
d'après config/taxes.json. Un TTC
calculé ainsi est une ESTIMATION, signalée par ``ttc_estime: true`` dans les JSON.
"""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "config" / "taxes.json"


def charger_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def valeur_au(serie: list[dict], d: date) -> dict | None:
    """Entrée de plus grand ``debut`` <= d."""
    best = None
    for e in serie:
        if date.fromisoformat(e["debut"]) <= d and (
            best is None or e["debut"] >= best["debut"]
        ):
            best = e
    return best


def accise(d: date, config: dict, observees: dict[str, float] | None = None) -> tuple[float, str]:
    """Accise applicable à la date d (config + valeurs lues dans les grilles EDF)."""
    serie = list(config["accise_eur_kwh"])
    for debut, v in (observees or {}).items():
        if not any(e["debut"] == debut for e in serie):
            serie.append({"debut": debut, "valeur": v, "source": "grille EDF"})
    e = valeur_au(serie, d)
    if e is None:
        raise ValueError(f"aucune accise connue au {d}")
    return e["valeur"], e.get("source", "config/taxes.json") + f" (en vigueur au {e['debut']})"


def tva(d: date, config: dict, cle: str) -> float:
    e = valeur_au(config[cle], d)
    if e is None:
        raise ValueError(f"aucune TVA {cle} au {d}")
    return e["valeur"]


# Avant 2014, la TVA sur l'énergie était de 19,6 %. config/taxes.json ne la porte pas :
# une ligne au 1er janvier 2014 y ouvrirait une révision du TTC des grilles de 2013,
# sans accise connue à cette date. Elle ne sert qu'aux grilles EJP d'avant 2023.
TVA_ENERGIE_AVANT_2014 = 0.196


def tva_energie(d: date, config: dict) -> float:
    """TVA sur l'énergie au jour d, y compris avant 2014 (19,6 %)."""
    return TVA_ENERGIE_AVANT_2014 if d < date(2014, 1, 1) else tva(d, config, "tva_energie")


def kwh_ttc(ht: float, accise_v: float, tva_v: float) -> float:
    return round((ht + accise_v) * (1 + tva_v) + 1e-9, 4)


def abonnement_ttc(ht: float, cta: float, tva_v: float) -> float:
    return round((ht + cta) * (1 + tva_v) + 1e-9, 2)


# Options dont la CTA est calculée à partir du TURPE (absentes de l'open data CRE).
OPTIONS_TURPE = {"ejp"}

# Part puissance du soutirage servant d'assiette à la CTA, propre à chaque période de
# config/taxes.json (une seule des deux clés par période). EJP : tarif CU (sans
# différenciation temporelle) sous le TURPE 5, vérifié au centime sur les grilles EDF
# d'août 2018, 2019, 2020 et 2021 ; CU4 à partir d'août 2022, vérifié
# sur les grilles EDF de février 2023 à août 2026.
FORMULES_SOUTIRAGE = {"soutirage_fixe_cu": "CU", "soutirage_fixe_cu4": "CU4"}


def cta_turpe(option: str, d: date, kva: int, config: dict) -> tuple[float, str] | None:
    """CTA annuelle (€/an HT) calculée à partir du TURPE, ou None si la date n'est pas couverte."""
    if option not in OPTIONS_TURPE:
        return None
    periode = next(
        (e for e in config.get("turpe_part_fixe", [])
         if date.fromisoformat(e["debut"]) <= d <= date.fromisoformat(e["fin"])),
        None,
    )
    taux = valeur_au(config.get("cta_taux", []), d)
    if periode is None or taux is None:
        return None
    champs = [c for c in FORMULES_SOUTIRAGE if c in periode]
    if len(champs) != 1:
        raise ValueError(f"période TURPE du {periode['debut']} : une et une seule de {sorted(FORMULES_SOUTIRAGE)}")
    champ = champs[0]
    part_fixe = periode["gestion"] + periode["comptage"] + periode[champ] * kva
    return (
        taux["valeur"] * part_fixe,
        f"CTA {taux['valeur']:.2%} × part fixe TURPE (gestion + comptage + {FORMULES_SOUTIRAGE[champ]} × kVA, "
        f"{periode['source']})",
    )


# --- abonnement TTC révisé par le TURPE avant 2018 (Base, HP/HC, Tempo) ----------------

REVISIONS_ABONNEMENT = Path(__file__).resolve().parents[2] / "config" / "revisions_abonnement.json"


def charger_revisions_abonnement(path: Path = REVISIONS_ABONNEMENT) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def abonnement_ttc_turpe(option: str, kva: int, ht: float, periode: dict, conf: dict) -> float:
    """Abonnement TTC = (HT + CTA) × (1 + TVA), CTA = taux × part fixe du TURPE de ``periode``.

    Soutirage « courte utilisation » pour la Base et au-delà de 18 kVA, « moyenne
    utilisation » pour HP/HC et Tempo jusqu'à 18 kVA (config/revisions_abonnement.json).
    """
    tranche = 0 if kva <= 9 else 1 if kva <= 18 else 2
    tarif = "cu" if option == "base" or kva > 18 else "mu"
    part_fixe = periode["gestion"] + periode["comptage"][kva > 18] + periode[tarif][tranche] * kva
    return abonnement_ttc(ht, round(conf["cta_taux"] * part_fixe + 1e-9, 2), conf["tva_abonnement"])


# --- révision du TTC en cours de grille ----------------------------------------------

def _changements(serie: list[dict], apres: date, jusqu_a: date) -> list[dict]:
    return [e for e in serie if apres < date.fromisoformat(e["debut"]) <= jusqu_a]


def reviser_ttc(grille: dict, jour: date, config: dict) -> dict:
    """TTC de la grille applicable le ``jour``, si une taxe a changé depuis sa date d'effet.

    Le TTC d'une grille (open data CRE, grille EDF) est celui du jour d'effet. Une taxe peut
    changer ensuite sans nouveau barème (accise par loi de finances, taux de CTA, TVA, TURPE
    pour l'EJP) : on recalcule alors le TTC à partir du HT et des taxes de ``config`` en
    vigueur le ``jour``. La grille révisée porte ``ttc_estime: true`` et ``taxes.revision_ttc``.
    Renvoie la grille telle quelle (même objet) si rien n'a changé.
    """
    d = date.fromisoformat(grille["date_effet"])
    option = grille["option"]
    ch = {
        cle: _changements(config.get(cle, []), d, jour)
        for cle in ("accise_eur_kwh", "tva_energie", "tva_abonnement", "cta_taux", "turpe_part_fixe")
    }
    if option not in OPTIONS_TURPE:
        ch["turpe_part_fixe"] = []
    if not any(ch.values()):
        return grille

    g = copy.deepcopy(grille)
    t = g["taxes"]
    kwh = bool(ch["accise_eur_kwh"] or ch["tva_energie"])
    acc, acc_src = accise(jour, config) if ch["accise_eur_kwh"] else (t["accise_eur_kwh"], t.get("accise_source"))
    tva_e = tva(jour, config, "tva_energie")
    tva_a_avant, tva_a = t["tva_abonnement"], tva(jour, config, "tva_abonnement")
    taux_avant, taux = valeur_au(config.get("cta_taux", []), d), valeur_au(config.get("cta_taux", []), jour)

    for k, p in g["puissances"].items():
        if kwh:
            p["prix_ttc"] = {per: kwh_ttc(v, acc, tva_e) for per, v in p["prix_ht"].items()}
        if p.get("abonnement_ttc") is None:
            continue
        cta = p["abonnement_ttc"] / (1 + tva_a_avant) - p["abonnement_ht"]
        calc = cta_turpe(option, jour, int(k), config) if (ch["turpe_part_fixe"] or ch["cta_taux"]) else None
        if calc is not None:
            cta = calc[0]
        elif ch["cta_taux"] and taux_avant and taux:
            cta *= taux["valeur"] / taux_avant["valeur"]
        p["abonnement_ttc"] = abonnement_ttc(p["abonnement_ht"], cta, tva_a)
        if "abonnement_ttc_mensuel" in p:
            p["abonnement_ttc_mensuel"] = round(p["abonnement_ttc"] / 12, 2)

    valeurs = [p["prix_ttc"] for p in g["puissances"].values()]
    if valeurs and all(v == valeurs[0] for v in valeurs):
        g["prix_ttc"] = valeurs[0]
    else:
        g.pop("prix_ttc", None)

    motifs = [
        f"{cle} au {e['debut']}" + (f" : {e['valeur']}" if "valeur" in e else "")
        + (f" ({e['source']})" if e.get("source") else "")
        for cle, lst in ch.items() for e in lst
    ]
    g["ttc_estime"] = True
    t.update({"accise_eur_kwh": acc, "tva_energie": tva_e, "tva_abonnement": tva_a})
    if acc_src:
        t["accise_source"] = acc_src
    t["revision_ttc"] = {
        "date": max(e["debut"] for lst in ch.values() for e in lst),
        "motifs": motifs,
    }
    return g
