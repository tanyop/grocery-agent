"""Kaufland: offers are embedded as JSON (window.SSR[...]) in the all-offers page."""
from __future__ import annotations

import json
import re
from datetime import date

import httpx

from ..models import Offer
from .base import fetch

SHOP = "Kaufland"
URL = "https://www.kaufland.bg/aktualni-predlozheniya/oferti.html"

_SSR_RE = re.compile(r"window\.SSR\[[^\]]+\]\s*=\s*")


def _money(text: str | None) -> float | None:
    """'6,99 €' -> 6.99"""
    if not text:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", text)
    return float(m.group().replace(",", ".")) if m else None


def _date(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None


def _ssr_payload(html: str) -> dict:
    decoder = json.JSONDecoder()
    for m in _SSR_RE.finditer(html):
        try:
            obj, _ = decoder.raw_decode(html[m.end():])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "offerData" in obj.get("props", {}):
            return obj["props"]["offerData"]
    raise ValueError("Kaufland: embedded offer data not found - page layout changed?")


def parse(html: str) -> list[Offer]:
    data = _ssr_payload(html)
    seen: set[str] = set()
    offers: list[Offer] = []
    for cycle in data.get("cycles", []):
        for category in cycle.get("categories", []):
            for o in category.get("offers", []):
                oid = o.get("offerId")
                if oid in seen:
                    continue
                seen.add(oid)

                price = o.get("price")
                old = _money(o.get("formattedOldPrice"))
                discount = o.get("discount") or None
                note = None
                card_price = _money(o.get("loyaltyFormattedPrice"))
                if price is None:
                    if card_price is None:
                        continue  # nothing to compare
                    price, old = card_price, _money(o.get("loyaltyFormattedOldPrice"))
                    discount = round((old - price) / old * 100) if old and old > price else None
                    note = "Само с Kaufland Card"
                elif card_price is not None:
                    note = f"С Kaufland Card: {o['loyaltyFormattedPrice']}"

                name = " ".join(f"{o.get('title') or ''} {o.get('subtitle') or ''}".split())
                if not name:
                    continue
                offers.append(
                    Offer(
                        shop=SHOP,
                        name=name,
                        price=float(price),
                        old_price=old,
                        discount_pct=discount,
                        unit=o.get("unit") or None,
                        valid_from=_date(o.get("dateFrom")),
                        valid_to=_date(o.get("dateTo")),
                        url=URL,
                        image=o.get("listImage"),
                        note=note,
                    )
                )
    if not offers:
        raise ValueError("Kaufland: data found but no offers parsed - page layout changed?")
    return offers


def scrape(client: httpx.Client, keywords: list[str] | None = None) -> list[Offer]:
    return parse(fetch(client, URL))
