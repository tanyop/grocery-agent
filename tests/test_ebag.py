import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from grocery_agent.scrapers.ebag import parse_item, parse_period, scrape

ITEM = json.loads((Path(__file__).parent / "fixtures" / "ebag_offer_item.json").read_text(encoding="utf-8"))


def item(**changes):
    return {**ITEM, **changes}


def test_parse_item_reads_prices_dates_and_links():
    o = parse_item(ITEM)
    assert (o.shop, o.name) == ("eBag", "Райска Ябълка")
    assert (o.price, o.old_price, o.discount_pct) == (0.69, 0.89, 22)
    assert o.unit == "1 бр."
    assert (o.valid_from, o.valid_to) == (date(2026, 11, 12), date(2026, 11, 18))
    assert o.url == "https://ebag.bg/raiska-iablka/640738"
    assert o.image == "https://ebag.bg/products/640738/images/0/800"
    assert o.note is None


def test_discount_is_computed_when_the_feed_has_none():
    o = parse_item(item(discount_percent=None))
    assert o.discount_pct == 22  # (0.89 - 0.69) / 0.89


@pytest.mark.parametrize(
    "changes",
    [
        {"is_promo": False},
        {"is_available": False},
        {"price_promo_eur": None},
        {"price_promo_eur": "0.89"},  # promo not cheaper than regular
        {"price_promo_eur": "1.20"},
        {"name": ""},
    ],
)
def test_items_that_are_not_real_deals_are_skipped(changes):
    assert parse_item(item(**changes)) is None


def test_item_without_picture_has_no_image():
    assert parse_item(item(image_count=0)).image is None


def test_parse_period():
    assert parse_period("12/11/2026 - 18/11/2026") == (date(2026, 11, 12), date(2026, 11, 18))
    assert parse_period(None) == (None, None)
    assert parse_period("") == (None, None)
    assert parse_period("whenever") == (None, None)
    assert parse_period("31/02/2026 - 18/11/2026") == (None, None)  # impossible date


def make_client(total, page_size=20, fail_pages=(), ids_offset=0):
    """A fake eBag feed serving `total` offers in pages of `page_size`."""
    requested = []

    def handler(request):
        page = int(request.url.params.get("page", 1))
        requested.append(page)
        if page in fail_pages:
            return httpx.Response(500)
        start = (page - 1) * page_size
        results = [item(id=ids_offset + i, name=f"Продукт {i}", url_slug=f"p{i}") for i in range(start, min(start + page_size, total))]
        nxt = f"https://ebag.bg/categories/offers-products/json?mode=all_offers&page={page + 1}" if start + page_size < total else None
        return httpx.Response(200, json={"count": total, "next": nxt, "previous": None, "results": results})

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def test_scrape_reads_every_page():
    client, requested = make_client(45)
    offers = scrape(client, pause=0)
    assert len(offers) == 45
    assert sorted(requested) == [1, 2, 3]
    assert len({o.url for o in offers}) == 45


def test_scrape_ignores_keywords_argument():
    client, _ = make_client(5)
    assert len(scrape(client, ["пилешк"], pause=0)) == 5


def test_one_failing_page_does_not_lose_the_others():
    client, _ = make_client(45, fail_pages=(2,))
    assert len(scrape(client, pause=0, attempts=1)) == 25


def test_first_page_failure_raises_so_the_shop_is_reported_as_failed():
    client, _ = make_client(45, fail_pages=(1,))
    with pytest.raises(httpx.HTTPStatusError):
        scrape(client, pause=0, attempts=1)


def test_empty_or_changed_feed_raises():
    def handler(request):
        return httpx.Response(200, json={"count": 0, "next": None, "results": []})

    with pytest.raises(ValueError):
        scrape(httpx.Client(transport=httpx.MockTransport(handler)), pause=0)

    def broken(request):
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(ValueError):
        scrape(httpx.Client(transport=httpx.MockTransport(broken)), pause=0)
