from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from veille.http import SourceError
from veille.models import Offer, normalize_url
from veille.sources.base import FetchContext, Source, register
from veille.text import clean_lines, normalize

# Libellés réservés aux lecteurs d'écran (« Location », « Functional Area »…) : pollueraient les valeurs.
HIDDEN = ".sr-only, .visually-hidden, script, style, noscript"
OFFER_FIELDS = ("location", "contract", "published_at")


def _text(el: Tag | None) -> str:
    return " ".join(el.get_text(" ").split()) if el else ""


def extract_offers(html: str, source: Source, base_url: str) -> list[Offer]:
    """Extrait les offres d'une page liste selon les sélecteurs CSS de la config de la source.

    Clés de config : item (obligatoire), title, link, id_attr, id_regex, link_pattern, description,
    fields {location, contract, published_at, <autre>: sélecteur}, container, exclude, empty_text.
    Lève SourceError si rien n'est lisible et que la page n'affiche pas le texte « aucune offre » attendu.
    """
    cfg = source.cfg
    soup = BeautifulSoup(html, "lxml")
    for el in soup.select(HIDDEN):
        el.decompose()
    scope: Tag | None = soup.select_one(cfg["container"]) if cfg.get("container") else soup
    if scope is None:
        raise SourceError(f"zone {cfg['container']!r} introuvable : la page a peut-être changé")
    if cfg.get("exclude"):
        for el in scope.select(cfg["exclude"]):
            el.decompose()

    link_pattern = re.compile(cfg["link_pattern"]) if cfg.get("link_pattern") else None
    id_regex = re.compile(cfg["id_regex"]) if cfg.get("id_regex") else None
    offers: dict[str, Offer] = {}
    for item in scope.select(cfg["item"]):
        link_el = item if item.name == "a" else (item.select_one(cfg["link"]) if cfg.get("link") else item.select_one("a[href]"))
        href = urljoin(base_url, link_el["href"]) if link_el is not None and link_el.get("href") else ""
        if link_pattern and not link_pattern.search(href):
            continue
        title = _text(item.select_one(cfg["title"])) if cfg.get("title") else _text(link_el)
        if not title:
            continue

        if cfg.get("id_attr") and item.get(cfg["id_attr"]):
            offer_id = item[cfg["id_attr"]]
        elif id_regex and (m := id_regex.search(href)):
            offer_id = m.group(1)
        elif href:
            offer_id = normalize_url(href)
        else:
            offer_id = normalize(title)

        values = {name: _text(item.select_one(sel)) for name, sel in cfg.get("fields", {}).items()}
        desc_el = item.select_one(cfg["description"]) if cfg.get("description") else None
        offer = source.offer(
            offer_id=offer_id,
            title=title,
            url=href or base_url,
            description=clean_lines(desc_el.get_text("\n")) if desc_el else "",
            raw={k: v for k, v in values.items() if k not in OFFER_FIELDS},
            **{k: values.get(k, "") for k in OFFER_FIELDS},
        )
        offers.setdefault(offer.offer_id, offer)

    if not offers:
        empty = cfg.get("empty_text")
        if not (empty and normalize(empty) in normalize(soup.get_text(" "))):
            raise SourceError("aucune offre lisible et pas de message « aucune offre » : la page a peut-être changé")
    return [o for o in offers.values() if source.keep(o)]


@register("html_list")
class HtmlListSource(Source):
    def fetch(self, ctx: FetchContext) -> list[Offer]:
        resp = ctx.http.get(self.url)
        return extract_offers(resp.text, self, resp.url)
