from datetime import date
from pathlib import Path

import pytest

from grocery_agent.scrapers.kaufland import parse

HTML = (Path(__file__).parent / "fixtures" / "kaufland.html").read_text(encoding="utf-8")


def by_name(offers, fragment):
    return next(o for o in offers if fragment in o.name)


def test_offers_from_both_weekly_cycles():
    offers = parse(HTML)
    assert {o.valid_to for o in offers} == {date(2026, 11, 15), date(2026, 11, 22)}


def test_dedupes_offers_repeated_in_several_categories():
    offers = parse(HTML)
    # 9 raw entries this week, one of them is the "Black week" copy of the pork fillet
    assert len([o for o in offers if o.valid_to == date(2026, 11, 15)]) == 8
    assert sum("Свинско филе" in o.name for o in offers) == 1


def test_card_only_offer_uses_card_price_and_says_so():
    o = by_name(parse(HTML), "Газов котлон")
    assert (o.price, o.old_price) == (19.99, 39.99)
    assert o.note is not None and "Kaufland Card" in o.note


def test_offer_with_no_price_at_all_is_skipped():
    html = (
        "<script>window.SSR = window.SSR || {}; window.SSR['x'] = "
        '{"props":{"offerData":{"cycles":[{"categories":[{"displayName":"X","offers":['
        '{"offerId":"1","title":"Без цена","subtitle":"","dateFrom":"2026-11-09","dateTo":"2026-11-15"},'
        '{"offerId":"2","title":"С цена","subtitle":"","price":1.5,"dateFrom":"2026-11-09","dateTo":"2026-11-15"}'
        "]}]}]}}};</script>"
    )
    assert [o.name for o in parse(html)] == ["С цена"]


def test_name_joins_brand_and_description():
    o = by_name(parse(HTML), "Свинско филе")
    assert o.name == "Леки Свинско филе"
    assert (o.shop, o.price, o.old_price, o.discount_pct, o.unit) == ("Kaufland", 5.79, 6.99, 17, "кг")
    assert (o.valid_from, o.valid_to) == (date(2026, 11, 9), date(2026, 11, 15))


def test_multiline_subtitle_is_flattened():
    o = by_name(parse(HTML), "Крема сирене")
    assert "\n" not in o.name


def test_offer_without_old_price():
    o = by_name(parse(HTML), "Луканков салам")
    assert (o.price, o.old_price, o.discount_pct) == (3.79, None, None)


def test_loyalty_price_is_noted_not_used_as_main_price():
    o = by_name(parse(HTML), "Банани")
    assert o.price == 1.29
    assert o.note is not None and "1,09" in o.note


def test_page_without_data_raises():
    with pytest.raises(ValueError):
        parse("<html><body>no data</body></html>")
