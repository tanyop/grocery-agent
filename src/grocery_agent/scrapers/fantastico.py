"""Fantastico: official daily price data published by the consumer protection commission (КЗП).

kolkostruva.bg/opendata offers one zip per day with a CSV for every retail chain that reports prices.
Fantastico's files list, per store, the regular price and (when on promotion) the promotion price.
There are no validity dates, and the newest zip is for the previous day.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from urllib.parse import urljoin

import httpx

from ..models import Offer, pct
from .base import fetch, fetch_bytes

SHOP = "Fantastico"
OPENDATA_URL = "https://kolkostruva.bg/opendata"
MAX_MEMBER_BYTES = 100 * 1024 * 1024  # refuse suspiciously large files inside the zip

COL_NAME = "Наименование на продукта"
COL_CODE = "Код на продукта"
COL_REGULAR = "Цена на дребно"
COL_PROMO = "Цена в промоция"

_ZIP_RE = re.compile(r"/opendata_files/(\d{4}-\d{2}-\d{2})\.zip")
_UNITS = {"гр", "г", "кг", "мл", "л", "бр", "см"}
_HAS_CYRILLIC = re.compile(r"[А-Яа-я]")

log = logging.getLogger(__name__)


def latest_zip_url(opendata_html: str) -> str:
    dates = _ZIP_RE.findall(opendata_html)
    if not dates:
        raise ValueError("Fantastico: no data archives listed on kolkostruva.bg/opendata - layout changed?")
    return urljoin(OPENDATA_URL, f"/opendata_files/{max(dates)}.zip")


def tidy_name(name: str) -> str:
    """ALL-CAPS names become Title Case; Latin brands, numbers and units keep a sensible form."""
    name = " ".join(name.split())
    if name != name.upper():
        return name  # already written normally
    words = []
    for token in name.split(" "):
        if not _HAS_CYRILLIC.search(token):
            words.append(token)
        elif token.lower() in _UNITS:
            words.append(token.lower())
        else:
            words.append(token.title())
    return " ".join(words)


def _price(text: str | None) -> float | None:
    try:
        value = float((text or "").strip().replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


def parse_csv(text: str) -> list[Offer]:
    reader = csv.DictReader(io.StringIO(text))
    missing = {COL_NAME, COL_CODE, COL_REGULAR, COL_PROMO} - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Fantastico: missing CSV columns {sorted(missing)} - format changed?")

    names: dict[str, str] = {}
    prices: dict[str, Counter] = defaultdict(Counter)
    for row in reader:
        regular, promo = _price(row[COL_REGULAR]), _price(row[COL_PROMO])
        if regular is None or promo is None or promo >= regular:
            continue
        code = row[COL_CODE]
        names.setdefault(code, row[COL_NAME])
        prices[code][(regular, promo)] += 1

    offers = []
    for code, counter in prices.items():
        # the promotion is chain-wide; if stores disagree, the most common pair wins (cheaper on a tie)
        (regular, promo), _ = min(counter.items(), key=lambda kv: (-kv[1], kv[0][1]))
        offers.append(Offer(SHOP, tidy_name(names[code]), promo, regular, pct(regular, promo)))
    return offers


def scrape(client: httpx.Client, keywords: list[str] | None = None) -> list[Offer]:
    zip_url = latest_zip_url(fetch(client, OPENDATA_URL))
    try:
        archive = zipfile.ZipFile(io.BytesIO(fetch_bytes(client, zip_url)))
    except zipfile.BadZipFile as e:
        raise ValueError("Fantastico: the downloaded archive is not a zip - layout changed?") from e

    members = [
        i for i in archive.infolist()
        if PurePosixPath(i.filename).name.casefold().startswith("фантастико")
        and i.filename.casefold().endswith(".csv")
        and i.file_size <= MAX_MEMBER_BYTES
    ]
    if not members:
        raise ValueError("Fantastico: no Fantastico file in the archive - layout changed?")

    merged: dict[tuple[str, float], Offer] = {}
    for info in members:
        for offer in parse_csv(archive.read(info).decode("utf-8-sig")):
            merged.setdefault((offer.name.casefold(), offer.price), offer)
    if not merged:
        raise ValueError("Fantastico: file read but no promotions found - format changed?")
    log.info("Fantastico: %d promotions from %s", len(merged), zip_url.rsplit("/", 1)[-1])
    return list(merged.values())
