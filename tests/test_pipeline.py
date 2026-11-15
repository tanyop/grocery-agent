from datetime import date

import pytest

from grocery_agent.models import Offer
from grocery_agent.pipeline import Options, run
from grocery_agent.state import State
from grocery_agent.watchlist import WatchItem

TODAY = date(2026, 11, 15)
ITEMS = [WatchItem("Мляко", ["мляко"])]


def offer(name="Прясно мляко", price=1.2, shop="Lidl", valid_to=date(2026, 11, 22)):
    return Offer(shop=shop, name=name, price=price, valid_to=valid_to)


class FakeTelegram:
    def __init__(self, fail=False):
        self.messages, self.documents, self.fail = [], [], fail

    def send_message(self, text):
        if self.fail:
            raise RuntimeError("telegram down")
        self.messages.append(text)

    def send_document(self, filename, content, caption=""):
        self.documents.append((filename, content.decode("utf-8")))


def scrapers(**by_shop):
    def make(value):
        def scrape():
            if isinstance(value, Exception):
                raise value
            return value
        return scrape
    return {shop: make(v) for shop, v in by_shop.items()}


def opts(tmp_path, **kw):
    return Options(out_dir=tmp_path / "out", state_path=tmp_path / "seen.json", today=TODAY, **kw)


def test_new_offer_is_sent_with_summary_and_html_and_remembered(tmp_path):
    tg = FakeTelegram()
    result = run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path), tg)
    assert result.sent and result.new_count == 1
    assert "Прясно мляко" in tg.messages[0]
    assert tg.documents[0][0].endswith(".html") and "Прясно мляко" in tg.documents[0][1]
    assert (tmp_path / "out" / "digest.html").exists()
    assert State.load(tmp_path / "seen.json").is_new(offer()) is False


def test_second_run_with_nothing_new_sends_nothing(tmp_path):
    run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path), FakeTelegram())
    tg = FakeTelegram()
    result = run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path), tg)
    assert not result.sent and tg.messages == [] and tg.documents == []


def test_always_flag_sends_even_without_news(tmp_path):
    run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path), FakeTelegram())
    tg = FakeTelegram()
    result = run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path, always=True), tg)
    assert result.sent and tg.documents


def test_ignore_seen_marks_everything_new(tmp_path):
    run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path), FakeTelegram())
    tg = FakeTelegram()
    result = run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path, ignore_seen=True), tg)
    assert result.sent and result.new_count == 1


def test_expired_offers_are_dropped(tmp_path):
    tg = FakeTelegram()
    result = run(ITEMS, scrapers(Lidl=[offer(valid_to=date(2026, 11, 14))]), opts(tmp_path), tg)
    assert not result.sent and result.new_count == 0


def test_one_failing_shop_does_not_stop_the_others_and_is_reported(tmp_path):
    tg = FakeTelegram()
    result = run(ITEMS, scrapers(Lidl=RuntimeError("blocked"), Billa=[offer(shop="Billa")]), opts(tmp_path), tg)
    assert result.failed_shops == ["Lidl"]
    assert result.sent and result.new_count == 1
    assert "Lidl" in tg.messages[0]
    assert not result.all_failed


def test_all_shops_failing_is_flagged_and_still_notifies(tmp_path):
    tg = FakeTelegram()
    result = run(ITEMS, scrapers(Lidl=RuntimeError("x"), Billa=RuntimeError("y")), opts(tmp_path), tg)
    assert result.all_failed and result.sent
    assert "Lidl" in tg.messages[0] and "Billa" in tg.messages[0]


def test_dry_run_writes_html_but_sends_nothing_and_keeps_state(tmp_path):
    result = run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path, dry_run=True), None)
    assert not result.sent and (tmp_path / "out" / "digest.html").exists()
    assert not (tmp_path / "seen.json").exists()


def test_failed_send_does_not_mark_offers_as_seen(tmp_path):
    with pytest.raises(RuntimeError):
        run(ITEMS, scrapers(Lidl=[offer()]), opts(tmp_path), FakeTelegram(fail=True))
    assert State.load(tmp_path / "seen.json").is_new(offer()) is True


def test_unmatched_offers_are_not_reported(tmp_path):
    tg = FakeTelegram()
    result = run(ITEMS, scrapers(Lidl=[offer("Дамски чорапи")]), opts(tmp_path), tg)
    assert not result.sent
