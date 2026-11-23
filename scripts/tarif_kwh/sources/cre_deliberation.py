"""Source 1 : délibérations CRE « portant proposition des TRVE » (annexe B).

Publiées ~2 semaines avant le 1er février / 1er août. Prix HORS TAXES.
L'annexe B1 contient les barèmes Bleu résidentiel en France métropolitaine
continentale ; on lit la *version standard* (hors autoconsommation collective).

Découverte : le site CRE (Cloudflare) refuse les recherches avec paramètres,
on lit donc la première page de la liste des délibérations et la page
« Comprendre les TRVE », puis chaque page de délibération candidate pour y
trouver le PDF « annexe B ».
"""
from __future__ import annotations

import io
import re
from collections import Counter
from datetime import date
from urllib.parse import urljoin

import pdfplumber

from .. import http
from ..schema import GrilleSource, Puissance, parse_nombre_fr

SOURCE = "cre_deliberation"
BASE_URL = "https://www.cre.fr"
PAGES_LISTE = (
    "https://www.cre.fr/documents/deliberations.html",
    "https://www.cre.fr/consommateurs/comprendre-les-tarifs-reglementes-de-vente-delectricite-trve.html",
)

# Titre normalisé (sans espaces, majuscules) des sections -> option
SECTIONS = {
    "TARIFBLEU-OPTIONBASERESIDENTIEL": "base",
    "TARIFBLEU-OPTIONHEURESCREUSESRESIDENTIEL": "hphc",
    "TARIFBLEU-OPTIONTEMPORESIDENTIEL": "tempo",
    "TARIFBLEU-OPTIONEJPRESIDENTIEL": "ejp",
}
# Ordre des colonnes de prix dans l'annexe (c€/kWh) après l'abonnement
COLONNES = {
    "base": ("base",),
    "hphc": ("hp", "hc"),
    "tempo": ("bleu_hc", "bleu_hp", "blanc_hc", "blanc_hp", "rouge_hc", "rouge_hp"),
    "ejp": ("normal", "pointe"),
}

RE_LIGNE = re.compile(r"^(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s+((?:\d[\d ]*,\d+\s*)+)$")
RE_NOMBRE = re.compile(r"\d+,\d+")
RE_DATE_EFFET = re.compile(r"\b(01)/(0[1-9]|1[0-2])/(20\d\d)\b")
SLUG_TRVE = re.compile(r"/documents/deliberations/[^\"'#?]*tarifs-reglementes-de-vente-delectricite[^\"'#?]*\.html")
RE_ANNEXE_B = re.compile(r"href=\"([^\"]+annexe_?b\.pdf)\"", re.I)


class ParseError(ValueError):
    pass


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


def _expand_puissances(a: str, b: str | None) -> list[int]:
    """'24-30' dans certaines annexes = une ligne pour 24 et 30 kVA."""
    if not b:
        return [int(a)]
    return [p for p in (3, 6, 9, 12, 15, 18, 24, 30, 36) if int(a) <= p <= int(b)]


def lignes_page(page) -> list[str]:
    """Reconstruit les lignes d'une page à partir de la position des mots.

    ``extract_text`` ne respecte pas toujours l'ordre visuel des colonnes
    (ex. annexe 2025 : « 13,27 3 102,12 »). On regroupe les mots par ligne
    (milieu vertical à ±3 pt) puis on les trie de gauche à droite.
    """
    mots = sorted(page.extract_words(use_text_flow=False), key=lambda w: (w["top"], w["x0"]))
    rangs: list[list] = []
    for w in mots:
        milieu = (w["top"] + w["bottom"]) / 2
        if rangs and abs(rangs[-1][0] - milieu) <= 3:
            rangs[-1][1].append(w)
        else:
            rangs.append([milieu, [w]])
    return [" ".join(w["text"] for w in sorted(r, key=lambda w: w["x0"])) for _, r in rangs]


def parse_annexe_b(pdf_bytes: bytes, url: str = "", date_effet: date | None = None) -> dict[str, GrilleSource]:
    """Extrait les barèmes Bleu résidentiel (métropole continentale) d'une annexe B.

    Les annexes antérieures à juin 2025 n'écrivent pas la date d'effet en
    « 01/MM/AAAA » : on la fournit alors (config/sources.json). Si l'annexe
    porte une date, elle doit être celle fournie.
    """
    fournie = date_effet
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        lignes: list[str] = []
        for page in pdf.pages:
            lp = lignes_page(page)
            n = _norm(" ".join(lp))
            # On s'arrête à l'annexe B2 (non résidentiel) : la suite contient
            # d'autres barèmes (non résidentiels, zones non interconnectées).
            if lignes and ("ANNEXEB2" in n or "CONSOMMATEURSNONRESIDENTIELS" in n[:300]):
                break
            lignes.extend(lp)

    dates = Counter(
        f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        for l in lignes
        for m in RE_DATE_EFFET.finditer(l)
    )
    if dates:
        date_effet = date.fromisoformat(dates.most_common(1)[0][0])
        if fournie and date_effet != fournie:
            raise ParseError(f"date d'effet de l'annexe B {date_effet} ≠ date fournie {fournie}")
    elif fournie:
        date_effet = fournie
    else:
        raise ParseError("date d'effet introuvable dans l'annexe B")

    grilles: dict[str, GrilleSource] = {}
    option = None
    for ligne in lignes:
        n = _norm(ligne)
        if n in SECTIONS:
            option = SECTIONS[n]
            if option in grilles:  # 2e occurrence (ZNI…) : ignorée
                option = None
                continue
            grilles[option] = GrilleSource(option, date_effet, SOURCE, url)
            continue
        if option is None:
            continue
        if n.startswith("MAJORATION") or n.startswith("VERSIONSAPPLICABLES") or n.startswith("TARIFBLEU"):
            option = None  # fin de la version standard
            continue
        m = RE_LIGNE.match(ligne.strip())
        if not m:
            continue
        nombres = [parse_nombre_fr(x) for x in RE_NOMBRE.findall(m.group(3))]
        cols = COLONNES[option]
        if len(nombres) != 1 + len(cols):
            raise ParseError(
                f"{option}: {len(nombres)} valeurs au lieu de {1 + len(cols)} sur « {ligne} »"
            )
        for kva in _expand_puissances(m.group(1), m.group(2)):
            grilles[option].puissances[kva] = Puissance(
                abonnement_ht=nombres[0],
                prix_ht={c: round(v / 100, 6) for c, v in zip(cols, nombres[1:])},
            )
    manquantes = set(COLONNES) - set(grilles)
    if manquantes:
        raise ParseError(f"options absentes de l'annexe B : {sorted(manquantes)}")
    return grilles


# --- Découverte -------------------------------------------------------------

def liens_deliberations_trve(html: str) -> list[str]:
    """Pages de délibérations TRVE électricité citées dans une page de liste."""
    vus: list[str] = []
    for m in SLUG_TRVE.finditer(html):
        u = urljoin(BASE_URL, m.group(0))
        if "gaz" in u:
            continue
        if u not in vus:
            vus.append(u)
    return vus


def liens_annexe_b(html: str, page_url: str) -> list[str]:
    return list(dict.fromkeys(urljoin(page_url, m.group(1)) for m in RE_ANNEXE_B.finditer(html)))


def decouvrir(deja_vues: set[str]) -> list[str]:
    """Renvoie les URL d'annexes B non encore traitées."""
    pages: list[str] = []
    for liste in PAGES_LISTE:
        pages += liens_deliberations_trve(http.get(liste).decode("utf-8", "replace"))
    annexes: list[str] = []
    for page in dict.fromkeys(pages):
        html = http.get(page).decode("utf-8", "replace")
        for a in liens_annexe_b(html, page):
            if a not in deja_vues and a not in annexes:
                annexes.append(a)
    return annexes


def collecter(url_annexe: str) -> dict[str, GrilleSource]:
    return parse_annexe_b(http.get(url_annexe), url_annexe)
