import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import yaml

import veille.main as main_mod
from veille.http import BlockedError, SourceError
from veille.notifiers import NotifyError
from veille.sources.base import Source, register

PARIS = ZoneInfo("Europe/Paris")
TUESDAY = datetime(2026, 10, 27, 10, 7, tzinfo=PARIS)

OFFERS = [
    {"offer_id": "1", "title": "Hôtesse de l'air / Steward H/F", "location": "Orly", "contract": "CDD"},
    {"offer_id": "2", "title": "Comptable fournisseurs H/F", "location": "Roissy", "contract": "CDI"},
]


@register("fake")
class FakeSource(Source):
    """Lit ses offres (ou l'erreur à lever) dans un fichier JSON modifiable entre deux runs."""

    def fetch(self, ctx):
        data = json.loads(open(self.cfg["file"], encoding="utf-8").read())
        if data.get("error") == "blocked":
            raise BlockedError(403)
        if data.get("error"):
            raise SourceError(data["error"])
        return [self.offer(url=f"https://example.com/offre/{o['offer_id']}", **o) for o in data["offers"]]


class FakeNotifier:
    def __init__(self, name="Fake", fail=False):
        self.name, self.fail, self.sent = name, fail, []

    def send(self, messages):
        if self.fail:
            raise NotifyError("HTTP 500")
        self.sent.append(messages)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "fake.json"
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"settings": {"weekly_summary": True},
                                      "sources": [{"id": "fake", "company": "Fake Air", "type": "fake", "file": str(data)}]}),
                      encoding="utf-8")
    notifier = FakeNotifier()
    monkeypatch.setattr(main_mod, "enabled_notifiers", lambda env: [notifier])

    class Env:
        state = tmp_path / "state.json"

        def set(self, **payload):
            data.write_text(json.dumps(payload), encoding="utf-8")

        def run(self, *extra, now=TUESDAY):
            notifier.sent.clear()
            main_mod.main(["--config", str(config), "--state", str(self.state), *extra], env={}, now=now)
            return [m for batch in notifier.sent for m in batch]

        def load(self):
            return json.loads(self.state.read_text(encoding="utf-8"))

    e = Env()
    e.notifier = notifier
    return e


def test_first_run_is_silent_initialization(env):
    env.set(offers=OFFERS)
    [msg] = env.run()
    assert msg.kind == "init"
    assert msg.title == "Veille PNC active – 2 offres indexées, dont 1 PNC"
    assert [a.offer.title for a in msg.alerts] == ["Hôtesse de l'air / Steward H/F"]
    assert len(env.load()["offers"]) == 2


def test_new_offer_is_notified_once(env):
    env.set(offers=OFFERS)
    env.run()
    state = env.load()
    del state["offers"]["fake::1"]  # « fausse offre » : on la fait oublier
    env.state.write_text(json.dumps(state), encoding="utf-8")
    [msg] = env.run()
    assert msg.kind == "offer" and msg.alerts[0].offer.offer_id == "1" and msg.url.endswith("/offre/1")
    assert env.run() == []  # déjà vue


def test_instructor_offer_is_notified(env):
    env.set(offers=[])
    env.run()
    env.set(offers=[{"offer_id": "9", "title": "Instructeur PNC H/F", "location": "Roissy", "contract": "CDI"}])
    [msg] = env.run()
    assert msg.alerts[0].tag == "Instructeur PNC"


def test_non_pnc_offer_is_not_notified(env):
    env.set(offers=[])
    env.run()
    env.set(offers=[OFFERS[1]])
    assert env.run() == []


def test_more_than_five_offers_are_grouped(env):
    env.set(offers=[])
    env.run()
    env.set(offers=[{**OFFERS[0], "offer_id": str(i)} for i in range(6)])
    [msg] = env.run()
    assert msg.kind == "offers_group" and len(msg.alerts) == 6


def test_source_down_alert_after_three_failures_then_recovery(env):
    env.set(offers=OFFERS)
    env.run()
    env.set(error="HTTP 404")
    assert env.run() == []
    assert env.run() == []
    [down] = env.run()
    assert down.kind == "source_down" and "HTTP 404" in " ".join(down.lines)
    before = env.state.read_text(encoding="utf-8")
    assert env.run() == [] and env.run() == []  # une seule alerte
    assert env.state.read_text(encoding="utf-8") == before  # et pas de commit à chaque run
    env.set(offers=OFFERS)
    [up] = env.run()
    assert up.kind == "source_up"
    assert "failures" not in env.load()["sources"]["fake"]


def test_blocked_source_is_paused(env):
    env.set(offers=OFFERS)
    env.run()
    env.set(error="blocked")
    env.run(), env.run()
    [down] = env.run()
    assert "403" in " ".join(down.lines)
    assert "paused_until" in env.load()["sources"]["fake"]


def test_all_channels_failing_keeps_offer_for_next_run(env):
    env.set(offers=[])
    env.run()
    env.notifier.fail = True
    env.set(offers=[OFFERS[0]])
    env.run()
    assert "fake::1" not in env.load()["offers"]
    env.notifier.fail = False
    [msg] = env.run()
    assert msg.kind == "offer"


def test_dry_run_writes_nothing(env, capsys):
    env.set(offers=OFFERS)
    assert env.run("--dry-run") == []
    assert not env.state.exists()
    assert "Veille PNC active" in capsys.readouterr().out


def test_weekly_summary_on_monday_morning(env):
    env.set(offers=OFFERS)
    env.run()
    monday = datetime(2026, 11, 2, 8, 7, tzinfo=PARIS)
    [weekly] = env.run(now=monday)
    assert weekly.kind == "weekly" and "Fake Air" in " ".join(weekly.lines)
    assert env.run(now=monday) == []  # une seule fois


def test_state_unchanged_means_no_write(env):
    env.set(offers=OFFERS)
    env.run()
    mtime = env.state.stat().st_mtime_ns
    env.run()
    assert env.state.stat().st_mtime_ns == mtime


def test_job_summary_written(env, tmp_path):
    env.set(offers=OFFERS)
    summary = tmp_path / "summary.md"
    main_mod.main(["--config", str(tmp_path / "sources.yaml"), "--state", str(env.state)],
                  env={"GITHUB_STEP_SUMMARY": str(summary)}, now=TUESDAY)
    text = summary.read_text(encoding="utf-8")
    assert "| `fake` | Fake Air | fake | ok | 2 | 2 |" in text


def test_notify_all_source_sends_every_entry(env, tmp_path):
    config = tmp_path / "alert.yaml"
    config.write_text(yaml.safe_dump({"sources": [{"id": "alerte", "company": "French Bee", "type": "fake",
                                                   "file": str(tmp_path / "fake.json"), "notify_all": True}]}),
                      encoding="utf-8")

    def run():
        env.notifier.sent.clear()
        main_mod.main(["--config", str(config), "--state", str(env.state)], env={}, now=TUESDAY)
        return [m for batch in env.notifier.sent for m in batch]

    env.set(offers=[])
    run()
    env.set(offers=[{"offer_id": "a1", "title": "French Bee ouvre sa saison de recrutement"}])
    [msg] = run()
    assert msg.title == "Alerte Google – French Bee" and msg.icon == "🔎" and msg.link_label == "Lire l'article"
