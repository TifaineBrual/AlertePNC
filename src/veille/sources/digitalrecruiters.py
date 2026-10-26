from __future__ import annotations

import logging

from veille.http import BlockedError, SourceError
from veille.models import Offer
from veille.sources.base import FetchContext, Source, register
from veille.text import html_to_text

log = logging.getLogger(__name__)

API = "https://api.digitalrecruiters.com/public/v1/careers-site/job-ads"
PAGE_SIZE = 50
MAX_PAGES = 5
MAX_DETAILS = 10


@register("digitalrecruiters")
class DigitalRecruitersSource(Source):
    """Sites carrières DigitalRecruiters (Cegid) : la page liste est rendue en JS mais lit une API JSON publique."""

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.domain: str = cfg["domain"]
        self.locale: str = cfg.get("locale", "fr_FR")
        self.url = self.url or f"https://{self.domain}/fr/annonces"

    def _list(self, ctx: FetchContext) -> list[dict]:
        items: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            resp = ctx.http.post(
                API,
                params={"domainName": self.domain, "limit": PAGE_SIZE, "page": page, "locale": self.locale},
                json={"filters": {}},
            )
            try:
                data = resp.json()
                batch, count = data["items"], int(data["count"])
            except (ValueError, KeyError, TypeError):
                raise SourceError("réponse de l'API DigitalRecruiters au format inattendu") from None
            items.extend(batch)
            if not batch or len(items) >= count:
                return items
        return items

    def _details(self, ctx: FetchContext, item: dict) -> dict:
        resp = ctx.http.get(
            f"{API}/{item['job_ad_id']}",
            params={"domainName": self.domain, "locale": self.locale, "addressId": item["id"].split("-")[-1]},
        )
        return resp.json()

    def fetch(self, ctx: FetchContext) -> list[Offer]:
        offers, details_fetched = [], 0
        for item in self._list(ctx):
            offer_id = str(item["id"])
            description = ""
            # Description lue seulement pour les nouvelles offres (et en nombre limité) : utile au scoring.
            if offer_id not in ctx.known_ids and details_fetched < MAX_DETAILS:
                details_fetched += 1
                try:
                    detail = self._details(ctx, item)
                    description = html_to_text(f"{detail.get('description', '')}\n{detail.get('profile', '')}")
                except BlockedError:
                    raise
                except (SourceError, ValueError) as exc:
                    log.warning("%s : détail indisponible pour %s (%s)", self.id, offer_id, exc)
            offers.append(self.offer(
                offer_id=offer_id,
                title=item.get("title", ""),
                url=f"https://{self.domain}/fr/annonce/{item['url']}",
                location=item.get("location") or "",
                contract=item.get("contract") or "",
                description=description,
                raw={"job": item.get("job", "")},
            ))
        return [o for o in offers if self.keep(o)]
