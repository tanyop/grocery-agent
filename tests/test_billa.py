from datetime import date
from pathlib import Path

from grocery_agent.scrapers.billa import parse

HTML = (Path(__file__).parent / "fixtures" / "billa.html").read_text(encoding="utf-8")


def by_name(offers, fragment):
    return next(o for o in offers if fragment in o.name)


def test_skips_info_blocks_without_prices():
    offers = parse(HTML)
    assert len(offers) == 6  # 8 blocks: validity + brand blurb carry no price


def test_old_price_discount_and_new_price():
    o = by_name(parse(HTML), "Странджански Бабек")
    assert (o.shop, o.price, o.old_price, o.discount_pct) == ("Billa", 3.19, 4.49, 28)
    assert o.name == "Обичам Странджански Бабек 250 г Произход - България"
    assert o.note == "Супер цена"


def test_card_price_pair_is_old_then_card_price():
    o = by_name(parse(HTML), "Слънчогледово олио")
    assert (o.price, o.old_price) == (1.39, 1.68)
    assert o.discount_pct == 17
    assert o.note == "Само с Billa Card"


def test_single_price_has_no_old_price():
    o = by_name(parse(HTML), "Пилешки крила")
    assert (o.price, o.old_price, o.discount_pct) == (3.29, None, None)
    assert o.note == "Сега в Billa"


def test_other_labels_are_moved_to_note():
    offers = parse(HTML)
    assert by_name(offers, "Домашни картофи").note == "Кешбек оферта"
    assert by_name(offers, "Colour Catcher").note == "Само с Billa App"


def test_brochure_validity_applied_to_every_offer():
    for o in parse(HTML):
        assert o.valid_from == date(2026, 11, 12)
        assert o.valid_to == date(2026, 11, 18)


def test_empty_page_raises_so_the_failure_is_visible():
    import pytest
    with pytest.raises(ValueError):
        parse("<html><body>nothing</body></html>")
