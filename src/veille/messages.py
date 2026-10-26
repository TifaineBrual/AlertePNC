"""Messages à notifier, sous forme de données structurées : chaque canal les met en forme à sa façon."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from veille.matching import Detection
from veille.models import Offer
from veille.text import excerpt

GROUP_THRESHOLD = 5
PAGE_EXCERPT_LINES = 15

ICONS = {
    "offer": "✈️", "offers_group": "✈️", "page_change": "📣", "source_down": "⚠️",
    "source_up": "✅", "init": "✅", "weekly": "📊", "test": "🔔",
}


@dataclass
class OfferAlert:
    offer: Offer
    detection: Detection

    @property
    def tag(self) -> str:
        return "Instructeur PNC" if self.detection.category == "instructeur_pnc" else ""

    @property
    def is_web_alert(self) -> bool:
        return self.detection.category == "alerte"

    @property
    def label(self) -> str:
        """« Nouvelle offre PNC » ou « Alerte Google » (article ou page web, pas forcément une offre)."""
        return "Alerte Google" if self.is_web_alert else "Nouvelle offre PNC"

    @property
    def icon(self) -> str:
        return "🔎" if self.is_web_alert else "✈️"


@dataclass
class Message:
    kind: str  # offer, offers_group, page_change, source_down, source_up, init, weekly
    title: str  # sans emoji : chaque canal ajoute l'icône à sa façon
    intro: str = ""
    lines: list[str] = field(default_factory=list)
    alerts: list[OfferAlert] = field(default_factory=list)
    url: str = ""
    link_label: str = "Voir l'offre"
    priority: str = "default"  # high, default, low

    @property
    def icon(self) -> str:
        if self.kind == "offer" and self.alerts:
            return self.alerts[0].icon
        return ICONS.get(self.kind, "🔔")


# --- présentation commune d'une offre ---

def format_date(value: str) -> str:
    """« 2026-10-26T15:03:14+00:00 » → « 26/10/2026 » ; une date déjà lisible est gardée telle quelle."""
    try:
        return datetime.fromisoformat(value.strip()).strftime("%d/%m/%Y")
    except ValueError:
        return value.strip()


SMALL_WORDS = {"de", "du", "des", "la", "le", "les", "en", "sur", "et", "aux", "au"}
POSTCODE_CITY = re.compile(r"\b\d{5}\s+(.+)$")
CEDEX = re.compile(r"\s+cedex(\s+\d+)?\s*$", re.I)


def display_location(location: str) -> str:
    """« 45 rue de Paris 95747 ROISSY CHARLES DE GAULLE CEDEX » → « Roissy Charles de Gaulle »."""
    text = location.strip()
    if m := POSTCODE_CITY.search(text):
        text = m.group(1)
    text = CEDEX.sub("", text)

    def fix(word: str) -> str:
        if not word.isupper() or len(word) <= 3 and word.lower() not in SMALL_WORDS:
            return word  # casse d'origine, sigles courts (CDG, ORY) conservés
        return word.lower() if word.lower() in SMALL_WORDS else word.capitalize()

    words = [fix(w) for w in text.split()]
    if words:
        words[0] = words[0][:1].upper() + words[0][1:]
    return " ".join(words)


def offer_facts(offer: Offer) -> list[tuple[str, str, str]]:
    """(icône, libellé, valeur) des informations disponibles, dans un ordre fixe."""
    facts = [("📍", "Lieu", display_location(offer.location)), ("📄", "Contrat", offer.contract),
             ("🗓️", "Publiée le", format_date(offer.published_at) if offer.published_at else "")]
    return [f for f in facts if f[2]]


def facts_line(offer: Offer, sep: str = "  ·  ") -> str:
    return sep.join(f"{icon} {value}" for icon, _, value in offer_facts(offer))


def offer_heading(alert: OfferAlert) -> str:
    """« Air France — Hôtesse de l'air / Steward (Instructeur PNC) »."""
    tag = f" ({alert.tag})" if alert.tag else ""
    return f"{alert.offer.company} — {alert.offer.title}{tag}"


# --- construction des messages ---

def offer_messages(alerts: list[OfferAlert]) -> list[Message]:
    """Un message par offre ; au-delà de 5 offres dans le même run, un seul message groupé."""
    if len(alerts) > GROUP_THRESHOLD:
        return [Message(kind="offers_group", title=f"{len(alerts)} nouvelles offres PNC",
                        intro="Plusieurs offres PNC viennent d'être publiées :", alerts=alerts, priority="high")]
    return [Message(kind="offer", title=f"{a.label} – {a.offer.company}", alerts=[a],
                    url=a.offer.url, link_label="Lire l'article" if a.is_web_alert else "Voir l'offre",
                    priority="high") for a in alerts]


def page_change_message(company: str, url: str, added: list[str], removed: list[str]) -> Message:
    if added:
        intro, shown = "Nouveau texte sur la page :", added
    else:
        intro, shown = "Du texte a été retiré de la page (fin de campagne ?) :", removed
    lines = [excerpt(line, 200) for line in shown[:PAGE_EXCERPT_LINES]]
    if len(shown) > PAGE_EXCERPT_LINES:
        lines.append(f"… et {len(shown) - PAGE_EXCERPT_LINES} autre(s) ligne(s)")
    return Message(kind="page_change", title=f"{company} : la page recrutement PNC a changé", intro=intro,
                   lines=lines, url=url, link_label="Ouvrir la page", priority="high" if added else "default")


def source_down_message(source_id: str, company: str, url: str, error: str, failures: int) -> Message:
    return Message(
        kind="source_down",
        title=f"Source en panne : {company}",
        intro=f"La source « {source_id} » a échoué {failures} fois de suite.",
        lines=[f"Dernière erreur : {error}",
               "Le site a peut-être été refait : config/sources.yaml est sans doute à adapter.",
               "Vous serez prévenu(e) quand la source fonctionnera de nouveau."],
        url=url,
        link_label="Ouvrir la page",
    )


def source_up_message(source_id: str, company: str, url: str) -> Message:
    return Message(kind="source_up", title=f"Source rétablie : {company}",
                   intro=f"La source « {source_id} » répond de nouveau normalement.",
                   url=url, link_label="Ouvrir la page", priority="low")


def init_message(total: int, alerts: list[OfferAlert], sources: list[str], pages: list[str]) -> Message:
    lines = [f"Sources : {', '.join(dict.fromkeys(sources))}."] if sources else []
    if pages:
        lines.append(f"Pages surveillées : {', '.join(dict.fromkeys(pages))}.")
    if alerts:
        intro = f"{len(alerts)} offre(s) PNC déjà en ligne :"
    else:
        intro = "Aucune offre PNC en ligne pour l'instant : vous serez prévenu(e) dès qu'une offre paraît."
    return Message(kind="init", title=f"Veille PNC active – {total} offres indexées, dont {len(alerts)} PNC",
                   intro=intro, lines=lines, alerts=alerts)


def weekly_message(rows: list[tuple[str, str, int, int]]) -> Message:
    """rows : (source, statut, offres en ligne, nouvelles cette semaine)."""
    lines = [f"{'✅' if status == 'ok' else '⚠️'} {source} : {online} en ligne, {new} nouvelle(s)"
             + ("" if status == "ok" else f" — {status}") for source, status, online, new in rows]
    return Message(kind="weekly", title="Veille PNC – résumé de la semaine",
                   intro="La veille tourne normalement. Offres par source :", lines=lines, priority="low")


# --- version texte (aperçu console en --dry-run) ---

def _text_offer(alert: OfferAlert) -> str:
    lines = [offer_heading(alert)]
    lines += [f"   {label} : {value}" for _, label, value in offer_facts(alert.offer)]
    lines.append(f"   {alert.offer.url}")
    return "\n".join(lines)


def render_text(messages: list[Message]) -> str:
    blocks = []
    for m in messages:
        # Pour une offre seule, la compagnie figure déjà sous le titre : titre court.
        heading = f"{m.icon} {m.alerts[0].label if m.kind == 'offer' else m.title}"
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
    return "\n\n\n".join(blocks) + "\n"
