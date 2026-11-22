import pytest

from grocery_agent.models import Offer
from grocery_agent.watchlist import WatchItem, load_watchlist, match


def offer(name, price=2.0, shop="Lidl"):
    return Offer(shop=shop, name=name, price=price)


def test_stem_keyword_matches_bulgarian_word_endings_case_insensitively():
    items = [WatchItem("Пилешко", ["пилешк"])]
    hits = match([offer("Прясно ПИЛЕШКО бутче"), offer("Пилешки крила"), offer("Свинско месо")], items)
    assert {o.name for o in hits["Пилешко"]} == {"Прясно ПИЛЕШКО бутче", "Пилешки крила"}


def test_latin_brand_keywords_match():
    hits = match([offer("Lavazza Qualità Rossa 250 г")], [WatchItem("Кафе", ["lavazza"])])
    assert len(hits["Кафе"]) == 1


def test_exclude_removes_offers():
    items = [WatchItem("Кафе", ["кафе"], exclude=["капсули"])]
    hits = match([offer("Кафе на зърна"), offer("Кафе капсули Dolce Gusto")], items)
    assert [o.name for o in hits["Кафе"]] == ["Кафе на зърна"]


def test_max_price_filters_expensive_offers():
    items = [WatchItem("Кафе", ["кафе"], max_price=8.0)]
    hits = match([offer("Кафе A", 7.99), offer("Кафе B", 8.0), offer("Кафе C", 9.5)], items)
    assert [o.name for o in hits["Кафе"]] == ["Кафе A", "Кафе B"]


def test_results_sorted_cheapest_first_and_items_without_hits_are_omitted():
    items = [WatchItem("Мляко", ["мляко"]), WatchItem("Сьомга", ["сьомга"])]
    hits = match([offer("Прясно мляко", 1.5, "Billa"), offer("Прясно мляко", 1.2, "Lidl")], items)
    assert [o.price for o in hits["Мляко"]] == [1.2, 1.5]
    assert "Сьомга" not in hits


def test_one_offer_can_match_several_items():
    items = [WatchItem("Сирене", ["сирене"]), WatchItem("Козе", ["козе"])]
    hits = match([offer("Козе сирене")], items)
    assert len(hits["Сирене"]) == len(hits["Козе"]) == 1


def test_load_watchlist(tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text(
        "items:\n  - name: Кафе\n    keywords: [кафе, lavazza]\n    exclude: [капсули]\n    max_price: 8.5\n"
        "  - name: Пилешко\n    keywords: [пилешк]\n",
        encoding="utf-8",
    )
    items = load_watchlist(f)
    assert items[0] == WatchItem("Кафе", ["кафе", "lavazza"], ["капсули"], 8.5)
    assert items[1] == WatchItem("Пилешко", ["пилешк"], [], None)


@pytest.mark.parametrize(
    "text",
    [
        "items: []\n",
        "items:\n  - name: X\n    keywords: []\n",
        "items:\n  - keywords: [a]\n",
        "items:\n  - name: X\n    keywords: [a]\n    max_price: abc\n",
        "nothing: here\n",
    ],
)
def test_invalid_watchlist_gives_clear_error(tmp_path, text):
    f = tmp_path / "w.yaml"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_watchlist(f)


def names(hits, item):
    return [o.name for o in hits.get(item, [])]


def test_keyword_matches_only_at_the_start_of_a_word():
    items = [WatchItem("Лук", ["лук"])]
    hits = match([offer("Червен лук"), offer("Лукът е здраве"), offer("Кош за боклук"), offer("Печени ядки Делукс")], items)
    assert set(names(hits, "Лук")) == {"Червен лук", "Лукът е здраве"}


def test_keyword_at_word_start_works_after_punctuation_and_at_name_start():
    items = [WatchItem("Домати", ["домат"])]
    hits = match([offer("Домати Рома"), offer("Салата (домати, краставици)"), offer("Пюре-домат")], items)
    assert len(hits["Домати"]) == 3


def test_dollar_suffix_requires_a_whole_word():
    items = [WatchItem("Зеле", ["зеле$"])]
    hits = match([offer("Зеле"), offer("Бяло зеле, кг"), offer("Зелени маслини"), offer("Зелето е здраво")], items)
    assert {o.name for o in hits["Зеле"]} == {"Зеле", "Бяло зеле, кг"}


def test_exclude_also_works_on_word_starts_not_inside_words():
    items = [WatchItem("Круши", ["круш"], exclude=["бар"])]
    hits = match([offer("Бар с круши"), offer("Круши Уилямс"), offer("Крушови барчета")], items)
    # "Бар с круши" excluded (word "бар"); "Крушови барчета" excluded too: "бар" starts the word "барчета"
    assert [o.name for o in hits["Круши"]] == ["Круши Уилямс"]


def test_inner_word_text_does_not_trigger_exclude():
    items = [WatchItem("Х", ["ябълк"], exclude=["сок"])]
    hits = match([offer("Ябълки Фуджи"), offer("Ябълки Босок")], items)  # "Босок" contains "сок" only inside a word
    assert len(hits["Х"]) == 2
