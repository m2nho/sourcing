"""번호가 실제로 WhatsApp에 있는지 확인한 결과를 등급에 반영한다.

wa.me 페이지는 등록된 비즈니스 계정의 프로필 이름을 보여준다. 미등록이거나
개인 계정이면 번호만 보인다. 즉 이름이 보이면 등록이 확실하고, 안 보인다고
미등록인 것은 아니다 - 이 신호는 항상 하한이다.

이 모듈은 조회 결과(이름 문자열)만 받는다. 실제 조회는 maps가 한다.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import replace

from sourcing.phone import CONFIRMED, VERIFIED, wa_link
from sourcing.store import SOURCE_PROFILE, PlaceRecord

#: 프로필 이름이 병원명과 같은 곳인지 보는 기준. 실측(런던 4건)에서 맞는
#: 짝은 0.67 이상, 무관한 짝은 훨씬 아래였다.
MATCH_THRESHOLD = 0.45

#: 상호에 흔히 붙어 비교를 방해하는 말. 빼고 견준다.
_FILLER = re.compile(
    r"\b(clinic|clinics|aesthetic|aesthetics|medical|skin|london|ltd|the|dr)\b", re.IGNORECASE
)


def profile_matches(clinic_name: str, profile_name: str) -> bool:
    """WhatsApp 프로필이 이 병원의 것인가.

    다국적 체인이나 대행사 번호를 잘못 붙이지 않으려면 이름을 견줘야 한다.
    'Bayati Clinic' 대 'Bayati Clinic'은 물론, 'Omniya Clinic' 대
    'Omniya London'처럼 뒷말이 달라도 같은 곳으로 본다.
    """
    if not clinic_name or not profile_name:
        return False
    if _core(clinic_name) and _core(clinic_name) in _core(profile_name):
        return True
    if _core(profile_name) and _core(profile_name) in _core(clinic_name):
        return True
    return _ratio(clinic_name, profile_name) >= MATCH_THRESHOLD


def apply_profile(record: PlaceRecord, profile_name: str) -> PlaceRecord:
    """조회 결과를 레코드에 반영한다.

    이름이 맞으면 추측(candidate)이나 버려진 것(unlikely)을 검증(verified)으로
    올린다. 이미 사이트 선언이 있는 confirmed는 그대로 둔다 - 선언이 더 강한
    근거이고, 프로필 이름은 참고로만 남긴다.

    이름이 안 맞아도 지우지 않고 남긴다. 남의 번호일 수 있다는 신호이므로
    사람이 보고 판단할 거리가 된다.
    """
    if not record.phone_e164:
        return record
    if not profile_name:
        return replace(record, profile_name="")

    if not profile_matches(record.name, profile_name):
        return replace(record, profile_name=profile_name)

    if record.whatsapp_status == CONFIRMED:
        return replace(record, profile_name=profile_name)

    return replace(
        record,
        whatsapp_status=VERIFIED,
        source=SOURCE_PROFILE,
        wa_link=wa_link(record.phone_e164),
        profile_name=profile_name,
    )


def _core(name: str) -> str:
    """상호에서 흔한 말을 걷어낸 알맹이."""
    return re.sub(r"[^a-z0-9]", "", _FILLER.sub(" ", name).lower())


def _ratio(a: str, b: str) -> float:
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()
