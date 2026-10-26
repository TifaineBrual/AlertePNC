from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, ClassVar

from veille.http import PoliteHttp, SourceError
from veille.models import Offer, PageSnapshot
from veille.text import has_term, normalize

if TYPE_CHECKING:
    from veille.sources.browser import BrowserPool

SOURCE_TYPES: dict[str, type["Source"]] = {}


def register(type_name: str) -> Callable[[type["Source"]], type["Source"]]:
    def deco(cls: type["Source"]) -> type["Source"]:
        cls.type = type_name
        SOURCE_TYPES[type_name] = cls
        return cls
    return deco


@dataclass
class FetchContext:
    http: PoliteHttp
    browser: "BrowserPool"
    known_ids: set[str] = field(default_factory=set)


class Source:
    """Une source = un type (rss, html_list…) + sa config dans config/sources.yaml."""

    type: ClassVar[str] = ""
    kind: ClassVar[str] = "offers"  # "offers" ou "page" (page_watch)

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.id: str = cfg["id"]
        self.company: str = cfg["company"]
        self.url: str = cfg.get("url", "")
        # Filtre optionnel : ne garder que les offres dont le titre ou le lieu contient un de ces mots.
        self.keep_if_any = [normalize(t) for t in cfg.get("keep_if_any", [])]

    @property
    def needs_browser(self) -> bool:
        return False

    def fetch(self, ctx: FetchContext) -> list[Offer]:
        raise NotImplementedError

    def snapshot(self, ctx: FetchContext) -> PageSnapshot:
        raise NotImplementedError

    def keep(self, offer: Offer) -> bool:
        if not self.keep_if_any:
            return True
        haystack = normalize(f"{offer.title} {offer.location}")
        return any(has_term(haystack, term) for term in self.keep_if_any)

    def offer(self, **kwargs) -> Offer:
        return Offer(source_id=self.id, company=kwargs.pop("company", self.company), **kwargs)


def build_source(cfg: dict) -> Source:
    # Import des modules pour remplir le registre.
    from veille.sources import browser, digitalrecruiters, html_list, page_watch, rss, sitemap  # noqa: F401

    try:
        cls = SOURCE_TYPES[cfg["type"]]
    except KeyError:
        raise SourceError(f"type de source inconnu : {cfg.get('type')!r}") from None
    return cls(cfg)
