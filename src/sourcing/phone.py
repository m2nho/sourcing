"""전화번호 정규화와 WhatsApp 연락 가능성 판정."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import phonenumbers

from sourcing.store import (
    SOURCE_MAP_LINK,
    SOURCE_MAP_PHONE_GUESS,
    SOURCE_NONE,
)

CONFIRMED = "confirmed"
VERIFIED = "verified"
CANDIDATE = "candidate"
UNLIKELY = "unlikely"

#: 번호를 담고 있는 WhatsApp click-to-chat 호스트.
#: chat.whatsapp.com은 그룹 초대 링크라 번호가 없으므로 제외한다.
WA_HOSTS = frozenset({"wa.me", "api.whatsapp.com", "web.whatsapp.com"})

_TYPE_NAMES = {
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
}

#: WhatsApp 후보로 볼 번호 유형. phonenumbers가 모바일/유선을 구분하지 못하는
#: 번호대(FIXED_LINE_OR_MOBILE)는 동남아에서 모바일일 확률이 높아 후보에 넣는다.
_MOBILE_ISH = frozenset({"mobile", "fixed_line_or_mobile"})


@dataclass(frozen=True)
class PhoneVerdict:
    e164: str
    type: str
    status: str
    wa_link: str
    source: str = SOURCE_NONE


def normalize(raw: str, region: str) -> tuple[str, str]:
    """전화번호를 E.164와 유형명으로 바꾼다. 파싱·검증 실패 시 ("", "unknown")."""
    if not raw or not raw.strip():
        return "", "unknown"
    try:
        num = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return "", "unknown"
    if not phonenumbers.is_valid_number(num):
        return "", "unknown"
    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    return e164, _TYPE_NAMES.get(phonenumbers.number_type(num), "unknown")


def wa_number_from_url(url: str) -> str:
    """WhatsApp click-to-chat URL에서 +E.164를 뽑는다. 해당 없으면 ""."""
    if not url or not url.strip():
        return ""
    candidate = url.strip()
    if "//" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in WA_HOSTS:
        return ""
    digits = _path_number(unquote(parsed.path))
    if not digits:
        phone_param = unquote(parse_qs(parsed.query).get("phone", [""])[0])
        digits = _segment_digits(phone_param)
    return _validated_e164(digits) if digits else ""


def _path_number(path: str) -> str:
    """경로가 번호 형태 세그먼트 하나뿐일 때만 번호로 본다.

    wa.me/message/<코드>, wa.me/qr/<코드> 같은 WhatsApp Business 단축링크는
    경로에 세그먼트가 두 개 이상 섞여 있으므로 여기서 걸러진다.
    """
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) != 1:
        return ""
    return _segment_digits(segments[0])


#: 번호 세그먼트에 허용하는 구분자. 링크 생성기가 흔히 넣는 하이픈·공백·점.
_ALLOWED_SEPARATORS = frozenset("-. ")


def _segment_digits(segment: str) -> str:
    """세그먼트가 선행 '+' 하나와 숫자·구분자로만 되어 있으면 숫자열을 뽑는다.

    알파벳이 하나라도 섞여 있으면 거부한다 (wa.me/message/..., wa.me/qr/...
    같은 단축링크 코드를 막는 방어선). '+'가 둘 이상이거나 위치가 맞지
    않아도 거부한다. 여기서 뽑은 숫자열은 이후 _validated_e164에서 실재
    가능한 번호인지 다시 검증되므로, 여기서는 형태만 느슨하게 허용한다.
    """
    if not segment or any(ch.isalpha() for ch in segment):
        return ""
    body = segment[1:] if segment.startswith("+") else segment
    if not body or any(ch not in _ALLOWED_SEPARATORS and not ch.isdigit() for ch in body):
        return ""
    digits = _digits(body)
    return digits


def _validated_e164(digits: str) -> str:
    """숫자열을 +E.164로 만들고 실재 가능한 번호인지 검증한다."""
    candidate = f"+{digits}"
    try:
        num = phonenumbers.parse(candidate, None)
    except phonenumbers.NumberParseException:
        return ""
    if not phonenumbers.is_valid_number(num):
        return ""
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def wa_link(e164: str) -> str:
    """E.164를 click-to-chat 링크로. 빈 입력이면 ""."""
    return f"https://wa.me/{e164.lstrip('+')}" if e164 else ""


#: 북미번호계획(+1) 국가들. NANP는 지역번호로 유선/모바일을 나누지 않아
#: 모든 번호가 fixed_line_or_mobile로 나온다 - 유형이 정보를 전혀 담지 않는다.
#: 실측: 마이애미 클리닉 304건 중 267건이 이 유형, mobile도 fixed_line도 0건.
NANP_PREFIX = "+1"


def classify(raw_phone: str, website: str, region: str) -> PhoneVerdict:
    """맵 리스팅의 전화·웹사이트로 WhatsApp 연락 가능성을 판정한다."""
    from_url = wa_number_from_url(website)
    if from_url:
        _, url_type = normalize(from_url, region)
        return PhoneVerdict(from_url, url_type, CONFIRMED, wa_link(from_url), SOURCE_MAP_LINK)

    e164, ntype = normalize(raw_phone, region)
    if e164 and _looks_reachable(e164, ntype):
        # 추측이라는 사실은 링크를 감추는 것이 아니라 상태·근거로 표시한다.
        # 링크가 없으면 담당자가 번호를 손으로 옮겨야 해서 불편만 커진다.
        return PhoneVerdict(e164, ntype, CANDIDATE, wa_link(e164), SOURCE_MAP_PHONE_GUESS)
    return PhoneVerdict(e164, ntype, UNLIKELY, "", SOURCE_NONE)


def _looks_reachable(e164: str, ntype: str) -> bool:
    """번호 유형이 WhatsApp 가능성을 실제로 시사하는가.

    NANP에서는 fixed_line_or_mobile이 "구분 불가"를 뜻할 뿐 아무 정보도
    담지 않으므로 후보로 올리지 않는다. 그 밖의 지역에서는 유지한다 -
    베트남·필리핀 일부 번호대가 실제로 이 유형이고, 그쪽에서는 모바일일
    확률이 높다는 정보가 된다.
    """
    if ntype not in _MOBILE_ISH:
        return False
    if e164.startswith(NANP_PREFIX) and ntype == "fixed_line_or_mobile":
        return False
    return True


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())
