# Contributing

1. Fork, create a branch, `pip install -r requirements-dev.txt`.
2. Make your change **with tests** (`pytest`). Security-relevant changes need a regression test
   in `tests/test_security.py`.
3. `ruff check . && ruff format .` must be clean.
4. Open a PR. CI runs tests on Linux/Windows and security scans.

Rules of thumb:
- Any URL you fetch goes through `security.safe_get`; any user text used in a file name goes
  through `safe_filename`; any scraped string written to CSV/XLSX goes through `sanitize_cell`.
- Never turn scraped data into executable code.
- Don't commit scraped output, credentials, or binaries.

## Adding a site

`python -m webscraper_pro autoconfig --url https://shop.tld --site shop`, then check/edit
`configs/shop.json` and run `python -m webscraper_pro test`.
