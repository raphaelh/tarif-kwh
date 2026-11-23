"""Schéma commun : définition des options tarifaires et structure d'une grille.

Une *grille* est le barème d'une option à une date d'effet donnée. Toutes les
sources (délibération CRE, grille EDF, open data CRE…) produisent des
``GrilleSource`` dans ce même format, ce qui permet de les comparer.

Unités : prix du kWh en €/kWh, abonnement en €/an (``abonnement_ttc_mensuel``
en €/mois quand le fournisseur le publie).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class OptionDef:
    code: str
    libelle: str
    periodes: tuple[str, ...]
    puissances: tuple[int, ...]  # puissances possibles (kVA)
    min_puissances: int  # nombre minimal de puissances attendues dans une grille
    plages: Optional[dict] = None  # plages horaires communes à tous les clients
    note: str = ""


TOUTES_PUISSANCES = (3, 6, 9, 12, 15, 18, 24, 30, 36)

OPTIONS: dict[str, OptionDef] = {
    "base": OptionDef(
        code="base",
        libelle="Tarif Bleu résidentiel - option Base",
        periodes=("base",),
        puissances=TOUTES_PUISSANCES,
        min_puissances=5,
        note="Le prix du kWh dépend de la puissance (≤ 6 kVA / ≥ 9 kVA). "
        "Option en extinction de 9 à 36 kVA.",
    ),
    "hphc": OptionDef(
        code="hphc",
        libelle="Tarif Bleu résidentiel - option Heures Creuses",
        periodes=("hp", "hc"),
        puissances=TOUTES_PUISSANCES,
        min_puissances=8,
        note="Les heures creuses (8 h/jour) sont fixées par Enedis pour chaque "
        "compteur : elles ne sont pas publiées ici.",
    ),
    "tempo": OptionDef(
        code="tempo",
        libelle="Tarif Bleu résidentiel - option Tempo",
        periodes=("bleu_hc", "bleu_hp", "blanc_hc", "blanc_hp", "rouge_hc", "rouge_hp"),
        puissances=(6, 9, 12, 15, 18, 24, 30, 36),
        min_puissances=8,
        plages={"hc": "22:00-06:00", "hp": "06:00-22:00"},
        note="Couleur du jour annoncée la veille par RTE (22 jours rouges, 43 blancs).",
    ),
    "ejp": OptionDef(
        code="ejp",
        libelle="Tarif Bleu résidentiel - option EJP (clients existants)",
        periodes=("normal", "pointe"),
        puissances=(9, 12, 15, 18, 36),
        min_puissances=5,
        plages={"pointe": "07:00-01:00 les 22 jours de pointe mobile"},
        note="Option en extinction, réservée aux clients existants.",
    ),
}

# Statuts de confiance, du moins sûr au plus sûr.
STATUTS = ("propose", "en_vigueur", "confirme")


@dataclass
class Puissance:
    """Valeurs d'une ligne de barème (une puissance souscrite)."""

    abonnement_ht: Optional[float] = None  # €/an
    abonnement_ttc: Optional[float] = None  # €/an
    abonnement_ttc_mensuel: Optional[float] = None  # €/mois (grille fournisseur)
    prix_ht: dict[str, float] = field(default_factory=dict)  # €/kWh
    prix_ttc: dict[str, float] = field(default_factory=dict)  # €/kWh


@dataclass
class GrilleSource:
    """Barème d'une option tel que lu dans UNE source."""

    option: str
    date_effet: date
    source: str  # 'cre_deliberation', 'jourtempo', 'edf_grille', 'cre_opendata'
    url: str
    puissances: dict[int, Puissance] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)  # ex. accise lue, date de publication

    def periodes(self) -> set[str]:
        s: set[str] = set()
        for p in self.puissances.values():
            s |= set(p.prix_ht) | set(p.prix_ttc)
        return s


def parse_nombre_fr(s: str) -> float:
    """'1 234,56' -> 1234.56"""
    s = s.replace(" ", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    return float(s)
