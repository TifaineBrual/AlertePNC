from __future__ import annotations

from typing import Mapping

from veille.messages import Message
from veille.notifiers.base import Notifier, post, truncate

EMBEDS_PER_POST = 10
CHARS_PER_POST = 5500  # Discord refuse au-delà de 6000 caractères d'embeds par message
COLORS = {"high": 0x2ECC71, "default": 0xF1C40F, "low": 0x95A5A6}
KIND_COLORS = {"source_down": 0xE74C3C, "page_change": 0x3498DB}


def embed(msg: Message) -> dict:
    data = {
        "title": truncate(msg.title, 256),
        "color": KIND_COLORS.get(msg.kind, COLORS[msg.priority]),
    }
    if msg.url:
        data["url"] = msg.url
    if msg.kind == "offer":
        alert = msg.alerts[0]
        o, s = alert.offer, alert.score
        data["fields"] = [
            {"name": "Compagnie", "value": o.company, "inline": True},
            {"name": "Lieu", "value": truncate(o.location or "non précisé", 1024), "inline": True},
            {"name": "Contrat", "value": truncate(o.contract or "non précisé", 1024), "inline": True},
            {"name": f"Score {s.value}/100 — {s.label}" + (" (à vérifier)" if s.to_check else ""),
             "value": truncate("\n".join(f"• {r}" for r in s.reasons), 1024)},
        ]
    else:
        data["description"] = truncate(msg.text, 4000)
    return data


def _size(e: dict) -> int:
    return len(e["title"]) + len(e.get("description", "")) + sum(len(f["name"]) + len(f["value"]) for f in e.get("fields", []))


class DiscordNotifier(Notifier):
    name = "Discord"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "DiscordNotifier | None":
        url = env.get("DISCORD_WEBHOOK_URL", "").strip()
        return cls(url) if url else None

    def send(self, messages: list[Message]) -> None:
        batch: list[dict] = []
        for e in map(embed, messages):
            if batch and (len(batch) >= EMBEDS_PER_POST or sum(map(_size, batch)) + _size(e) > CHARS_PER_POST):
                self._post(batch)
                batch = []
            batch.append(e)
        if batch:
            self._post(batch)

    def _post(self, embeds: list[dict]) -> None:
        post(self.webhook_url, json={"username": "Veille PNC", "embeds": embeds})
