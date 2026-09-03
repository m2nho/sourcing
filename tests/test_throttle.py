"""조회 제한을 감지한다.

WhatsApp은 조회가 많아지면 오류 대신 프로필 없는 빈 페이지를 준다. 그걸
'개인/미등록'으로 확정 기록하면 틀린 답을 확신에 차서 저장하게 된다.
실측(버밍엄): City Centre에서 24건 중 12건 이름이 나오다가, 네 지구 뒤에는
91건 중 0건이 됐다. 이름이 확실히 있던 번호도 그 시점엔 빈 페이지가 왔다.
"""

import pytest

from sourcing.throttle import ThrottleWatch


def test_a_found_profile_is_remembered_as_a_canary():
    w = ThrottleWatch(streak_limit=3)
    w.record("+447877850549", "Skinor")
    assert w.canary == "+447877850549"


def test_streak_of_empties_triggers_a_check():
    w = ThrottleWatch(streak_limit=3)
    w.record("+447877850549", "Skinor")
    for i in range(2):
        assert not w.should_check_canary()
        w.record(f"+44770000000{i}", "")
    w.record("+447700000099", "")
    assert w.should_check_canary()


def test_no_canary_means_no_check():
    # 이번 실행에서 한 번도 이름이 나온 적 없으면 대조할 기준이 없다
    w = ThrottleWatch(streak_limit=2)
    w.record("+447700000001", "")
    w.record("+447700000002", "")
    assert not w.should_check_canary()


def test_a_found_profile_resets_the_streak():
    w = ThrottleWatch(streak_limit=2)
    w.record("+447877850549", "Skinor")
    w.record("+447700000001", "")
    w.record("+447963770519", "Simply Clinics")
    w.record("+447700000002", "")
    assert not w.should_check_canary()


def test_canary_silence_marks_us_throttled():
    w = ThrottleWatch(streak_limit=1)
    w.record("+447877850549", "Skinor")
    w.record("+447700000001", "")
    assert w.should_check_canary()
    w.canary_result("")          # 확실히 있던 번호가 이름을 안 준다
    assert w.throttled


def test_canary_still_answering_means_we_are_fine():
    w = ThrottleWatch(streak_limit=1)
    w.record("+447877850549", "Skinor")
    w.record("+447700000001", "")
    w.canary_result("Skinor")
    assert not w.throttled


def test_checking_the_canary_resets_the_streak():
    w = ThrottleWatch(streak_limit=2)
    w.record("+447877850549", "Skinor")
    w.record("+447700000001", "")
    w.record("+447700000002", "")
    assert w.should_check_canary()
    w.canary_result("Skinor")
    assert not w.should_check_canary()


def test_once_throttled_it_stays_throttled():
    w = ThrottleWatch(streak_limit=1)
    w.record("+447877850549", "Skinor")
    w.record("+447700000001", "")
    w.canary_result("")
    w.record("+447877850549", "Skinor")
    assert w.throttled
