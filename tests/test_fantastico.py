import io
import zipfile

import httpx
import pytest

from grocery_agent.scrapers.fantastico import latest_zip_url, parse_csv, scrape, tidy_name

HEADER = "Населено място,Търговски обект,Наименование на продукта,Код на продукта,Категория,Цена на дребно,Цена в промоция\n"


def csv_text(*rows):
    """rows: (store, name, code, regular, promo)"""
    body = "".join(f'68134,"{store}","{name}",{code},6,{regular},{promo}\n' for store, name, code, regular, promo in rows)
    return HEADER + body


OPENDATA = (
    '<a href="/opendata_files/2026-11-13.zip">13</a>'
    '<a href="/opendata_files/2026-11-15.zip">15</a>'
    '<a href="/opendata_files/2026-11-14.zip">14</a>'
)


def test_latest_zip_url_picks_the_newest_date():
    assert latest_zip_url(OPENDATA) == "https://kolkostruva.bg/opendata_files/2026-11-15.zip"


def test_latest_zip_url_without_links_raises():
    with pytest.raises(ValueError):
        latest_zip_url("<html>no files</html>")


def test_tidy_name_title_cases_cyrillic_keeps_latin_and_units():
    assert tidy_name("МЛЯКО ПРЯСНО ВЕРЕЯ 3% 1 Л") == "Мляко Прясно Верея 3% 1 л"
    assert tidy_name("МАСЛО КРАВЕ PRESIDENT 125 ГР") == "Масло Краве PRESIDENT 125 гр"
    assert tidy_name("Вече Хубаво Име") == "Вече Хубаво Име"  # mixed case is left alone


def test_one_offer_per_product_across_stores_with_prices_and_discount():
    rows = [(f"Ф{i:02d}", "МЛЯКО ПРЯСНО ВЕРЕЯ 3% 1 Л", "001102", "1.78", "1.29") for i in range(3)]
    offers = parse_csv(csv_text(*rows))
    assert len(offers) == 1
    o = offers[0]
    assert (o.shop, o.name, o.price, o.old_price, o.discount_pct) == ("Fantastico", "Мляко Прясно Верея 3% 1 л", 1.29, 1.78, 28)
    assert o.note is None and o.valid_from is None and o.valid_to is None and o.url is None


def test_products_without_a_real_promotion_are_skipped():
    offers = parse_csv(
        csv_text(
            ("Ф01", "БЕЗ ПРОМО", "1", "2.00", ""),
            ("Ф01", "ПРОМО ПО-СКЪПО", "2", "2.00", "2.50"),
            ("Ф01", "ПРОМО СЪЩАТА", "3", "2.00", "2.00"),
            ("Ф01", "ГРЕШНА ЦЕНА", "4", "abc", "1.00"),
            ("Ф01", "НУЛА", "5", "2.00", "0"),
            ("Ф01", "ДОБЪР ПРОДУКТ", "6", "2.00", "1.50"),
        )
    )
    assert [o.name for o in offers] == ["Добър Продукт"]


def test_when_stores_disagree_the_most_common_price_wins():
    offers = parse_csv(
        csv_text(
            ("Ф01", "СИРЕНЕ", "9", "6.00", "5.00"),
            ("Ф02", "СИРЕНЕ", "9", "6.00", "5.00"),
            ("Ф03", "СИРЕНЕ", "9", "6.00", "4.00"),
        )
    )
    assert [(o.price, o.old_price) for o in offers] == [(5.0, 6.0)]


def test_comma_decimals_are_accepted():
    offers = parse_csv(csv_text(("Ф01", "СИРЕНЕ", "9", '"6,00"', '"5,50"')))
    assert (offers[0].price, offers[0].old_price) == (5.5, 6.0)


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text.encode("utf-8"))
    return buf.getvalue()


def client_for(zip_bytes):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        if request.url.path == "/opendata":
            return httpx.Response(200, text=OPENDATA)
        if request.url.path.endswith("2026-11-15.zip"):
            return httpx.Response(200, content=zip_bytes)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def test_scrape_reads_only_fantastico_files_from_the_latest_zip_and_merges_duplicates():
    promo = csv_text(("Ф01", "СИРЕНЕ КРАВЕ", "1", "6.00", "5.00"))
    only_in_second = csv_text(("Д01", "СИРЕНЕ КРАВЕ", "7", "6.00", "5.00"), ("Д01", "МАСЛО", "8", "4.00", "3.00"))
    other_chain = csv_text(("Л01", "ЧУЖД ПРОДУКТ", "99", "3.00", "1.00"))
    z = make_zip(
        {
            "ФАНТАСТИКО (ФАНТАСТИКО ГРУП ООД)_206255903.csv": promo,
            "ФАНТАСТИКО (ДАР Г.Н.)_831556063.csv": only_in_second,
            "Лидл България_131071587.csv": other_chain,
        }
    )
    client, requested = client_for(z)
    offers = scrape(client)
    assert sorted(o.name for o in offers) == ["Масло", "Сирене Краве"]  # same name+price in both files counted once
    assert requested == ["/opendata", "/opendata_files/2026-11-15.zip"]


def test_scrape_ignores_keywords_argument():
    z = make_zip({"ФАНТАСТИКО (X)_1.csv": csv_text(("Ф01", "СИРЕНЕ", "1", "6.00", "5.00"))})
    client, _ = client_for(z)
    assert len(scrape(client, ["пилешк"])) == 1


def test_zip_without_a_fantastico_file_raises():
    client, _ = client_for(make_zip({"Лидл България_1.csv": csv_text(("Л01", "X", "1", "2", "1"))}))
    with pytest.raises(ValueError):
        scrape(client)


def test_download_that_is_not_a_zip_raises():
    client, _ = client_for(b"<html>not a zip</html>")
    with pytest.raises(ValueError):
        scrape(client)


def test_fantastico_file_with_no_promotions_raises_as_probably_changed_format():
    client, _ = client_for(make_zip({"ФАНТАСТИКО (X)_1.csv": csv_text(("Ф01", "СИРЕНЕ", "1", "6.00", ""))}))
    with pytest.raises(ValueError):
        scrape(client)
