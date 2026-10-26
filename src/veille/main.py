"""Orchestration : relève → diff → filtre → score → notifie → sauvegarde."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import yaml

from veille.http import BlockedError, PoliteHttp, SourceError
from veille.matching import Profile, detect, load_profile, score_offer
from veille.messages import (Message, OfferAlert, init_message, offer_messages, page_change_message,
                             source_down_message, source_up_message, weekly_message)
from veille.models import Offer, PageSnapshot, normalize_url
from veille.notifiers import Notifier, NotifyError, enabled_notifiers
from veille.sources.base import FetchContext, Source, build_source
from veille.sources.browser import BrowserPool
from veille.sources.page_watch import added_lines, removed_lines
from veille.state import State

log = logging.getLogger("veille")

PARIS = ZoneInfo("Europe/Paris")
ROOT = Path(__file__).resolve().parents[2]
FAILURES_BEFORE_ALERT = 3
BLOCKED_PAUSE = timedelta(hours=6)
HEARTBEAT_EVERY = timedelta(days=7)


@dataclass
class SourceRow:
    """Ligne du résumé du run pour une source."""
    id: str
    company: str
    type: str
    status: str = "ok"
    count: int | str = "—"
    new: int = 0


@dataclass
class Run:
    state: State
    profile: Profile
    now: datetime
    messages: list[Message] = field(default_factory=list)
    alerts: list[OfferAlert] = field(default_factory=list)
    rows: list[SourceRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Initialisation silencieuse (premier run ou nouvelle source)
    init_sources: list[str] = field(default_factory=list)
    init_pages: list[str] = field(default_factory=list)
    init_total: int = 0
    init_pnc: list[OfferAlert] = field(default_factory=list)

    @property
    def today(self) -> date:
        return self.now.date()

    # --- offres ---

    def handle_offers(self, source: Source, offers: list[Offer], row: SourceRow) -> None:
        sstate = self.state.source(source.id)
        initialized = bool(sstate.get("initialized"))
        known_urls = self.state.known_urls()
        row.count = len(offers)
        for offer in offers:
            if offer.key in self.state.offers:
                self.state.touch(offer.key, self.today)
                continue
            if not offer.title:
                continue
            detection = detect(offer.title, offer.description)
            score = score_offer(offer, detection, self.profile) if detection.is_pnc else None
            duplicate_of = known_urls.get(normalize_url(offer.url))
            extra = {"category": detection.category} if detection.category else {}
            if score:
                extra["score"] = score.value
            self.state.record(offer, self.today, **extra)
            known_urls[normalize_url(offer.url)] = offer.key
            row.new += 1
            alert = OfferAlert(offer, detection, score) if score else None
            log.info("  + %s%s", offer.title, f"  [PNC {score.value}/100]" if score else "")

            if not initialized:
                if alert and not duplicate_of:
                    self.init_pnc.append(alert)
                continue
            if duplicate_of:
                log.info("    (déjà vue via %s)", duplicate_of)
                continue
            if detection.category == "instructeur_pnc":
                self.notes.append(f"Poste d'instructeur PNC (non notifié) : {source.company} — {offer.title} {offer.url}")
            elif alert and score.value >= self.profile.min_score_to_notify:
                self.alerts.append(alert)
            elif alert:
                self.notes.append(f"Offre PNC sous le seuil ({score.value} < {self.profile.min_score_to_notify}) : "
                                  f"{source.company} — {offer.title} {offer.url}")

        if not initialized:
            sstate["initialized"] = True
            self.init_sources.append(source.company)
            self.init_total += len(offers)
        elif row.new:
            sstate["new_week"] = sstate.get("new_week", 0) + row.new
        sstate["count"] = len(offers)

    # --- pages surveillées ---

    def handle_page(self, source: Source, snap: PageSnapshot, row: SourceRow) -> None:
        previous = self.state.page(source.id)
        row.count = "page"
        if previous is None:
            self.state.set_page(source.id, snap.text, snap.hash, self.today)
            self.init_pages.append(source.company)
            return
        if previous["hash"] == snap.hash:
            return
        added, removed = added_lines(previous["text"], snap.text), removed_lines(previous["text"], snap.text)
        self.state.set_page(source.id, snap.text, snap.hash, self.today)
        if added or removed:
            row.new = 1
            row.status = "ok (changement)"
            self.messages.append(page_change_message(source.company, snap.url, added, removed))

    # --- santé des sources ---

    def source_ok(self, source: Source) -> None:
        sstate = self.state.source(source.id)
        if sstate.get("down_alerted"):
            self.messages.append(source_up_message(source.id, source.company, source.url))
        for key in ("failures", "down_alerted", "last_error", "paused_until"):
            sstate.pop(key, None)
        sstate["last_ok"] = self.today.isoformat()

    def source_failed(self, source: Source, error: str, blocked: bool, row: SourceRow) -> None:
        sstate = self.state.source(source.id)
        row.status = f"❌ {error}"
        log.warning("  ✗ %s", error)
        if sstate.get("down_alerted"):
            # Déjà signalée : on ne touche plus à l'état (pas de commit à chaque run pendant la panne).
            if blocked:
                sstate["paused_until"] = (self.now + BLOCKED_PAUSE).isoformat(timespec="minutes")
            return
        sstate["failures"] = sstate.get("failures", 0) + 1
        sstate["last_error"] = error
        if sstate["failures"] >= FAILURES_BEFORE_ALERT:
            sstate["down_alerted"] = True
            self.messages.append(source_down_message(source.id, source.company, source.url, error, sstate["failures"]))
            if blocked:
                sstate["paused_until"] = (self.now + BLOCKED_PAUSE).isoformat(timespec="minutes")

    def paused(self, source: Source) -> bool:
        until = self.state.source(source.id).get("paused_until")
        return bool(until) and datetime.fromisoformat(until) > self.now

    # --- fin de run ---

    def final_messages(self, configs: list[dict], weekly_enabled: bool, force_weekly: bool) -> list[Message]:
        messages = []
        if self.init_sources or self.init_pages:
            messages.append(init_message(self.init_total, self.init_pnc, self.init_sources, self.init_pages))
        messages += offer_messages(self.alerts) + self.messages
        if force_weekly or (weekly_enabled and self.weekly_due()):
            messages.append(self.weekly(configs))
        return messages

    def weekly_due(self) -> bool:
        # Lundi matin, heure de Paris, une seule fois.
        return self.now.weekday() == 0 and 7 <= self.now.hour < 12 and self.state.data.get("weekly_sent") != self.today.isoformat()

    def weekly(self, configs: list[dict]) -> Message:
        rows = []
        for cfg in configs:
            sstate = self.state.source(cfg["id"])
            status = "ok" if not sstate.get("failures") else f"en échec ({sstate.get('last_error', '?')})"
            if not cfg.get("enabled", True):
                status = "désactivée"
            rows.append((f"{cfg['company']} ({cfg['id']})", status, sstate.get("count", 0), sstate.get("new_week", 0)))
            sstate["new_week"] = 0
        self.state.data["weekly_sent"] = self.today.isoformat()
        return weekly_message(rows)

    def housekeeping(self) -> None:
        purged = self.state.purge(self.today)
        if purged:
            self.notes.append(f"{purged} offre(s) non revue(s) depuis 90 jours retirée(s) de l'état.")
        last = self.state.data.get("heartbeat", "")
        if not last or date.fromisoformat(last) <= self.today - HEARTBEAT_EVERY:
            self.state.data["heartbeat"] = self.today.isoformat()


def send_all(notifiers: list[Notifier], messages: list[Message]) -> dict[str, str]:
    """Envoie sur chaque canal ; un canal en échec n'empêche pas les autres. Renvoie {canal: résultat}."""
    results = {}
    for notifier in notifiers:
        try:
            notifier.send(messages)
            results[notifier.name] = "ok"
        except NotifyError as exc:
            results[notifier.name] = f"échec : {exc}"
        except Exception as exc:  # ne jamais interrompre le run à cause d'un canal
            results[notifier.name] = f"échec : erreur interne {type(exc).__name__}"
        log.info("Notification %s : %s", notifier.name, results[notifier.name])
    return results


def print_messages(messages: list[Message]) -> None:
    for m in messages:
        print(f"\n━━ [{m.kind} · {m.priority}] {m.title}\n{m.text}" + (f"\n→ {m.url}" if m.url else ""))


def summary_markdown(run: Run, channels: dict[str, str], configured: list[str], dry_run: bool) -> str:
    lines = [f"## Veille PNC – {run.now:%d/%m/%Y %H:%M} (heure de Paris){' — DRY RUN' if dry_run else ''}", "",
             "| Source | Compagnie | Type | Statut | Offres | Nouvelles |", "|---|---|---|---|---|---|"]
    lines += [f"| `{r.id}` | {r.company} | {r.type} | {r.status} | {r.count} | {r.new} |" for r in run.rows]
    lines += ["", f"**Offres PNC notifiées :** {len(run.alerts)}"]
    lines += [f"- {a.short_line()} — [lien]({a.offer.url})" for a in run.alerts]
    if run.init_sources or run.init_pages:
        lines += ["", f"**Initialisation silencieuse :** {', '.join(run.init_sources + run.init_pages)}"]
    if channels:
        lines += ["", "**Canaux :** " + ", ".join(f"{name} {'✅' if res == 'ok' else '❌ ' + res}" for name, res in channels.items())]
    elif configured:
        lines += ["", f"**Canaux configurés :** {', '.join(configured)} (rien à envoyer)"]
    elif not dry_run:
        lines += ["", "**Canaux :** aucun canal configuré (ajoutez les secrets, voir README)."]
    if run.notes:
        lines += ["", "**Notes :**"] + [f"- {n}" for n in run.notes]
    return "\n".join(lines) + "\n"


def load_config(path: Path) -> tuple[dict, list[dict]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources") or []
    ids = [s["id"] for s in sources]
    if len(ids) != len(set(ids)):
        raise SystemExit("config : identifiants de sources en double")
    return data.get("settings") or {}, sources


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="veille", description="Veille automatique des offres PNC")
    p.add_argument("--dry-run", action="store_true", help="aucune notification, aucune écriture d'état, affichage console")
    p.add_argument("--source", action="append", default=[], metavar="ID", help="ne traiter que cette source (répétable)")
    p.add_argument("--config", type=Path, default=ROOT / "config" / "sources.yaml")
    p.add_argument("--state", type=Path, default=ROOT / "data" / "state.json")
    p.add_argument("--profile", type=Path, help="fichier profil YAML (sinon variable d'environnement PROFILE_YAML)")
    p.add_argument("--weekly", action="store_true", help="envoyer le résumé hebdomadaire maintenant")
    p.add_argument("--needs-browser", action="store_true", help="affiche true/false : une source active a-t-elle besoin de Playwright ?")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def select_sources(configs: list[dict], wanted: list[str]) -> list[dict]:
    if not wanted:
        return [c for c in configs if c.get("enabled", True)]
    unknown = set(wanted) - {c["id"] for c in configs}
    if unknown:
        raise SystemExit(f"source(s) inconnue(s) : {', '.join(sorted(unknown))}")
    return [c for c in configs if c["id"] in wanted]  # --source permet aussi de tester une source désactivée


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None, now: datetime | None = None) -> int:
    args = parse_args(argv)
    env = os.environ if env is None else env
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    for noisy in ("urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings, all_configs = load_config(args.config)
    configs = select_sources(all_configs, args.source)
    sources = [build_source(c) for c in configs]
    if args.needs_browser:
        print("true" if any(s.needs_browser for s in sources) else "false")
        return 0

    profile_text = args.profile.read_text(encoding="utf-8") if args.profile else env.get("PROFILE_YAML")
    run = Run(State.load(args.state), load_profile(profile_text), (now or datetime.now(PARIS)).astimezone(PARIS))
    if not run.profile.provided:
        run.notes.append("Aucun profil fourni (secret PROFILE_YAML) : score neutre pour toutes les offres PNC.")

    http, browser = PoliteHttp(), BrowserPool()
    try:
        for source in sources:
            row = SourceRow(source.id, source.company, source.type)
            run.rows.append(row)
            log.info("%s (%s)", source.id, source.type)
            if run.paused(source) and not args.source:
                row.status = "⏸ en pause (accès refusé par le site)"
                continue
            ctx = FetchContext(http, browser, run.state.known_ids(source.id))
            try:
                if source.kind == "page":
                    run.handle_page(source, source.snapshot(ctx), row)
                else:
                    run.handle_offers(source, source.fetch(ctx), row)
                run.source_ok(source)
            except SourceError as exc:
                run.source_failed(source, str(exc), isinstance(exc, BlockedError), row)
            except Exception as exc:  # une source ne doit jamais interrompre le run
                log.exception("erreur inattendue sur %s", source.id)
                run.source_failed(source, f"erreur interne {type(exc).__name__}: {exc}", False, row)
    finally:
        browser.close()

    messages = run.final_messages(all_configs, bool(settings.get("weekly_summary", True)) and not args.source, args.weekly)
    channels: dict[str, str] = {}
    notifiers = [] if args.dry_run else enabled_notifiers(env)
    if args.dry_run:
        print_messages(messages)
    else:
        if messages and notifiers:
            channels = send_all(notifiers, messages)
            if all(res != "ok" for res in channels.values()):
                # Aucun canal n'a fonctionné : on « oublie » ces offres pour les renvoyer au prochain run.
                for alert in run.alerts:
                    run.state.offers.pop(alert.offer.key, None)
                run.notes.append("Tous les canaux ont échoué : les nouvelles offres seront renvoyées au prochain run.")
        elif messages:
            print_messages(messages)
        run.housekeeping()
        if run.state.save(args.state):
            log.info("État enregistré (%s)", args.state)

    summary = summary_markdown(run, channels, [n.name for n in notifiers], args.dry_run)
    print("\n" + summary)
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
