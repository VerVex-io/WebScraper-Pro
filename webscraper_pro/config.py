"""Site configurations.

v1 stored configs as Python modules that were generated from scraped data and
then imported (i.e. data -> code).  v2 uses plain JSON that is *validated*
and never executed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import soupsieve

from .security import SecurityError, validate_site_name

MAX_SELECTOR_LEN = 500
FIELDS = ("name", "price", "url", "image_url")
REQUIRED = ("item", "name")


class ConfigError(ValueError):
    """Raised when a site config is missing or invalid."""


def default_config_dir() -> Path:
    """configs/ next to the project, overridable with WSP_CONFIG_DIR."""
    env = os.environ.get("WSP_CONFIG_DIR")
    if env:
        return Path(env)
    return Path.cwd() / "configs"


@dataclass(frozen=True)
class SiteConfig:
    name: str
    search_url: str
    selectors: dict[str, str]
    wait_selector: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        parts = urlsplit(self.search_url)
        return f"{parts.scheme}://{parts.netloc}/"

    def to_dict(self) -> dict:
        data = {"name": self.name, "search_url": self.search_url, "selectors": dict(self.selectors)}
        if self.wait_selector:
            data["wait_selector"] = self.wait_selector
        return data


def validate_selector(selector: str, label: str = "selector") -> str:
    if not isinstance(selector, str) or not selector.strip():
        raise ConfigError(f"{label}: empty selector")
    if len(selector) > MAX_SELECTOR_LEN:
        raise ConfigError(f"{label}: selector longer than {MAX_SELECTOR_LEN} chars")
    try:
        soupsieve.compile(selector)
    except Exception as exc:  # soupsieve.SelectorSyntaxError and friends
        raise ConfigError(f"{label}: invalid CSS selector ({exc})") from exc
    return selector


def parse_config(data: dict) -> SiteConfig:
    """Validate a raw dict and turn it into a SiteConfig."""
    if not isinstance(data, dict):
        raise ConfigError("Config must be a JSON object.")
    try:
        name = validate_site_name(str(data.get("name", "")))
    except SecurityError as exc:
        raise ConfigError(str(exc)) from exc

    search_url = data.get("search_url")
    if not isinstance(search_url, str) or search_url.count("{query}") != 1:
        raise ConfigError("search_url must be a string containing '{query}' exactly once.")
    parts = urlsplit(search_url.replace("{query}", "x"))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError("search_url must be an absolute http(s) URL.")
    if parts.username or parts.password:
        raise ConfigError("search_url must not contain credentials.")

    raw = data.get("selectors")
    if not isinstance(raw, dict):
        raise ConfigError("'selectors' must be an object.")
    unknown = set(raw) - set(FIELDS) - {"item"}
    if unknown:
        raise ConfigError(f"Unknown selector keys: {sorted(unknown)}")
    selectors: dict[str, str] = {}
    for key in ("item", *FIELDS):
        value = raw.get(key)
        if value in (None, "", "N/A"):
            if key in REQUIRED:
                raise ConfigError(f"selectors.{key} is required.")
            continue
        selectors[key] = validate_selector(value, f"selectors.{key}")

    wait = data.get("wait_selector")
    if wait:
        validate_selector(wait, "wait_selector")
    return SiteConfig(name=name, search_url=search_url, selectors=selectors, wait_selector=wait or None)


def config_path(site: str, config_dir: Path | None = None) -> Path:
    site = validate_site_name(site)  # blocks '../' etc.
    base = (config_dir or default_config_dir()).resolve()
    path = (base / f"{site}.json").resolve()
    if path.parent != base:
        raise ConfigError("Config path escapes the config directory.")
    return path


def load_config(site: str, config_dir: Path | None = None) -> SiteConfig:
    path = config_path(site, config_dir)
    if not path.is_file():
        raise ConfigError(f"Config '{path.name}' not found in {path.parent}.")
    if path.stat().st_size > 64 * 1024:
        raise ConfigError("Config file unexpectedly large (>64 KB).")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path.name}: invalid JSON ({exc})") from exc
    cfg = parse_config(data)
    if cfg.name != validate_site_name(site):
        raise ConfigError(f"{path.name}: 'name' ({cfg.name}) does not match file name.")
    return cfg


def save_config(cfg: SiteConfig, config_dir: Path | None = None, overwrite: bool = False) -> Path:
    path = config_path(cfg.name, config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise ConfigError(f"{path.name} already exists (use overwrite).")
    path.write_text(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def list_sites(config_dir: Path | None = None) -> list[str]:
    base = config_dir or default_config_dir()
    if not base.is_dir():
        return []
    return sorted(p.stem for p in base.glob("*.json"))
