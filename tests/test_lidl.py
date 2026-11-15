from datetime import date
from pathlib import Path

import pytest

from grocery_agent.scrapers.lidl import discover_links, parse

FIX = Path(__file__).parent / "fixtures"
CAMPAIGN = (FIX / "lidl_campaign.html").read_text(encoding="utf-8")
HOME = (FIX / "lidl_home.html").read_text(encoding="utf-8")


def test_only_food_tiles_and_no_duplicates():
    offers = parse(CAMPAIGN)
    # fixture: 3 food tiles + 1 non-food + 1 repeated food tile
    assert [o.name for o in offers] == [
        "Гурме бургери",
        "ПОРЦИЯ СВЕЖЕСТ Свински гърди",
        "Прясно филе от сьомга",
    ]


def test_prices_discount_unit_and_link():
    o = parse(CAMPAIGN)[0]
    assert (o.shop, o.price, o.old_price, o.discount_pct) == ("Lidl", 3.19, 3.83, 16)
    assert o.unit == "300 g/опаковка"
    assert o.url == "https://www.lidl.bg/p/gurme-burgeri/p11588589"
    assert o.image and o.image.startswith("https://www.lidl.bg/assets/")


def test_validity_uses_sofia_calendar_days():
    o = parse(CAMPAIGN)[0]
    # 2026-11-08T22:00Z .. 2026-12-06T21:59:59Z is 09 Nov .. 06 Dec in Sofia (UTC+2)
    assert (o.valid_from, o.valid_to) == (date(2026, 11, 9), date(2026, 12, 6))


def test_page_without_tiles_returns_empty_list():
    assert parse("<html><body>nothing</body></html>") == []


def test_discover_links_picks_campaigns_categories_and_food_page():
    links = discover_links(HOME)
    assert "/c/aktsiya/a10106189" in links
    assert any(l.startswith("/h/meso-i-mesni-delikatesi/") for l in links)
    assert any(l.startswith("/c/khrani-i-napitki/") for l in links)


def test_discover_links_dedupes_and_ignores_assets_and_info_pages():
    links = discover_links(HOME)
    assert len(links) == len(set(links))
    assert not any("assets" in l for l in links)
    assert not any(l.startswith("/c/lidl-impresum") for l in links)
