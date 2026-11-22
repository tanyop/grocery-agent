from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .pipeline import Options, run
from .scrapers import billa, ebag, fantastico, kaufland, lidl
from .scrapers.base import make_client
from .telegram import Telegram
from .watchlist import load_watchlist

SCRAPERS = {"Lidl": lidl.scrape, "Kaufland": kaufland.scrape, "Billa": billa.scrape, "eBag": ebag.scrape, "Fantastico": fantastico.scrape}


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader for a local .env file (never committed)."""
    values: dict[str, str] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def extract_chat_ids(updates: dict) -> list[tuple[int, str]]:
    """(chat id, display name) for every chat that has written to the bot."""
    found: dict[int, str] = {}
    for update in updates.get("result", []):
        for part in update.values():
            chat = part.get("chat") if isinstance(part, dict) else None
            if chat and "id" in chat:
                name = chat.get("title") or chat.get("first_name") or chat.get("username") or ""
                found.setdefault(chat["id"], name)
    return list(found.items())


def _find_chat_id(token: str) -> int:
    try:
        r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
        data = r.json()
    except (httpx.HTTPError, ValueError):
        print("Could not reach Telegram (check the token).", file=sys.stderr)
        return 1
    if not data.get("ok"):
        print(f"Telegram refused the request: {data.get('description', r.status_code)}", file=sys.stderr)
        return 1
    chats = extract_chat_ids(data)
    if not chats:
        print("No messages found. Send any message to your bot in Telegram, then run this again.")
        return 1
    for chat_id, name in chats:
        print(f"TELEGRAM_CHAT_ID={chat_id}    ({name})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="grocery_agent", description="Daily supermarket promotions digest.")
    p.add_argument("--watchlist", default="watchlist.yaml", type=Path)
    p.add_argument("--state", default="state/seen.json", type=Path)
    p.add_argument("--out", default="out", type=Path, help="folder for digest.html")
    p.add_argument("--shops", default=",".join(SCRAPERS), help="comma separated: " + ", ".join(SCRAPERS))
    p.add_argument("--dry-run", action="store_true", help="scrape and write out/digest.html; send nothing, keep state")
    p.add_argument("--always", action="store_true", help="send even when nothing is new")
    p.add_argument("--all", dest="ignore_seen", action="store_true", help="treat every match as new")
    p.add_argument("--find-chat-id", action="store_true", help="print your Telegram chat id and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its request lines contain the bot token URL

    env = {**parse_env_file(".env"), **os.environ}
    token, chat_id = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")

    if args.find_chat_id:
        if not token:
            print("Set TELEGRAM_BOT_TOKEN first (env var or .env file).", file=sys.stderr)
            return 2
        return _find_chat_id(token)

    wanted = [s.strip() for s in args.shops.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in SCRAPERS]
    if unknown:
        parser.error(f"unknown shop(s): {', '.join(unknown)}; choose from {', '.join(SCRAPERS)}")

    sender = None
    if not args.dry_run:
        if not token or not chat_id:
            print("Missing TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID (env vars or .env file).", file=sys.stderr)
            return 2
        sender = Telegram(token, chat_id)

    items = load_watchlist(args.watchlist)
    client = make_client()
    keywords = [k for item in items for k in item.keywords]
    scrapers = {shop: (lambda s=SCRAPERS[shop]: s(client, keywords)) for shop in wanted}
    options = Options(
        out_dir=args.out,
        state_path=args.state,
        today=datetime.now(ZoneInfo("Europe/Sofia")).date(),
        dry_run=args.dry_run,
        always=args.always,
        ignore_seen=args.ignore_seen,
    )
    try:
        result = run(items, scrapers, options, sender)
    finally:
        client.close()

    print(
        f"matches: {result.match_count}, new: {result.new_count}, "
        f"failed shops: {', '.join(result.failed_shops) or 'none'}, sent: {result.sent}"
    )
    print(f"digest: {result.html_path}")
    return 1 if result.all_failed else 0


if __name__ == "__main__":
    sys.exit(main())
