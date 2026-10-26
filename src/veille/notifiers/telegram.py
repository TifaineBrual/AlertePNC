from __future__ import annotations

import html
from typing import Mapping

from veille.messages import Message
from veille.notifiers.base import Notifier, post, truncate

MAX_CHARS = 4000


def render(msg: Message) -> str:
    parts = [f"<b>{html.escape(msg.title, quote=False)}</b>", html.escape(truncate(msg.text, MAX_CHARS - 400), quote=False)]
    if msg.url:
        parts.append(f'<a href="{html.escape(msg.url, quote=True)}">{html.escape(msg.link_label, quote=False)}</a>')
    return "\n\n".join(parts)


class TelegramNotifier(Notifier):
    name = "Telegram"

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TelegramNotifier | None":
        token, chat_id = env.get("TELEGRAM_BOT_TOKEN", "").strip(), env.get("TELEGRAM_CHAT_ID", "").strip()
        return cls(token, chat_id) if token and chat_id else None

    def send(self, messages: list[Message]) -> None:
        for msg in messages:
            post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": render(msg),
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                    "disable_notification": msg.priority == "low",
                },
            )
