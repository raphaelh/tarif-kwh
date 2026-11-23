"""Source 2 : grille de prix « Tarif Bleu » publiée par EDF (PDF, TTC).

Publiée à l'entrée en vigueur. Prix TTC : abonnement mensuel (€/mois) et kWh
(c€/kWh). Pas d'option EJP. La page 2 indique le montant de l'accise appliqué,
ce qui permet de recalculer le TTC à partir des prix HT de la CRE.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pdfplumber

from .. import http
from ..schema import GrilleSource, Puissance, parse_nombre_fr

SOURCE = "edf_grille"
URL = "https://particulier.edf.fr/content/dam/2-Actifs/Documents/Offres/Grille_prix_Tarif_Bleu.pdf"

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


def parse_grille(pdf_bytes: bytes, url: str = URL) -> dict[str, GrilleSource]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        texte = page.extract_text() or ""
        tout = "\n".join((p.extract_text() or "") for p in pdf.pages)
        m = RE_APPLICABLE.search(texte)
        if not m or m.group(2).lower() not in MOIS:
            raise ParseError("grille EDF : date « Applicable au … » introuvable")
        d = date(int(m.group(3)), MOIS[m.group(2).lower()], int(m.group(1)))

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
    ma = RE_ACCISE.search(tout.replace("\n", " "))
    if ma:
        accise = round(parse_nombre_fr(ma.group(1)) / 100, 6)  # €/kWh
        for g in grilles.values():
            g.meta["accise_eur_kwh"] = accise
    return grilles


RELAIS_MAX_JOURS = 3


class RelaisInactif(RuntimeError):
    """La copie relayée est utilisée mais le relais ne donne plus signe de vie."""


def collecter(copie_relais: Path | None = None, relais_vu_le: str | None = None,
              maintenant: datetime | None = None) -> tuple[dict[str, GrilleSource], str | None]:
    """Grille EDF : accès direct, sinon copie déposée par scripts/relais_edf.py.

    Renvoie (grilles, avertissement éventuel sur le relais).
    """
    try:
        return parse_grille(http.get(URL, tries=1), URL), None
    except http.FetchError as direct:
        if copie_relais is None or not copie_relais.exists():
            raise http.FetchError(f"{direct} ; aucune copie relayée dans data/edf/") from direct
    grilles = parse_grille(copie_relais.read_bytes(), URL)
    for g in grilles.values():
        g.meta["via"] = "relais"
    maintenant = maintenant or datetime.now(timezone.utc)
    avertissement = None
    if not relais_vu_le:
        avertissement = "le relais EDF n'a jamais signalé de passage (variable EDF_RELAIS_VU_LE absente)"
    else:
        age = maintenant - datetime.fromisoformat(relais_vu_le)
        if age > timedelta(days=RELAIS_MAX_JOURS):
            avertissement = f"le relais EDF ne s'est pas manifesté depuis {age.days} jours ({relais_vu_le})"
    return grilles, avertissement
