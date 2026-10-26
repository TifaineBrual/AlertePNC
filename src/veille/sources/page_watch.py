from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup

from veille.http import SourceError
from veille.models import PageSnapshot
from veille.sources.base import FetchContext, Source, register
from veille.text import clean_lines, normalize

DEFAULT_MIN_CHARS = 200


def extract_zone(html: str, zone: str, exclude: str = "", ignore_lines: list[str] | None = None) -> str:
    """Texte normalisé (une ligne par bloc) de la zone surveillée, sans les éléments exclus."""
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one(zone)
    if el is None:
        raise SourceError(f"zone {zone!r} introuvable : la page a peut-être changé")
    for bad in el.select("script, style, noscript, form" + (f", {exclude}" if exclude else "")):
        bad.decompose()
    ignored = [re.compile(p, re.I) for p in ignore_lines or []]
    lines = [line for line in clean_lines(el.get_text("\n")).splitlines() if not any(rx.search(line) for rx in ignored)]
    return "\n".join(lines)


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


def added_lines(old: str, new: str) -> list[str]:
    old_set = {normalize(line) for line in old.splitlines()}
    return [line for line in new.splitlines() if normalize(line) not in old_set]


def removed_lines(old: str, new: str) -> list[str]:
    return added_lines(new, old)


@register("page_watch")
class PageWatchSource(Source):
    """Surveille une zone de page : tout changement du texte normalisé = « campagne possible »."""

    kind = "page"

    @property
    def needs_browser(self) -> bool:
        return bool(self.cfg.get("render", False))

    def snapshot(self, ctx: FetchContext) -> PageSnapshot:
        if self.needs_browser:
            html = ctx.browser.render(self.url, wait_for=self.cfg["zone"])
        else:
            html = ctx.http.get(self.url).text
        text = extract_zone(html, self.cfg["zone"], self.cfg.get("exclude", ""), self.cfg.get("ignore_lines"))
        if len(text) < self.cfg.get("min_chars", DEFAULT_MIN_CHARS):
            raise SourceError(f"zone surveillée presque vide ({len(text)} caractères) : la page a peut-être changé")
        return PageSnapshot(self.id, self.company, self.url, text, text_hash(text))
