"""Billa: the accessible text version of the weekly brochure (ssbbilla.site)."""
from __future__ import annotations

import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from ..models import Offer
from .base import fetch

SHOP = "Billa"
URL = "https://ssbbilla.site/"

LABELS = ("Супер цена", "Сега в Billa", "Само с Billa Card", "Кешбек оферта", "Само с Billa App")
_LABEL_RE = re.compile(r"^(" + "|".join(map(re.escape, LABELS)) + r")\s+-\s+")
_VALIDITY_RE = re.compile(
    r"Валидност:\s*от\s+(?:\S+\s+)?(\d{1,2})\.(\d{1,2})\.\s*до\s+(?:\S+\s+)?(\d{1,2})\.(\d{1,2})\.(\d{4})"
)


def _validity(text: str) -> tuple[date | None, date | None]:
    m = _VALIDITY_RE.search(text)
    if not m:
        return None, None
    d1, m1, d2, m2, year = map(int, m.groups())
    start_year = year - 1 if m1 > m2 else year
    return date(start_year, m1, d1), date(year, m2, d2)


def _num(text: str) -> float:
    return float(text.replace(",", ".").strip())


def parse(html: str) -> list[Offer]:
    soup = BeautifulSoup(html, "lxml")
    blocks = soup.select("div.product")
    if not blocks:
        raise ValueError("Billa: no product blocks found - page layout changed?")

    valid_from = valid_to = None
    offers: list[Offer] = []
    for block in blocks:
        name_el = block.select_one(".actualProduct")
        if name_el is None:
            continue
        text = " ".join(name_el.get_text(" ", strip=True).split())
        if valid_from is None:
            valid_from, valid_to = _validity(" ".join(name_el.get_text(" ").split()))

        euros: list[float] = []
        pct: int | None = None
        for price_el in block.select("span.price"):
            value = price_el.get_text(strip=True)
            currency = price_el.find_next_sibling("span", class_="currency")
            cur = currency.get_text(strip=True) if currency else ""
            if value.endswith("%"):
                pct = int(value.rstrip("%"))
            elif cur == "€":
                euros.append(_num(value))
        if not euros:
            continue

        note = None
        m = _LABEL_RE.match(text)
        if m:
            note, text = m.group(1), text[m.end():]
        price = euros[-1]
        old = euros[0] if len(euros) > 1 else None
        if pct is None and old:
            pct = round((old - price) / old * 100) if old > price else None
        offers.append(Offer(SHOP, text, price, old, pct, None, valid_from, valid_to, URL, None, note))

    # brochure-level validity is found while walking; apply it to every offer
    offers = [
        Offer(o.shop, o.name, o.price, o.old_price, o.discount_pct, o.unit, valid_from, valid_to, o.url, o.image, o.note)
        for o in offers
    ]
    if not offers:
        raise ValueError("Billa: page parsed but no priced offers found - page layout changed?")
    return offers


def scrape(client: httpx.Client) -> list[Offer]:
    return parse(fetch(client, URL))
