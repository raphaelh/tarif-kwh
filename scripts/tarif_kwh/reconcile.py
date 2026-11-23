"""Recoupement des sources et calcul du statut de chaque grille.

Statuts (du moins sûr au plus sûr) :
- ``propose``    : délibération CRE seule (prix HT officiels, TTC estimé) ;
- ``en_vigueur`` : date d'effet atteinte sans texte signalé au JORF, ou
                   grille EDF (copie archive.org) concordante ;
- ``confirme``   : l'open data CRE (HT + TTC) concorde.

Tout désaccord entre sources, ou toute incohérence, est BLOQUANT.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from . import checks, taxes
from .schema import OPTIONS, GrilleSource, Puissance

TOL_KWH = 0.00011  # arrondi à 4 décimales des deux côtés
TOL_ABO = 0.011  # €/an
TOL_MENSUEL = 0.01  # 1 % entre abonnement mensuel EDF ×12 et annuel

ORDRE_SOURCES = ("cre_deliberation", "edf_grille", "cre_opendata")


# --- (dé)sérialisation du registre ---------------------------------------------

def grille_to_dict(g: GrilleSource) -> dict:
    return {
        "option": g.option,
        "date_effet": g.date_effet.isoformat(),
        "source": g.source,
        "url": g.url,
        "meta": g.meta,
        "puissances": {str(k): asdict(p) for k, p in sorted(g.puissances.items())},
    }


def grille_from_dict(d: dict) -> GrilleSource:
    return GrilleSource(
        option=d["option"],
        date_effet=date.fromisoformat(d["date_effet"]),
        source=d["source"],
        url=d["url"],
        meta=d.get("meta", {}),
        puissances={int(k): Puissance(**v) for k, v in d["puissances"].items()},
    )


# --- recoupement -------------------------------------------------------------

def _cta_connues(registre: dict, option: str, avant: date) -> tuple[dict[int, float], str | None]:
    """CTA par puissance déduite de la dernière grille open data (date <= avant)."""
    meilleures: tuple[str, dict] | None = None
    for d, obs in registre.get("grilles", {}).get(option, {}).items():
        od = obs.get("cre_opendata")
        if od and date.fromisoformat(d) <= avant and (meilleures is None or d > meilleures[0]):
            meilleures = (d, od)
    if not meilleures:
        return {}, None
    d, od = meilleures
    g = grille_from_dict(od)
    tva = taxes.tva(g.date_effet, taxes.charger_config(), "tva_abonnement")
    return (
        {k: p.abonnement_ttc / (1 + tva) - p.abonnement_ht for k, p in g.puissances.items()},
        d,
    )


def recouper(
    option: str,
    date_effet: date,
    obs: dict[str, GrilleSource],
    registre: dict,
    config_taxes: dict,
    aujourd_hui: date,
    alertes_jorf: list[dict] | None = None,
) -> tuple[dict | None, list[str]]:
    """Fusionne les observations d'une (option, date). Renvoie (grille, problèmes)."""
    pb: list[str] = []
    for g in obs.values():
        pb += checks.coherence(g)
    delib = obs.get("cre_deliberation")
    edf = obs.get("edf_grille")
    od = obs.get("cre_opendata")
    if not (delib or od):
        if edf:
            pb.append(
                f"{option} {date_effet}: grille EDF publiée mais aucune délibération CRE "
                "ni open data correspondante (délibération non découverte ?)"
            )
        return None, pb
    if pb:
        return None, pb

    # Délibération vs open data : HT identiques
    if delib and od:
        for k, q in od.puissances.items():
            p = delib.puissances.get(k)
            if p is None:
                pb.append(f"{option} {date_effet}: {k} kVA dans l'open data mais pas dans la délibération")
                continue
            if abs(p.abonnement_ht - q.abonnement_ht) > TOL_ABO:
                pb.append(f"{option} {date_effet} {k} kVA: abonnement HT CRE {p.abonnement_ht} ≠ open data {q.abonnement_ht}")
            for per, v in q.prix_ht.items():
                if abs(p.prix_ht[per] - v) > TOL_KWH / 2:
                    pb.append(f"{option} {date_effet} {k} kVA {per}: HT CRE {p.prix_ht[per]} ≠ open data {v}")

    # Accise : lue dans la grille EDF de cette date, sinon configuration
    observees = registre.get("accise_observee", {})
    if edf and edf.meta.get("accise_eur_kwh"):
        accise_v = edf.meta["accise_eur_kwh"]
        accise_src = f"grille EDF ({edf.url})"
    else:
        accise_v, accise_src = taxes.accise(date_effet, config_taxes, observees)
    tva_e = taxes.tva(date_effet, config_taxes, "tva_energie")
    tva_a = taxes.tva(date_effet, config_taxes, "tva_abonnement")
    cta, cta_date = _cta_connues(registre, option, date_effet)

    kvas = sorted(set(delib.puissances if delib else {}) | set(od.puissances if od else {}))
    puissances: dict[str, dict] = {}
    estime = False
    for k in kvas:
        src_ht = od.puissances[k] if od and k in od.puissances else delib.puissances[k]
        e = edf.puissances.get(k) if edf else None
        prix_ht = dict(src_ht.prix_ht)
        calc = {per: taxes.kwh_ttc(v, accise_v, tva_e) for per, v in prix_ht.items()}
        if od and k in od.puissances:
            prix_ttc = dict(od.puissances[k].prix_ttc)
        elif e:
            prix_ttc = dict(e.prix_ttc)
        else:
            prix_ttc = calc
            estime = True
        if e:  # EDF : TTC = HT CRE + accise EDF + TVA ; et = open data
            for per, v in e.prix_ttc.items():
                if abs(v - calc[per]) > TOL_KWH:
                    pb.append(
                        f"{option} {date_effet} {k} kVA {per}: TTC EDF {v} ≠ HT {prix_ht[per]} + taxes ({calc[per]})"
                    )
                if abs(v - prix_ttc[per]) > TOL_KWH:
                    pb.append(f"{option} {date_effet} {k} kVA {per}: TTC EDF {v} ≠ open data {prix_ttc[per]}")

        abo_ht = src_ht.abonnement_ht
        if od and k in od.puissances:
            abo_ttc = od.puissances[k].abonnement_ttc
        elif e and e.abonnement_ttc_mensuel:
            abo_ttc = round(e.abonnement_ttc_mensuel * 12, 2)
        elif k in cta:
            abo_ttc = taxes.abonnement_ttc(abo_ht, cta[k], tva_a)
            estime = True
        else:
            abo_ttc = None
            estime = True
        mensuel = e.abonnement_ttc_mensuel if e else (round(abo_ttc / 12, 2) if abo_ttc else None)
        if e and e.abonnement_ttc_mensuel and abo_ttc:
            if abs(e.abonnement_ttc_mensuel * 12 / abo_ttc - 1) > TOL_MENSUEL:
                pb.append(
                    f"{option} {date_effet} {k} kVA: abonnement EDF {e.abonnement_ttc_mensuel} €/mois "
                    f"incompatible avec {abo_ttc} €/an"
                )
        puissances[str(k)] = {
            "abonnement_ht": abo_ht,
            "abonnement_ttc": abo_ttc,
            "abonnement_ttc_mensuel": mensuel,
            "prix_ht": prix_ht,
            "prix_ttc": prix_ttc,
        }
    if edf:
        manquantes = set(edf.puissances) - set(kvas)
        if manquantes:
            pb.append(f"{option} {date_effet}: puissances EDF absentes côté CRE {sorted(manquantes)}")
    if pb:
        return None, pb

    # Statut
    alertes = [
        a for a in (alertes_jorf or [])
        if a.get("date_publication")
        and date_effet - timedelta(days=90)
        <= date.fromisoformat(a["date_publication"])
        <= date_effet + timedelta(days=30)
    ]
    if od:
        statut = "confirme"
    elif edf:
        statut = "en_vigueur"
    elif date_effet <= aujourd_hui and not alertes:
        statut = "en_vigueur"
    else:
        statut = "propose"

    sources = []
    for s in ORDRE_SOURCES:
        if s in obs:
            sources.append({"type": s, "url": obs[s].url, **({"recupere_le": obs[s].meta["recupere_le"]} if "recupere_le" in obs[s].meta else {})})

    grille = {
        "option": option,
        "date_effet": date_effet.isoformat(),
        "statut": statut,
        "ttc_estime": estime,
        "puissances": puissances,
        "sources": sources,
        "taxes": {
            "accise_eur_kwh": accise_v,
            "accise_source": accise_src,
            "tva_energie": tva_e,
            "tva_abonnement": tva_a,
            **({"cta_deduite_de": f"open data CRE, grille du {cta_date}"} if estime and cta_date else {}),
        },
        "alertes": [f"JORF {a['date_publication']}: {a['titre']} ({a['url']})" for a in alertes],
    }
    # Prix communs à toutes les puissances : remontés au niveau de la grille
    for champ in ("prix_ht", "prix_ttc"):
        valeurs = [p[champ] for p in puissances.values()]
        if valeurs and all(v == valeurs[0] for v in valeurs):
            grille[champ] = valeurs[0]

    return grille, []


def verifier_variation(grille: dict, precedente: dict | None, nb_sources: int, validee: bool = False) -> tuple[list[str], list[str]]:
    """(bloquants, remarques) selon la variation vs grille précédente."""
    ecarts = checks.variations(grille, precedente)
    if not ecarts:
        return [], []
    msg = f"{grille['option']} {grille['date_effet']}: variation > {checks.VARIATION_MAX:.0%} vs grille du {precedente['date_effet']} : " + "; ".join(ecarts[:6])
    if validee:
        return [], [msg + " (validée à la main dans config/validations.json)"]
    if nb_sources > 1:
        return [], [msg + " (confirmée par plusieurs sources)"]
    return [msg + " — en attente d'une seconde source"], []


# --- contrôle de l'accise appliquée --------------------------------------------

TOL_ACCISE = 0.0001  # €/kWh (0,1 €/MWh) : le TTC publié est arrondi au 1/10000


def accises_appliquees(registre: dict, config_taxes: dict) -> dict[str, tuple[float, str]]:
    """Accise réellement appliquée par date d'effet, d'après les sources officielles.

    Grille EDF : montant imprimé. Open data CRE : (TTC / (1 + TVA) - HT), médiane
    sur toutes les puissances et périodes.
    """
    out: dict[str, tuple[float, str]] = {}
    for option, dates in registre.get("grilles", {}).items():
        for d, obs in dates.items():
            if d in out:
                continue
            edf = obs.get("edf_grille")
            if edf and edf.get("meta", {}).get("accise_eur_kwh"):
                out[d] = (edf["meta"]["accise_eur_kwh"], "grille EDF")
                continue
            od = obs.get("cre_opendata")
            if od:
                tva = taxes.tva(date.fromisoformat(d), config_taxes, "tva_energie")
                v = sorted(
                    p["prix_ttc"][k] / (1 + tva) - p["prix_ht"][k]
                    for p in od["puissances"].values()
                    for k in p["prix_ht"]
                )
                if v:
                    out[d] = (round(v[len(v) // 2], 5), "open data CRE (TTC/1,2 - HT)")
    return out


def ecarts_accise(registre: dict, config_taxes: dict) -> list[str]:
    """Écarts entre l'accise appliquée et celle de config/taxes.json."""
    pb = []
    for d, (v, src) in sorted(accises_appliquees(registre, config_taxes).items()):
        e = taxes.valeur_au(config_taxes["accise_eur_kwh"], date.fromisoformat(d))
        if e is None or abs(e["valeur"] - v) > TOL_ACCISE:
            attendu = f"{e['valeur']} (ligne du {e['debut']})" if e else "aucune valeur"
            pb.append(f"grille du {d} : accise appliquée {v} €/kWh ({src}), config/taxes.json : {attendu}")
    return pb
