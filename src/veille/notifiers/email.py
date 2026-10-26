from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage
from typing import Mapping

from veille.messages import Message
from veille.notifiers.base import Notifier, NotifyError

TIMEOUT = 30


def subject(messages: list[Message]) -> str:
    if len(messages) == 1:
        return messages[0].title
    offers = sum(len(m.alerts) for m in messages if m.kind in ("offer", "offers_group"))
    if offers:
        return f"✈️ Veille PNC : {offers} nouvelle(s) offre(s) PNC"
    return f"Veille PNC : {len(messages)} notifications"


def render_text(messages: list[Message]) -> str:
    blocks = []
    for m in messages:
        block = f"{m.title}\n{'-' * min(len(m.title), 60)}\n{m.text}"
        if m.url:
            block += f"\n{m.link_label} : {m.url}"
        blocks.append(block)
    return "\n\n\n".join(blocks) + "\n"


def render_html(messages: list[Message]) -> str:
    blocks = []
    for m in messages:
        link = f'<p><a href="{html.escape(m.url, quote=True)}">{html.escape(m.link_label)}</a></p>' if m.url else ""
        text = html.escape(m.text).replace("\n", "<br>")
        blocks.append(f"<h3>{html.escape(m.title)}</h3><p>{text}</p>{link}")
    return f'<html><body style="font-family:sans-serif">{"<hr>".join(blocks)}</body></html>'


class EmailNotifier(Notifier):
    """Un seul e-mail récapitulatif par run, quel que soit le nombre de messages."""

    name = "E-mail"

    def __init__(self, host: str, port: int, user: str, password: str, to: str):
        self.host, self.port, self.user, self.password, self.to = host, port, user, password, to

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "EmailNotifier | None":
        keys = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO")
        values = {k: env.get(k, "").strip() for k in keys}
        if not all(values.values()):
            return None
        port = int(env.get("SMTP_PORT", "").strip() or 465)
        return cls(values["SMTP_HOST"], port, values["SMTP_USER"], values["SMTP_PASSWORD"], values["EMAIL_TO"])

    def send(self, messages: list[Message]) -> None:
        mail = EmailMessage()
        mail["Subject"] = subject(messages)
        mail["From"] = f"Veille PNC <{self.user}>"
        mail["To"] = self.to
        mail.set_content(render_text(messages))
        mail.add_alternative(render_html(messages), subtype="html")
        context = ssl.create_default_context()
        try:
            if self.port == 465:
                with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=TIMEOUT) as smtp:
                    smtp.login(self.user, self.password)
                    smtp.send_message(mail)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=TIMEOUT) as smtp:
                    smtp.starttls(context=context)
                    smtp.login(self.user, self.password)
                    smtp.send_message(mail)
        except smtplib.SMTPAuthenticationError:
            raise NotifyError("authentification SMTP refusée (vérifiez le mot de passe d'application)") from None
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifyError(f"erreur SMTP ({type(exc).__name__})") from None
