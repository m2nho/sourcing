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


# ── 프로필은 있는데 이름이 상호와 다른 경우 ──────────────────────────
# 실측(런던 Dr. Bennett Aesthetics Clinics → "Isabella"): 원장 개인 이름을
# 프로필로 쓰는 곳이 있다. 번호가 WhatsApp에 있다는 것은 확인된 사실이므로
# 링크를 준다. 다만 그 번호가 이 병원 것인지는 확인되지 않았으므로 등급을
# 올리지 않고, 왜 그런지 근거에 밝힌다.


def test_mismatched_profile_still_gets_a_link():
    from sourcing.store import SOURCE_PROFILE_MISMATCH

    out = apply_profile(base(), "Isabella")
    assert out.whatsapp_status == "candidate"
    assert out.wa_link == "https://wa.me/442081645799"
    assert out.source == SOURCE_PROFILE_MISMATCH
    assert out.profile_name == "Isabella"


def test_candidate_without_any_profile_keeps_its_link():
    # 조회해도 이름이 안 뜬 번호는 여전히 추측이지만 링크는 유지한다.
    # 구분은 상태와 근거로 한다.
    out = apply_profile(base(), "")
    assert out.source == SOURCE_MAP_PHONE_GUESS
    assert out.profile_name == ""


def test_mismatch_does_not_downgrade_a_confirmed_record():
    out = apply_profile(base(status="confirmed", source=SOURCE_SITE_LINK), "Isabella")
    assert out.whatsapp_status == "confirmed"
    assert out.source == SOURCE_SITE_LINK


# ── 조회하지 못한 것과 조회했는데 없는 것을 구분한다 ──────────────────
# 둘 다 profile_name이 빈 값이면 재조회로 건질 수 있는 것과 그래도 소용없는
# 것이 섞인다. 확정 49건 중 몇이 타임아웃이었는지 알 수 없었다.


def test_lookup_with_no_name_is_recorded_as_checked():
    from sourcing.store import PROFILE_NONE

    out = apply_profile(base(), "")
    assert out.profile_checked == PROFILE_NONE
    assert out.profile_name == ""


def test_found_profile_is_recorded_as_found():
    from sourcing.store import PROFILE_FOUND

    out = apply_profile(base(), "Bayati Clinic")
    assert out.profile_checked == PROFILE_FOUND


def test_lookup_failure_is_recorded_separately():
    from sourcing.store import PROFILE_ERROR
    from sourcing.verify import mark_lookup_failed

    out = mark_lookup_failed(base())
    assert out.profile_checked == PROFILE_ERROR
    assert out.profile_name == ""
    assert out.whatsapp_status == "candidate"  # 등급은 건드리지 않는다


def test_a_record_never_checked_stays_blank():
    assert base().profile_checked == ""


def test_mismatched_profile_counts_as_found():
    from sourcing.store import PROFILE_FOUND

    out = apply_profile(base(), "Isabella")
    assert out.profile_checked == PROFILE_FOUND
    assert out.profile_name == "Isabella"
