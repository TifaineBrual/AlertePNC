from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DESCRIPTION_MAX = 4000


def normalize_url(url: str) -> str:
    """URL comparable : schéma/hôte en minuscules, paramètres triés, sans fragment ni utm_*."""
    parts = urlsplit(url.strip())
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    )
    scheme = parts.scheme.lower()
    if scheme == "http":
        scheme = "https"
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, parts.netloc.lower(), path, urlencode(query), ""))


@dataclass
class Offer:
    source_id: str
    company: str
    offer_id: str
    title: str
    url: str
    location: str = ""
    contract: str = ""
    published_at: str = ""
    description: str = ""
    raw: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = " ".join(self.title.split())
        self.location = " ".join(self.location.split())
        self.contract = " ".join(self.contract.split())
        if len(self.description) > DESCRIPTION_MAX:
            self.description = self.description[:DESCRIPTION_MAX].rstrip() + "…"
        if not self.offer_id:
            self.offer_id = normalize_url(self.url)

    @property
    def key(self) -> str:
        return f"{self.source_id}::{self.offer_id}"


@dataclass
class PageSnapshot:
    """Contenu normalisé d'une zone de page surveillée (sources page_watch)."""
    source_id: str
    company: str
    url: str
    text: str
    hash: str
