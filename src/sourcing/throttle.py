"""WhatsApp 프로필 조회가 막혔는지 감지한다.

조회가 많아지면 WhatsApp은 오류를 주지 않고 프로필이 빠진 빈 페이지를
돌려준다. 그것을 '개인 계정이거나 미등록'으로 확정 기록하면, 틀린 답을
확신에 차서 저장하게 된다 - 나중에 봐도 왜 틀렸는지 알 수 없다.

실측(버밍엄): City Centre에서 24건 중 12건 이름이 나오다가 네 지구 뒤에는
91건 중 0건이 됐다. 그 시점에 이름이 확실히 있던 런던 번호 셋을 조회해
보니 전부 빈 페이지였다. 번호가 바뀐 게 아니라 조회가 막힌 것이었다.

판별법: 이번 실행에서 이름이 나왔던 번호를 하나 기억해 두고(대조군),
빈 응답이 연달아 나오면 그 번호를 다시 조회한다. 확실히 있던 이름이
안 나오면 막힌 것이다. 남의 번호를 하드코딩하지 않아도 된다.
"""

from __future__ import annotations

#: 빈 응답이 이만큼 연달아 나오면 대조군을 확인한다. 정상적으로도 개인
#: 계정이 몇 건씩 이어질 수 있으므로 너무 짧게 잡지 않는다.
DEFAULT_STREAK_LIMIT = 12


class ThrottleWatch:
    def __init__(self, streak_limit: int = DEFAULT_STREAK_LIMIT) -> None:
        self.streak_limit = streak_limit
        self.canary: str = ""
        self.streak = 0
        self.throttled = False

    def record(self, e164: str, profile_name: str) -> None:
        """조회 결과 하나를 반영한다."""
        if profile_name:
            if not self.canary:
                self.canary = e164
            self.streak = 0
        else:
            self.streak += 1

    def should_check_canary(self) -> bool:
        """지금 대조군을 확인해 볼 때인가."""
        return bool(self.canary) and not self.throttled and self.streak >= self.streak_limit

    def canary_result(self, profile_name: str) -> None:
        """대조군 조회 결과를 반영한다. 이름이 안 나오면 막힌 것이다."""
        self.streak = 0
        if not profile_name:
            self.throttled = True
