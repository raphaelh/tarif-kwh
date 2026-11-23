#!/usr/bin/env python3
"""Collecte quotidienne : sources -> data/registre.json -> docs/*.json.

Usage :
    python scripts/collect.py                 # collecte complète
    python scripts/collect.py --hors-ligne    # reconstruit docs/ depuis le registre
    python scripts/collect.py --annexe URL    # force la lecture d'une annexe B CRE
    python scripts/collect.py --site _site    # prépare aussi le site GitHub Pages (signe de vie)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tarif_kwh import calendrier, http, issues, page, publish, reconcile, taxes  # noqa: E402
from tarif_kwh.sources import arretes, cre_deliberation, cre_opendata, edf_grille, jorf, jourtempo  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
REGISTRE = RACINE / "data" / "registre.json"
SOURCES = RACINE / "config" / "sources.json"
DOCS = RACINE / "docs"


PROCEDURE_ACCISE = """### Si le texte change l'accise sur l'électricité

1. Chercher le tarif de l'accise sur l'électricité, catégorie **« ménages et assimilés »** (€/MWh), et sa date
   d'entrée en vigueur. Barème à jour aussi sur douane.gouv.fr (« accise sur l'électricité »).
2. Convertir en €/kWh : diviser par 1 000 (30,62 €/MWh -> `0.03062`).
3. Ajouter une ligne à `config/taxes.json` (éditeur web GitHub : crayon, puis *Commit changes*) :
   `{"debut": "AAAA-MM-JJ", "valeur": 0.0xxxx, "source": "<texte, article>"}`
4. Les tests vérifient le fichier ; la collecte suivante (ou *Actions → Collecte des tarifs → Run workflow*)
   recalcule le TTC des grilles proposées.

Si le texte ne change pas l'accise, fermer simplement cette issue.
"""


PROCEDURE_TURPE = """### Mettre à jour la configuration TURPE

L'abonnement TTC de l'EJP (absente de l'open data CRE) est calculé : (HT + CTA) × (1 + TVA), avec
CTA = taux × (gestion + comptage + soutirage fixe CU4 × kVA) du TURPE HTA-BT.

1. Trouver la délibération CRE sur le TURPE applicable au 1er août (cre.fr, « TURPE HTA-BT », publiée vers mai-juin) :
   composante annuelle de gestion (contrat unique), de comptage (compteur communicant), et coefficient de
   soutirage fixe **CU4** (b, €/kVA/an).
2. Ajouter une période à `turpe_part_fixe` dans `config/taxes.json` :
   `{"debut": "AAAA-08-01", "fin": "AAAA+1-07-31", "gestion": …, "comptage": …, "soutirage_fixe_cu4": …, "source": "<délibération>"}`
3. Si l'écart vient du taux de CTA (formulaire DGFIP 2040-TIC-SD, facture EDF), ajouter une ligne à `cta_taux`.
4. Les tests vérifient le fichier ; la collecte suivante (ou *Actions → Collecte des tarifs → Run workflow*)
   recalcule l'abonnement EJP et compare de nouveau aux grilles EDF.
"""


def charger(path: Path, defaut: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else defaut


def maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def enregistrer_obs(registre: dict, g) -> bool:
    """Ajoute/actualise l'observation d'une source. Renvoie True si nouvelle ou modifiée."""
    d = reconcile.grille_to_dict(g)
    place = registre.setdefault("grilles", {}).setdefault(g.option, {}).setdefault(g.date_effet.isoformat(), {})
    ancien = place.get(g.source)
    if ancien:
        volatil = {"recupere_le", "copie_archive"}  # même grille, autre capture : pas de changement
        a = {**ancien, "meta": {k: v for k, v in ancien["meta"].items() if k not in volatil}}
        b = {**d, "meta": {k: v for k, v in d["meta"].items() if k not in volatil}}
        if a == b:
            return False
    d["meta"]["recupere_le"] = maintenant()
    place[g.source] = d
    return True


def etape(nom: str, erreurs: list[tuple[str, str]], fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # une source en panne ne doit pas bloquer les autres
        erreurs.append((nom, f"{type(e).__name__}: {e}\n\n```\n{traceback.format_exc()[-3000:]}\n```"))
        return None


def collecter(registre: dict, forcer: list[str], erreurs: list, historique: dict) -> None:
    traitees = registre.setdefault("annexes_traitees", {})
    # 1. Délibérations CRE (annexe B) : connues + découvertes + forcées
    sources = charger(SOURCES, {})
    connues = sources.get("annexes_b_connues", [])
    # Annexes anciennes sans date d'effet lisible : date fournie dans la configuration
    dates_fournies = {a["url"]: date.fromisoformat(a["date_effet"]) for a in sources.get("annexes_b_anciennes", [])}
    decouvertes = etape("Découverte des délibérations CRE", erreurs, cre_deliberation.decouvrir, set(traitees)) or []
    for url in dict.fromkeys(connues + list(dates_fournies) + decouvertes + forcer):
        if url in traitees and url not in forcer:
            continue
        contenu = etape(f"Téléchargement {url}", erreurs, http.get, url)
        if contenu is None:
            continue
        grilles = etape(
            f"Lecture de l'annexe B {url}", erreurs, cre_deliberation.parse_annexe_b, contenu, url, dates_fournies.get(url)
        )
        if grilles is None:
            continue
        for g in grilles.values():
            enregistrer_obs(registre, g)
        traitees[url] = {
            "sha256": hashlib.sha256(contenu).hexdigest(),
            "date_effet": next(iter(grilles.values())).date_effet.isoformat(),
            "traitee_le": maintenant(),
        }

    # 2. Grille EDF
    # Copie archive.org (EDF refuse GitHub) : source d'appoint, son absence n'est pas une erreur.
    try:
        grilles = edf_grille.collecter()
    except Exception as e:
        print(f"grille EDF (archive.org) indisponible : {e}", file=sys.stderr)
        grilles = {}
    for g in grilles.values():
        enregistrer_obs(registre, g)
        if g.meta.get("accise_eur_kwh"):
            registre.setdefault("accise_observee", {})[g.date_effet.isoformat()] = g.meta["accise_eur_kwh"]

    # 2 bis. Jour Tempo (data.gouv) : HT EJP depuis 2013 et Tempo 2013-2016, texte officiel cité. Source d'appoint.
    try:
        for g in jourtempo.collecter():
            enregistrer_obs(registre, g)
    except Exception as e:
        print(f"Jour Tempo indisponible : {e}", file=sys.stderr)

    # 2 ter. Barèmes HT recopiés d'arrêtés (config) : Tempo et EJP au 23 juillet 2012.
    for g in etape("Barèmes des arrêtés (config)", erreurs, arretes.collecter) or []:
        enregistrer_obs(registre, g)

    # 3. Open data CRE
    grilles = etape("Open data CRE", erreurs, cre_opendata.collecter, historique)
    for g in (grilles or {}).values():
        enregistrer_obs(registre, g)
    if historique:  # TTC reconnus faux (Tempo 2022), avant d'en déduire les taxes de l'EJP
        for ligne in cre_opendata.corriger(historique, cre_opendata.charger_corrections(), taxes.charger_config()):
            print(ligne, file=sys.stderr)
    if historique:  # taxes au kWh d'avant 2023, pour le TTC de l'EJP (gardées hors ligne)
        registre["taxes_kwh_opendata"] = reconcile.taxes_kwh_opendata(historique, taxes.charger_config())

    # 4. JORF
    # On relit les 6 dernières éditions (~3 jours) à chaque passage et on
    # dédoublonne par URL : pas de curseur à committer chaque jour.
    j = registre.setdefault("jorf", {"textes": []})
    j.pop("derniere_archive", None)
    res = etape("Veille JORF", erreurs, jorf.collecter, None, 6)
    if res:
        textes, _ = res
        connus = {t["url"] for t in j["textes"]}
        for t in textes:
            if t["url"] not in connus:
                connus.add(t["url"])  # un même texte peut figurer dans plusieurs archives
                j["textes"].append(t)
                corps = (
                    "Un texte publié au Journal officiel concerne peut-être les TRVE ou l'accise :\n\n"
                    f"- **{t['titre']}**\n- {t['nature']} publié le {t['date_publication']}\n- {t['url']}\n\n"
                )
                if jorf.concerne_les_taxes(t["titre"], t.get("nature") or ""):
                    corps += PROCEDURE_ACCISE
                else:
                    corps += "Vérifier s'il modifie ou bloque les prix proposés par la CRE."
                issues.alerter(f"JORF : texte à vérifier — {t['titre'][:90]}", corps)


def amorcer_captures_ejp(registre: dict) -> None:
    """Lit toutes les captures archivées de la grille EDF EJP (amorçage de l'historique).

    Une grille EDF n'est retenue que si une grille EJP HT existe à la même date
    (délibération CRE ou Jour Tempo) : sinon (ex. révision du seul TTC au 1er novembre 2024, après une
    hausse de la CTA) elle n'est pas une nouvelle grille tarifaire.
    """
    grilles, illisibles = edf_grille.collecter_captures_ejp()
    for msg in illisibles:
        print(f"capture EJP illisible : {msg}", file=sys.stderr)
    connues = registre.get("grilles", {}).get("ejp", {})
    for g in grilles:
        d = g.date_effet.isoformat()
        if not {"cre_deliberation", "jourtempo", "arrete"} & set(connues.get(d, {})):
            print(f"grille EDF EJP du {d} ignorée : aucune grille HT (CRE, Jour Tempo) à cette date", file=sys.stderr)
            continue
        enregistrer_obs(registre, g)
        if g.meta.get("accise_eur_kwh"):
            registre.setdefault("accise_observee", {})[d] = g.meta["accise_eur_kwh"]
        print(f"grille EDF EJP du {d} enregistrée ({g.meta.get('copie_archive', g.url)})", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hors-ligne", action="store_true", help="ne télécharge rien")
    ap.add_argument("--annexe", action="append", default=[], help="URL d'annexe B à lire")
    ap.add_argument("--date", help="date du jour simulée (AAAA-MM-JJ)")
    ap.add_argument(
        "--captures-edf", action="store_true",
        help="lit toutes les captures archive.org de la grille EDF EJP (amorçage de l'historique)",
    )
    ap.add_argument("--site", type=Path, help="dossier du site GitHub Pages à préparer (copie de docs/)")
    args = ap.parse_args()

    registre = charger(REGISTRE, {"schema_version": 1})
    erreurs: list[tuple[str, str]] = []
    historique: dict = {}  # open data CRE complet, pour docs/historique.json
    if not args.hors_ligne:
        collecter(registre, args.annexe, erreurs, historique)
        if args.captures_edf:
            amorcer_captures_ejp(registre)

    aujourd_hui = date.fromisoformat(args.date) if args.date else date.today()
    etat = publish.publier(
        DOCS, registre, taxes.charger_config(), aujourd_hui, registre.get("jorf", {}).get("textes", []),
        historique_opendata=historique or None,
    )
    REGISTRE.parent.mkdir(exist_ok=True)
    REGISTRE.write_text(json.dumps(registre, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    manque = calendrier.deliberation_manquante(registre, aujourd_hui)
    if manque:
        d = calendrier.echeance_surveillee(aujourd_hui)
        issues.alerter(f"Délibération TRVE attendue non trouvée (échéance du {d:%d/%m/%Y})", manque)
    ecarts = reconcile.ecarts_accise(registre, taxes.charger_config())
    if ecarts:
        issues.alerter(
            "Accise à mettre à jour dans config/taxes.json",
            "L'accise appliquée par les sources officielles diffère de `config/taxes.json` : les TTC "
            "estimés des prochaines grilles seraient faux.\n\n"
            + "\n".join(f"- {e}" for e in ecarts) + "\n\n" + PROCEDURE_ACCISE,
        )
    hors = reconcile.ejp_hors_turpe(registre, taxes.charger_config())
    if hors:
        issues.alerter(
            "TURPE à ajouter dans config/taxes.json (abonnement EJP)",
            "Une grille EJP tombe hors des périodes TURPE configurées : son abonnement TTC ne peut pas être "
            "calculé (publié à `null` tant qu'EDF n'a pas publié sa grille).\n\n"
            + "\n".join(f"- {e}" for e in hors) + "\n\n" + PROCEDURE_TURPE,
        )
    ecarts_ejp = reconcile.ecarts_abonnement_ejp(registre, taxes.charger_config())
    if ecarts_ejp:
        issues.alerter(
            "Abonnement EJP calculé ≠ grille EDF : vérifier config/taxes.json",
            "L'abonnement EJP calculé par la CTA du TURPE diffère de celui imprimé sur la grille EDF : période "
            "TURPE ou taux de CTA à corriger, sinon les abonnements calculés (grilles sans grille EDF) sont faux.\n\n"
            + "\n".join(f"- {e}" for e in ecarts_ejp) + "\n\n" + PROCEDURE_TURPE,
        )
    for nom, detail in erreurs:
        issues.alerter(f"Source en échec : {nom[:100]}", detail)
    for option, e in etat.items():
        if e["publication"] == "bloquee":
            issues.alerter(
                f"Publication bloquée : option {option}",
                "Les contrôles ont échoué ; le JSON précédent de cette option est conservé.\n\n"
                + "\n".join(f"- {p}" for p in e["problemes"]),
            )
        for r in e["remarques"]:
            print("remarque:", r, file=sys.stderr)
    if args.site:
        publish.preparer_site(DOCS, args.site, [nom for nom, _ in erreurs])
        page.ecrire_index(args.site)  # page lisible : un tableau par option
    print(json.dumps({o: e["publication"] for o, e in etat.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
