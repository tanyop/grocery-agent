from datetime import date

import pytest

from grocery_agent import __main__ as cli
from grocery_agent.models import Offer

WATCH = "items:\n  - name: Мляко\n    keywords: [мляко]\n"


def test_parse_env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# comment\nTELEGRAM_BOT_TOKEN=abc:123\nTELEGRAM_CHAT_ID = "42"\n\nBAD LINE\n', encoding="utf-8")
    assert cli.parse_env_file(f) == {"TELEGRAM_BOT_TOKEN": "abc:123", "TELEGRAM_CHAT_ID": "42"}
    assert cli.parse_env_file(tmp_path / "missing") == {}


def test_extract_chat_ids_from_updates():
    updates = {
        "ok": True,
        "result": [
            {"message": {"chat": {"id": 111, "first_name": "Ана", "type": "private"}}},
            {"message": {"chat": {"id": 111, "first_name": "Ана", "type": "private"}}},
            {"my_chat_member": {"chat": {"id": -5, "title": "Група", "type": "group"}}},
            {"edited_message": {"chat": {"id": 222, "username": "bob", "type": "private"}}},
        ],
    }
    assert cli.extract_chat_ids(updates) == [(111, "Ана"), (-5, "Група"), (222, "bob")]


def test_main_dry_run_end_to_end_with_fake_shop(tmp_path, monkeypatch):
    w = tmp_path / "w.yaml"
    w.write_text(WATCH, encoding="utf-8")
    fake = lambda client: [Offer("Lidl", "Прясно мляко", 1.2, valid_to=date(2099, 1, 1))]
    monkeypatch.setattr(cli, "SCRAPERS", {"Lidl": fake})
    code = cli.main(["--dry-run", "--watchlist", str(w), "--out", str(tmp_path / "out"), "--state", str(tmp_path / "s.json")])
    assert code == 0
    assert "Прясно мляко" in (tmp_path / "out" / "digest.html").read_text(encoding="utf-8")
    assert not (tmp_path / "s.json").exists()


def test_main_without_telegram_credentials_fails_clearly(tmp_path, monkeypatch, capsys):
    w = tmp_path / "w.yaml"
    w.write_text(WATCH, encoding="utf-8")
    monkeypatch.setattr(cli, "SCRAPERS", {"Lidl": lambda client: []})
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    code = cli.main(["--watchlist", str(w), "--out", str(tmp_path / "o"), "--state", str(tmp_path / "s.json")])
    assert code == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_unknown_shop_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["--shops", "Nope", "--dry-run"])
