"""État persistant (data/state.json), commité par le workflow.

Les dates sont stockées au jour près pour que le fichier ne change pas à chaque run :
le workflow ne commite que si quelque chose a réellement changé.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from veille.models import Offer, normalize_url

VERSION = 1
PURGE_AFTER_DAYS = 90
PAGE_TEXT_MAX = 20_000


class State:
    def __init__(self, data: dict | None = None):
        self.data = data or {}
        self.data.setdefault("version", VERSION)
        self.data.setdefault("sources", {})
        self.data.setdefault("offers", {})
        self._loaded = self.dumps()

    @classmethod
    def load(cls, path: Path) -> "State":
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return cls(json.loads(path.read_text(encoding="utf-8")))
        return cls()

    def dumps(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"

    @property
    def changed(self) -> bool:
        return self.dumps() != self._loaded

    def save(self, path: Path) -> bool:
        """Écrit le fichier si l'état a changé ; renvoie True si écrit."""
        if not self.changed:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dumps(), encoding="utf-8")
        self._loaded = self.dumps()
        return True

    # --- sources ---

    def source(self, source_id: str) -> dict:
        return self.data["sources"].setdefault(source_id, {})

    def forget_source(self, source_id: str) -> None:
        self.data["sources"].pop(source_id, None)
        prefix = f"{source_id}::"
        for key in [k for k in self.data["offers"] if k.startswith(prefix)]:
            del self.data["offers"][key]

    # --- offres ---

    @property
    def offers(self) -> dict[str, dict]:
        return self.data["offers"]

    def known_ids(self, source_id: str) -> set[str]:
        prefix = f"{source_id}::"
        return {k[len(prefix):] for k in self.offers if k.startswith(prefix)}

    def known_urls(self) -> dict[str, str]:
        """URL normalisée → clé, pour repérer une même offre publiée dans plusieurs flux."""
        return {normalize_url(rec["url"]): key for key, rec in self.offers.items() if rec.get("url")}

    def record(self, offer: Offer, today: date, **extra) -> None:
        self.offers[offer.key] = {
            "company": offer.company,
            "title": offer.title,
            "url": offer.url,
            "location": offer.location,
            "contract": offer.contract,
            "first_seen": today.isoformat(),
            "last_seen": today.isoformat(),
            **extra,
        }

    def touch(self, key: str, today: date) -> None:
        self.offers[key]["last_seen"] = today.isoformat()

    def purge(self, today: date, days: int = PURGE_AFTER_DAYS) -> int:
        limit = (today - timedelta(days=days)).isoformat()
        old = [k for k, rec in self.offers.items() if rec.get("last_seen", "") < limit]
        for key in old:
            del self.offers[key]
        return len(old)

    # --- pages surveillées ---

    def page(self, source_id: str) -> dict | None:
        return self.source(source_id).get("page")

    def set_page(self, source_id: str, text: str, text_hash: str, today: date) -> None:
        self.source(source_id)["page"] = {"hash": text_hash, "text": text[:PAGE_TEXT_MAX], "changed": today.isoformat()}
