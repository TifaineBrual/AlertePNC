from __future__ import annotations

import logging
import os
import re

from veille import USER_AGENT
from veille.http import BlockedError, SourceError
from veille.models import Offer
from veille.sources.base import FetchContext, Source, register
from veille.sources.html_list import extract_offers
from veille.text import normalize

log = logging.getLogger(__name__)

RENDER_TIMEOUT_MS = 30_000
SKIPPED_RESOURCES = {"image", "media", "font"}


class BrowserPool:
    """Chromium headless (Playwright), démarré seulement si une source en a besoin pendant le run."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None

    def _ensure(self):
        if self._browser is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                raise SourceError("Playwright n'est pas installé (pip install -r requirements-browser.txt)") from None
            self._playwright = sync_playwright().start()
            # VEILLE_BROWSER_CHANNEL=chrome permet d'utiliser un Chrome déjà installé.
            channel = os.environ.get("VEILLE_BROWSER_CHANNEL") or None
            self._browser = self._playwright.chromium.launch(channel=channel)
        return self._browser

    def render(self, url: str, wait_for: str | None = None, settle_ms: int = 1000) -> str:
        """HTML de la page après exécution du JavaScript."""
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        context = self._ensure().new_context(user_agent=USER_AGENT, locale="fr-FR")
        page = context.new_page()
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in SKIPPED_RESOURCES else route.continue_())
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS)
            if resp is not None and resp.status in (403, 429):
                raise BlockedError(resp.status)
            if resp is not None and resp.status >= 400:
                raise SourceError(f"HTTP {resp.status}")
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, state="attached", timeout=RENDER_TIMEOUT_MS)
                except PlaywrightTimeout:
                    log.debug("sélecteur %r non trouvé sur %s", wait_for, url)
            else:
                page.wait_for_load_state("networkidle", timeout=RENDER_TIMEOUT_MS)
            page.wait_for_timeout(settle_ms)
            return page.content()
        except PlaywrightTimeout:
            raise SourceError("délai dépassé pendant le rendu de la page") from None
        except PlaywrightError as exc:
            raise SourceError(f"erreur navigateur : {exc.message.splitlines()[0]}") from None
        finally:
            context.close()

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._playwright.stop()
            self._browser = self._playwright = None


@register("browser")
class BrowserSource(Source):
    """Liste d'offres rendue en JavaScript : rendu Playwright puis mêmes sélecteurs que html_list."""

    @property
    def needs_browser(self) -> bool:
        return True

    def fetch(self, ctx: FetchContext) -> list[Offer]:
        html = ctx.browser.render(self.url, wait_for=self.cfg.get("wait_for"), settle_ms=self.cfg.get("settle_ms", 1000))
        offers = extract_offers(html, self, self.url)
        # La liste est paginée côté navigateur : on signale si le total affiché dépasse ce qu'on a lu.
        if self.cfg.get("count_regex") and (m := re.search(self.cfg["count_regex"], normalize(html))):
            total = int(m.group(1))
            if total > len(offers):
                log.warning("%s : %d offres annoncées, %d lues (pagination non suivie)", self.id, total, len(offers))
        return offers
