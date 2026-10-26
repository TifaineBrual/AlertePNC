from __future__ import annotations

from typing import Mapping

from veille.messages import Message, facts_line, offer_heading
from veille.notifiers.base import Notifier, post, truncate

PRIORITIES = {"high": 4, "default": 3, "low": 2}
# ntfy affiche ces tags sous forme d'emoji devant le titre.
TAGS = {"offer": "airplane", "offers_group": "airplane", "page_change": "loudspeaker",
        "source_down": "warning", "source_up": "white_check_mark", "init": "white_check_mark", "weekly": "bar_chart"}
MESSAGE_MAX = 3800


def render(msg: Message) -> dict:
    """Titre et texte brut (l'application mobile n'interprète pas le markdown)."""
    if msg.kind == "offer":
        alert = msg.alerts[0]
        title = offer_heading(alert)
        body = facts_line(alert.offer, sep="\n") or ("Alerte Google" if alert.is_web_alert else "Détails sur l'offre.")
    else:
        title = msg.title
        parts = [msg.intro] if msg.intro else []
        if msg.alerts:
            parts.append("\n".join(f"• {offer_heading(a)}" + (f"\n   {facts_line(a.offer)}" if facts_line(a.offer) else "")
                                   for a in msg.alerts))
        if msg.lines:
            prefix = "« " if msg.kind == "page_change" else ""
            suffix = " »" if msg.kind == "page_change" else ""
            parts.append("\n".join(f"{prefix}{line}{suffix}" for line in msg.lines))
        body = "\n\n".join(parts)
    payload = {
        "title": truncate(title, 250),
        "message": truncate(body, MESSAGE_MAX),
        "priority": PRIORITIES[msg.priority],
        "tags": ["mag" if msg.kind == "offer" and msg.alerts[0].is_web_alert else TAGS.get(msg.kind, "bell")],
    }
    if msg.url:
        payload["click"] = msg.url
        payload["actions"] = [{"action": "view", "label": msg.link_label, "url": msg.url, "clear": True}]
    return payload


class NtfyNotifier(Notifier):
    name = "ntfy"

    def __init__(self, topic: str, server: str = "https://ntfy.sh", token: str = ""):
        self.topic = topic
        self.server = server.rstrip("/")
        self.token = token

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "NtfyNotifier | None":
        topic = env.get("NTFY_TOPIC", "").strip()
        if not topic:
            return None
        return cls(topic, env.get("NTFY_SERVER", "").strip() or "https://ntfy.sh", env.get("NTFY_TOKEN", "").strip())

    def send(self, messages: list[Message]) -> None:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        for msg in messages:
            # Publication JSON : évite les soucis d'encodage des accents/emojis dans les en-têtes HTTP.
            post(self.server, json={"topic": self.topic, **render(msg)}, headers=headers)
