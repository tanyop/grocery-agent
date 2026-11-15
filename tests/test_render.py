from datetime import date

from grocery_agent.models import Offer
from grocery_agent.render import Entry, render_digest, summary_messages

TODAY = date(2026, 11, 15)


def make(name="Lavazza кафе 250 г", price=6.99, shop="Lidl", **kw):
    return Offer(shop=shop, name=name, price=price, valid_to=date(2026, 11, 22), **kw)


GROUPS = {
    "Кафе": [
        Entry(make(old_price=8.74, discount_pct=20, url="https://www.lidl.bg/p/x/p1"), True),
        Entry(make("Jacobs кафе", 7.5, "Billa", note="Само с Billa Card"), False),
    ]
}


def test_html_has_items_prices_shops_and_new_marker():
    html = render_digest(GROUPS, [], TODAY)
    assert "<html" in html and 'name="viewport"' in html
    assert "Кафе" in html and "Lavazza кафе 250 г" in html
    assert "6,99 €" in html and "8,74 €" in html and "-20%" in html
    assert "до 22.11" in html
    assert "Само с Billa Card" in html
    assert "https://www.lidl.bg/p/x/p1" in html
    assert html.count("class=\"new\"") == 1


def test_html_escapes_product_names():
    groups = {"X": [Entry(make("<script>alert(1)</script>"), True)]}
    html = render_digest(groups, [], TODAY)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_lists_failed_shops_and_empty_state():
    html = render_digest({}, ["Lidl"], TODAY)
    assert "Lidl" in html and "не можа да бъде прочетен" in html
    assert "Няма промоции" in html


def test_summary_lists_only_new_offers():
    msgs = summary_messages(GROUPS, [], TODAY)
    text = "\n".join(msgs)
    assert "Lavazza" in text and "6,99 €" in text and "-20%" in text
    assert "Jacobs" not in text  # already reported earlier


def test_summary_mentions_failures():
    text = "\n".join(summary_messages({}, ["Kaufland"], TODAY))
    assert "Kaufland" in text


def test_summary_is_split_below_telegram_limit():
    groups = {"Много": [Entry(make(f"Продукт номер {i} " + "х" * 60, 1.0 + i), True) for i in range(200)]}
    msgs = summary_messages(groups, [], TODAY)
    assert len(msgs) > 1
    assert all(len(m) <= 4096 for m in msgs)
    assert sum(m.count("Продукт номер") for m in msgs) == 200
