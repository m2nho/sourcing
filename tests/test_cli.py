import pytest

from sourcing.cli import build_record, parse_args, parse_center


def test_parse_center_accepts_lat_lng():
    assert parse_center("-6.2,106.8") == (-6.2, 106.8)


def test_parse_center_tolerates_spaces():
    assert parse_center(" -6.2 , 106.8 ") == (-6.2, 106.8)


@pytest.mark.parametrize("value", ["-6.2", "a,b", "", "1,2,3"])
def test_parse_center_rejects_bad_input(value):
    with pytest.raises(Exception):
        parse_center(value)


def test_args_require_region():
    with pytest.raises(SystemExit):
        parse_args(["rumah sakit"])


def test_args_defaults():
    args = parse_args(["rumah sakit", "--region", "ID"])
    assert args.keyword == "rumah sakit"
    assert args.region == "ID"
    assert args.lang == "en"
    assert args.center is None
    assert args.grid == 3
    assert args.radius_km == 10.0


def test_build_record_marks_wa_website_confirmed():
    fields = {
        "place_cid": "0xa:0xb",
        "name": "Klinik Contoh",
        "category": "Klinik",
        "address": "Jl. Contoh 1",
        "phone_raw": "(021) 3915-000",
        "website": "https://wa.me/6281234567890",
        "rating": "4.3",
        "reviews": "1234",
        "maps_url": "https://maps.google.com/x",
    }
    record = build_record(fields, region="ID", query="rumah sakit", tile_label="t1")
    assert record.whatsapp_status == "confirmed"
    assert record.phone_e164 == "+6281234567890"
    assert record.wa_link == "https://wa.me/6281234567890"
    assert record.phone_raw == "(021) 3915-000"
    assert record.query == "rumah sakit"
    assert record.tile == "t1"
    assert record.scraped_at.endswith("+00:00")


def test_build_record_marks_mobile_candidate():
    fields = {
        "place_cid": "0xa:0xb",
        "name": "RS Contoh",
        "category": "",
        "address": "",
        "phone_raw": "0812-3456-7890",
        "website": "https://rscontoh.co.id",
        "rating": "",
        "reviews": "",
        "maps_url": "",
    }
    record = build_record(fields, region="ID", query="q", tile_label="")
    assert record.whatsapp_status == "candidate"
    assert record.phone_type == "mobile"
