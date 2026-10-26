from __future__ import annotations

import time
from typing import Mapping

import requests

from veille import USER_AGENT
from veille.messages import Message

TIMEOUT = 20


class NotifyError(Exception):
    """Échec d'envoi. Le message ne contient jamais l'URL (elle peut contenir un jeton secret)."""


class Notifier:
    name = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Notifier | None":
        raise NotImplementedError

    def send(self, messages: list[Message]) -> None:
        raise NotImplementedError


def post(url: str, *, retry_on_429: bool = True, **kwargs) -> requests.Response:
    """POST qui ne laisse jamais fuiter l'URL dans les erreurs ; respecte un éventuel « retry after »."""
    kwargs.setdefault("timeout", TIMEOUT)
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    try:
        resp = requests.post(url, headers=headers, **kwargs)
    except requests.RequestException as exc:
        raise NotifyError(f"erreur réseau ({type(exc).__name__})") from None
    if resp.status_code == 429 and retry_on_429:
        time.sleep(min(_retry_after(resp), 30))
        return post(url, retry_on_429=False, headers=headers, **kwargs)
    if resp.status_code >= 400:
        raise NotifyError(f"HTTP {resp.status_code}")
    return resp


def _retry_after(resp: requests.Response) -> float:
    try:
        data = resp.json()
        value = data.get("retry_after") or data.get("parameters", {}).get("retry_after")
    except ValueError:
        value = None
    try:
        return float(value or resp.headers.get("Retry-After", 2))
    except ValueError:
        return 2.0


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
