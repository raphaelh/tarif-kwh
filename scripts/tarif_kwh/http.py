"""Téléchargements HTTP avec reprises. Les sites publics (CRE derrière
Cloudflare, EDF) refusent parfois les clients sans User-Agent de navigateur."""
from __future__ import annotations

import time

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


class FetchError(RuntimeError):
    pass


def get(url: str, *, timeout: int = 60, tries: int = 3) -> bytes:
    last: Exception | None = None
    for i in range(tries):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"},
                timeout=timeout,
            )
            if r.status_code == 200:
                return r.content
            last = FetchError(f"HTTP {r.status_code} pour {url}")
            if r.status_code in (403, 404):
                break  # inutile d'insister
        except requests.RequestException as e:  # réseau
            last = e
        time.sleep(2 * (i + 1))
    raise FetchError(str(last))
