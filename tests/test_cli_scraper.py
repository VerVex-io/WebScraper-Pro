import pytest

from tests.conftest import FakeResponse
from webscraper_pro import scraper
from webscraper_pro.cli import main


def test_cli_list(capsys, tmp_path):
    from pathlib import Path

    assert main(["list", "--config-dir", str(Path(__file__).parent.parent / "configs")]) == 0
    assert "alibaba" in capsys.readouterr().out


@pytest.mark.parametrize("site", ["../x", "no such", "a/b"])
def test_cli_rejects_bad_site(site, capsys):
    assert main(["scrape", "--site", site, "--keyword", "x"]) == 2
    assert "error" in capsys.readouterr().err


def test_cli_missing_config_is_clean_error(tmp_path, capsys):
    assert main(["scrape", "--site", "nope", "--keyword", "x", "--config-dir", str(tmp_path)]) == 2


def test_cli_bad_scheme_autoconfig(tmp_path, capsys):
    assert (
        main(
            [
                "autoconfig",
                "--url",
                "file:///etc/passwd/{query}",
                "--site",
                "x",
                "--config-dir",
                str(tmp_path),
            ]
        )
        == 2
    )


def test_robots_disallow_blocks_fetch(cfg, monkeypatch, fake_dns):
    monkeypatch.setattr(
        scraper, "safe_get", lambda *a, **k: (b"User-agent: *\nDisallow: /search\n", FakeResponse())
    )
    with pytest.raises(PermissionError, match="robots.txt"):
        scraper.fetch_html(cfg, "phone")


def test_robots_unreachable_means_allowed(monkeypatch, fake_dns):
    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(scraper, "safe_get", boom)
    assert scraper.robots_allows("https://shop.test/search?q=1", log=lambda m: None)


def test_scrape_pipeline_end_to_end(cfg, listing_html, tmp_path, monkeypatch, fake_dns):
    monkeypatch.setattr(scraper, "fetch_html", lambda *a, **k: listing_html)
    res = scraper.scrape_site(cfg, "phone", out_dir=tmp_path, images=False, log=lambda m: None)
    assert len(res.rows) == 4 and len(res.files) == 3
    assert all(f.parent == tmp_path.resolve() for f in res.files)


def test_private_search_url_blocked_before_browser(cfg, monkeypatch):
    from webscraper_pro.config import parse_config
    from webscraper_pro.security import SecurityError

    bad = parse_config(
        {
            "name": "x",
            "search_url": "http://127.0.0.1:8080/?q={query}",
            "selectors": {"item": "div", "name": "a"},
        }
    )
    with pytest.raises(SecurityError):
        scraper.fetch_html(bad, "kw", respect_robots=False)
