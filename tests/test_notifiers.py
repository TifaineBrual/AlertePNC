import pytest
import requests

from veille.matching import detect
from veille.messages import (OfferAlert, format_date, init_message, offer_messages, page_change_message,
                             source_down_message)
from veille.models import Offer
from veille.notifiers import NotifyError, enabled_notifiers
from veille.notifiers import base as notif_base
from veille.notifiers.discord import DiscordNotifier, embed
from veille.notifiers.email import render_html, render_text, subject
from veille.notifiers.ntfy import NtfyNotifier, render


def alert(title="Hôtesse de l'air / Steward H/F", **kw):
    fields = {"location": "Orly", "contract": "CDI", "published_at": "2026-10-26T15:03:14+00:00", **kw}
    offer = Offer("airfrance_pnc", "Air France", "1", title, "https://example.com/o?a=1&b=2", **fields)
    return OfferAlert(offer, detect(offer.title))


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
    names = [n.name for n in enabled_notifiers({"DISCORD_WEBHOOK_URL": "https://d", "NTFY_TOPIC": "t", "SMTP_HOST": "h"})]
    assert names == ["Discord", "ntfy"]  # e-mail incomplet


def test_format_date():
    assert format_date("2026-10-26T15:03:14+00:00") == "26/10/2026"
    assert format_date("2026-10-15T01:37:37.000Z") == "15/10/2026"
    assert format_date("12 oct. 2026") == "12 oct. 2026"


def test_every_pnc_offer_gets_its_own_message_up_to_five():
    assert [m.kind for m in offer_messages([alert()] * 5)] == ["offer"] * 5
    [group] = offer_messages([alert()] * 6)
    assert group.kind == "offers_group" and len(group.alerts) == 6


# --- Discord ---

def test_discord_offer_embed():
    e = embed(offer_messages([alert()])[0])
    assert e["author"]["name"] == "✈️ Nouvelle offre PNC · Air France"
    assert e["title"] == "Hôtesse de l'air / Steward H/F"
    assert e["url"] == "https://example.com/o?a=1&b=2"
    assert [(f["name"], f["value"]) for f in e["fields"]] == [("Lieu", "Orly"), ("Contrat", "CDI"), ("Publiée le", "26/10/2026")]
    assert e["footer"]["text"] == "Veille PNC · airfrance_pnc"


def test_discord_hides_missing_facts():
    e = embed(offer_messages([alert(location="", contract="", published_at="")])[0])
    assert e["fields"] == []


def test_discord_group_lists_linked_offers():
    e = embed(offer_messages([alert()] * 6)[0])
    assert e["title"] == "✈️ 6 nouvelles offres PNC"
    assert e["description"].count("**[Hôtesse de l'air / Steward H/F](https://example.com/o?a=1&b=2)**") == 6


def test_discord_long_group_is_cut_cleanly():
    e = embed(offer_messages([alert(title="Hôtesse " * 20)] * 60)[0])
    assert len(e["description"]) <= 4000 and "autre(s) offre(s)" in e["description"]


def test_discord_page_change_quotes_new_text():
    e = embed(page_change_message("French Bee", "https://x", ["Campagne PNC 2027 ouverte"], []))
    assert e["title"] == "📣 French Bee : la page recrutement PNC a changé"
    assert "> Campagne PNC 2027 ouverte" in e["description"]


def test_discord_batches_embeds(recorder):
    DiscordNotifier("https://discord/webhook").send(offer_messages([alert()] * 5) * 3)
    assert [len(kw["json"]["embeds"]) for _, kw in recorder.calls] == [10, 5]


# --- ntfy ---

def test_ntfy_offer(recorder):
    NtfyNotifier("mon-topic-secret").send(offer_messages([alert()]))
    url, kw = recorder.calls[0]
    p = kw["json"]
    assert url == "https://ntfy.sh" and p["topic"] == "mon-topic-secret"
    assert p["title"] == "Air France — Hôtesse de l'air / Steward H/F"
    assert p["message"] == "📍 Orly\n📄 CDI\n🗓️ 26/10/2026"
    assert p["priority"] == 4 and p["tags"] == ["airplane"]
    assert p["actions"] == [{"action": "view", "label": "Voir l'offre", "url": "https://example.com/o?a=1&b=2", "clear": True}]


def test_ntfy_instructor_tag_and_group():
    single = render(offer_messages([alert(title="Instructeur PNC")])[0])
    assert single["title"].endswith("(Instructeur PNC)")
    group = render(offer_messages([alert()] * 6)[0])
    assert group["title"] == "6 nouvelles offres PNC" and group["message"].count("• Air France —") == 6
    assert "click" not in group


def test_ntfy_init_without_offers():
    p = render(init_message(85, [], ["Air France", "Air France", "Transavia"], []))
    assert p["title"] == "Veille PNC active – 85 offres indexées, dont 0 PNC"
    assert "Sources : Air France, Transavia." in p["message"]


# --- e-mail ---

def test_email_subjects():
    assert subject(offer_messages([alert()])) == "✈️ Nouvelle offre PNC – Air France — Hôtesse de l'air / Steward H/F"
    assert subject(offer_messages([alert()] * 3)) == "✈️ 3 nouvelles offres PNC"
    assert subject([page_change_message("French Bee", "https://x", ["Campagne"], [])]) == \
        "📣 French Bee : la page recrutement PNC a changé"


def test_email_html_is_escaped_and_has_button():
    page = render_html(offer_messages([alert(title="PNC <Orly> & CDG")]))
    assert "PNC &lt;Orly&gt; &amp; CDG" in page
    assert 'href="https://example.com/o?a=1&amp;b=2"' in page and "Voir l’offre" in page


def test_email_text_version():
    text = render_text(offer_messages([alert()]) + [source_down_message("hop", "HOP!", "https://h", "HTTP 404", 3)])
    assert "Lieu : Orly" in text and "Contrat : CDI" in text and "https://example.com/o?a=1&b=2" in text
    assert "⚠️ Source en panne : HOP!" in text and "Dernière erreur : HTTP 404" in text


# --- sécurité ---

def test_error_never_leaks_secret_url(monkeypatch):
    def boom(url, **kw):
        raise requests.ConnectionError(f"cannot reach {url}")
    monkeypatch.setattr(notif_base.requests, "post", boom)
    with pytest.raises(NotifyError) as exc:
        DiscordNotifier("https://discord.com/api/webhooks/1/SECRET").send(offer_messages([alert()]))
    assert "SECRET" not in str(exc.value)


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(notif_base.requests, "post", Recorder(status=404))
    with pytest.raises(NotifyError, match="HTTP 404"):
        DiscordNotifier("https://discord/webhook/secret").send(offer_messages([alert()]))


def test_web_alert_rendering():
    from veille.matching import ALERT
    offer = Offer("frenchbee_alerte", "French Bee", "x", "French Bee recrute 150 PNC", "https://news.example/a")
    msg = offer_messages([OfferAlert(offer, ALERT)])[0]
    assert embed(msg)["author"]["name"] == "🔎 Alerte Google · French Bee"
    assert render(msg)["tags"] == ["mag"] and render(msg)["actions"][0]["label"] == "Lire l'article"
    assert subject([msg]) == "🔎 Alerte Google – French Bee — French Bee recrute 150 PNC"
    assert "Lire l’article" in render_html([msg])


def test_rss_source_without_secret_url_fails_clearly():
    from veille.http import SourceError
    from veille.sources.base import FetchContext, build_source
    src = build_source({"id": "a", "company": "A", "type": "rss", "url_env": "VEILLE_TEST_ABSENT"})
    with pytest.raises(SourceError, match="VEILLE_TEST_ABSENT"):
        src.fetch(FetchContext(None, None))


@pytest.mark.parametrize("raw, shown", [
    ("45 rue de Paris 95747 ROISSY CHARLES DE GAULLE CEDEX", "Roissy Charles de Gaulle"),
    ("2 AV du Maréchal Devaux 94390 Orly", "Orly"),
    ("ORLY", "Orly"),
    ("CDG ORY", "CDG ORY"),
    ("Zone de Fret aéroport de LYON", "Zone de Fret aéroport de Lyon"),
    ("LA RÉUNION", "La Réunion"),
    ("Tremblay-en-France France", "Tremblay-en-France France"),
    ("", ""),
])
def test_display_location(raw, shown):
    from veille.messages import display_location
    assert display_location(raw) == shown


def test_ntfy_topic_given_as_full_url():
    n = NtfyNotifier.from_env({"NTFY_TOPIC": "https://ntfy.sh/veille-pnc-abc123/"})
    assert (n.server, n.topic) == ("https://ntfy.sh", "veille-pnc-abc123")


def test_email_settings_are_tolerant():
    from veille.notifiers.email import EmailNotifier
    base = {"SMTP_USER": "moi@gmail.com", "SMTP_PASSWORD": "abcd efgh ijkl mnop", "EMAIL_TO": "moi@gmail.com"}
    n = EmailNotifier.from_env({**base, "SMTP_HOST": "smtp.gmail.com:587"})
    assert (n.host, n.port, n.password) == ("smtp.gmail.com", 587, "abcdefghijklmnop")
    assert EmailNotifier.from_env({**base, "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "465 (SSL)"}).port == 465


def test_email_falls_back_to_working_mode(monkeypatch):
    import smtplib
    from veille.notifiers import email as email_mod
    tried = []

    class FakeSMTP:
        def __init__(self, host, port, **kw):
            tried.append(("plain", port))
            if port != 587:
                raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

        def starttls(self, **kw):
            pass

    class FakeSSL(FakeSMTP):
        def __init__(self, host, port, **kw):
            tried.append(("ssl", port))
            if port != 465:
                raise OSError("wrong version number")

    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", FakeSSL)
    n = email_mod.EmailNotifier("smtp.gmail.com", 465, "u", "p", "t")
    assert isinstance(n._connect(), FakeSSL) and tried == [("ssl", 465)]
    tried.clear()
    n.port = 4650  # port erroné : on finit par 465 en SSL
    assert isinstance(n._connect(), FakeSSL)
    assert tried == [("plain", 4650), ("ssl", 4650), ("ssl", 465)]
