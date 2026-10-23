"""Orchestration: robots.txt check -> browser -> parse -> export."""

from __future__ import annotations

import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .config import SiteConfig
from .exporter import export_all
from .parser import NA, parse_html
from .security import USER_AGENT, SecurityError, build_search_url, safe_get, validate_url

Log = Callable[[str], None]


def _stamp(log: Log) -> Log:
    return lambda msg: log(f"[{time.strftime('%H:%M:%S')}] {msg}")


def robots_allows(url: str, *, allow_private: bool = False, log: Log = print) -> bool:
    """Check robots.txt.  An unreachable robots.txt counts as 'allowed'."""
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        body, _ = safe_get(robots_url, max_bytes=512 * 1024, allow_private=allow_private)
    except (SecurityError, requests.RequestException, OSError) as exc:
        log(f"robots.txt not available ({exc}); assuming allowed.")
        return True
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(body.decode("utf-8", "ignore").splitlines())
    return parser.can_fetch(USER_AGENT, url) and parser.can_fetch("*", url)


@dataclass
class ScrapeResult:
    rows: list[dict]
    files: list[Path]
    html_length: int = 0


def fetch_html(
    cfg: SiteConfig,
    keyword: str,
    *,
    headless: bool = True,
    no_sandbox: bool | None = None,
    allow_private: bool = False,
    respect_robots: bool = True,
    log: Log = print,
) -> str:
    log = _stamp(log)
    url = validate_url(build_search_url(cfg.search_url, keyword), allow_private=allow_private)
    if respect_robots and not robots_allows(url, allow_private=allow_private, log=log):
        raise PermissionError(
            f"robots.txt of {urlsplit(url).netloc} disallows this URL. "
            "Pass --ignore-robots only if you have permission to scrape this site."
        )
    from .browser import init_driver, load_page  # lazy: needs Chrome

    driver = init_driver(headless=headless, no_sandbox=no_sandbox)
    try:
        return load_page(driver, url, wait_selector=cfg.wait_selector or cfg.selectors["item"], log=log)
    finally:
        try:
            driver.quit()
        except Exception as exc:  # noqa: BLE001 - nothing useful to do on shutdown errors
            log(f"Browser shutdown warning: {exc}")
        log("Browser closed")


def scrape_site(
    cfg: SiteConfig,
    keyword: str,
    *,
    out_dir: Path = Path("output"),
    formats=("json", "csv", "xlsx"),
    images: bool = True,
    max_images: int = 50,
    headless: bool = True,
    no_sandbox: bool | None = None,
    allow_private: bool = False,
    respect_robots: bool = True,
    log: Log = print,
) -> ScrapeResult:
    log = _stamp(log)
    log(f"Scraping {cfg.name} for '{keyword}'")
    html = fetch_html(
        cfg,
        keyword,
        headless=headless,
        no_sandbox=no_sandbox,
        allow_private=allow_private,
        respect_robots=respect_robots,
        log=log,
    )
    rows = parse_html(html, cfg)
    log(f"Parsed {len(rows)} products")
    if not rows:
        log("No items parsed - the site layout may have changed (try 'preview'/'test').")
        return ScrapeResult([], [], len(html))
    files = export_all(
        rows,
        out_dir,
        cfg.name,
        keyword,
        formats=formats,
        images=images,
        max_images=max_images,
        allow_private=allow_private,
        log=log,
    )
    return ScrapeResult(rows, files, len(html))


def check_config(
    cfg: SiteConfig, keyword: str = "laptop", *, sample: int = 3, log: Log = print, **kw
) -> float:
    """Live-test one config; returns the share of fields parsed (0..1)."""
    html = fetch_html(cfg, keyword, log=log, **kw)
    rows = parse_html(html, cfg)[:sample]
    log(f"{cfg.name}: {len(rows)} sample item(s) parsed")
    total = ok = 0
    for i, row in enumerate(rows, 1):
        for key, val in row.items():
            total += 1
            ok += val != NA
            log(f"  #{i} {'OK ' if val != NA else 'MISS'} {key}: {val}")
    return ok / total if total else 0.0
