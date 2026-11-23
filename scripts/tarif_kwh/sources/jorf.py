"""Source 4 : veille du Journal officiel (JORF).

Les TRVE proposés par la CRE s'appliquent sauf opposition des ministres ; un
arrêté ou une décision publiée au JORF peut les modifier, les bloquer, ou
changer une taxe (accise). On ne lit pas ces textes automatiquement : on
signale tout texte dont le titre correspond, pour vérification humaine.

Données : flux ouvert DILA (https://echanges.dila.gouv.fr/OPENDATA/JORF/),
une archive tar.gz par édition, sans authentification (Légifrance exige un
compte PISTE).
"""
from __future__ import annotations

import io
import re
import tarfile
import xml.etree.ElementTree as ET

from .. import http

SOURCE = "jorf"
INDEX = "https://echanges.dila.gouv.fr/OPENDATA/JORF/"
RE_ARCHIVE = re.compile(r'href="(JORF_(\d{8})-\d{6}\.tar\.gz)"')

MOTIFS = [
    re.compile(r"tarifs? réglementés? de vente (de l'|d'|de l’|d’)électricité", re.I),
    re.compile(r"tarifs? réglementés? .{0,60}électricité", re.I),
    # Taxes : l'accise change par loi de finances (1er février) mais aussi en
    # cours d'année (30,85 -> 30,62 €/MWh au 1er août 2026).
    re.compile(r"\baccises?\b.{0,80}\bénergies?\b|\baccises?\b.{0,80}électricité|électricité.{0,80}\baccises?\b", re.I),
    re.compile(r"\bloi\b.{0,60}\bde finances\b", re.I),  # initiale ou rectificative
]
MOTIFS_TAXES = MOTIFS[2:]


def concerne_les_taxes(titre: str) -> bool:
    return any(p.search(titre) for p in MOTIFS_TAXES)


def lister_archives(html: str) -> list[tuple[str, str]]:
    """[(nom, AAAAMMJJ)] triées."""
    return sorted(set(RE_ARCHIVE.findall(html)))


def textes_pertinents(archive: bytes) -> list[dict]:
    out = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for m in tar:
            if not (m.isfile() and m.name.endswith(".xml") and "/TEXT/" in m.name):
                continue
            f = tar.extractfile(m)
            if f is None:
                continue
            try:
                root = ET.fromstring(f.read())
            except ET.ParseError:
                continue
            titre = (root.findtext(".//TITREFULL") or "").strip()
            if titre and any(p.search(titre) for p in MOTIFS):
                cid = root.findtext(".//CID") or root.findtext(".//ID") or ""
                out.append(
                    {
                        "titre": titre,
                        "date_publication": root.findtext(".//DATE_PUBLI"),
                        "nature": root.findtext(".//NATURE"),
                        "url": f"https://www.legifrance.gouv.fr/jorf/id/{cid}",
                    }
                )
    return out


def collecter(dernier_traite: str | None, max_archives: int = 30) -> tuple[list[dict], str | None]:
    """Parcourt les archives postérieures à ``dernier_traite``.

    Renvoie (textes trouvés, nom de la dernière archive traitée).
    """
    archives = [a for a, _ in lister_archives(http.get(INDEX).decode("utf-8", "replace"))]
    if dernier_traite:
        archives = [a for a in archives if a > dernier_traite]
    archives = archives[-max_archives:]
    trouves: list[dict] = []
    for a in archives:
        trouves += textes_pertinents(http.get(INDEX + a))
    return trouves, (archives[-1] if archives else dernier_traite)
