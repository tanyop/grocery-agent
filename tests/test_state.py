from datetime import date

from grocery_agent.models import Offer
from grocery_agent.state import State

TODAY = date(2026, 11, 15)


def offer(name="Мляко", price=1.0, valid_to=date(2026, 11, 18)):
    return Offer(shop="Lidl", name=name, price=price, valid_to=valid_to)


def test_unseen_offers_are_new_and_seen_ones_are_not():
    state = State({})
    a, b = offer("A"), offer("B")
    state.remember([a])
    assert state.is_new(a) is False
    assert state.is_new(b) is True


def test_same_product_in_a_new_week_or_at_a_new_price_is_new_again():
    state = State({})
    state.remember([offer()])
    assert state.is_new(offer(valid_to=date(2026, 11, 25))) is True
    assert state.is_new(offer(price=0.9)) is True


def test_prune_drops_expired_entries_only():
    state = State({})
    old, current = offer("old", valid_to=date(2026, 11, 10)), offer("cur", valid_to=date(2026, 11, 18))
    state.remember([old, current])
    state.prune(TODAY)
    assert state.is_new(old) is True
    assert state.is_new(current) is False


def test_offer_without_end_date_is_pruned_after_a_week():
    state = State({})
    undated = Offer(shop="Billa", name="X", price=1.0)
    state.remember([undated], today=TODAY)
    state.prune(date(2026, 11, 20))
    assert state.is_new(undated) is False
    state.prune(date(2026, 11, 23))
    assert state.is_new(undated) is True


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "state" / "seen.json"
    state = State({})
    state.remember([offer()])
    state.save(path)
    assert State.load(path).is_new(offer()) is False


def test_load_missing_or_corrupt_file_gives_empty_state(tmp_path):
    assert State.load(tmp_path / "nope.json").is_new(offer()) is True
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert State.load(bad).is_new(offer()) is True
