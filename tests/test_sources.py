import json
from pathlib import Path

import pytest
import yaml

from veille.http import SourceError
from veille.sources.base import FetchContext, build_source
from veille.sources.html_list import extract_offers
from veille.sources.page_watch import added_lines, extract_zone, removed_lines, text_hash
from veille.sources.rss import parse_rss
from veille.sources.sitemap import parse_offer_page, parse_sitemap

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = {s["id"]: s for s in yaml.safe_load((Path(__file__).parents[1] / "config" / "sources.yaml").read_text(encoding="utf-8"))["sources"]}


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def source(source_id: str):
    return build_source(CONFIG[source_id])


# --- RSS ---

def test_talentsoft_rss_fields():
    [offer] = parse_rss(fixture("talentsoft_pn.xml"), source("airfrance_pn"))
    assert offer.title == "Pilote de ligne F/H"  # référence « 2026-23622 - » retirée
    assert offer.offer_id == "2026-23622"
    assert offer.contract == "CDI"
    assert "ROISSY" in offer.location
    assert offer.published_at.startswith("2026-")
    assert "ATPL" in offer.description


def test_talentsoft_empty_feed_is_valid():
    assert parse_rss(fixture("talentsoft_empty.xml"), source("aircalin")) == []


def test_talentsoft_recent_feed():
    offers = parse_rss(fixture("talentsoft_recent.xml"), source("hop"))
    assert len(offers) == 20
    assert len({o.offer_id for o in offers}) == 20
    assert all(o.contract for o in offers)


def test_taleo_rss_and_france_filter():
    src = source("easyjet")
    offers = parse_rss(fixture("taleo.xml"), src)
    assert len(offers) == 11
    assert any(o.offer_id == "17446" and o.title.startswith("Cabin Crew London Gatwick") for o in offers)
    assert [o for o in offers if src.keep(o)] == []  # aucune offre en France dans ce flux


GOOGLE_ALERT = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><id>tag:google.com,2005:reader/user/1/state/com.google/alerts/2</id>
<title>Alerte Google - French Bee PNC</title>
<entry><id>tag:google.com,2013:googlealerts/feed:123</id>
<title type="html">&lt;b&gt;French Bee&lt;/b&gt; recrute 150 PNC pour 2027</title>
<link href="https://www.google.com/url?rct=j&amp;sa=t&amp;url=https://www.exemple.fr/article-pnc&amp;ct=ga"/>
<published>2026-10-26T08:00:00Z</published>
<content type="html">La compagnie ouvre une campagne de recrutement de &lt;b&gt;PNC&lt;/b&gt;</content></entry></feed>"""


def test_atom_google_alert():
    [offer] = parse_rss(GOOGLE_ALERT, source("hop"))
    assert offer.title == "French Bee recrute 150 PNC pour 2027"
    assert offer.url == "https://www.exemple.fr/article-pnc"
    assert offer.offer_id == "tag:google.com,2013:googlealerts/feed:123"


def test_invalid_rss_raises():
    with pytest.raises(SourceError):
        parse_rss(b"<html><body>Maintenance</body></html>", source("hop"))


# --- html_list ---

def test_asl_list():
    src = source("asl")
    offers = extract_offers(fixture("asl.html").decode(), src, src.url)
    assert len(offers) == 4  # filtre keep_if_any: France
    pnc = next(o for o in offers if "PNC" in o.title)
    assert pnc.location == "Tremblay-en-France France"
    assert pnc.raw["category"] == "Aircrew"
    assert pnc.url.endswith("/en/") and pnc.offer_id.isdigit()
    assert pnc.description


ATN_EMPTY = """<html><body><main><div id="block-atn-content"><div class="hero"><a href="/emploi/offres">Nos offres</a>
<a href="/candidature-spontanee">Candidature spontanée</a></div><div class="job-description-listing"><p>Découvrez…</p></div>
<div class="error-message">Aucune offre d'emploi n'est disponible pour le moment</div></div></main></body></html>"""


def test_air_tahiti_nui_empty_page_is_coherent():
    src = source("airtahitinui")
    assert extract_offers(ATN_EMPTY, src, src.url) == []


def test_air_tahiti_nui_with_offer():
    src = source("airtahitinui")
    html = ATN_EMPTY.replace('<div class="error-message">Aucune offre d\'emploi n\'est disponible pour le moment</div>',
                             '<div class="views"><a href="/emploi/offres/pnc-2027">Personnel Navigant Commercial H/F</a></div>')
    [offer] = extract_offers(html, src, src.url)
    assert offer.title == "Personnel Navigant Commercial H/F"
    assert offer.url == "https://fr.airtahitinui.com/emploi/offres/pnc-2027"


def test_changed_page_without_empty_text_raises():
    src = source("airtahitinui")
    with pytest.raises(SourceError):
        extract_offers("<html><body><div id='block-atn-content'>Nouveau site</div></body></html>", src, src.url)


# --- browser (rendu enregistré) ---

def test_air_corsica_rendered_list():
    src = source("aircorsica")
    offers = extract_offers(fixture("aircorsica_rendered.html").decode(), src, src.url)
    assert len(offers) == 2
    o = next(o for o in offers if o.title.startswith("Chargé de planification"))
    assert (o.location, o.contract, o.published_at) == ("Ajaccio", "CDD", "12 oct. 2026")
    assert o.offer_id.startswith("a10")
    assert o.raw["direction"] == "Direction des Opérations"


# --- sitemap ---

def test_sitemap_offer_urls():
    urls = parse_sitemap(fixture("aircaraibes_sitemap.xml"), r"/offer/([^/?#]+)")
    assert len(urls) == 15 and "11381-aWx4aWJmYnZpcA" in urls


def test_sitemap_prefers_french_urls():
    urls = parse_sitemap(fixture("frenchbee_sitemap.xml"), r"/offer/([^/?#]+)", prefer="/fr/")
    assert len(urls) == 3 and all("/fr/offer/" in u for u in urls.values())


def test_hellowork_offer_page():
    info = parse_offer_page(fixture("hellowork_offer_rendered.html").decode())
    assert info["title"] == "Attaché(e) commercial"
    assert info["contract"] == "CDD"
    assert info["location"] == "Saint-Martin"
    assert info["published_at"].startswith("2026-10-15")
    assert "direction commerciale" in info["description"]


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes

    def _resp(self, url):
        class R:
            pass
        r = R()
        body = self.routes[next(k for k in self.routes if k in url)]
        r.content = body
        r.text = body.decode()
        r.url = url
        r.json = lambda: json.loads(body)
        return r

    def get(self, url, **kw):
        return self._resp(url)

    def post(self, url, **kw):
        return self._resp(url)


class FakeBrowser:
    def __init__(self, html):
        self.html, self.calls = html, 0

    def render(self, url, **kw):
        self.calls += 1
        return self.html


def test_sitemap_renders_only_new_urls():
    src = source("aircaraibes")
    browser = FakeBrowser(fixture("hellowork_offer_rendered.html").decode())
    ctx = FetchContext(FakeHttp({"sitemap.xml": fixture("aircaraibes_sitemap.xml")}), browser,
                       known_ids=set(list(parse_sitemap(fixture("aircaraibes_sitemap.xml"), r"/offer/([^/?#]+)"))[:14]))
    offers = src.fetch(ctx)
    assert browser.calls == 1
    assert len(offers) == 15
    assert sum(1 for o in offers if o.title) == 1


# --- DigitalRecruiters ---

def test_transavia_api():
    src = source("transavia")
    detail = json.dumps({"description": "<p>Missions</p>", "profile": "<p>Anglais B2</p>"}).encode()
    http = FakeHttp({"job-ads/": detail, "job-ads": fixture("transavia_list.json")})
    known = {item["id"] for item in json.loads(fixture("transavia_list.json"))["items"][1:]}
    offers = src.fetch(FetchContext(http, FakeBrowser(""), known_ids=known))
    assert len(offers) == 40
    first = offers[0]
    assert first.url.startswith("https://recrutement.transavia.com/fr/annonce/4658009-")
    assert first.contract == "CDD" and first.location == "Orly"
    assert "Anglais B2" in first.description
    assert all(not o.description for o in offers[1:])  # détail lu seulement pour les nouvelles offres


# --- page_watch ---

PAGE = """<html><body><nav>Menu Réserver</nav><article id="content"><h2>Recrutement</h2>
<p>Air Austral recherche de nouveaux talents.</p><p>Note obtenue à l'Index Égalité : 81/100</p>
<form>Réserver votre vol</form></article></body></html>"""


def test_page_watch_zone_and_diff():
    old = extract_zone(PAGE, "article#content", ignore_lines=["^Note obtenue"])
    assert old == "Recrutement\nAir Austral recherche de nouveaux talents."
    new_html = PAGE.replace("<h2>Recrutement</h2>", "<h2>Recrutement</h2><p>Campagne PNC 2027 : candidatures ouvertes</p>")
    new = extract_zone(new_html, "article#content", ignore_lines=["^Note obtenue"])
    assert text_hash(new) != text_hash(old)
    assert added_lines(old, new) == ["Campagne PNC 2027 : candidatures ouvertes"]
    assert removed_lines(old, new) == []
    # changement ignoré (index égalité) ou d'espaces : même hash
    assert text_hash(extract_zone(PAGE.replace("81/100", "85/100"), "article#content", ignore_lines=["^Note obtenue"])) == text_hash(old)


def test_page_watch_missing_zone_raises():
    with pytest.raises(SourceError):
        extract_zone("<html><body>Refonte</body></html>", "article#content")
