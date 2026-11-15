from __future__ import annotations

from datetime import date
from typing import NamedTuple

from jinja2 import Environment, PackageLoader, select_autoescape

from .models import Offer

TELEGRAM_LIMIT = 4000  # real limit is 4096; keep a margin


class Entry(NamedTuple):
    offer: Offer
    is_new: bool


def money(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}".replace(".", ",") + " €"


def short_date(d: date | None) -> str:
    return d.strftime("%d.%m") if d else ""


_env = Environment(loader=PackageLoader("grocery_agent", "templates"), autoescape=select_autoescape(["html", "j2"]))
_env.filters["money"] = money
_env.filters["short_date"] = short_date


def render_digest(groups: dict[str, list[Entry]], failed_shops: list[str], today: date) -> str:
    new_count = sum(e.is_new for entries in groups.values() for e in entries)
    return _env.get_template("digest.html.j2").render(
        groups=groups, failed_shops=failed_shops, today=today, new_count=new_count
    )


def _line(o: Offer) -> str:
    parts = [f"• {o.shop} · {o.name} — {money(o.price)}"]
    if o.discount_pct:
        parts.append(f"(-{o.discount_pct}%)")
    if o.valid_to:
        parts.append(f"до {short_date(o.valid_to)}")
    if o.note:
        parts.append(f"[{o.note}]")
    return " ".join(parts)


def summary_messages(groups: dict[str, list[Entry]], failed_shops: list[str], today: date) -> list[str]:
    """Plain-text Telegram messages: only NEW offers, split under the message size limit."""
    lines: list[str] = []
    new_total = 0
    for item, entries in groups.items():
        new = [e.offer for e in entries if e.is_new]
        if not new:
            continue
        new_total += len(new)
        lines.append("")
        lines.append(f"▪ {item}")
        lines.extend(_line(o) for o in new)

    header = f"🛒 Промоции {today:%d.%m.%Y}"
    header += f" — {new_total} нови от списъка ти" if new_total else ""
    out = [header]
    if failed_shops:
        out.append("⚠ Не можах да прочета: " + ", ".join(failed_shops))
    lines = out + lines

    messages: list[str] = []
    current = ""
    for line in lines:
        if current and len(current) + len(line) + 1 > TELEGRAM_LIMIT:
            messages.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current:
        messages.append(current)
    return messages
