## What & why

## Checklist
- [ ] `ruff check . && ruff format --check .` pass
- [ ] `pytest` passes; new behaviour has tests
- [ ] No scraped data, credentials or binaries committed
- [ ] Anything touching URLs, files or HTML goes through `webscraper_pro/security.py`
