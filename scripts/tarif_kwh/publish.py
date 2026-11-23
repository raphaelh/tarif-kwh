"""Construction des JSON publiés dans docs/ à partir du registre."""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import reconcile, taxes
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


def grilles_validees(option: str, registre: dict, config_taxes: dict, aujourd_hui: date, alertes_jorf: list[dict], validations: set | None = None):
    """Recoupe toutes les grilles du registre : (grilles sans problème par date, problèmes par date, remarques)."""
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
            bloq, rem = reconcile.verifier_variation(g, precedente, len(obs), (option, d) in validations)
            pb += bloq
            remarques += rem
        if g:
            precedente = g  # on compare toujours à la grille immédiatement antérieure
        if pb:
            problemes[d] = pb
        else:
            ok[d] = g
    return ok, problemes, remarques


def evaluer_option(option: str, registre: dict, config_taxes: dict, aujourd_hui: date, alertes_jorf: list[dict], validations: set | None = None):
    """Renvoie (bloc publié ou None si bloqué, problèmes, remarques)."""
    ok, problemes, remarques = grilles_validees(option, registre, config_taxes, aujourd_hui, alertes_jorf, validations)

    passees = [d for d in ok if d <= aujourd_hui.isoformat()]
    futures = [d for d in ok if d > aujourd_hui.isoformat()]
    # TTC du jour : une taxe peut avoir changé depuis la date d'effet sans nouveau barème
    actuelle = taxes.reviser_ttc(ok[max(passees)], aujourd_hui, config_taxes) if passees else None
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


def _prix_communs(grille: dict) -> dict:
    """Remonte prix_ht / prix_ttc au niveau de la grille s'ils sont identiques pour toutes les puissances."""
    for champ in ("prix_ht", "prix_ttc"):
        valeurs = [p[champ] for p in grille["puissances"].values()]
        if valeurs and all(v == valeurs[0] for v in valeurs):
            grille[champ] = valeurs[0]
    return grille


def _grille_historique(debut: str, g: dict) -> dict:
    h = {
        "date_debut": debut,
        "date_fin": None,
        "statut": g["statut"],
        "ttc_estime": g["ttc_estime"],
        "sources": [{"type": s["type"], "url": s["url"]} for s in g["sources"]],
        "puissances": {
            k: {c: v for c, v in p.items() if c != "abonnement_ttc_mensuel"}
            for k, p in g["puissances"].items()
        },
    }
    if "revision_ttc" in g.get("taxes", {}):
        h["revision_ttc"] = g["taxes"]["revision_ttc"]
    return _prix_communs(h)


def _revisions(d: str, g: dict, bornes: set[str], aujourd_hui: date, config_taxes: dict | None) -> list[tuple[str, dict]]:
    """La grille du ``d``, puis une grille révisée à chaque changement de taxe avant la date d'effet suivante."""
    out = [(d, g)]
    if not config_taxes:
        return out
    suivante = min((b for b in bornes if b > d), default=None)
    changements = sorted({
        e["debut"]
        for serie in config_taxes.values() if isinstance(serie, list)
        for e in serie if isinstance(e, dict) and "debut" in e
        if d < e["debut"] <= aujourd_hui.isoformat() and (suivante is None or e["debut"] < suivante)
    })
    for c in changements:
        r = taxes.reviser_ttc(g, date.fromisoformat(c), config_taxes)
        if r is not g and r["puissances"] != out[-1][1]["puissances"]:
            out.append((c, r))
    return out


def construire_historique(
    opendata: dict | None,
    ancien: dict | None,
    validees: dict[str, dict[str, dict]],
    aujourd_hui: date,
    dates_connues: dict[str, set[str]] | None = None,
    config_taxes: dict | None = None,
) -> dict:
    """Toutes les grilles entrées en vigueur, par option, de la plus ancienne à l'actuelle.

    - ``opendata`` : ``{option: {"url", "grilles"}}`` lu dans l'open data CRE ce passage
      (None si non téléchargé : on reprend alors la partie open data de ``ancien``).
    - ``validees`` : grilles recoupées du registre, qui complètent l'open data (publié
      ≈ 4 semaines après la date d'effet ; pas d'EJP).
    - ``dates_connues`` : toutes les dates d'effet du registre, même celles dont la grille
      est rejetée : une grille rejetée clôt quand même la précédente (on laisse un trou
      plutôt que de prolonger à tort l'ancienne grille).
    - ``config_taxes`` : une taxe qui change en cours de grille (TURPE de l'EJP au 1er
      novembre 2024, par exemple) ouvre une période révisée, au TTC recalculé
      (``taxes.reviser_ttc``, ``ttc_estime: true``, ``revision_ttc``).
    """
    options: dict[str, dict] = {}
    for option, opt in OPTIONS.items():
        if opendata and option in opendata:
            url = opendata[option]["url"]
            od = [
                _prix_communs({**g, "statut": "confirme", "ttc_estime": False, "sources": [{"type": "cre_opendata", "url": url}]})
                for g in opendata[option]["grilles"]
            ]
        else:
            precedent = ((ancien or {}).get("options") or {}).get(option, {}).get("grilles", [])
            od = [g for g in precedent if [s["type"] for s in g.get("sources", [])] == ["cre_opendata"]]
        dernier = od[-1]["date_debut"] if od else ""
        retenues = {
            d: g for d, g in validees.get(option, {}).items() if dernier < d <= aujourd_hui.isoformat()
        }
        bornes = set(retenues) | set((dates_connues or {}).get(option, ()))
        suite = [
            _grille_historique(debut, g)
            for d, g in sorted(retenues.items())
            for debut, g in _revisions(d, g, bornes, aujourd_hui, config_taxes)
        ]
        grilles = [dict(g) for g in od + suite]
        debuts = sorted({g["date_debut"] for g in grilles} | {
            d for d in (dates_connues or {}).get(option, ()) if dernier < d <= aujourd_hui.isoformat()
        })
        for g in grilles:  # la date d'effet suivante clôt la grille
            suivante = next((d for d in debuts if d > g["date_debut"]), None)
            if suivante and (g["date_fin"] is None or g["date_fin"] >= suivante):
                g["date_fin"] = (date.fromisoformat(suivante) - timedelta(days=1)).isoformat()
        options[option] = {"libelle": opt.libelle, "periodes": list(opt.periodes), "grilles": grilles}
    return {
        "unites": {"prix": "EUR/kWh", "abonnement_ht": "EUR/an", "abonnement_ttc": "EUR/an"},
        "note": "date_fin = dernier jour d'application (inclus), null pour la grille en vigueur. "
        "TTC tel que publié par la CRE avec les taxes de l'époque (CSPE, TCFE, CTA, TVA), "
        "ou calculé si ttc_estime vaut true. Une période sans grille est une grille non publiée "
        "(rejetée par les contrôles). Une taxe changée en cours de grille ouvre une période au TTC "
        "recalculé (revision_ttc). Pas d'historique EJP dans l'open data CRE.",
        "options": options,
    }


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
    historique_opendata: dict | None = None,
) -> dict:
    """Écrit docs/<option>.json, docs/tarifs.json, docs/historique.json et docs/etat.json.

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
    f_hist = docs / "historique.json"
    try:
        ancien_hist = json.loads(f_hist.read_text(encoding="utf-8")) if f_hist.exists() else None
    except json.JSONDecodeError:
        ancien_hist = None
    validees = {o: grilles_validees(o, registre, config_taxes, aujourd_hui, alertes_jorf)[0] for o in OPTIONS}
    _stable_write(
        f_hist,
        {
            "schema_version": SCHEMA_VERSION,
            "avertissement": AVERTISSEMENT,
            **construire_historique(
                historique_opendata, ancien_hist, validees, aujourd_hui,
                {o: set(registre.get("grilles", {}).get(o, {})) for o in OPTIONS},
                config_taxes,
            ),
        },
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


def preparer_site(docs: Path, site: Path, sources_en_echec: list[str], maintenant: datetime | None = None) -> None:
    """Copie docs/ dans site/ (déployé sur GitHub Pages) et ajoute le signe de vie à site/etat.json.

    docs/etat.json, versionné, ne change qu'avec son contenu ; la copie publiée porte en plus
    derniere_verification (date de ce passage réussi) et sources_en_echec, sans commit.
    """
    horodatage = (maintenant or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(docs, site)
    f = site / "etat.json"
    etat = json.loads(f.read_text(encoding="utf-8"))
    etat["derniere_verification"] = horodatage
    etat["sources_en_echec"] = sorted(set(sources_en_echec))
    f.write_text(json.dumps(etat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

