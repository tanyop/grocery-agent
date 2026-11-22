from __future__ import annotations

import time

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "bg,en;q=0.7"},
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
    )


def _get(client: httpx.Client, url: str, attempts: int, backoff: float) -> httpx.Response:
    """GET with retries on network errors and 5xx. 4xx fails at once."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            r = client.get(url)
            if r.status_code < 500:
                r.raise_for_status()
                return r
            last = httpx.HTTPStatusError(f"{r.status_code} for {url}", request=r.request, response=r)
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as e:
            last = e
        if i < attempts - 1:
            time.sleep(backoff * (i + 1))
    assert last is not None
    raise last


def fetch(client: httpx.Client, url: str, attempts: int = 3, backoff: float = 2.0) -> str:
    """GET a page as text."""
    return _get(client, url, attempts, backoff).text


def fetch_bytes(client: httpx.Client, url: str, attempts: int = 3, backoff: float = 2.0) -> bytes:
    """GET a file (for example a zip) as bytes."""
    return _get(client, url, attempts, backoff).content
