from __future__ import annotations

from typing import Mapping

from veille.notifiers.base import Notifier, NotifyError
from veille.notifiers.discord import DiscordNotifier
from veille.notifiers.email import EmailNotifier
from veille.notifiers.ntfy import NtfyNotifier
from veille.notifiers.telegram import TelegramNotifier

ALL = (DiscordNotifier, NtfyNotifier, TelegramNotifier, EmailNotifier)


def enabled_notifiers(env: Mapping[str, str]) -> list[Notifier]:
    """Les canaux dont les secrets sont présents."""
    return [n for cls in ALL if (n := cls.from_env(env)) is not None]


__all__ = ["Notifier", "NotifyError", "enabled_notifiers"]
