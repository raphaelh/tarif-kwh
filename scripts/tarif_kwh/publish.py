"""Construction des JSON publiés dans docs/ à partir du registre."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from . import reconcile
from .schema import OPTIONS, SCHEMA_VERSION

AVERTISSEMENT = (
    "Projet NON officiel, sans lien avec EDF, la CRE ou les pouvoirs publics. "
    "Données issues des publications officielles (délibérations CRE, grille Tarif Bleu EDF, "
    "open data CRE), sans garantie. Vérifiez sur votre facture."
)
OFFRE = "Tarif réglementé de vente d'électricité (TRVE) - Tarif Bleu résidentiel, France métropolitaine continentale"
UNITES = {
    "prix": "EUR/kWh",
    "abonnement_ht": "EUR/an",
    "abonnement_ttc": "EUR/an",
    "abonnement_ttc_mensuel": "EUR/mois",
}


VALIDATIONS = Path(__file__).resolve().parents[2] / "config" / "validations.json"


def charger_validations(path: Path = VALIDATIONS) -> set[tuple[str, str]]:
    """Grilles validées à la main (variation forte confirmée par un humain)."""
    if not path.exists():
        return set()
    return {(v["option"], v["date_effet"]) for v in json.loads(path.read_text(encoding="utf-8"))["validations"]}


def evaluer_option(option: str, registre: dict, config_taxes: dict, aujourd_hui: date, alertes_jorf: list[dict], validations: set | None = None):
    """Renvoie (bloc publié ou None si bloqué, problèmes, remarques)."""
    validations = charger_validations() if validations is None else validations
    dates = sorted(registre.get("grilles", {}).get(option, {}))
    ok: dict[str, dict] = {}
    problemes: dict[str, list[str]] = {}
    remarques: list[str] = []
    precedente = None
    for d in dates:
        obs = {s: reconcile.grille_from_dict(v) for s, v in registre["grilles"][option][d].items()}
        g, pb = reconcile.recouper(option, date.fromisoformat(d), obs, registre, config_taxes, aujourd_hui, alertes_jorf)
        if g:
            nb = len(obs) + (1 if (option, d) in validations else 0)
            bloq, rem = reconcile.verifier_variation(g, precedente, nb)
            pb += bloq
            remarques += rem
        if g:
            precedente = g  # on compare toujours à la grille immédiatement antérieure
        if pb:
            problemes[d] = pb
        else:
            ok[d] = g

    passees = [d for d in ok if d <= aujourd_hui.isoformat()]
    futures = [d for d in ok if d > aujourd_hui.isoformat()]
    actuelle = ok[max(passees)] if passees else None
    prochaine = ok[min(futures)] if futures else None
    # Un problème sur la grille courante ou une grille plus récente bloque l'option.
    seuil = actuelle["date_effet"] if actuelle else ""
    bloquants = [p for d, pbs in problemes.items() if d >= seuil for p in pbs]
    if bloquants or not actuelle:
        if not actuelle and not bloquants:
            bloquants = [f"{option}: aucune grille en vigueur connue"]
        return None, bloquants, remarques

    opt = OPTIONS[option]
    bloc = {
        "option": option,
        "libelle": opt.libelle,
        "offre": OFFRE,
        "fournisseur": "EDF",
        "type_prix": "reglemente",
        "periodes": list(opt.periodes),
        "plages_horaires": opt.plages,
        "note": opt.note,
        "unites": UNITES,
        "actuelle": actuelle,
        "prochaine": prochaine,
    }
    return bloc, [], remarques


def _stable_write(path: Path, data: dict, horodatage: str) -> bool:
    """Écrit le fichier si le contenu (hors horodatage) a changé. Renvoie True si écrit."""
    ancien = None
    if path.exists():
        try:
            ancien = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ancien = None
    if ancien is not None:
        a = dict(ancien)
        a.pop("mis_a_jour_le", None)
        if a == data:
            return False
    path.write_text(
        json.dumps({**data, "mis_a_jour_le": horodatage}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def publier(
    docs: Path,
    registre: dict,
    config_taxes: dict,
    aujourd_hui: date,
    alertes_jorf: list[dict],
    maintenant: datetime | None = None,
) -> dict:
    """Écrit docs/<option>.json, docs/tarifs.json et docs/etat.json.

    Une option bloquée garde son fichier précédent (rien de nouveau n'est publié).
    Renvoie l'état : {option: {"publication", "problemes", "remarques"}}.
    """
    horodatage = (maintenant or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    docs.mkdir(parents=True, exist_ok=True)
    etat: dict[str, dict] = {}
    blocs: dict[str, dict] = {}
    for option in OPTIONS:
        bloc, pb, rem = evaluer_option(option, registre, config_taxes, aujourd_hui, alertes_jorf)
        f = docs / f"{option}.json"
        if bloc is None:
            etat[option] = {"publication": "bloquee", "problemes": pb, "remarques": rem}
            if f.exists():  # on republie l'ancien contenu tel quel dans tarifs.json
                ancien = json.loads(f.read_text(encoding="utf-8"))
                ancien.pop("mis_a_jour_le", None)
                ancien.pop("schema_version", None)
                ancien.pop("avertissement", None)
                blocs[option] = ancien
            continue
        etat[option] = {"publication": "ok", "problemes": [], "remarques": rem}
        blocs[option] = bloc
        _stable_write(f, {"schema_version": SCHEMA_VERSION, "avertissement": AVERTISSEMENT, **bloc}, horodatage)

    _stable_write(
        docs / "tarifs.json",
        {"schema_version": SCHEMA_VERSION, "avertissement": AVERTISSEMENT, "options": blocs},
        horodatage,
    )
    _stable_write(
        docs / "etat.json",
        {
            "schema_version": SCHEMA_VERSION,
            "options": etat,
            "jorf_textes_signales": alertes_jorf[-20:],
        },
        horodatage,
    )
    return etat
