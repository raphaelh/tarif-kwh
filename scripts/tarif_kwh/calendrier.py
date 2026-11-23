"""Échéances des TRVE : alerte si la délibération attendue n'est pas trouvée.

Depuis 2023, les TRVE évoluent au 1er février et au 1er août ; la CRE publie
sa délibération ~2 semaines avant. Si, à J-7, aucune grille n'est connue pour
l'échéance, c'est que la découverte a échoué (page CRE modifiée, blocage…) ou
que le calendrier a changé : dans les deux cas, un humain doit regarder.
"""
from __future__ import annotations

from datetime import date, timedelta

ECHEANCES = ((2, 1), (8, 1))  # (mois, jour)
ALERTE_AVANT = timedelta(days=7)  # alerte à partir de J-7…
ALERTE_APRES = timedelta(days=45)  # …et jusqu'à J+45 (ensuite, l'échéance suivante prend le relais)


def echeance_surveillee(aujourd_hui: date) -> date | None:
    """Échéance dont la fenêtre d'alerte contient ``aujourd_hui``, sinon None."""
    for annee in (aujourd_hui.year - 1, aujourd_hui.year, aujourd_hui.year + 1):
        for mois, jour in ECHEANCES:
            d = date(annee, mois, jour)
            if d - ALERTE_AVANT <= aujourd_hui <= d + ALERTE_APRES:
                return d
    return None


def deliberation_manquante(registre: dict, aujourd_hui: date) -> str | None:
    """Message d'alerte si aucune grille n'est connue pour l'échéance en cours."""
    d = echeance_surveillee(aujourd_hui)
    if d is None:
        return None
    # Une grille datée de l'échéance (ou un peu après) dans n'importe quelle source suffit.
    for dates in registre.get("grilles", {}).values():
        if any(d <= date.fromisoformat(x) <= d + ALERTE_APRES for x in dates):
            return None
    return (
        f"Aucune grille TRVE n'est connue pour l'échéance du {d:%d/%m/%Y} "
        f"(nous sommes le {aujourd_hui:%d/%m/%Y}). La délibération CRE est d'habitude publiée "
        "environ deux semaines avant.\n\n"
        "À vérifier :\n"
        "1. https://www.cre.fr/documents/deliberations.html : chercher « tarifs réglementés de vente d'électricité » ;\n"
        "2. si elle existe, ajouter l'URL de son annexe B à `config/sources.json` (`annexes_b_connues`) "
        "puis relancer la collecte, et signaler pourquoi la découverte automatique l'a manquée "
        "(journal du workflow) ;\n"
        "3. si la CRE n'a pas fait de proposition pour cette date, fermer cette issue."
    )
