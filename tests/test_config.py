import json

import pytest

from webscraper_pro.config import ConfigError, list_sites, load_config, parse_config, save_config

GOOD = {
    "name": "demo",
    "search_url": "https://a.test/s?q={query}",
    "selectors": {"item": "div.card", "name": "h3"},
}


def test_valid_config_parses():
    c = parse_config(GOOD)
    assert c.name == "demo" and c.base_url == "https://a.test/"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(name="../evil"),
        lambda d: d.update(name=""),
        lambda d: d.update(search_url="file:///etc/passwd"),
        lambda d: d.update(search_url="javascript:{query}"),
        lambda d: d.update(search_url="https://a.test/"),  # no {query}
        lambda d: d.update(search_url="https://a.test/{query}{query}"),  # twice
        lambda d: d.update(search_url="https://u:p@a.test/{query}"),
        lambda d: d["selectors"].update(item='div"); import os; ('),  # invalid CSS
        lambda d: d["selectors"].update(item="x" * 501),
        lambda d: d["selectors"].update(evil="a"),  # unknown key
        lambda d: d["selectors"].pop("item"),
        lambda d: d.update(selectors="nope"),
        lambda d: d.update(wait_selector="((("),
    ],
)
def test_invalid_configs_rejected(mutate):
    data = json.loads(json.dumps(GOOD))
    mutate(data)
    with pytest.raises(ConfigError):
        parse_config(data)


def test_non_dict_rejected():
    with pytest.raises(ConfigError):
        parse_config([1, 2])


def test_path_traversal_in_load(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps(GOOD))
    with pytest.raises(Exception):
        load_config("../x", tmp_path)


def test_name_must_match_filename(tmp_path):
    (tmp_path / "other.json").write_text(json.dumps(GOOD))  # name=demo
    with pytest.raises(ConfigError, match="does not match"):
        load_config("other", tmp_path)


def test_oversized_config_rejected(tmp_path):
    (tmp_path / "demo.json").write_text(" " * 70000)
    with pytest.raises(ConfigError, match="large"):
        load_config("demo", tmp_path)


def test_invalid_json_rejected(tmp_path):
    (tmp_path / "demo.json").write_text("{not json")
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config("demo", tmp_path)


def test_roundtrip_and_overwrite_protection(tmp_path):
    c = parse_config(GOOD)
    p = save_config(c, tmp_path)
    assert load_config("demo", tmp_path) == c
    assert list_sites(tmp_path) == ["demo"]
    with pytest.raises(ConfigError):
        save_config(c, tmp_path)
    save_config(c, tmp_path, overwrite=True)
    assert p.read_text().endswith("\n")


def test_bundled_configs_are_valid():
    from pathlib import Path

    root = Path(__file__).parent.parent / "configs"
    sites = list_sites(root)
    assert {"alibaba", "sbs"} <= set(sites)
    for s in sites:
        load_config(s, root)
