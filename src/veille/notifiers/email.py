from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage
from typing import Mapping

from veille.messages import Message, OfferAlert, facts_line, offer_facts, offer_heading
from veille.notifiers.base import Notifier, NotifyError

TIMEOUT = 30
ACCENT = "#0b5cad"
MUTED = "#6b7280"


def subject(messages: list[Message]) -> str:
    offers = [a for m in messages if m.kind in ("offer", "offers_group") for a in m.alerts]
    if len(offers) == 1:
        return f"{offers[0].icon} {offers[0].label} – {offer_heading(offers[0])}"
    if offers:
        return f"✈️ {len(offers)} nouvelles offres PNC"
    if len(messages) == 1:
        return f"{messages[0].icon} {messages[0].title}"
    return f"Veille PNC – {len(messages)} notifications"


# --- texte brut ---

def _text_offer(alert: OfferAlert) -> str:
    lines = [offer_heading(alert)]
    lines += [f"   {label} : {value}" for _, label, value in offer_facts(alert.offer)]
    lines.append(f"   {alert.offer.url}")
    return "\n".join(lines)


def render_text(messages: list[Message]) -> str:
    blocks = []
    for m in messages:
        heading = f"{m.icon} {_heading(m)}"
        parts = [f"{heading}\n{'=' * len(heading)}"]
        if m.intro and m.kind != "offer":
            parts.append(m.intro)
        if m.alerts:
            parts.append("\n\n".join(_text_offer(a) for a in m.alerts))
        if m.lines:
            parts.append("\n".join(f"  {line}" for line in m.lines))
        if m.url and m.kind != "offer":
            parts.append(f"{m.link_label} : {m.url}")
        blocks.append("\n\n".join(parts))
    return "\n\n\n".join(blocks) + "\n\n--\nVeille PNC (message automatique)\n"


# --- HTML (styles en ligne : seuls styles fiables dans les clients mail) ---

def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _button(url: str, label: str) -> str:
    return (f'<a href="{_e(url)}" style="display:inline-block;background:{ACCENT};color:#ffffff;text-decoration:none;'
            f'padding:9px 16px;border-radius:6px;font-weight:600;font-size:14px">{_e(label)}</a>')


def _html_offer(alert: OfferAlert) -> str:
    o = alert.offer
    tag = (f' <span style="background:#fef3c7;color:#92400e;border-radius:4px;padding:1px 6px;font-size:12px">'
           f'{_e(alert.tag)}</span>') if alert.tag else ""
    facts = facts_line(o)
    return (
        '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin:12px 0">'
        f'<div style="color:{MUTED};font-size:12px;text-transform:uppercase;letter-spacing:.04em">{_e(o.company)}</div>'
        f'<div style="font-size:17px;font-weight:600;margin:4px 0 6px"><a href="{_e(o.url)}" '
        f'style="color:#111827;text-decoration:none">{_e(o.title)}</a>{tag}</div>'
        + (f'<div style="color:#374151;font-size:14px;margin-bottom:12px">{_e(facts)}</div>' if facts else "")
        + f'{_button(o.url, "Lire l’article" if alert.is_web_alert else "Voir l’offre")}</div>'
    )


def _heading(m: Message) -> str:
    # Pour une offre seule, la compagnie figure déjà dans la carte : titre court.
    return m.alerts[0].label if m.kind == "offer" else m.title


def _html_message(m: Message) -> str:
    parts = [f'<h2 style="font-size:18px;margin:24px 0 8px">{_e(m.icon)} {_e(_heading(m))}</h2>']
    if m.intro and m.kind != "offer":
        parts.append(f'<p style="margin:0 0 8px">{_e(m.intro)}</p>')
    parts += [_html_offer(a) for a in m.alerts]
    if m.lines:
        if m.kind == "page_change":
            quoted = "<br>".join(_e(line) for line in m.lines)
            parts.append(f'<blockquote style="border-left:3px solid {ACCENT};margin:8px 0;padding:4px 12px;'
                         f'color:#374151">{quoted}</blockquote>')
        else:
            color = MUTED if m.alerts else "#374151"
            parts.append(f'<p style="color:{color};font-size:14px;margin:8px 0">'
                         + "<br>".join(_e(line) for line in m.lines) + "</p>")
    if m.url and m.kind != "offer":
        parts.append(f'<p style="margin:12px 0">{_button(m.url, m.link_label)}</p>')
    return "".join(parts)


def render_html(messages: list[Message]) -> str:
    body = "".join(_html_message(m) for m in messages)
    return (
        '<!doctype html><html><body style="margin:0;background:#f3f4f6">'
        '<div style="max-width:600px;margin:0 auto;padding:16px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
        'color:#111827;line-height:1.45">'
        f'<div style="background:#ffffff;border-radius:10px;padding:8px 20px 20px">{body}</div>'
        f'<p style="color:{MUTED};font-size:12px;text-align:center;margin:12px 0">Veille PNC · message automatique</p>'
        '</div></body></html>'
    )


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
