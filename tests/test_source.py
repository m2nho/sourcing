"""번호를 어디서 얻었는지(근거)를 레코드에 남긴다."""

from sourcing.crawl import branch_records
from sourcing.phone import classify
from sourcing.store import (
    SOURCE_MAP_LINK,
    SOURCE_MAP_PHONE_GUESS,
    SOURCE_NONE,
    SOURCE_SITE_CONFIRMS_MAP,
    SOURCE_SITE_LINK,
    PlaceRecord,
)


def test_map_website_wa_link_is_marked_as_map_link():
    v = classify("(021) 3915-000", "https://wa.me/6281234567890", "ID")
    assert v.source == SOURCE_MAP_LINK


def test_mobile_guess_is_marked_as_guess():
    v = classify("0812-3456-7890", "https://klinik.co.id", "ID")
    assert v.source == SOURCE_MAP_PHONE_GUESS


def test_landline_has_no_source():
    v = classify("(021) 3915-000", "https://klinik.co.id", "ID")
    assert v.source == SOURCE_NONE


def base(phone_e164: str = "+62213915000") -> PlaceRecord:
    return PlaceRecord(
        place_cid="0xa:0xb",
        name="Klinik Contoh",
        phone_raw="(021) 3915-000",
        phone_e164=phone_e164,
        whatsapp_status="unlikely",
        website="https://klinik.co.id",
    )


def test_site_number_that_map_did_not_have_is_site_link():
    [rec] = branch_records(base(), ["+6281510032464"])
    assert rec.source == SOURCE_SITE_LINK


def test_site_number_matching_the_map_phone_is_the_combined_case():
    # 맵의 추측을 사이트가 증명한 경우 - 가장 강한 근거다
    [rec] = branch_records(base("+6281510032464"), ["+6281510032464"])
    assert rec.source == SOURCE_SITE_CONFIRMS_MAP


def test_each_extra_branch_number_is_a_site_link():
    records = branch_records(base("+6281510032464"), ["+6281510032464", "+6285714011402"])
    assert [r.source for r in records] == [SOURCE_SITE_CONFIRMS_MAP, SOURCE_SITE_LINK]


def test_no_numbers_leaves_the_source_alone():
    original = base()
    [rec] = branch_records(original, [])
    assert rec.source == original.source
