#!/usr/bin/env python3
"""Relais de la grille Tarif Bleu EDF vers le dépôt GitHub.

particulier.edf.fr refuse les serveurs de GitHub (HTTP 403) mais pas une
connexion domestique. Ce script, lancé UNE fois par jour depuis chez le
mainteneur (serveur Home Assistant, PC, NAS…), télécharge le PDF et le dépose
dans ``data/edf/`` du dépôt s'il a changé. Le collecteur GitHub le lit ensuite,
le contrôle et le recoupe : tout le monde consulte GitHub, EDF n'est sollicité
qu'une fois par jour.

Python 3 seul (bibliothèque standard), pour tourner aussi dans Home Assistant.

Jeton : GitHub fine-grained, limité à ce dépôt, permissions
« Contents: read and write » et « Variables: read and write ».

    TARIF_KWH_TOKEN=github_pat_… python3 relais_edf.py
    python3 relais_edf.py --jeton-fichier /config/.tarif_kwh_token
    python3 relais_edf.py --essai      # télécharge et vérifie, n'envoie rien
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

URL_EDF = "https://particulier.edf.fr/content/dam/2-Actifs/Documents/Offres/Grille_prix_Tarif_Bleu.pdf"
DEPOT = os.environ.get("TARIF_KWH_DEPOT", "raphaelh/tarif-kwh")
CHEMIN = "data/edf/Grille_prix_Tarif_Bleu.pdf"
VARIABLE = "EDF_RELAIS_VU_LE"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
API = "https://api.github.com"


def telecharger() -> bytes:
    req = urllib.request.Request(URL_EDF, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
    with urllib.request.urlopen(req, timeout=60) as r:
        pdf = r.read()
    if not pdf.startswith(b"%PDF") or not 20_000 < len(pdf) < 5_000_000:
        raise RuntimeError(f"réponse EDF inattendue ({len(pdf)} octets)")
    return pdf


def github(methode: str, chemin: str, jeton: str, corps: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        API + chemin,
        method=methode,
        data=json.dumps(corps).encode() if corps is not None else None,
        headers={
            "Authorization": f"Bearer {jeton}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "tarif-kwh-relais",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read()
            return r.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        txt = e.read()
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, {"message": txt.decode(errors="replace")}


def blob_sha(contenu: bytes) -> str:
    """SHA « git blob », celui que renvoie l'API GitHub pour un fichier."""
    return hashlib.sha1(b"blob %d\0" % len(contenu) + contenu).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jeton-fichier", help="fichier contenant le jeton GitHub")
    ap.add_argument("--essai", action="store_true", help="ne rien envoyer à GitHub")
    args = ap.parse_args()

    pdf = telecharger()
    print(f"EDF : {len(pdf)} octets, sha256 {hashlib.sha256(pdf).hexdigest()[:16]}")
    if args.essai:
        return 0

    jeton = os.environ.get("TARIF_KWH_TOKEN", "")
    if args.jeton_fichier:
        with open(args.jeton_fichier, encoding="utf-8") as f:
            jeton = f.read().strip()
    if not jeton:
        print("jeton GitHub manquant (TARIF_KWH_TOKEN ou --jeton-fichier)", file=sys.stderr)
        return 2

    code, actuel = github("GET", f"/repos/{DEPOT}/contents/{CHEMIN}", jeton)
    if code not in (200, 404):
        print(f"GitHub HTTP {code} : {actuel.get('message')}", file=sys.stderr)
        return 1
    if code == 200 and actuel.get("sha") == blob_sha(pdf):
        print("Grille inchangée.")
    else:
        corps = {
            "message": f"Relais grille Tarif Bleu EDF ({datetime.now(timezone.utc):%Y-%m-%d})",
            "content": base64.b64encode(pdf).decode(),
            **({"sha": actuel["sha"]} if code == 200 else {}),
        }
        code, rep = github("PUT", f"/repos/{DEPOT}/contents/{CHEMIN}", jeton, corps)
        if code not in (200, 201):
            print(f"Envoi refusé, HTTP {code} : {rep.get('message')}", file=sys.stderr)
            return 1
        print("Nouvelle grille envoyée :", rep["commit"]["html_url"])

    # Signe de vie sans commit : une variable du dépôt horodatée.
    maintenant = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    code, _ = github("PATCH", f"/repos/{DEPOT}/actions/variables/{VARIABLE}", jeton, {"name": VARIABLE, "value": maintenant})
    if code == 404:
        code, _ = github("POST", f"/repos/{DEPOT}/actions/variables", jeton, {"name": VARIABLE, "value": maintenant})
    if code not in (201, 204):
        print(f"Variable {VARIABLE} non mise à jour (HTTP {code})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
