"""Detect CSS selectors for a product-listing page and write a JSON config.

Selectors are built only from tag names and class names that match a strict
identifier pattern, so scraped markup can never inject anything into the
config.  The result is additionally validated by ``config.parse_config``.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

import requests
import soupsieve
from bs4 import BeautifulSoup, Tag

from .config import SiteConfig, parse_config, save_config
from .security import SecurityError, safe_get, validate_site_name

COMMON_SEARCH_PATTERNS = [
    "/search?q={query}",
    "/recherche?s={query}",
    "/recherche?controller=search&s={query}",
    "/?s={query}",
    "/catalogsearch/result/?q={query}",
    "/rech?q={query}",
]
TEST_KEYWORD = "laptop"

_CUR = r"(?:[$€£]|\b(?:usd|eur|gbp|tnd|dt|dinars?)\b|د\.ت)"
PRICE_RE = re.compile(rf"{_CUR}\s?\d|\d[\d.,\s]*\s?{_CUR}", re.I)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_SKIP_TAGS = {"html", "body", "head", "script", "style", "[document]"}
_MAX_CLASSES = 4
_MAX_DEPTH = 8


def css_for(tag: Tag) -> str:
    """Build a safe selector (tag + up to 4 identifier-like classes)."""
    classes = [c for c in (tag.get("class") or []) if _IDENT_RE.fullmatch(c)][:_MAX_CLASSES]
    name = tag.name if re.fullmatch(r"[a-z][a-z0-9]*", tag.name or "") else "div"
    return name + "".join(f".{c}" for c in classes)


def guess_search_url(base_url: str, *, allow_private: bool = False) -> str | None:
    """Try common search URL patterns and return a template with ``{query}``."""
    for pattern in COMMON_SEARCH_PATTERNS:
        url = urljoin(base_url.rstrip("/") + "/", pattern.format(query=TEST_KEYWORD).lstrip("/"))
        try:
            body, _ = safe_get(url, allow_private=allow_private, accept_prefix="text/html")
        except (SecurityError, requests.RequestException):
            continue  # expected: most patterns will not exist on a given site
        if body.decode("utf-8", "ignore").lower().count(TEST_KEYWORD) >= 2:
            head, _, tail = url.rpartition(TEST_KEYWORD)  # keyword is always the last occurrence
            return f"{head}{{query}}{tail}"
    return None


def detect_selectors(html: str) -> dict[str, str]:
    """Heuristic: the repeating element that contains a price AND a link."""
    soup = BeautifulSoup(html, "html.parser")
    votes: Counter[str] = Counter()
    price_nodes = [n for n in soup.find_all(string=PRICE_RE) if n.parent and n.parent.name not in _SKIP_TAGS]
    for node in price_nodes:
        for depth, anc in enumerate(node.parents):
            if depth >= _MAX_DEPTH or anc.name in _SKIP_TAGS:
                break
            if anc.find("a", href=True) is None:
                continue
            sel = css_for(anc)
            try:
                count = len(soup.select(sel))
            except soupsieve.SelectorSyntaxError:
                continue
            if 3 <= count <= 300:
                votes[sel] += 1
                break
    if not votes:
        raise ValueError("Could not find a repeating product container with a price.")
    item_sel = votes.most_common(1)[0][0]
    first = soup.select_one(item_sel)

    selectors = {"item": item_sel}
    heading = first.find(["h1", "h2", "h3", "h4"])
    name_tag = (
        heading
        or next((a for a in first.find_all("a", href=True) if a.get_text(strip=True)), None)
        or first.find(attrs={"title": True})
    )
    if name_tag is not None:
        selectors["name"] = css_for(name_tag)
    price_text = first.find(string=PRICE_RE)
    if price_text is not None and price_text.parent is not first:
        selectors["price"] = css_for(price_text.parent)
    link = first.find("a", href=True)
    if link is not None:
        selectors["url"] = css_for(link)
    img = first.find("img")
    if img is not None:
        selectors["image_url"] = css_for(img)
    if "name" not in selectors:
        raise ValueError("Could not detect a product name element.")
    return selectors


def suggest_fixes(item: Tag) -> dict[str, str]:
    """Fallback selectors for fields that came back empty (used by the GUI)."""
    fallback = {
        "name": ["h1", "h2", "h3", ".title", ".product-title", "a[title]"],
        "price": ["span.price", ".c-price", ".price", ".amount", "[class*=price]"],
        "url": ["a[href]"],
        "image_url": ["img[src]", "img[data-src]", "img[data-original]"],
    }
    best: dict[str, str] = {}
    for field_name, candidates in fallback.items():
        for sel in candidates:
            el = item.select_one(sel)
            if el is None:
                continue
            if field_name == "url" and el.get("href"):
                best[field_name] = sel
                break
            if field_name == "image_url" and (el.get("src") or el.get("data-src") or el.get("data-original")):
                best[field_name] = sel
                break
            if field_name in ("name", "price") and len(el.get_text(strip=True)) > 2:
                best[field_name] = sel
                break
    return best


def autoconfigure(
    target: str,
    site: str,
    *,
    config_dir: Path | None = None,
    allow_private: bool = False,
    overwrite: bool = False,
) -> Path:
    """Create ``configs/<site>.json`` from a domain or a full search URL."""
    site = validate_site_name(site)
    search_url = target
    if "{query}" not in target:
        search_url = guess_search_url(target, allow_private=allow_private)
        if not search_url:
            raise SecurityError("Could not auto-detect the search URL; pass one containing {query}.")
    test_url = search_url.replace("{query}", TEST_KEYWORD)
    body, _ = safe_get(test_url, allow_private=allow_private, accept_prefix="text/html")
    selectors = detect_selectors(body.decode("utf-8", "ignore"))
    cfg: SiteConfig = parse_config({"name": site, "search_url": search_url, "selectors": selectors})
    return save_config(cfg, config_dir, overwrite=overwrite)
