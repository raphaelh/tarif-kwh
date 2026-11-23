"""Calcul du TTC à partir du HT.

kWh TTC        = (HT + accise) × (1 + TVA énergie)
abonnement TTC = (HT + CTA) × (1 + TVA abonnement)

La CTA dépend de la part fixe du tarif d'acheminement (TURPE), propre à chaque
option et puissance, et change chaque 1er août : on la déduit de la dernière
grille officielle connue (open data CRE). Un TTC calculé ainsi est une
ESTIMATION, signalée par ``ttc_estime: true`` dans les JSON.
"""
from __future__ import annotations

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


def kwh_ttc(ht: float, accise_v: float, tva_v: float) -> float:
    return round((ht + accise_v) * (1 + tva_v) + 1e-9, 4)


def abonnement_ttc(ht: float, cta: float, tva_v: float) -> float:
    return round((ht + cta) * (1 + tva_v) + 1e-9, 2)
