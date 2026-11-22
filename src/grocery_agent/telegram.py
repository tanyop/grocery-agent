from __future__ import annotations

import logging
import re

import httpx

log = logging.getLogger(__name__)


def parse_chat_ids(value: str | None) -> list[str]:
    """'111, 222 -333' -> ['111', '222', '-333'] (commas, semicolons and spaces separate; duplicates collapse)."""
    return list(dict.fromkeys(p for p in re.split(r"[,;\s]+", value or "") if p))


class Telegram:
    def __init__(self, token: str, chat_ids: str, client: httpx.Client | None = None):
        self._token = token
        self._chat_ids = parse_chat_ids(chat_ids)
        if not self._chat_ids:
            raise ValueError("at least one Telegram chat id is required")
        self._client = client or httpx.Client(timeout=60)

    def _call(self, method: str, chat_id: str, **kwargs) -> None:
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        try:
            r = self._client.post(url, **kwargs)
        except httpx.HTTPError as e:
            # never chain the original error: its request URL contains the bot token
            raise RuntimeError(f"Telegram {method} to {chat_id} failed: {type(e).__name__}") from None
        if r.status_code != 200:
            try:
                reason = r.json().get("description", "")
            except ValueError:
                reason = ""
            raise RuntimeError(f"Telegram {method} to {chat_id} failed: HTTP {r.status_code} {reason}".strip())

    def _to_everyone(self, method: str, build) -> None:
        """Send to every chat. One unreachable chat only logs a warning; if none can be reached, raise."""
        errors: list[str] = []
        for chat_id in self._chat_ids:
            try:
                self._call(method, chat_id, **build(chat_id))
            except RuntimeError as e:
                log.warning("%s", e)
                errors.append(str(e))
        if len(errors) == len(self._chat_ids):
            raise RuntimeError("; ".join(errors))

    def send_message(self, text: str) -> None:
        self._to_everyone(
            "sendMessage",
            lambda chat_id: {"json": {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}},
        )

    def send_document(self, filename: str, content: bytes, caption: str = "") -> None:
        self._to_everyone(
            "sendDocument",
            lambda chat_id: {
                "data": {"chat_id": chat_id, "caption": caption},
                "files": {"document": (filename, content, "text/html")},
            },
        )
