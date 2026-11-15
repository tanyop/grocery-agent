"""Remembers which offers were already reported so each one is announced once."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .models import Offer

UNDATED_KEEP_DAYS = 7


class State:
    def __init__(self, seen: dict[str, str]):
        self._seen = seen  # offer key -> last day to remember it (ISO date)

    @classmethod
    def load(cls, path: str | Path) -> "State":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            seen = data["seen"]
            if not isinstance(seen, dict):
                raise TypeError
            return cls({str(k): str(v) for k, v in seen.items()})
        except (OSError, ValueError, KeyError, TypeError):
            return cls({})

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"seen": dict(sorted(self._seen.items()))}, indent=1), encoding="utf-8")

    def is_new(self, offer: Offer) -> bool:
        return offer.key not in self._seen

    def remember(self, offers: list[Offer], today: date | None = None) -> None:
        today = today or date.today()
        for o in offers:
            expiry = o.valid_to or today + timedelta(days=UNDATED_KEEP_DAYS)
            self._seen[o.key] = expiry.isoformat()

    def prune(self, today: date) -> None:
        self._seen = {k: v for k, v in self._seen.items() if v >= today.isoformat()}
