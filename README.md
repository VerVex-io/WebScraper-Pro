# 🕷️ WebScraper Pro

[![CI](https://github.com/VerVex-io/webscraper-pro/actions/workflows/ci.yml/badge.svg)](https://github.com/VerVex-io/webscraper-pro/actions/workflows/ci.yml)
[![Security](https://github.com/VerVex-io/webscraper-pro/actions/workflows/security.yml/badge.svg)](https://github.com/VerVex-io/webscraper-pro/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

A config-driven product scraper for e-commerce sites. Pick a site, type a keyword, and get
**JSON, CSV and Excel (with embedded product images)**. Includes a Tkinter GUI, a CLI, and an
auto-config tool that detects CSS selectors for new sites.

## Features

- Headless or visible Chrome scraping (Selenium + undetected-chromedriver)
- GUI **and** CLI
- Site configs are plain, validated **JSON** (no code execution)
- `autoconfig`: detects item/name/price/link/image selectors for a new site
- Selector preview with suggested fixes for empty fields
- Excel export with embedded thumbnails
- Secure by default: SSRF protection, size limits, CSV-injection protection,
  robots.txt respected (see [SECURITY.md](SECURITY.md))

## Install

Requires Python 3.10+ and Google Chrome.

```bash
git clone https://github.com/VerVex-io/webscraper-pro.git
cd webscraper-pro
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

On Linux you may need `sudo apt install python3-tk` for the GUI.

## Usage

```bash
python -m webscraper_pro list                                    # available site configs
python -m webscraper_pro scrape --site sbs --keyword "laptop"    # -> output/sbs_laptop_<time>.{json,csv,xlsx}
python -m webscraper_pro scrape --site sbs --keyword "laptop" --formats csv --no-images --headful
python -m webscraper_pro autoconfig --url https://www.example-shop.com --site myshop
python -m webscraper_pro test --keyword laptop                   # live-test every config
python -m webscraper_pro gui                                     # or: python run_gui.py
```

| Flag | Meaning |
|------|---------|
| `--ignore-robots` | Don't obey robots.txt. **Only with the site owner's permission.** |
| `--allow-private` | Allow localhost/LAN targets (turns off SSRF protection). |
| `--no-sandbox` | Disable Chrome's sandbox. Only for Docker/root; also `WSP_NO_SANDBOX=1`. |
| `--no-images` / `--max-images N` | Control Excel image embedding. |

## Config format

`configs/<site>.json`:

```json
{
  "name": "myshop",
  "search_url": "https://shop.example.com/search?q={query}",
  "selectors": {
    "item": "div.product-description",
    "name": "div.tvproduct-name.product-title",
    "price": "div.product-price-and-shipping",
    "url": "a",
    "image_url": "img"
  },
  "wait_selector": "div.product-description"
}
```

`item` and `name` are required; `{query}` must appear exactly once; every selector is
validated as real CSS at load time. Set `WSP_CONFIG_DIR` to use a different config folder.

> ⚠️ Selectors break when sites change their markup. Run `test` to find out which configs need
> attention. The bundled Alibaba/SBS configs are examples and may need updating.

## Migrating from v1

v1 configs were Python files (`configs/*.py`). v2 uses JSON. Convert by copying the values of
`site_config["search_url"]` and `site_config["selectors"]` into a `.json` file (note: the
selector key `image` is now `image_url`).

## Building the Windows .exe

```bash
pip install pyinstaller
pyinstaller gui.spec          # -> dist/WebScraperPro.exe
```

Attach the exe to a **GitHub Release** rather than committing it.

## Development

```bash
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest --cov
bandit -r webscraper_pro && pip-audit -r requirements.txt
```

## Responsible use

Scraping may be restricted by a site's Terms of Service and by law. You are responsible for
complying with them. The tool obeys robots.txt by default and is not designed to bypass
access controls, logins or paywalls. Don't use it for personal data harvesting.

## License

[MIT](LICENSE)
