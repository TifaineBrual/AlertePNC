from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup
from lxml import etree

from veille.http import BlockedError, SourceError
from veille.models import Offer
from veille.sources.base import FetchContext, Source, register
from veille.text import html_to_text

log = logging.getLogger(__name__)

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
DEFAULT_MAX_RENDERS = 25


def parse_sitemap(content: bytes, url_pattern: str, prefer: str = "") -> dict[str, str]:
    """{offer_id: url} pour les URLs du sitemap qui correspondent à `url_pattern` (groupe 1 = id)."""
    try:
        root = etree.fromstring(content, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise SourceError(f"sitemap illisible ({exc.msg})") from None
    if root.tag != f"{SITEMAP_NS}urlset":
        raise SourceError("sitemap au format inattendu (pas de <urlset>)")
    rx = re.compile(url_pattern)
    urls: dict[str, str] = {}
    for loc in root.iter(f"{SITEMAP_NS}loc"):
        url = (loc.text or "").strip()
        if not (m := rx.search(url)):
            continue
        # Une même offre peut exister en plusieurs langues : on garde la version préférée (ex. « /fr/ »).
        if m.group(1) not in urls or (prefer and prefer in url):
            urls[m.group(1)] = url
    return urls


def _find_job_posting(data):
    if isinstance(data, list):
        return next((jp for d in data if (jp := _find_job_posting(d))), None)
    if isinstance(data, dict):
        if data.get("@type") == "JobPosting":
            return data
        return _find_job_posting(data.get("@graph", []))
    return None


def parse_offer_page(html: str) -> dict:
    """Titre, lieu, contrat, date, description d'une page offre rendue (JSON-LD JobPosting + <title>)."""
    soup = BeautifulSoup(html, "lxml")
    info = {"title": "", "location": "", "contract": "", "published_at": "", "description": ""}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            posting = _find_job_posting(json.loads(script.string or ""))
        except json.JSONDecodeError:
            continue
        if posting:
            place = posting.get("jobLocation") or {}
            place = place[0] if isinstance(place, list) and place else place
            info.update(
                title=posting.get("title", ""),
                location=(place.get("address") or {}).get("addressLocality", "") if isinstance(place, dict) else "",
                published_at=posting.get("datePosted", ""),
                description=html_to_text(posting.get("description", "")),
            )
            break
    # Hellowork : <title>Compagnie - Intitulé - Contrat - Lieu</title>
    parts = [p.strip() for p in (soup.title.string if soup.title and soup.title.string else "").split(" - ")]
    if len(parts) >= 4:
        info["contract"] = parts[-2]
        info["location"] = info["location"] or parts[-1]
        info["title"] = info["title"] or " - ".join(parts[1:-2])
    if not info["title"] and (h1 := soup.select_one("h1")):
        info["title"] = h1.get_text(" ", strip=True)
    return info


@register("sitemap")
class SitemapSource(Source):
    """Diff des URLs d'un sitemap ; seules les nouvelles URLs sont rendues pour lire l'intitulé."""

    @property
    def needs_browser(self) -> bool:
        return bool(self.cfg.get("render", True))

    def fetch(self, ctx: FetchContext) -> list[Offer]:
        resp = ctx.http.get(self.url)
        urls = parse_sitemap(resp.content, self.cfg["url_pattern"], self.cfg.get("prefer", ""))
        offers, rendered, failures = [], 0, 0
        for offer_id, url in urls.items():
            if offer_id in ctx.known_ids:
                # Déjà connue : l'état conserve titre et détails, on signale juste qu'elle est toujours en ligne.
                offers.append(self.offer(offer_id=offer_id, title="", url=url))
                continue
            if rendered >= self.cfg.get("max_renders", DEFAULT_MAX_RENDERS):
                continue  # reportée au run suivant pour garder des exécutions courtes
            rendered += 1
            try:
                html = ctx.browser.render(url, wait_for='script[type="application/ld+json"], h1') if self.needs_browser else ctx.http.get(url).text
                info = parse_offer_page(html)
            except BlockedError:
                raise
            except SourceError as exc:
                failures += 1
                log.warning("%s : rendu impossible pour %s (%s)", self.id, url, exc)
                continue  # pas marquée comme vue : nouvel essai au prochain run
            if not info["title"]:
                failures += 1
                continue
            offers.append(self.offer(offer_id=offer_id, url=url, **info))
        if failures and failures == rendered:
            raise SourceError(f"aucune page offre lisible ({failures} échec(s) de rendu)")
        return [o for o in offers if not o.title or self.keep(o)]
