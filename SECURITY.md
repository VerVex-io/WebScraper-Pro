# Security Policy

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's
[private vulnerability reporting](../../security/advisories/new) (Security tab → "Report a vulnerability").
Include steps to reproduce and the version. You can expect an initial response within 7 days.

## Supported versions

Only the latest release receives security fixes.

## Security model

WebScraper Pro fetches **untrusted** web content on your machine. Defences built in:

| Threat | Mitigation |
|--------|-----------|
| SSRF (scraping internal services / cloud metadata via a URL or redirect) | Only `http(s)`; hosts resolving to private/loopback/link-local ranges are blocked, **re-checked on every redirect**. Override with `--allow-private`. |
| Malicious config / code injection | Configs are JSON, validated, never executed. Selectors are compiled as CSS at load time. Auto-detected selectors use a strict identifier allow-list. |
| Path traversal | Site names are `[a-z0-9_-]`; output file names are sanitised and verified to stay inside the output folder. |
| URL parameter injection | Keywords are percent-encoded; templates are never evaluated with `str.format`. |
| CSV / Excel formula injection | Cells starting with `= + - @` (and tab/CR) are neutralised in CSV and XLSX. |
| Resource exhaustion | 5 MB cap on HTML/images, timeouts, redirect limit, image pixel limit (decompression bombs), max embedded images. |
| Malicious pages exploiting the browser | Chrome's sandbox stays **on** unless you explicitly pass `--no-sandbox`. |
| Policy violations | robots.txt is obeyed by default. |

### Known limitations

- DNS is resolved for validation and again by the HTTP library, so a hostile DNS server could
  **rebind** between the two (TOCTOU). The browser (Chrome) also resolves hostnames itself.
  For untrusted targets, run inside a container/VM with restricted network egress.
- Page content is rendered by a real Chrome instance; keep Chrome up to date.
- `--ignore-robots`, `--allow-private` and `--no-sandbox` deliberately weaken protections.
- Scraped data is untrusted: sanitise it before inserting it into databases or web pages.

See [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) for the full audit of v1 → v2.
