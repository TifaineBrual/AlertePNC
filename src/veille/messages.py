"""Messages à notifier, indépendants du canal (chaque notifier les met en forme)."""
from __future__ import annotations

from dataclasses import dataclass, field

from veille.matching import Detection, Score
from veille.models import Offer
from veille.text import excerpt

GROUP_THRESHOLD = 5
PAGE_EXCERPT_LINES = 15


@dataclass
class OfferAlert:
    offer: Offer
    detection: Detection
    score: Score

    def short_line(self) -> str:
        where = f" ({self.offer.location})" if self.offer.location else ""
        return f"{self.score.label} {self.score.value}/100 — {self.offer.company} : {self.offer.title}{where}"


@dataclass
class Message:
    kind: str  # offer, offers_group, page_change, source_down, source_up, init, weekly
    title: str
    text: str
    url: str = ""
    priority: str = "default"  # high, default, low
    alerts: list[OfferAlert] = field(default_factory=list)
    link_label: str = "Ouvrir l'offre"


def offer_messages(alerts: list[OfferAlert]) -> list[Message]:
    """Un message par offre ; au-delà de 5 offres dans le même run, un seul message groupé."""
    if len(alerts) > GROUP_THRESHOLD:
        alerts = sorted(alerts, key=lambda a: -a.score.value)
        return [Message(
            kind="offers_group",
            title=f"✈️ {len(alerts)} nouvelles offres PNC",
            text="\n".join(f"• {a.short_line()}\n  {a.offer.url}" for a in alerts),
            priority="high" if any(a.score.value >= 70 for a in alerts) else "default",
            alerts=alerts,
        )]
    return [offer_message(a) for a in alerts]


def offer_message(alert: OfferAlert) -> Message:
    o, s = alert.offer, alert.score
    lines = [
        f"🏢 {o.company}",
        f"📍 {o.location or 'lieu non précisé'}",
        f"📄 {o.contract or 'contrat non précisé'}",
        f"⭐ {s.value}/100 — {s.label}" + (" (à vérifier)" if s.to_check else ""),
        *[f"  • {r}" for r in s.reasons],
    ]
    return Message(
        kind="offer",
        title=f"{s.label.split()[0]} {o.company} — {o.title}",
        text="\n".join(lines),
        url=o.url,
        priority="high" if s.value >= 70 else "default",
        alerts=[alert],
    )


def page_change_message(company: str, url: str, added: list[str], removed: list[str]) -> Message:
    if added:
        shown = added[:PAGE_EXCERPT_LINES]
        body = "Nouveau texte sur la page :\n" + "\n".join(f"+ {excerpt(line, 200)}" for line in shown)
        if len(added) > len(shown):
            body += f"\n… et {len(added) - len(shown)} autre(s) ligne(s)"
    else:
        body = "Du texte a été retiré de la page (campagne terminée ?) :\n" + "\n".join(
            f"− {excerpt(line, 200)}" for line in removed[:PAGE_EXCERPT_LINES])
    return Message(
        kind="page_change",
        title=f"📣 {company} : la page recrutement PNC a changé",
        text=body,
        url=url,
        priority="high" if added else "default",
        link_label="Ouvrir la page",
    )


def source_down_message(source_id: str, company: str, url: str, error: str, failures: int) -> Message:
    return Message(
        kind="source_down",
        title=f"⚠️ Source en panne : {company} ({source_id})",
        text=(f"{failures} échecs consécutifs. Dernière erreur : {error}\n"
              "Le site a peut-être été refait : il faut sans doute adapter config/sources.yaml. "
              "Vous serez prévenu(e) quand la source fonctionnera de nouveau."),
        url=url,
        link_label="Ouvrir la page",
    )


def source_up_message(source_id: str, company: str, url: str) -> Message:
    return Message(
        kind="source_up",
        title=f"✅ Source rétablie : {company} ({source_id})",
        text="La source répond de nouveau normalement.",
        url=url,
        priority="low",
        link_label="Ouvrir la page",
    )


def init_message(total: int, pnc: list[OfferAlert], sources: list[str], pages: list[str]) -> Message:
    lines = [f"Sources initialisées : {', '.join(dict.fromkeys(sources))}."]
    if pages:
        lines.append(f"Pages surveillées : {', '.join(dict.fromkeys(pages))}.")
    if pnc:
        lines.append("Offres PNC déjà en ligne :")
        lines += [f"• {a.short_line()}\n  {a.offer.url}" for a in sorted(pnc, key=lambda a: -a.score.value)]
    else:
        lines.append("Aucune offre PNC en ligne pour l'instant. Vous serez prévenu(e) dès qu'une offre paraît.")
    return Message(
        kind="init",
        title=f"✅ Veille PNC active – {total} offres indexées, dont {len(pnc)} PNC",
        text="\n".join(lines),
        priority="default",
        alerts=pnc,
    )


def weekly_message(rows: list[tuple[str, str, int, int]]) -> Message:
    """rows : (source, statut, offres en ligne, nouvelles cette semaine)."""
    lines = [f"{'✅' if status == 'ok' else '⚠️'} {source} : {online} offre(s) en ligne, {new} nouvelle(s) cette semaine"
             + ("" if status == "ok" else f" — {status}") for source, status, online, new in rows]
    return Message(
        kind="weekly",
        title="📊 Veille PNC – résumé de la semaine",
        text="\n".join(lines) + "\n\nLa veille tourne normalement (preuve de vie hebdomadaire).",
        priority="low",
    )
