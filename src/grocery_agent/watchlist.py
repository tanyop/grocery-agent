from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .models import Offer


@dataclass(frozen=True)
class WatchItem:
    name: str
    keywords: list[str]
    exclude: list[str] = field(default_factory=list)
    max_price: float | None = None


def _str_list(value, where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, (str, int, float)) for v in value):
        raise ValueError(f"{where} must be a list of words")
    return [str(v).strip() for v in value if str(v).strip()]


def load_watchlist(path: str | Path) -> list[WatchItem]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not raw_items or not isinstance(raw_items, list):
        raise ValueError(f"{path}: expected a non-empty 'items:' list")
    items: list[WatchItem] = []
    for i, raw in enumerate(raw_items, 1):
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            raise ValueError(f"{path}: item #{i} needs a 'name'")
        name = str(raw["name"]).strip()
        keywords = _str_list(raw.get("keywords"), f"{name}: keywords")
        if not keywords:
            raise ValueError(f"{path}: item '{name}' needs at least one keyword")
        if any(not k.rstrip("$") for k in keywords):
            raise ValueError(f"{path}: item '{name}' has an empty keyword")
        max_price = raw.get("max_price")
        if max_price is not None:
            try:
                max_price = float(max_price)
            except (TypeError, ValueError):
                raise ValueError(f"{path}: item '{name}' has a non-numeric max_price") from None
        items.append(WatchItem(name, keywords, _str_list(raw.get("exclude"), f"{name}: exclude"), max_price))
    return items


@lru_cache(maxsize=None)
def _pattern(word: str) -> re.Pattern[str]:
    """A keyword matches at the start of a word; a trailing '$' also requires the word to end there."""
    whole = word.endswith("$")
    core = word[:-1] if whole else word
    return re.compile(r"(?<!\w)" + re.escape(core.casefold()) + (r"(?!\w)" if whole else ""))


def _hit(offer: Offer, item: WatchItem) -> bool:
    text = offer.name.casefold()
    if not any(_pattern(k).search(text) for k in item.keywords):
        return False
    if any(_pattern(x).search(text) for x in item.exclude):
        return False
    return item.max_price is None or offer.price <= item.max_price


def match(offers: list[Offer], items: list[WatchItem]) -> dict[str, list[Offer]]:
    """Offers per watchlist item (cheapest first). Items with no hits are left out."""
    result: dict[str, list[Offer]] = {}
    for item in items:
        hits = sorted((o for o in offers if _hit(o, item)), key=lambda o: (o.price, o.shop, o.name))
        if hits:
            result[item.name] = hits
    return result
