from pathlib import Path

import pytest

from webscraper_pro.config import parse_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def listing_html() -> str:
    return (FIXTURES / "listing.html").read_text(encoding="utf-8")


@pytest.fixture
def cfg():
    return parse_config(
        {
            "name": "demo",
            "search_url": "https://shop.example.test/search?q={query}",
            "selectors": {
                "item": "div.product-card",
                "name": "h3.ttl",
                "price": "span.price",
                "url": "a.lnk",
                "image_url": "img.thumb",
            },
        }
    )


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b"", chunks=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks if chunks is not None else [body]

    def iter_content(self, chunk_size=65536):
        yield from self._chunks

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        pass


class FakeSession:
    """Returns queued responses in order; records requested URLs."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requested = []
        self.trust_env = True

    def get(self, url, **kwargs):
        self.requested.append(url)
        assert kwargs.get("allow_redirects") is False
        assert kwargs.get("verify") is True
        assert kwargs.get("timeout")
        return self.responses.pop(0)


@pytest.fixture
def fake_dns(monkeypatch):
    """Resolve *.test hosts to a public IP so tests need no network."""
    import socket

    real = socket.getaddrinfo

    def fake(host, port, *a, **k):
        if str(host).endswith(".test"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        return real(host, port, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", fake)
