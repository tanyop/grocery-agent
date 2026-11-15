# grocery-agent

Every day it reads the current promotions of **Lidl, Kaufland and Billa** (Bulgaria), keeps only the products on your
`watchlist.yaml`, builds a phone-friendly `digest.html`, and sends it to you on **Telegram**: a short text with
the *new* matches, plus the full HTML file.

Offers change weekly, so the daily run only messages you when something new matches (or a shop could not be read).

Fantastico is not included: its site refuses automated requests (HTTP 403) and publishes brochures only.

## One-time setup

1. **Create the bot.** In Telegram open `@BotFather`, send `/newbot`, copy the token.
2. **Write to your bot.** Open the new bot and send it any message (for example "hi").
3. **Find your chat id** (token goes in a local `.env` file, which git ignores):
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   ```
   then run `python -m grocery_agent --find-chat-id` and copy the printed `TELEGRAM_CHAT_ID=...` into `.env` too.
4. **Edit `watchlist.yaml`** with the products you buy.

## Run locally

```
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"          # Windows; on Linux/macOS: .venv/bin/pip
.venv\Scripts\python -m grocery_agent --dry-run   # scrape + write out/digest.html, send nothing
.venv\Scripts\python -m grocery_agent             # the real thing: sends to Telegram
```

Flags: `--always` send even if nothing is new, `--all` treat every match as new, `--shops Lidl,Billa`,
`--watchlist`, `--state`, `--out`. Tests: `.venv\Scripts\python -m pytest`.

## Run daily in the cloud (GitHub Actions)

1. Push this folder to a GitHub repository (private is fine).
2. Repository **Settings → Secrets and variables → Actions → New repository secret**: add `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_CHAT_ID`.
3. **Actions → daily-promotions → Run workflow** to test it once. After that it runs every day at 05:00 UTC.

The workflow commits `state/seen.json` (the offers already reported) back to the repo, which also keeps GitHub
from pausing the schedule after 60 days of inactivity. If a shop ever blocks GitHub's servers, run the same command
on your own PC with Windows Task Scheduler instead.

## How it works

| Shop | Source |
|---|---|
| Billa | text version of the weekly brochure, `ssbbilla.site` |
| Kaufland | offer JSON embedded in the all-offers page |
| Lidl | product tiles (`data-grid-data`) on campaign and category pages found from the homepage |

If a site changes its layout, that shop's scraper fails on its own, the digest says which shop could not be read,
and the other shops still arrive. Parsers are tested against trimmed snapshots in `tests/fixtures/`.
