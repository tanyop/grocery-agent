from __future__ import annotations

from datetime import date
from typing import NamedTuple

from jinja2 import Environment, PackageLoader, select_autoescape

from .models import Offer


class Entry(NamedTuple):
    offer: Offer
    is_new: bool


def money(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}".replace(".", ",") + " €"


def short_date(d: date | None) -> str:
    return d.strftime("%d.%m") if d else ""


def period(o: Offer) -> str:
    """'от 16.11 до 22.11', or just one side when the other date is unknown."""
    if o.valid_from and o.valid_to:
        return f"от {short_date(o.valid_from)} до {short_date(o.valid_to)}"
    if o.valid_to:
        return f"до {short_date(o.valid_to)}"
    if o.valid_from:
        return f"от {short_date(o.valid_from)}"
    return ""


_env = Environment(loader=PackageLoader("grocery_agent", "templates"), autoescape=select_autoescape(["html", "j2"]))
_env.filters["money"] = money
_env.filters["short_date"] = short_date
_env.filters["period"] = period


def render_digest(groups: dict[str, list[Entry]], failed_shops: list[str], today: date) -> str:
    new_count = sum(e.is_new for entries in groups.values() for e in entries)
    shop_counts: dict[str, int] = {}
    for entries in groups.values():
        for e in entries:
            shop_counts[e.offer.shop] = shop_counts.get(e.offer.shop, 0) + 1
    return _env.get_template("digest.html.j2").render(
        groups=groups,
        failed_shops=failed_shops,
        today=today,
        new_count=new_count,
        shop_counts=dict(sorted(shop_counts.items())),
    )
