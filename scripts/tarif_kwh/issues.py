"""Alertes : ouverture d'issues GitHub (dédoublonnées par titre).

Utilise GITHUB_TOKEN et GITHUB_REPOSITORY (fournis par GitHub Actions). Sans
eux (exécution locale), les alertes sont seulement affichées.
"""
from __future__ import annotations

import os
import sys

import requests

LABEL = "alerte-tarif"
API = "https://api.github.com"


def _session() -> tuple[requests.Session, str] | None:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    s = requests.Session()
    s.headers.update(
        {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    )
    return s, repo


def alerter(titre: str, corps: str) -> None:
    print(f"::warning title=tarif-kwh::{titre}", file=sys.stderr)
    print(corps, file=sys.stderr)
    sr = _session()
    if sr is None:
        return
    s, repo = sr
    r = s.get(f"{API}/repos/{repo}/issues", params={"state": "open", "labels": LABEL, "per_page": 100})
    r.raise_for_status()
    for issue in r.json():
        if issue["title"] == titre:
            return  # déjà ouverte
    s.post(
        f"{API}/repos/{repo}/issues",
        json={"title": titre, "body": corps, "labels": [LABEL]},
    ).raise_for_status()
