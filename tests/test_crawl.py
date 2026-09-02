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


# ── tel: 링크에 WhatsApp 라벨이 붙은 형태 ──────────────────────────
# 실측(런던 Dr Hala): 업체가 wa.me 대신 tel: 링크를 쓰고 옆에 WhatsApp이라고
# 적어두는 경우가 있다. 이것도 선언이므로 읽는다. 다만 "전화 또는 WhatsApp"
# 처럼 두 링크가 나란한 문장에서 엉뚱한 쪽을 집으면 안 된다.


def test_tel_link_whose_anchor_says_whatsapp():
    html = '<a href="tel:+447488732737">WhatsApp</a>'
    assert wa_numbers_from_html(html, region="GB") == ["+447488732737"]


def test_tel_link_preceded_by_a_whatsapp_label():
    html = 'WhatsApp Us: <a href="tel:+447776103599">0777 610 3599</a>'
    assert wa_numbers_from_html(html, region="GB") == ["+447776103599"]


def test_plain_tel_link_is_not_a_whatsapp_number():
    assert wa_numbers_from_html('<a href="tel:+442073718939">Call us</a>', region="GB") == []


def test_call_link_next_to_a_whatsapp_link_is_not_picked_up():
    # 실제 Dr Hala 마크업의 형태다. 020은 '전화', 07은 'WhatsApp'이다.
    html = (
        '<a href="tel:+442073718939">give us a call</a> or drop us a '
        '<a href="tel:+447488732737">WhatsApp</a> anytime'
    )
    assert wa_numbers_from_html(html, region="GB") == ["+447488732737"]


def test_tel_numbers_need_a_region_to_be_read():
    # 지역 정보가 없으면 국내 표기(07...)를 정규화할 수 없다. 조용히 틀린
    # 번호를 만드느니 읽지 않는다.
    assert wa_numbers_from_html('<a href="tel:07488732737">WhatsApp</a>') == []


def test_local_format_tel_number_is_normalised_with_the_region():
    assert wa_numbers_from_html('<a href="tel:07488732737">WhatsApp</a>', region="GB") == [
        "+447488732737"
    ]


def test_wa_me_links_still_come_first():
    html = (
        '<a href="tel:+447488732737">WhatsApp</a>'
        '<a href="https://wa.me/447776103599">Chat</a>'
    )
    # 선언이 더 명확한 wa.me를 앞에 둔다
    assert wa_numbers_from_html(html, region="GB") == ["+447776103599", "+447488732737"]


def test_invalid_tel_number_is_rejected():
    assert wa_numbers_from_html('<a href="tel:+441234">WhatsApp</a>', region="GB") == []


# ── 다국적 체인의 타 지점 번호 걸러내기 ─────────────────────────────
# 실측(런던 Sisu Clinic Mayfair): 사이트에 전 지점 번호가 깔려 있어
# 메이페어 지점에 캐나다(+1 249)·미국 번호가 붙었다. 마이애미 수집에서도
# 같은 번호가 나왔다. 수집 지역과 다른 나라 번호는 다른 지점의 것이다.


def test_foreign_numbers_are_rejected_when_a_region_is_given():
    html = (
        '<a href="https://wa.me/12497018842">Canada</a>'
        '<a href="https://wa.me/447496873334">London</a>'
    )
    assert wa_numbers_from_html(html, region="GB") == ["+447496873334"]


def test_every_number_foreign_means_no_number():
    html = '<a href="https://wa.me/12497018842">Chat</a>'
    assert wa_numbers_from_html(html, region="GB") == []


def test_without_a_region_nothing_is_filtered_by_country():
    html = '<a href="https://wa.me/12497018842">Chat</a>'
    assert wa_numbers_from_html(html) == ["+12497018842"]


def test_indonesian_numbers_survive_an_indonesian_run():
    html = '<a href="https://wa.me/6281100000001">Chat</a>'
    assert wa_numbers_from_html(html, region="ID") == ["+6281100000001"]
