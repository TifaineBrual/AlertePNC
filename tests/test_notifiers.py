import pytest
import requests

from veille.matching import Profile, detect, score_offer
from veille.messages import OfferAlert, offer_message, page_change_message
from veille.models import Offer
from veille.notifiers import NotifyError, enabled_notifiers
from veille.notifiers import base as notif_base
from veille.notifiers.discord import DiscordNotifier, embed
from veille.notifiers.email import subject
from veille.notifiers.ntfy import NtfyNotifier
from veille.notifiers.telegram import TelegramNotifier, render


def alert():
    offer = Offer("af", "Air France", "1", "Hôtesse de l'air <Orly> & CDG", "https://example.com/o?a=1&b=2",
                  location="Orly", contract="CDI")
    d = detect(offer.title)
    return OfferAlert(offer, d, score_offer(offer, d, Profile()))


class Recorder:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        resp = requests.Response()
        resp.status_code = self.status
        resp._content = b"{}"
        return resp


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(notif_base.requests, "post", rec)
    return rec


def test_channels_enabled_only_with_secrets():
    assert enabled_notifiers({}) == []
    names = [n.name for n in enabled_notifiers({"DISCORD_WEBHOOK_URL": "https://d", "NTFY_TOPIC": "t",
                                                "TELEGRAM_BOT_TOKEN": "x"})]
    assert names == ["Discord", "ntfy"]  # Telegram incomplet (pas de chat id)


def test_discord_offer_embed():
    e = embed(offer_message(alert()))
    assert e["url"] == "https://example.com/o?a=1&b=2"
    assert [f["name"] for f in e["fields"]][:3] == ["Compagnie", "Lieu", "Contrat"]
    assert e["fields"][3]["name"].startswith("Score 50/100")


def test_discord_batches_embeds(recorder):
    DiscordNotifier("https://discord/webhook").send([offer_message(alert())] * 12)
    assert [len(kw["json"]["embeds"]) for _, kw in recorder.calls] == [10, 2]


def test_ntfy_payload(recorder):
    NtfyNotifier("mon-topic-secret").send([offer_message(alert())])
    url, kw = recorder.calls[0]
    assert url == "https://ntfy.sh"
    p = kw["json"]
    assert p["topic"] == "mon-topic-secret" and p["priority"] == 3
    assert p["actions"][0] == {"action": "view", "label": "Ouvrir l'offre", "url": "https://example.com/o?a=1&b=2", "clear": True}


def test_telegram_html_is_escaped():
    html = render(offer_message(alert()))
    assert "&lt;Orly&gt; &amp; CDG" in html
    assert '<a href="https://example.com/o?a=1&amp;b=2">Ouvrir l\'offre</a>' in html


def test_error_never_leaks_token(monkeypatch):
    def boom(url, **kw):
        raise requests.ConnectionError(f"cannot reach {url}")
    monkeypatch.setattr(notif_base.requests, "post", boom)
    with pytest.raises(NotifyError) as exc:
        TelegramNotifier("123:SECRET", "42").send([offer_message(alert())])
    assert "SECRET" not in str(exc.value)


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(notif_base.requests, "post", Recorder(status=404))
    with pytest.raises(NotifyError, match="HTTP 404"):
        DiscordNotifier("https://discord/webhook/secret").send([offer_message(alert())])


def test_email_subject_summarizes_run():
    msgs = [offer_message(alert()), offer_message(alert()), page_change_message("French Bee", "https://x", ["Campagne"], [])]
    assert subject(msgs) == "✈️ Veille PNC : 2 nouvelle(s) offre(s) PNC"
    assert subject(msgs[2:]) == "📣 French Bee : la page recrutement PNC a changé"
