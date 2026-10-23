"""Turn HTML into product dicts using a SiteConfig (pure functions, no I/O)."""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit

import soupsieve
from bs4 import BeautifulSoup, Tag

from .config import SiteConfig

NA = "N/A"
_MAX_TEXT = 500
_NAME_ATTRS = ("title", "aria-label", "alt")
_IMG_ATTRS = ("src", "data-src", "data-original", "data-lazy-src")


def _select(item: Tag, selector: str | None) -> Tag | None:
    if not selector:
        return None
    try:
        return item.select_one(selector)
    except soupsieve.SelectorSyntaxError:  # defensive: selector was validated at load time
        return None


def _clean(text: str) -> str:
    return " ".join(text.split())[:_MAX_TEXT]


def _text_of(tag: Tag | None) -> str:
    if tag is None:
        return NA
    text = _clean(tag.get_text(" ", strip=True))
    if not text:  # e.g. <a><img alt="Phone"></a> - fall back to attributes
        for attr in _NAME_ATTRS:
            val = tag.get(attr)
            if isinstance(val, str) and val.strip():
                return _clean(val)
        img = tag.find("img")
        if img is not None and isinstance(img.get("alt"), str) and img["alt"].strip():
            return _clean(img["alt"])
    return text or NA


def absolutize(value: str | None, base_url: str) -> str:
    """Resolve a (possibly protocol-relative) URL; drop non-http(s) schemes
    such as ``javascript:`` or ``data:``."""
    if not value or not isinstance(value, str):
        return NA
    full = urljoin(base_url, value.strip())
    return full if urlsplit(full).scheme in ("http", "https") else NA


def parse_item(item: Tag, cfg: SiteConfig) -> dict | None:
    sel = cfg.selectors
    link = _select(item, sel.get("url"))
    if link is not None and not link.get("href") and item.name != "a":
        link = link.find_parent("a") or link
    image = _select(item, sel.get("image_url"))

    image_url = NA
    if image is not None:
        for attr in _IMG_ATTRS:
            candidate = image.get(attr)
            if isinstance(candidate, str) and candidate.strip() and not candidate.startswith("data:"):
                image_url = absolutize(candidate, cfg.base_url)
                break

    data = {
        "name": _text_of(_select(item, sel.get("name"))),
        "price": _text_of(_select(item, sel.get("price"))),
        "url": absolutize(link.get("href"), cfg.base_url) if link is not None else NA,
        "image_url": image_url,
    }
    return data if any(v != NA for v in data.values()) else None


def parse_html(html: str, cfg: SiteConfig) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select(cfg.selectors["item"]):
        parsed = parse_item(item, cfg)
        if parsed:
            results.append(parsed)
    return results
