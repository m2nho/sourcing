"""전화번호 정규화와 WhatsApp 연락 가능성 판정."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import phonenumbers

CONFIRMED = "confirmed"
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
    digits = _digits(unquote(parsed.path))
    if not digits:
        digits = _digits(unquote(parse_qs(parsed.query).get("phone", [""])[0]))
    return f"+{digits}" if digits else ""


def wa_link(e164: str) -> str:
    """E.164를 click-to-chat 링크로. 빈 입력이면 ""."""
    return f"https://wa.me/{e164.lstrip('+')}" if e164 else ""


def classify(raw_phone: str, website: str, region: str) -> PhoneVerdict:
    """맵 리스팅의 전화·웹사이트로 WhatsApp 연락 가능성을 판정한다."""
    from_url = wa_number_from_url(website)
    if from_url:
        _, url_type = normalize(from_url, region)
        return PhoneVerdict(from_url, url_type, CONFIRMED, wa_link(from_url))

    e164, ntype = normalize(raw_phone, region)
    if e164 and ntype in _MOBILE_ISH:
        return PhoneVerdict(e164, ntype, CANDIDATE, wa_link(e164))
    return PhoneVerdict(e164, ntype, UNLIKELY, "")


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())
