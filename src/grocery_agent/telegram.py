from __future__ import annotations

import httpx


class Telegram:
    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None):
        self._token = token
        self._chat_id = str(chat_id)
        self._client = client or httpx.Client(timeout=60)

    def _call(self, method: str, **kwargs) -> None:
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        try:
            r = self._client.post(url, **kwargs)
        except httpx.HTTPError as e:
            # never chain the original error: its request URL contains the bot token
            raise RuntimeError(f"Telegram {method} failed: {type(e).__name__}") from None
        if r.status_code != 200:
            try:
                reason = r.json().get("description", "")
            except ValueError:
                reason = ""
            raise RuntimeError(f"Telegram {method} failed: HTTP {r.status_code} {reason}".strip())

    def send_message(self, text: str) -> None:
        self._call("sendMessage", json={"chat_id": self._chat_id, "text": text, "disable_web_page_preview": True})

    def send_document(self, filename: str, content: bytes, caption: str = "") -> None:
        self._call(
            "sendDocument",
            data={"chat_id": self._chat_id, "caption": caption},
            files={"document": (filename, content, "text/html")},
        )
