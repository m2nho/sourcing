from pathlib import Path

import pytest

from sourcing.crawl import branch_records, wa_numbers_from_html
from sourcing.store import PlaceRecord

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_extracts_every_department_number_from_escaped_json():
    # 실제 캡처: 위젯이 JSON 안에 이스케이프된 형태로 링크를 담고 있다
    assert wa_numbers_from_html(load("site_wa_href.html")) == [
        "+6281100000001",
        "+6281100000002",
        "+6281100000003",
    ]


def test_extracts_api_whatsapp_send_query_form():
    assert wa_numbers_from_html(load("site_wa_api.html")) == ["+6281100000004"]


def test_ignores_ordinary_links():
    html = '<a href="https://klinik.co.id/kontak">Kontak</a><a href="tel:+62211234567">Telp</a>'
    assert wa_numbers_from_html(html) == []


def test_rejects_business_shortlinks():
    # wa.me/message/<코드>는 번호가 아니다 — phone.wa_number_from_url의 검증 관문이 막는다
    html = '<a href="https://wa.me/message/K5H2VQ7N4EXAMPLE">Chat</a>'
    assert wa_numbers_from_html(html) == []


def test_rejects_invalid_numbers():
    assert wa_numbers_from_html('<a href="https://wa.me/1234">Chat</a>') == []


def test_dedupes_and_preserves_first_seen_order():
    html = (
        '<a href="https://wa.me/6285218757012">A</a>'
        '<a href="https://wa.me/628551806670">B</a>'
        '<a href="https://wa.me/6285218757012">A again</a>'
    )
    assert wa_numbers_from_html(html) == ["+6285218757012", "+628551806670"]


def test_handles_protocol_relative_and_whatsapp_scheme():
    html = '<a href="//wa.me/6285218757012">A</a><a href="whatsapp://send?phone=628551806670">B</a>'
    assert wa_numbers_from_html(html) == ["+6285218757012", "+628551806670"]


@pytest.mark.parametrize("html", ["", "   ", "<html><body>no links</body></html>"])
def test_empty_input_yields_nothing(html):
    assert wa_numbers_from_html(html) == []


def base_record() -> PlaceRecord:
    return PlaceRecord(
        place_cid="0xa:0xb",
        name="Klinik Contoh",
        phone_raw="(021) 3915-000",
        phone_e164="+62213915000",
        phone_type="fixed_line",
        whatsapp_status="unlikely",
        website="https://klinik.co.id",
    )


def test_no_numbers_leaves_the_record_untouched():
    base = base_record()
    assert branch_records(base, []) == [base]


def test_first_number_promotes_the_record_to_confirmed():
    [record] = branch_records(base_record(), ["+6281100000001"])
    assert record.place_cid == "0xa:0xb"
    assert record.whatsapp_status == "confirmed"
    assert record.phone_e164 == "+6281100000001"
    assert record.wa_link == "https://wa.me/6281100000001"
    # 맵에 적혀 있던 원문 번호는 보존한다
    assert record.phone_raw == "(021) 3915-000"


def test_extra_numbers_become_separate_records_like_branches():
    records = branch_records(
        base_record(), ["+6281100000001", "+6281100000002", "+6281100000003"]
    )
    assert [r.place_cid for r in records] == ["0xa:0xb", "0xa:0xb#1", "0xa:0xb#2"]
    assert [r.phone_e164 for r in records] == [
        "+6281100000001",
        "+6281100000002",
        "+6281100000003",
    ]
    assert all(r.whatsapp_status == "confirmed" for r in records)
    assert all(r.name == "Klinik Contoh" for r in records)


def test_branch_records_do_not_mutate_the_input():
    base = base_record()
    branch_records(base, ["+6281100000001"])
    assert base.whatsapp_status == "unlikely"
    assert base.phone_e164 == "+62213915000"
