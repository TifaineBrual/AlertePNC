from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit

import requests

from veille import USER_AGENT

log = logging.getLogger(__name__)

TIMEOUT = 20
ATTEMPTS = 2
RETRY_DELAY = 3.0
MIN_INTERVAL_PER_DOMAIN = 1.0


class SourceError(Exception):
    """Échec de lecture d'une source (réseau, format inattendu, rien de lisible…)."""


class BlockedError(SourceError):
    """Le site refuse l'accès (403/429) : on n'insiste pas."""

    def __init__(self, status: int):
        super().__init__(f"accès refusé par le site (HTTP {status})")
        self.status = status


class PoliteHttp:
    """Client HTTP poli : User-Agent explicite, timeout, 2 tentatives, une requête à la fois par domaine."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5"})
        self._last_call: dict[str, float] = {}

    def _wait_for_domain(self, url: str) -> None:
        domain = urlsplit(url).netloc
        elapsed = time.monotonic() - self._last_call.get(domain, 0.0)
        if elapsed < MIN_INTERVAL_PER_DOMAIN:
            time.sleep(MIN_INTERVAL_PER_DOMAIN - elapsed)
        self._last_call[domain] = time.monotonic()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", TIMEOUT)
        last_error = "erreur inconnue"
        for attempt in range(1, ATTEMPTS + 1):
            self._wait_for_domain(url)
            try:
                resp = self.session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}"
            else:
                if resp.status_code in (403, 429):
                    raise BlockedError(resp.status_code)
                if resp.status_code < 400:
                    if "charset" not in resp.headers.get("Content-Type", "").lower():
                        resp.encoding = resp.apparent_encoding
                    return resp
                last_error = f"HTTP {resp.status_code}"
                if resp.status_code < 500:
                    break
            if attempt < ATTEMPTS:
                log.debug("nouvelle tentative pour %s (%s)", url, last_error)
                time.sleep(RETRY_DELAY)
        raise SourceError(last_error)

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)
