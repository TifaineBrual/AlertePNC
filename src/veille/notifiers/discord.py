from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from veille.messages import Message, OfferAlert, facts_line, offer_facts
from veille.notifiers.base import Notifier, post, truncate

EMBEDS_PER_POST = 10
CHARS_PER_POST = 5500  # Discord refuse au-delà de 6000 caractères d'embeds par message
DESCRIPTION_MAX = 4000
COLORS = {
    "offer": 0x2ECC71, "offers_group": 0x2ECC71, "page_change": 0x3498DB, "source_down": 0xE74C3C,
    "source_up": 0x95A5A6, "init": 0x95A5A6, "weekly": 0x95A5A6,
}


def _offer_item(alert: OfferAlert) -> str:
    o = alert.offer
    tag = f" · *{alert.tag}*" if alert.tag else ""
    facts = facts_line(o)
    return f"**[{truncate(o.title, 200)}]({o.url})**{tag}\n{o.company}" + (f"  ·  {facts}" if facts else "")


def _offer_list(alerts: list[OfferAlert], budget: int) -> str:
    """Liste d'offres en markdown Discord, coupée proprement si elle dépasse `budget` caractères."""
    out: list[str] = []
    for i, alert in enumerate(alerts):
        item = _offer_item(alert)
        rest = f"\n… et {len(alerts) - i} autre(s) offre(s)"
        if sum(len(x) + 2 for x in out) + len(item) + len(rest) > budget:
            out.append(rest.strip())
            break
        out.append(item)
    return "\n\n".join(out)


def embed(msg: Message) -> dict:
    data: dict = {"color": COLORS.get(msg.kind, 0x95A5A6), "footer": {"text": "Veille PNC"},
                  "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if msg.kind == "offer":
        alert = msg.alerts[0]
        o = alert.offer
        data["author"] = {"name": f"{alert.icon} {alert.label} · {o.company}" + (f" · {alert.tag}" if alert.tag else "")}
        data["title"] = truncate(o.title, 256)
        data["url"] = o.url
        data["fields"] = [{"name": label, "value": truncate(value, 1024), "inline": True} for _, label, value in offer_facts(o)]
        data["footer"]["text"] = f"Veille PNC · {o.source_id}"
        return data

    data["title"] = truncate(f"{msg.icon} {msg.title}", 256)
    if msg.url:
        data["url"] = msg.url
    if msg.kind == "page_change":
        details = "\n".join(f"> {line}" for line in msg.lines)
    elif msg.alerts:
        details = "\n".join(f"*{line}*" for line in msg.lines)  # informations secondaires sous la liste
    else:
        details = "\n".join(msg.lines)
    offers = _offer_list(msg.alerts, DESCRIPTION_MAX - len(msg.intro) - len(details) - 10) if msg.alerts else ""
    data["description"] = truncate("\n\n".join(p for p in (msg.intro, offers, details) if p), DESCRIPTION_MAX)
    return data


def _size(e: dict) -> int:
    return (len(e.get("title", "")) + len(e.get("description", "")) + len(e.get("author", {}).get("name", ""))
            + len(e["footer"]["text"]) + sum(len(f["name"]) + len(f["value"]) for f in e.get("fields", [])))


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
