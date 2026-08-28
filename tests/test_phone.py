import pytest

from sourcing.phone import (
    CANDIDATE,
    CONFIRMED,
    UNLIKELY,
    classify,
    normalize,
    wa_number_from_url,
)


@pytest.mark.parametrize(
    "raw,region,expected_e164,expected_type",
    [
        ("0812-3456-7890", "ID", "+6281234567890", "mobile"),
        ("+62 812 3456 7890", "ID", "+6281234567890", "mobile"),
        ("(021) 3915-000", "ID", "+62213915000", "fixed_line"),
        ("021-29962888", "ID", "+622129962888", "fixed_line"),
        ("0912 345 678", "VN", "+84912345678", "mobile"),
        ("028 3822 5052", "VN", "+842838225052", "fixed_line"),
        ("0917 123 4567", "PH", "+639171234567", "mobile"),
        ("(02) 8888 8888", "PH", "+63288888888", "fixed_line"),
        ("(415) 555-2671", "US", "+14155552671", "fixed_line_or_mobile"),
    ],
)
def test_normalize_valid_numbers(raw, region, expected_e164, expected_type):
    assert normalize(raw, region) == (expected_e164, expected_type)


@pytest.mark.parametrize("raw", ["", "   ", "not a phone", "123"])
def test_normalize_rejects_garbage(raw):
    assert normalize(raw, "ID") == ("", "unknown")


def test_normalize_service_number_is_not_mobile():
    # 인니 UAN(1500-135)은 유효하지만 모바일이 아니다
    e164, ntype = normalize("1500-135", "ID")
    assert e164 == "+621500135"
    assert ntype == "unknown"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://wa.me/6281234567890", "+6281234567890"),
        ("https://wa.me/6281234567890?text=Halo", "+6281234567890"),
        ("wa.me/6281234567890", "+6281234567890"),
        ("https://api.whatsapp.com/send?phone=6281234567890", "+6281234567890"),
        ("https://api.whatsapp.com/send/?phone=%2B6281234567890", "+6281234567890"),
        ("https://rscontoh.co.id/kontak", ""),
        ("", ""),
        ("https://chat.whatsapp.com/AbCdEf123", ""),
        # wa.me/message/... , wa.me/qr/... 는 WhatsApp Business 단축링크다.
        # 경로에 숫자 아닌 세그먼트가 섞여 있으면 번호로 취급하면 안 된다.
        ("https://wa.me/message/K5H2VQ7N4EXAMPLE", ""),
        ("https://wa.me/qr/4XKLMN2P3", ""),
        ("https://wa.me/message/ABCDEFG", ""),
    ],
)
def test_wa_number_from_url(url, expected):
    assert wa_number_from_url(url) == expected


def test_classify_website_wa_link_is_confirmed():
    v = classify("(021) 3915-000", "https://wa.me/6281234567890", "ID")
    assert v.status == CONFIRMED
    assert v.e164 == "+6281234567890"
    assert v.type == "mobile"
    assert v.wa_link == "https://wa.me/6281234567890"


def test_classify_mobile_is_candidate():
    v = classify("0812-3456-7890", "https://rscontoh.co.id", "ID")
    assert v.status == CANDIDATE
    assert v.e164 == "+6281234567890"
    assert v.wa_link == "https://wa.me/6281234567890"


def test_classify_fixed_line_or_mobile_is_candidate():
    v = classify("(415) 555-2671", "", "US")
    assert v.status == CANDIDATE


def test_classify_fixed_line_is_unlikely():
    v = classify("(021) 3915-000", "https://rscontoh.co.id", "ID")
    assert v.status == UNLIKELY
    assert v.e164 == "+62213915000"
    assert v.wa_link == ""


def test_classify_no_phone_is_unlikely():
    v = classify("", "", "ID")
    assert v.status == UNLIKELY
    assert v.e164 == ""
    assert v.type == "unknown"
    assert v.wa_link == ""
