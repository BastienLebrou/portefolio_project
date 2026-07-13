"""Couche réseau : session HTTP robuste (retry + backoff) et helper JSON.

Centralise timeouts, retries et messages d'erreur clairs pour tous les appels
(WFS IGN, API recherche-entreprises, API découpage administratif).
"""
from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SourceError(RuntimeError):
    """Erreur "métier" sur une source de données (réponse vide, indisponible…)."""


def make_session(user_agent: str, retries: int) -> requests.Session:
    """Session avec retry automatique sur 429/5xx et backoff exponentiel."""
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=0.8,  # 0.8, 1.6, 3.2, ... secondes
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    timeout: float,
) -> Any:
    """GET -> JSON, avec messages d'erreur explicites."""
    try:
        resp = session.get(url, params=params, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise SourceError(f"Timeout ({timeout}s) sur {url}") from exc
    except requests.exceptions.RequestException as exc:
        raise SourceError(f"Erreur réseau sur {url} : {exc}") from exc

    if resp.status_code != 200:
        snippet = resp.text[:200].replace("\n", " ")
        raise SourceError(
            f"HTTP {resp.status_code} sur {url}\n  params={params}\n  corps: {snippet}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError(
            f"Réponse non-JSON depuis {url} : {resp.text[:200]!r}"
        ) from exc
