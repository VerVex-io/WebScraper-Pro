"""Security regression tests - each one maps to a finding in SECURITY_AUDIT.md."""

import pytest

from tests.conftest import FakeResponse, FakeSession
from webscraper_pro import security as sec
from webscraper_pro.security import SecurityError


# --- F-01 path traversal via site/keyword -----------------------------------
@pytest.mark.parametrize(
    "bad", ["../x", "a/b", "a\\b", "", " ", "x" * 41, "-lead", "a b", "a;rm", "con\x00", "é"]
)
def test_site_name_rejects_unsafe(bad):
    with pytest.raises(SecurityError):
        sec.validate_site_name(bad)


@pytest.mark.parametrize("good", ["sbs", "alibaba", "my-site_2"])
def test_site_name_accepts_safe(good):
    assert sec.validate_site_name(good) == good


@pytest.mark.parametrize("kw", ["../../etc/passwd", "a/b\\c", "x\x00y", "..", "C:\\win"])
def test_safe_filename_has_no_separators(kw):
    out = sec.safe_filename(kw)
    assert not any(c in out for c in "/\\\x00:.")
    assert out


def test_safe_filename_truncates_and_defaults():
    assert len(sec.safe_filename("a" * 500)) == 50
    assert sec.safe_filename("///") == "query"


# --- F-02 URL parameter injection / format-string ----------------------------
def test_keyword_cannot_inject_params():
    url = sec.build_search_url("https://s.test/?s={query}", "a&admin=1#frag")
    assert url == "https://s.test/?s=a%26admin%3D1%23frag"


def test_template_braces_not_evaluated():
    url = sec.build_search_url("https://s.test/?s={query}&x={0.__class__}", "kw")
    assert "{0.__class__}" in url and "<class" not in url


def test_keyword_limits():
    with pytest.raises(SecurityError):
        sec.encode_query("   ")
    with pytest.raises(SecurityError):
        sec.encode_query("a" * 201)


# --- F-03 CSV / Excel formula injection --------------------------------------
@pytest.mark.parametrize("val", ['=cmd|"/c calc"!A1', "+1+1", "-2+3", "@SUM(A1)", "\t=1", "\r=1"])
def test_formula_prefixes_neutralised(val):
    assert sec.sanitize_cell(val).startswith("'")


def test_normal_values_untouched():
    assert sec.sanitize_cell("$19.99") == "$19.99"
    assert sec.sanitize_cell(5) == 5
    assert sec.sanitize_cell("N/A") == "N/A"


# --- F-04 SSRF ----------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file://ok.test/etc/passwd",
        "ftp://ok.test/x",
        "javascript:alert(1)",
        "data:text/html,x",
        "gopher://ok.test/",
        "ws://ok.test/",
        "FILE:///etc/passwd",
    ],
)
def test_non_http_schemes_blocked(url, fake_dns):
    # DNS is faked to a public IP, so only the scheme check can reject these.
    with pytest.raises(SecurityError, match="scheme"):
        sec.validate_url(url)


def test_credentials_blocked(fake_dns):
    with pytest.raises(SecurityError, match="credentials"):
        sec.validate_url("http://user:pw@ok.test/")


@pytest.mark.parametrize("url", ["", "   ", "http:///nohost"])
def test_empty_or_hostless_blocked(url):
    with pytest.raises(SecurityError):
        sec.validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://[::1]/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fe80::1]/",
        "http://224.0.0.1/",
        "http://100.64.0.1/",
    ],
)
def test_private_targets_blocked(url):
    with pytest.raises(SecurityError):
        sec.validate_url(url)


def test_allow_private_override():
    assert sec.validate_url("http://127.0.0.1:8000/", allow_private=True)


def test_public_literal_ip_ok():
    assert sec.validate_url("https://93.184.216.34/x")


def test_redirect_to_private_address_blocked(fake_dns):
    s = FakeSession(FakeResponse(302, {"Location": "http://169.254.169.254/latest/meta-data/"}))
    with pytest.raises(SecurityError):
        sec.safe_get("https://ok.test/", session=s)
    assert s.requested == ["https://ok.test/"]  # the internal URL was never requested


def test_redirect_to_file_scheme_blocked(fake_dns):
    s = FakeSession(FakeResponse(301, {"Location": "file://ok.test/etc/passwd"}))
    with pytest.raises(SecurityError, match="scheme"):
        sec.safe_get("https://ok.test/", session=s)


def test_redirect_loop_stops(fake_dns):
    s = FakeSession(*[FakeResponse(302, {"Location": "https://ok.test/"}) for _ in range(10)])
    with pytest.raises(SecurityError, match="redirects"):
        sec.safe_get("https://ok.test/", session=s)


def test_redirects_followed_when_safe(fake_dns):
    s = FakeSession(
        FakeResponse(302, {"Location": "/next"}), FakeResponse(200, {"Content-Type": "text/html"}, b"hi")
    )
    body, _ = sec.safe_get("https://ok.test/", session=s)
    assert body == b"hi" and s.requested[1] == "https://ok.test/next"


def test_proxy_env_not_trusted(fake_dns):
    s = FakeSession(FakeResponse(200, {}, b"x"))
    sec.safe_get("https://ok.test/", session=s)
    assert s.trust_env is False


# --- F-05 unbounded downloads --------------------------------------------------
def test_size_cap_on_declared_length(fake_dns):
    s = FakeSession(FakeResponse(200, {"Content-Length": "999999999"}, b"x"))
    with pytest.raises(SecurityError, match="too large"):
        sec.safe_get("https://ok.test/", session=s, max_bytes=1000)


def test_size_cap_on_streamed_body(fake_dns):
    s = FakeSession(FakeResponse(200, {}, chunks=[b"x" * 600, b"x" * 600]))  # lies about/omits length
    with pytest.raises(SecurityError, match="exceeded"):
        sec.safe_get("https://ok.test/", session=s, max_bytes=1000)


def test_content_type_enforced(fake_dns):
    s = FakeSession(FakeResponse(200, {"Content-Type": "text/html"}, b"<html>"))
    with pytest.raises(SecurityError, match="Content-Type"):
        sec.safe_get("https://ok.test/a.png", session=s, accept_prefix="image/")


def test_http_error_raises(fake_dns):
    s = FakeSession(FakeResponse(500, {}, b""))
    with pytest.raises(RuntimeError):
        sec.safe_get("https://ok.test/", session=s)
