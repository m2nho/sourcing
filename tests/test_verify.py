"""번호가 실제로 WhatsApp에 있는지 확인한 결과를 등급에 반영한다.

실측(런던): 사이트에 선언이 없어도 프로필이 확인되는 곳이 45건 중 4건 있었고,
반대로 모바일이라 추정했지만 프로필이 없는 곳이 절반이었다. 추측과 확인을
구분해야 영업 담당자가 어디부터 걸지 정할 수 있다.
"""

import pytest

from sourcing.store import (
    SOURCE_MAP_PHONE_GUESS,
    SOURCE_PROFILE,
    SOURCE_SITE_LINK,
    PlaceRecord,
)
from sourcing.verify import apply_profile, profile_matches


@pytest.mark.parametrize(
    "clinic,profile",
    [
        ("Bayati Clinic", "Bayati Clinic"),
        ("Dr.Derme Skin Clinic Wimbledon", "Dr Derme Skin Clinics"),
        ("Omniya Clinic", "Omniya London"),
        ("EC Clinic London", "EC Aesthetic Clinic"),
    ],
)
def test_real_matches_are_recognised(clinic, profile):
    assert profile_matches(clinic, profile)


@pytest.mark.parametrize(
    "clinic,profile",
    [
        ("Bayati Clinic", "Webdesign Agency Ltd"),
        ("Skinor", "Domino's Pizza"),
        ("Omniya Clinic", ""),
    ],
)
def test_unrelated_profiles_are_rejected(clinic, profile):
    assert not profile_matches(clinic, profile)


def base(status="candidate", source=SOURCE_MAP_PHONE_GUESS, name="Bayati Clinic"):
    return PlaceRecord(
        place_cid="0xa:0xb",
        name=name,
        phone_e164="+442081645799",
        whatsapp_status=status,
        source=source,
        wa_link="",
    )


def test_matching_profile_promotes_a_guess_to_verified():
    out = apply_profile(base(), "Bayati Clinic")
    assert out.whatsapp_status == "verified"
    assert out.source == SOURCE_PROFILE
    assert out.profile_name == "Bayati Clinic"
    assert out.wa_link == "https://wa.me/442081645799"


def test_matching_profile_promotes_an_unlikely_record_too():
    # 유선이라 버려졌지만 실제로 WhatsApp Business인 경우 (실측 4건)
    out = apply_profile(base(status="unlikely", source=""), "Bayati Clinic")
    assert out.whatsapp_status == "verified"


def test_confirmed_stays_confirmed_but_records_the_profile():
    # 선언이 이미 있으면 그게 더 강한 근거다. 등급을 내리지 않는다.
    out = apply_profile(base(status="confirmed", source=SOURCE_SITE_LINK), "Bayati Clinic")
    assert out.whatsapp_status == "confirmed"
    assert out.source == SOURCE_SITE_LINK
    assert out.profile_name == "Bayati Clinic"


def test_no_profile_leaves_the_guess_as_a_guess():
    out = apply_profile(base(), "")
    assert out.whatsapp_status == "candidate"
    assert out.source == SOURCE_MAP_PHONE_GUESS
    assert out.profile_name == ""


def test_mismatched_profile_does_not_promote_but_is_recorded():
    # 남의 번호일 수 있다. 등급은 올리지 않되 사람이 판단하도록 이름은 남긴다.
    out = apply_profile(base(), "Some Other Business")
    assert out.whatsapp_status == "candidate"
    assert out.profile_name == "Some Other Business"


def test_apply_profile_does_not_mutate_the_input():
    original = base()
    apply_profile(original, "Bayati Clinic")
    assert original.whatsapp_status == "candidate"
    assert original.profile_name == ""


def test_record_without_a_number_is_untouched():
    empty = PlaceRecord(place_cid="0xa:0xb", name="X", phone_e164="")
    assert apply_profile(empty, "Anything") == empty
