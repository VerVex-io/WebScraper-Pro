from webscraper_pro.parser import NA, absolutize, parse_html


def test_parses_all_items(listing_html, cfg):
    rows = parse_html(listing_html, cfg)
    assert len(rows) == 4
    assert rows[0] == {
        "name": "Phone One 128GB",
        "price": "$199.99",
        "url": "https://shop.example.test/p/1",
        "image_url": "https://cdn.example.test/1.jpg",
    }  # protocol-relative + lazy attr


def test_javascript_and_data_urls_dropped(listing_html, cfg):
    third = parse_html(listing_html, cfg)[2]
    assert third["url"] == NA and third["image_url"] == NA


def test_name_falls_back_to_attributes(listing_html, cfg):
    # item 4 has no <h3>; name stays N/A (no selector hit) but price/url parse
    fourth = parse_html(listing_html, cfg)[3]
    assert fourth["price"] == "€ 49,90" and fourth["url"].endswith("/p/4")


def test_anchor_with_only_image_uses_alt_or_title():
    from webscraper_pro.config import parse_config

    c = parse_config(
        {
            "name": "x",
            "search_url": "https://a.test/{query}",
            "selectors": {"item": "div.i", "name": "a", "url": "a"},
        }
    )
    html = '<div class="i"><a href="/p"><img alt="  Cool   Phone "></a></div>'
    assert parse_html(html, c)[0]["name"] == "Cool Phone"


def test_empty_items_skipped(cfg):
    assert parse_html('<div class="product-card"></div>', cfg) == []


def test_text_is_length_capped(cfg):
    html = '<div class="product-card"><h3 class="ttl">' + "A" * 5000 + "</h3></div>"
    assert len(parse_html(html, cfg)[0]["name"]) == 500


def test_absolutize():
    assert absolutize("//x.test/a.jpg", "https://b.test/") == "https://x.test/a.jpg"
    assert absolutize("/a", "https://b.test/") == "https://b.test/a"
    assert absolutize("javascript:1", "https://b.test/") == NA
    assert absolutize("file:///etc/passwd", "https://b.test/") == NA
    assert absolutize(None, "https://b.test/") == NA
