"""Source 2 : grilles de prix « Tarif Bleu » publiées par EDF (PDF, TTC).

Publiées à l'entrée en vigueur. Prix TTC : abonnement mensuel (€/mois) et kWh
(c€/kWh). Deux documents : la grille Base / Heures Creuses / Tempo, et une
grille à part pour l'option EJP (seule source officielle de l'abonnement EJP
TTC). Chacune indique le montant de l'accise appliqué, ce qui permet de
recalculer le TTC à partir des prix HT de la CRE.
"""
from __future__ import annotations

import io
import json
import re
import sys
from datetime import date
from urllib.parse import urlencode

import pdfplumber

from .. import http
from ..schema import GrilleSource, Puissance, parse_nombre_fr

SOURCE = "edf_grille"
URL = "https://particulier.edf.fr/content/dam/2-Actifs/Documents/Offres/Grille_prix_Tarif_Bleu.pdf"
URL_EJP = "https://particulier.edf.fr/content/dam/2-Actifs/Documents/Offres/Grille_prix_EJP.pdf"

MOIS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "décembre": 12,
}
RE_APPLICABLE = re.compile(r"Applicable au (\d{1,2})(?:er)?\s+([a-zéû]+)\s+(20\d\d)", re.I)
RE_ACCISE = re.compile(r"Accise sur l.électricité\S*,?\s*d.un montant de\s*([\d,]+)\s*cts", re.I)
RE_LIGNE = re.compile(r"^(\d{1,2})\s+((?:\d+,\d+\s*)+)$")
RE_NOMBRE = re.compile(r"\d+,\d+")

COLONNES = {
    "base": ("base",),
    "hphc": ("hp", "hc"),
    "tempo": ("bleu_hc", "bleu_hp", "blanc_hc", "blanc_hp", "rouge_hc", "rouge_hp"),
    "ejp": ("normal", "pointe"),
}


class ParseError(ValueError):
    pass


def _table(texte: str, option: str, url: str, d: date) -> GrilleSource:
    g = GrilleSource(option, d, SOURCE, url)
    cols = COLONNES[option]
    for ligne in texte.splitlines():
        m = RE_LIGNE.match(ligne.strip())
        if not m:
            continue
        nombres = [parse_nombre_fr(x) for x in RE_NOMBRE.findall(m.group(2))]
        if len(nombres) != 1 + len(cols):
            continue
        g.puissances[int(m.group(1))] = Puissance(
            abonnement_ttc_mensuel=nombres[0],
            prix_ttc={c: round(v / 100, 6) for c, v in zip(cols, nombres[1:])},
        )
    if not g.puissances:
        raise ParseError(f"grille EDF : tableau {option} introuvable")
    return g


def _date_applicable(texte: str) -> date:
    m = RE_APPLICABLE.search(texte)
    if not m or m.group(2).lower() not in MOIS:
        raise ParseError("grille EDF : date « Applicable au … » introuvable")
    return date(int(m.group(3)), MOIS[m.group(2).lower()], int(m.group(1)))


def _ajouter_accise(grilles: dict[str, GrilleSource], tout: str) -> None:
    ma = RE_ACCISE.search(tout.replace("\n", " "))
    if ma:
        accise = round(parse_nombre_fr(ma.group(1)) / 100, 6)  # €/kWh
        for g in grilles.values():
            g.meta["accise_eur_kwh"] = accise


def parse_grille_ejp(pdf_bytes: bytes, url: str = URL_EJP) -> dict[str, GrilleSource]:
    """Grille « Tarif Bleu option EJP » : un seul tableau (kVA, abonnement, normal, pointe)."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texte = pdf.pages[0].extract_text() or ""
        tout = "\n".join((p.extract_text() or "") for p in pdf.pages)
    if "Option EJP" not in texte:
        raise ParseError("grille EDF EJP : titre « Option EJP » introuvable")
    grilles = {"ejp": _table(texte, "ejp", url, _date_applicable(texte))}
    _ajouter_accise(grilles, tout)
    return grilles


def parse_grille(pdf_bytes: bytes, url: str = URL) -> dict[str, GrilleSource]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        texte = page.extract_text() or ""
        tout = "\n".join((p.extract_text() or "") for p in pdf.pages)
        d = _date_applicable(texte)

        mots = page.extract_words()
        options_y = [w for w in mots if w["text"] == "Option"]
        tempo = [w for w in mots if w["text"] == "Tempo"]
        if len(options_y) < 3 or not tempo:
            raise ParseError("grille EDF : mise en page inattendue (titres d'options)")
        # Base (colonne gauche) et Heures Creuses (colonne droite) sont côte à côte
        y_tempo = tempo[0]["top"]
        xs = sorted(w["x0"] for w in options_y if w["top"] < y_tempo)
        x_split = page.width / 2
        if not xs[0] < x_split < xs[-1]:
            raise ParseError("grille EDF : colonnes Base / Heures Creuses non séparables")
        gauche = page.crop((0, 0, x_split, y_tempo)).extract_text() or ""
        droite = page.crop((x_split, 0, page.width, y_tempo)).extract_text() or ""
        bas = page.crop((0, y_tempo, page.width, page.height)).extract_text() or ""

    grilles = {
        "base": _table(gauche, "base", url, d),
        "hphc": _table(droite, "hphc", url, d),
        "tempo": _table(bas, "tempo", url, d),
    }
    _ajouter_accise(grilles, tout)
    return grilles


# particulier.edf.fr refuse les serveurs de GitHub (HTTP 403, filtrage des
# adresses de centres de données). On ne contourne pas ce filtrage : on lit
# seulement, à la demande explicite du mainteneur, la dernière capture publique
# du PDF déjà faite par la Wayback Machine (web.archive.org), sans lui demander
# de nouvelle capture. Source d'appoint : son absence n'est pas une erreur.
CDX = "https://web.archive.org/cdx/search/cdx"


DOCUMENTS = ((URL, parse_grille), (URL_EJP, parse_grille_ejp))


def derniere_capture(url: str = URL) -> str | None:
    """Horodatage (AAAAMMJJhhmmss) de la dernière capture réussie, ou None."""
    q = urlencode({"url": url, "output": "json", "fl": "timestamp", "filter": "statuscode:200", "limit": "-1"})
    lignes = json.loads(http.get(f"{CDX}?{q}"))
    return lignes[-1][0] if len(lignes) > 1 else None


def captures(url: str) -> list[str]:
    """Horodatages de toutes les captures réussies, une par contenu distinct."""
    q = urlencode({"url": url, "output": "json", "fl": "timestamp", "filter": "statuscode:200", "collapse": "digest"})
    return [l[0] for l in json.loads(http.get(f"{CDX}?{q}"))[1:]]


def url_capture(ts: str, url: str = URL) -> str:
    """Copie brute (« id_ ») : octets identiques au PDF d'EDF."""
    return f"https://web.archive.org/web/{ts}id_/{url}"


def _collecter_document(url: str, parse) -> dict[str, GrilleSource]:
    ts = derniere_capture(url)
    if ts is None:
        return {}
    copie = url_capture(ts, url)
    grilles = parse(http.get(copie), url)
    for g in grilles.values():
        g.meta["copie_archive"] = copie
    return grilles


def collecter() -> dict[str, GrilleSource]:
    """Les deux grilles ; un document illisible n'empêche pas de lire l'autre."""
    grilles: dict[str, GrilleSource] = {}
    erreurs: list[str] = []
    for url, parse in DOCUMENTS:
        try:
            grilles.update(_collecter_document(url, parse))
        except Exception as e:  # noqa: BLE001 — source d'appoint
            erreurs.append(f"{url.rsplit('/', 1)[-1]} : {e}")
    if erreurs and not grilles:
        raise http.FetchError(" ; ".join(erreurs))
    for err in erreurs:
        print(f"grille EDF (archive.org) ignorée : {err}", file=sys.stderr)
    return grilles


def collecter_captures_ejp() -> tuple[list[GrilleSource], list[str]]:
    """Amorçage de l'historique EJP : toutes les captures archivées de la grille EJP.

    Une grille par date d'effet (la capture la plus récente). Renvoie aussi les
    captures illisibles, pour information.
    """
    par_date: dict[date, GrilleSource] = {}
    illisibles: list[str] = []
    for ts in captures(URL_EJP):
        copie = url_capture(ts, URL_EJP)
        try:
            g = parse_grille_ejp(http.get(copie), URL_EJP)["ejp"]
        except Exception as e:  # noqa: BLE001
            illisibles.append(f"{copie} : {e}")
            continue
        g.meta["copie_archive"] = copie
        par_date[g.date_effet] = g  # captures dans l'ordre chronologique
    return [par_date[d] for d in sorted(par_date)], illisibles
