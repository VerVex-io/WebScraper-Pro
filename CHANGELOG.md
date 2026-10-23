# Changelog

## 2.0.0
### Security
- Replaced executable Python configs with validated JSON (data is never turned into code).
- Added SSRF protection, redirect re-validation, download size caps, timeouts, content-type checks.
- Fixed path traversal in output file names and site names; fixed URL parameter injection via keywords.
- Neutralised CSV/Excel formula injection; added decompression-bomb guard for images.
- Chrome sandbox now on by default; robots.txt respected by default.
- Pinned dependencies; upgraded Pillow, soupsieve, urllib3, idna, certifi to patched versions.
### Changed
- Restructured into the `webscraper_pro` package with a unified CLI (`scrape`, `autoconfig`, `test`, `list`, `gui`).
- Config key `image` renamed `image_url`; configs are now `configs/<site>.json`.
- Replaced fixed ~20 s of sleeps with waiting for the product selector; Chrome version auto-detected.
- Improved selector auto-detection (repeating container with price + link).
### Fixed
- GUI: blocking `input()` call, non-thread-safe widget updates, `subprocess` call that broke the frozen .exe.
- Relative/protocol-relative URLs are now resolved to absolute; `javascript:`/`data:` URLs dropped.
- Names for image-only links fall back to `title`/`alt` (Alibaba exports had empty names).
- `requirements.txt` file name (was `requirement.txt`).
### Added
- 126 tests (~90 % coverage), CI, CodeQL, Dependabot, SECURITY.md.

## 1.0.0
- Initial release.
