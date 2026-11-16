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


def test_filter_dropdowns_list_shops_and_categories_with_counts():
    html = render_digest(GROUPS, [], TODAY)
    assert '<select id="shop-filter"' in html and '<select id="group-filter"' in html
    assert '<option value="">Всички магазини</option>' in html
    assert '<option value="Lidl">Lidl (1)</option>' in html
    assert '<option value="Billa">Billa (1)</option>' in html
    assert '<option value="">Всички категории</option>' in html
    assert '<option value="Кафе">Кафе (2)</option>' in html


def test_offers_and_sections_carry_filter_attributes():
    html = render_digest(GROUPS, [], TODAY)
    assert 'data-group="Кафе"' in html
    assert html.count('data-shop="Lidl"') == 1 and html.count('data-shop="Billa"') == 1


def test_filter_attribute_values_are_escaped():
    groups = {'A"B': [Entry(make(), True)]}
    html = render_digest(groups, [], TODAY)
    assert 'data-group="A&#34;B"' in html


def test_no_filter_bar_when_there_is_nothing_to_filter():
    html = render_digest({}, [], TODAY)
    assert "shop-filter" not in html


def test_period_shows_start_and_end_in_html_and_summary():
    o = make(valid_from=date(2026, 11, 16))
    groups = {"Кафе": [Entry(o, True)]}
    assert "от 16.11 до 22.11" in render_digest(groups, [], TODAY)
    assert "от 16.11 до 22.11" in "\n".join(summary_messages(groups, [], TODAY))


def test_period_with_only_one_date():
    only_end = {"X": [Entry(make(), True)]}  # make() has valid_to only
    html = render_digest(only_end, [], TODAY)
    assert "до 22.11" in html and "от " not in html.split('class="meta"')[1].split("</div>")[0]
    only_start = {"X": [Entry(Offer(shop="Lidl", name="Y", price=1.0, valid_from=date(2026, 11, 16)), True)]}
    assert "от 16.11" in render_digest(only_start, [], TODAY)
    no_dates = {"X": [Entry(Offer(shop="Lidl", name="Z", price=1.0), True)]}
    meta = render_digest(no_dates, [], TODAY).split('class="meta"')[1].split("</div>")[0]
    assert "до" not in meta and "от " not in meta
