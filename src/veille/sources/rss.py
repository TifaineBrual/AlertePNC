from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlsplit

from lxml import etree

from veille.http import SourceError
from veille.models import Offer
from veille.sources.base import FetchContext, Source, register
from veille.text import html_to_text

# Paramètres d'URL qui portent l'identifiant de l'offre (Talentsoft, Taleo).
ID_PARAMS = ("offerReference", "idOffre", "job")
# Talentsoft préfixe les titres par la référence : « 2026-23622 - Pilote de ligne F/H ».
TITLE_REF = re.compile(r"^\s*\d{4}-\d+\s*-\s*")
BR = re.compile(r"<br\s*/?>", re.I)
ATOM = "{http://www.w3.org/2005/Atom}"
LABELS = {
    "contract": re.compile(r"^Type de contrat\s*:\s*(.+)$", re.M),
    "location": re.compile(r"^(?:Site|Localisation|Lieu)\s*:\s*(.+)$", re.M),
}


def _offer_id(link: str, guid: str) -> str:
    params = parse_qs(urlsplit(link).query)
    for name in ID_PARAMS:
        if params.get(name):
            return params[name][0]
    return guid


def _date(value: str) -> str:
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return value


def parse_rss(content: bytes, source: Source) -> list[Offer]:
    try:
        root = etree.fromstring(content, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise SourceError(f"flux RSS illisible ({exc.msg})") from None
    if root.tag == f"{ATOM}feed":
        return _parse_atom(root, source)
    channel = root.find("channel")
    if channel is None:
        raise SourceError("flux RSS sans <channel> : format inattendu")

    offers = []
    for item in channel.findall("item"):
        link = (item.findtext("link") or "").strip()
        title = TITLE_REF.sub("", item.findtext("title") or "")
        if not link or not title.strip():
            continue
        # Les descriptions Talentsoft sont du HTML échappé avec des libellés « Type de contrat : … ».
        text = html_to_text(BR.sub("\n", item.findtext("description") or ""), sep="")
        fields = {name: (m.group(1).strip() if (m := rx.search(text)) else "") for name, rx in LABELS.items()}
        categories = [c.text.strip() for c in item.findall("category") if c.text]
        offers.append(source.offer(
            offer_id=_offer_id(link, (item.findtext("guid") or "").strip()),
            title=title,
            url=link,
            location=fields["location"] or (categories[-1] if len(categories) >= 3 else ""),
            contract=fields["contract"],
            published_at=_date(item.findtext("pubDate") or ""),
            description=text,
            raw={"categories": categories},
        ))
    return offers


def _parse_atom(root, source: Source) -> list[Offer]:
    """Flux Atom (ex. alertes Google « distribuer à : flux RSS »)."""
    offers = []
    for entry in root.findall(f"{ATOM}entry"):
        link_el = entry.find(f"{ATOM}link")
        link = link_el.get("href", "") if link_el is not None else ""
        # Les alertes Google passent par une redirection : on garde l'URL de l'article.
        link = parse_qs(urlsplit(link).query).get("url", [link])[0]
        title = html_to_text(entry.findtext(f"{ATOM}title") or "", sep="")
        if not link or not title:
            continue
        offers.append(source.offer(
            offer_id=(entry.findtext(f"{ATOM}id") or "").strip(),
            title=title,
            url=link,
            published_at=entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated") or "",
            description=html_to_text(entry.findtext(f"{ATOM}content") or entry.findtext(f"{ATOM}summary") or "", sep=""),
        ))
    return offers


@register("rss")
class RssSource(Source):
    def fetch(self, ctx: FetchContext) -> list[Offer]:
        if not self.url:
            raise SourceError(f"URL absente : le secret {self.cfg.get('url_env', '?')} n'est pas défini")
        resp = ctx.http.get(self.url)
        return [o for o in parse_rss(resp.content, self) if self.keep(o)]
