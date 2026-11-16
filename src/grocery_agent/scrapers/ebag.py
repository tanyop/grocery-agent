"""eBag (online supermarket): the "Оферти" page loads its products from a JSON feed on ebag.bg itself.

The feed is paginated (20 products per page, about 4,000 offers) and gives, per product, the regular price,
the promo price, the discount percentage and the promo period - all in EUR (`*_eur` fields).
"""
from __future__ import annotations

import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import httpx

from ..models import Offer, pct
from .base import fetch

SHOP = "eBag"
BASE = "https://ebag.bg"
FEED = BASE + "/categories/offers-products/json?page={page}&mode=all_offers"
MAX_PAGES = 500  # safety net: the feed has about 205

log = logging.getLogger(__name__)


def parse_period(text: str | None) -> tuple[date | None, date | None]:
    """'12/11/2026 - 18/11/2026' -> (date(2026, 11, 12), date(2026, 11, 18)); (None, None) if unusable."""
    if not text:
        return None, None
    try:
        start, end = (datetime.strptime(part.strip(), "%d/%m/%Y").date() for part in text.split("-"))
    except ValueError:
        return None, None
    return start, end


def _money(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_item(item: dict) -> Offer | None:
    """One feed entry -> Offer, or None when it is not a genuine, buyable discount."""
    if not item.get("is_promo") or not item.get("is_available"):
        return None
    promo, regular = _money(item.get("price_promo_eur")), _money(item.get("price_eur"))
    if promo is None or regular is None or promo >= regular:
        return None
    name = " ".join(str(item.get("name") or "").split())
    if not name:
        return None
    pid, slug = item.get("id"), item.get("url_slug")
    valid_from, valid_to = parse_period(item.get("promo_period"))
    return Offer(
        shop=SHOP,
        name=name,
        price=promo,
        old_price=regular,
        discount_pct=item.get("discount_percent") or pct(regular, promo),
        unit=item.get("unit_weight_text") or None,
        valid_from=valid_from,
        valid_to=valid_to,
        url=f"{BASE}/{slug}/{pid}" if slug and pid else None,
        image=f"{BASE}/products/{pid}/images/0/800" if pid and item.get("image_count") else None,
    )


def _page(client: httpx.Client, number: int, attempts: int) -> dict:
    try:
        data = json.loads(fetch(client, FEED.format(page=number), attempts=attempts))
    except json.JSONDecodeError as e:
        raise ValueError(f"eBag: page {number} is not JSON - layout changed?") from e
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("eBag: unexpected feed format - layout changed?")
    return data


def scrape(
    client: httpx.Client,
    keywords: list[str] | None = None,  # unused: the whole feed is read
    workers: int = 3,
    pause: float = 0.25,
    attempts: int = 3,
) -> list[Offer]:
    first = _page(client, 1, attempts)
    results = first["results"]
    if not results:
        raise ValueError("eBag: the offers feed is empty - layout changed?")
    pages = min(MAX_PAGES, math.ceil(int(first.get("count") or len(results)) / len(results)))
    log.info("eBag: %s offers in %d pages", first.get("count"), pages)

    def one(number: int) -> list[dict]:
        time.sleep(pause)
        try:
            return _page(client, number, attempts)["results"]
        except Exception as e:  # one bad page must not lose the others
            log.warning("eBag page %d failed: %s", number, e)
            return []

    items = list(results)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for chunk in pool.map(one, range(2, pages + 1)):
            items.extend(chunk)

    seen: set = set()
    offers: list[Offer] = []
    for entry in items:
        if entry.get("id") in seen:
            continue
        seen.add(entry.get("id"))
        offer = parse_item(entry)
        if offer:
            offers.append(offer)
    return offers
