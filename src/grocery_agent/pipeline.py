from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

from .models import Offer
from .render import Entry, render_digest
from .state import State
from .watchlist import WatchItem, match

log = logging.getLogger(__name__)


class Sender(Protocol):
    def send_document(self, filename: str, content: bytes, caption: str = "") -> None: ...


@dataclass
class Options:
    out_dir: Path
    state_path: Path
    today: date
    dry_run: bool = False
    always: bool = False  # send even when nothing is new
    ignore_seen: bool = False  # treat every match as new


@dataclass
class Result:
    sent: bool = False
    new_count: int = 0
    failed_shops: list[str] = field(default_factory=list)
    all_failed: bool = False
    html_path: Path | None = None
    match_count: int = 0


def run(
    items: list[WatchItem],
    scrapers: dict[str, Callable[[], list[Offer]]],
    options: Options,
    sender: Sender | None,
) -> Result:
    result = Result()

    offers: list[Offer] = []
    for shop, scrape in scrapers.items():
        try:
            got = scrape()
        except Exception as e:  # a broken shop must not hide the others
            log.error("%s failed: %s: %s", shop, type(e).__name__, e)
            result.failed_shops.append(shop)
            continue
        log.info("%s: %d offers", shop, len(got))
        offers.extend(got)
    result.all_failed = bool(scrapers) and len(result.failed_shops) == len(scrapers)

    active = [o for o in offers if o.valid_to is None or o.valid_to >= options.today]
    matched = match(active, items)

    state = State.load(options.state_path)
    groups = {
        name: [Entry(o, options.ignore_seen or state.is_new(o)) for o in hits]
        for name, hits in matched.items()
    }
    result.new_count = sum(e.is_new for entries in groups.values() for e in entries)
    result.match_count = sum(len(v) for v in groups.values())

    html = render_digest(groups, result.failed_shops, options.today)
    options.out_dir.mkdir(parents=True, exist_ok=True)
    result.html_path = options.out_dir / "digest.html"
    result.html_path.write_text(html, encoding="utf-8")

    if options.dry_run:
        return result

    if sender is None:
        raise ValueError("a sender is required unless dry_run is set")

    if result.new_count or result.failed_shops or options.always:
        # only the HTML file is sent: failed shops and "nothing matched" are already explained inside it
        sender.send_document(f"promocii-{options.today:%Y-%m-%d}.html", html.encode("utf-8"))
        result.sent = True

    # only reached when sending (if any) succeeded, so a failed send is retried next run
    state.remember([e.offer for entries in groups.values() for e in entries], options.today)
    state.prune(options.today)
    state.save(options.state_path)
    return result
