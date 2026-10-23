# Security audit: WebScraper Pro v1 → v2

Scope: all source in the v1 archive (`scraper.py`, `autoconfig.py`, `gui.py`, `run.py`,
`test_all_configs.py`, `configs/*.py`, `gui.spec`, packaging/licence files).
Method: manual code review, proof-of-concept testing against v1, `bandit`, `ruff` (security
rules), `pip-audit`, then regression tests and mutation checks against v2.

## Findings

| ID | Severity | Finding in v1 | Status in v2 |
|----|----------|---------------|--------------|
| F-01 | **High** | **Path traversal.** Output file name built from the raw keyword (`output/sbs_../../evil_x_…`); site name used unvalidated as a file/module name. *PoC confirmed.* | Fixed: `validate_site_name`, `safe_filename`, output path containment check. |
| F-02 | **High** | **No SSRF protection.** `autoconfig`, the GUI and image download fetched any URL a user, config or *scraped page* supplied: `localhost`, `169.254.169.254`, redirects to internal hosts. | Fixed: `validate_url` + `safe_get` (scheme allow-list, public-IP check, re-validation on each redirect, no env proxies). |
| F-03 | **Medium** | **URL parameter injection.** Keyword only had spaces replaced by `+` and was passed to `str.format`: `a&admin=1#` altered the request. *PoC confirmed.* | Fixed: `quote_plus`; template filled with `.replace`, never `.format`. |
| F-04 | **Medium** | **CSV / Excel formula injection.** Scraped text starting with `=`, `+`, `-`, `@` was written verbatim to CSV/XLSX. | Fixed: `sanitize_cell` on CSV and XLSX output (JSON stays raw). |
| F-05 | **Medium** | **Unbounded downloads.** `requests.get` for images with no size limit, no content-type check, no pixel limit (memory exhaustion / decompression bomb). | Fixed: 5 MB streaming cap, content-type check, Pillow pixel limit, re-encode to thumbnail, max images. |
| F-06 | **Medium** | **Chrome sandbox always disabled** (`--no-sandbox`) while rendering untrusted pages. | Fixed: sandbox on by default; opt-in flag/env var. |
| F-07 | Low-Med | **Data → code generation.** `autoconfig` wrote scraped class/id names into a `.py` file that was later imported. | Fixed by design: JSON configs, strict identifier allow-list, schema + CSS validation. See note below. |
| F-08 | Low | Unpinned dependencies (`requirement.txt` had no versions; wrong file name vs README). | Fixed: pinned `requirements.txt`; Dependabot. |
| F-09 | Low | `subprocess.run(["python", …])` from the GUI: partial path, breaks when frozen. `input()` inside a GUI thread. Widgets updated from worker threads. | Fixed: direct function calls; queue-based UI updates (a smoke test found a *second* thread-safety bug in my first rewrite, also fixed). |
| F-10 | Low | `debug_<site>.html` dumped into the working directory on every run. | Removed. |
| F-11 | Low | Silent `except: pass` blocks hid failures. | Narrowed to specific exceptions. |
| F-12 | Info | **Licence forbade publishing on GitHub** and contained a placeholder e-mail. 52 MB `.exe` + 150 MB build output in the archive. | Replaced by MIT (author's decision, see README/hand-off); binaries excluded via `.gitignore`. |
| F-13 | Info | No robots.txt handling; hard-coded Chrome version (`version_main=137`). | robots.txt obeyed by default; version auto-detected. |

### Note on F-07 (downgraded after testing)

I initially suspected remote code execution: a hostile page's class name flowing into the
generated Python config. I tried to exploit it against v1 and **could not**: v1 accidentally
protects itself because BeautifulSoup rejects selectors containing raw quotes *before* they are
written out. So this was a fragile design rather than an exploitable bug, and is rated Low-Med.
Moving to JSON removes the whole class of problem. A regression test
(`test_hostile_class_names_never_reach_selectors`) keeps it that way.

## Dependency audit (`pip-audit`, clean virtualenv, full transitive tree)

Before: Pillow 12.1.1 (dozens of advisories; fixed in 13.0.0), soupsieve 2.8.3, urllib3 2.6.3, idna 3.11, certifi (older CA bundle).
After: pinned to Pillow 13.0.0, soupsieve 3.0.4, urllib3 2.8.0, idna 3.20, certifi 2026.10.23 →
**no known vulnerabilities in runtime dependencies** (only the virtualenv's own `pip` was flagged; it is tooling, not a dependency).
Pillow and soupsieve matter most: both parse untrusted input. Re-run weekly via the Security workflow.

## Verification

- `bandit`: 0 issues (v1: 9 low, mostly noise: it did not see F-01…F-06).
- `ruff` incl. security (`S`) and blind-except (`BLE`) rules: clean.
- 126 tests, ~90 % line coverage (GUI/browser excluded; GUI covered by a manual Xvfb smoke test).
- **Mutation checks:** disabling each protection individually (formula sanitising, private-IP check,
  redirect validation, size cap, query encoding, `javascript:` filtering, scheme check, credential
  check, CSS validation, decompression-bomb limit, robots.txt) makes at least one test fail.
  This exposed one weak test (scheme check passing for the wrong reason), now fixed.

## Not covered / residual risk

- **Live scraping was not tested** (no internet or Chrome in the audit environment). Parsing,
  exporting and the pipeline are tested against fixtures; the Alibaba/SBS selectors in
  `configs/` are the v1 ones (minus Alibaba's tracking `spm` parameter and a brittle
  `rank_id_2` class) and may be stale. Run `python -m webscraper_pro test`.
- DNS-rebinding TOCTOU and Chrome's own DNS resolution (see SECURITY.md).
- No fuzzing, no penetration test of third-party sites, no review of Chrome/undetected-chromedriver themselves.
- Scraping legality / Terms-of-Service compliance is the user's responsibility.
