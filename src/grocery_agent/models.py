from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Offer:
    """One promotional product in one shop. Prices are in EUR."""

    shop: str
    name: str
    price: float
    old_price: float | None = None
    discount_pct: int | None = None
    unit: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    url: str | None = None
    image: str | None = None
    note: str | None = None  # e.g. "Само с Billa Card"
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def key(self) -> str:
        """Stable identity used to remember what was already reported."""
        raw = f"{self.shop}|{self.name.casefold()}|{self.price:.2f}|{self.valid_to or ''}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def pct(old: float | None, new: float) -> int | None:
    """Discount percentage computed from prices, or None when there is no old price."""
    if not old or old <= 0 or new >= old:
        return None
    return round((old - new) / old * 100)
