import json

from sourcing.recheck import needs_lookup
from sourcing.store import PROFILE_ERROR, PROFILE_FOUND, PROFILE_NONE, PlaceRecord


def rec(status="candidate", checked="", phone="+447700000001"):
    return PlaceRecord(place_cid="0xa:0xb", name="A", phone_e164=phone,
                       whatsapp_status=status, profile_checked=checked)


def test_records_without_a_number_are_skipped():
    assert not needs_lookup(rec(phone=""), only_errors=False)


def test_unlikely_records_are_skipped():
    # 연락 불가로 분류된 곳은 엑셀에도 안 나온다. 조회 한도를 쓸 이유가 없다.
    assert not needs_lookup(rec(status="unlikely"), only_errors=False)


def test_failed_lookups_are_always_retried():
    assert needs_lookup(rec(checked=PROFILE_ERROR), only_errors=True)
    assert needs_lookup(rec(checked=PROFILE_ERROR), only_errors=False)


def test_only_errors_mode_leaves_settled_records_alone():
    assert not needs_lookup(rec(checked=PROFILE_FOUND), only_errors=True)
    assert not needs_lookup(rec(checked=PROFILE_NONE), only_errors=True)


def test_full_mode_revisits_everything_with_a_number():
    # 조회가 막힌 채로 'none'이 찍힌 것들이 섞여 있을 수 있다.
    assert needs_lookup(rec(checked=PROFILE_NONE), only_errors=False)
    assert needs_lookup(rec(checked=PROFILE_FOUND), only_errors=False)


def test_never_checked_records_are_looked_up_in_both_modes():
    assert needs_lookup(rec(checked=""), only_errors=True)
    assert needs_lookup(rec(checked=""), only_errors=False)
