import json

import pytest

from tests.conftest import FakeResponse
from webscraper_pro import autoconfig, security
from webscraper_pro.autoconfig import autoconfigure, css_for, detect_selectors
from webscraper_pro.config import parse_config
from webscraper_pro.parser import parse_html
from webscraper_pro.security import SecurityError


def test_detects_working_selectors(listing_html):
    sel = detect_selectors(listing_html)
    assert sel["item"] == "div.card.product-card"
    cfg = parse_config({"name": "t", "search_url": "https://a.test/{query}", "selectors": sel})
    rows = parse_html(listing_html, cfg)
    assert len(rows) == 4 and rows[0]["price"] == "$199.99"


def test_header_and_script_prices_ignored(listing_html):
    assert "header" not in detect_selectors(listing_html)["item"]


def test_no_products_raises():
    with pytest.raises(ValueError):
        detect_selectors("<html><body><p>nothing here</p></body></html>")


def test_hostile_class_names_never_reach_selectors():
    """v1 interpolated class names into generated Python source."""
    evil = '''x"),__import__("os").system("id"),("'''
    html = (f"""<div class='ok {evil} y'><a href="/p">n</a><h3>Name</h3><span>$10.00</span></div>""") * 4
    sel = detect_selectors(html)
    for value in sel.values():
        assert '"' not in value and "(" not in value and ";" not in value and "\\" not in value
    parse_config({"name": "t", "search_url": "https://a.test/{query}", "selectors": sel})  # still valid


def test_css_for_filters_odd_classes():
    from bs4 import BeautifulSoup

    tag = BeautifulSoup('<div class="good 9bad a.b a:b ok-2"></div>', "html.parser").div
    assert css_for(tag) == "div.good.ok-2"


def test_autoconfigure_writes_json_only(tmp_path, listing_html, monkeypatch):
    monkeypatch.setattr(autoconfig, "safe_get", lambda url, **k: (listing_html.encode(), FakeResponse()))
    path = autoconfigure("https://shop.example.test/s?q={query}", "demo", config_dir=tmp_path)
    assert path.suffix == ".json" and not list(tmp_path.glob("*.py"))
    data = json.loads(path.read_text())
    assert data["name"] == "demo" and data["search_url"].endswith("{query}")


@pytest.mark.parametrize("site", ["../evil", "a/b", "x;y", ""])
def test_autoconfigure_rejects_bad_site(tmp_path, site):
    with pytest.raises(SecurityError):
        autoconfigure("https://a.test/{query}", site, config_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_autoconfigure_blocks_internal_targets(tmp_path):
    with pytest.raises(SecurityError):
        autoconfigure("http://169.254.169.254/{query}", "meta", config_dir=tmp_path)


def test_guess_search_url(monkeypatch):
    calls = []

    def fake(url, **k):
        calls.append(url)
        if "recherche" in url:
            return b"laptop laptop results", FakeResponse()
        raise security.SecurityError("404")

    monkeypatch.setattr(autoconfig, "safe_get", fake)
    got = autoconfig.guess_search_url("https://shop.test")
    assert got == "https://shop.test/recherche?s={query}"


def test_suggest_fixes():
    from bs4 import BeautifulSoup

    item = BeautifulSoup(
        '<div><h2>Title here</h2><span class="price">$5</span>'
        '<a href="/x">l</a><img data-src="/i.png"></div>',
        "html.parser",
    ).div
    fixes = autoconfig.suggest_fixes(item)
    assert fixes["name"] == "h2" and fixes["url"] == "a[href]" and fixes["image_url"] == "img[data-src]"
