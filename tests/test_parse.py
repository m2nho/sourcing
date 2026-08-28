from pathlib import Path

import pytest

from sourcing.parse import cid_from_url, parse_panel

FIXTURES = Path(__file__).parent / "fixtures"

PLACE_URL = (
    "https://www.google.com/maps/place/Klinik+Contoh/"
    "@-6.2,106.8,17z/data=!3m1!4b1!4m6!3m5!1s0x2e69f5d1a2b3c4d5:0x123abc456def7890!8m2"
)


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_cid_from_url_extracts_hex_pair():
    assert cid_from_url(PLACE_URL) == "0x2e69f5d1a2b3c4d5:0x123abc456def7890"


def test_cid_from_url_falls_back_to_url_when_absent():
    url = "https://www.google.com/maps/place/Klinik+Contoh/@-6.2,106.8,17z"
    assert cid_from_url(url) == url


def test_parses_indonesian_panel():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["name"] == "Klinik Contoh Jakarta"
    assert result["category"] == "Klinik Umum"
    assert result["address"] == "Jl. Contoh No. 1, Jakarta Selatan"
    assert result["place_cid"] == "0x2e69f5d1a2b3c4d5:0x123abc456def7890"
    assert result["maps_url"] == PLACE_URL


def test_phone_comes_from_the_data_item_id_attribute():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["phone_raw"] == "+62 812-3456-7890"


def test_website_href_is_taken_verbatim():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["website"] == "https://wa.me/6281234567890"


def test_rating_is_normalised_to_a_dot_decimal():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["rating"] == "4.3"


def test_review_count_strips_locale_separators():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["reviews"] == "1234"


def test_missing_fields_become_empty_strings():
    result = parse_panel(load("place_panel_en_minimal.html"), PLACE_URL)
    assert result["name"] == "Contoh General Hospital"
    assert result["address"] == "12 Example Road, Manila"
    assert result["phone_raw"] == ""
    assert result["website"] == ""
    assert result["rating"] == ""
    assert result["reviews"] == ""


def test_empty_html_yields_all_empty_but_keeps_url():
    result = parse_panel("", PLACE_URL)
    assert result["name"] == ""
    assert result["maps_url"] == PLACE_URL
    assert set(result) == {
        "place_cid",
        "name",
        "category",
        "address",
        "phone_raw",
        "website",
        "rating",
        "reviews",
        "maps_url",
    }
