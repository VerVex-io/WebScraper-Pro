"""Security helpers: URL/SSRF validation, safe HTTP fetching, filename and
spreadsheet-formula sanitising.  Everything that touches untrusted input
(URLs, scraped HTML, keywords, site names) goes through this module."""

from __future__ import annotations

import io
import ipaddress
import re
import socket
from urllib.parse import quote_plus, urljoin, urlsplit

import requests

USER_AGENT = "Mozilla/5.0 (compatible; WebScraperPro/2.0)"
MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = 10

_SITE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


class SecurityError(ValueError):
    """Raised when an input is rejected for security reasons."""


# --------------------------------------------------------------------------
# names / filenames / queries
# --------------------------------------------------------------------------
def validate_site_name(name: str) -> str:
    """Site names become file names (configs/<name>.json): keep them boring."""
    name = (name or "").strip().lower()
    if not _SITE_NAME_RE.fullmatch(name):
        raise SecurityError(
            "Invalid site name. Use 1-40 chars: a-z, 0-9, '_' or '-' (must start with a letter or digit)."
        )
    return name


def safe_filename(text: str, max_len: int = 50) -> str:
    """Reduce arbitrary user text to a safe file-name fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text or "").strip("_")
    return cleaned[:max_len] or "query"


def encode_query(keyword: str) -> str:
    """Percent-encode a keyword so it cannot add or alter URL parameters."""
    keyword = (keyword or "").strip()
    if not keyword:
        raise SecurityError("Keyword must not be empty.")
    if len(keyword) > 200:
        raise SecurityError("Keyword too long (max 200 characters).")
    return quote_plus(keyword)


def build_search_url(template: str, keyword: str) -> str:
    """Fill ``{query}`` in a search URL template.

    Deliberately NOT ``str.format``: a template containing other braces must
    never be evaluated as a format string.
    """
    return template.replace("{query}", encode_query(keyword))


# --------------------------------------------------------------------------
# spreadsheet formula injection (CSV / XLSX)
# --------------------------------------------------------------------------
def sanitize_cell(value):
    """Neutralise CSV/Excel formula injection (OWASP "CSV Injection").

    Scraped text such as ``=HYPERLINK(...)`` would execute when the file is
    opened in Excel or LibreOffice.  Prefix such strings with an apostrophe.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


# --------------------------------------------------------------------------
# URL validation (SSRF defence)
# --------------------------------------------------------------------------
def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """Accept only http(s) URLs without credentials that resolve to public IPs."""
    if not isinstance(url, str) or not url.strip():
        raise SecurityError("Empty URL.")
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise SecurityError(f"Blocked URL scheme '{parts.scheme}': only http/https allowed.")
    if not parts.hostname:
        raise SecurityError("URL has no host.")
    if parts.username or parts.password:
        raise SecurityError("URLs with embedded credentials are not allowed.")
    if allow_private:
        return url
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SecurityError(f"Cannot resolve host '{parts.hostname}': {exc}") from exc
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise SecurityError(
                f"Blocked: '{parts.hostname}' resolves to a non-public address "
                f"({info[4][0]}). Use --allow-private to override."
            )
    return url


def _read_capped(resp: requests.Response, limit: int) -> bytes:
    declared = resp.headers.get("Content-Length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise SecurityError(f"Response too large ({declared} bytes > {limit}).")
    buf = io.BytesIO()
    for chunk in resp.iter_content(chunk_size=65536):
        buf.write(chunk)
        if buf.tell() > limit:
            raise SecurityError(f"Response exceeded {limit} bytes; aborted.")
    return buf.getvalue()


def safe_get(
    url: str,
    *,
    max_bytes: int = MAX_HTML_BYTES,
    timeout: int = DEFAULT_TIMEOUT,
    allow_private: bool = False,
    session: requests.Session | None = None,
    accept_prefix: str | None = None,
) -> tuple[bytes, requests.Response]:
    """GET with URL validation on every redirect hop, TLS verification, a
    timeout, a streaming size cap and an optional Content-Type check.

    Limitation: validation resolves DNS separately from the actual connection,
    so a hostile DNS server could still rebind between the two (TOCTOU).  Run
    the tool in a network-isolated environment when scraping untrusted targets.
    """
    sess = session or requests.Session()
    sess.trust_env = False  # don't silently pick up proxies from the environment
    current = validate_url(url, allow_private=allow_private)
    for _ in range(MAX_REDIRECTS + 1):
        resp = sess.get(
            current,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=False,
            stream=True,
            verify=True,
        )
        try:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise SecurityError("Redirect without Location header.")
                current = validate_url(urljoin(current, location), allow_private=allow_private)
                continue
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "").lower()
            if accept_prefix and not ctype.startswith(accept_prefix):
                raise SecurityError(f"Unexpected Content-Type '{ctype}'.")
            return _read_capped(resp, max_bytes), resp
        finally:
            resp.close()
    raise SecurityError("Too many redirects.")
