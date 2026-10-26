from __future__ import annotations

from typing import Mapping

from veille.messages import Message
from veille.notifiers.base import Notifier, post, truncate

PRIORITIES = {"high": 4, "default": 3, "low": 2}
TAGS = {"offer": "airplane", "offers_group": "airplane", "page_change": "loudspeaker",
        "source_down": "warning", "source_up": "white_check_mark", "init": "white_check_mark", "weekly": "bar_chart"}


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
            payload = {
                "topic": self.topic,
                "title": truncate(msg.title, 250),
                "message": truncate(msg.text, 3800),
                "priority": PRIORITIES[msg.priority],
                "tags": [TAGS.get(msg.kind, "bell")],
            }
            if msg.url:
                payload["click"] = msg.url
                payload["actions"] = [{"action": "view", "label": msg.link_label, "url": msg.url, "clear": True}]
            post(self.server, json=payload, headers=headers)
