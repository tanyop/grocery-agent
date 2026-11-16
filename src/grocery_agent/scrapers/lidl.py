"""Lidl: every product tile carries its data as JSON in a data-grid-data attribute.

The homepage links to campaign pages (/c/<slug>/a<id>) and category pages
(/h/<slug>/h<id>); we open all of them and keep tiles whose category is "Food".
"""
from __future__ import annotations

import html as htmllib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from ..models import Offer
from .base import fetch

SHOP = "Lidl"
BASE = "https://www.lidl.bg"
SOFIA = ZoneInfo("Europe/Sofia")

log = logging.getLogger(__name__)

_TILE_RE = re.compile(r'data-grid-data="(.*?)"', re.S)
_LINK_RE = re.compile(r'href="(/(?:c/[^/"#?]+/a\d+|h/[^/"#?]+/h\d+|c/khrani-i-napitki/s\d+))(?:[?#][^"]*)?"')


def discover_links(home_html: str) -> list[str]:
    """Site-relative paths of the pages worth opening, in page order, without duplicates."""
    return list(dict.fromkeys(_LINK_RE.findall(home_html)))


def _day(ts: int | float | None) -> date | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(SOFIA).date()


def _tile_to_offer(d: dict) -> Offer | None:
    if d.get("category") != "Food":
        return None
    price = d.get("price") or {}
    value = price.get("price")
    if value is None:
        return None
    discount = price.get("discount") or {}
    old = price.get("oldPrice")
    pct = discount.get("percentageDiscount")
    image = d.get("image")
    if not isinstance(image, str):
        image = None
    path = d.get("canonicalPath")
    return Offer(
        shop=SHOP,
        name=" ".join((d.get("fullTitle") or d.get("title") or "").split()),
        price=float(value),
        old_price=float(old) if old else None,
        discount_pct=int(pct) if pct else None,
        unit=(price.get("packaging") or {}).get("text"),
        valid_from=_day(d.get("storeStartDate")),
        valid_to=_day(d.get("storeEndDate")),
        url=BASE + path if path else None,
        image=image,
    )


def parse(html: str) -> list[Offer]:
    """Food offers on one page. Returns [] for a page without product tiles."""
    seen: set = set()
    offers: list[Offer] = []
    for m in _TILE_RE.finditer(html):
        try:
            tile = json.loads(htmllib.unescape(m.group(1)))
        except json.JSONDecodeError:
            continue
        pid = tile.get("productId")
        if pid in seen:
            continue
        seen.add(pid)
        offer = _tile_to_offer(tile)
        if offer and offer.name:
            offers.append(offer)
    return offers


def scrape(
    client: httpx.Client, keywords: list[str] | None = None, workers: int = 4, pause: float = 0.2
) -> list[Offer]:
    home = fetch(client, BASE + "/")
    paths = discover_links(home)
    if not paths:
        raise ValueError("Lidl: no offer pages linked from the homepage - layout changed?")

    def one(path: str) -> list[Offer]:
        time.sleep(pause)
        try:
            return parse(fetch(client, BASE + path))
        except Exception as e:  # one bad page must not lose the others
            log.warning("Lidl page %s failed: %s", path, e)
            return []

    merged: dict[str, Offer] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for offers in pool.map(one, paths):
            for o in offers:
                merged.setdefault(o.url or o.name, o)
    if not merged:
        raise ValueError("Lidl: pages opened but no food offers found - layout changed?")
    return list(merged.values())
