"""병원 웹사이트에서 WhatsApp 링크를 찾아 번호를 확정한다.

맵 리스팅만으로는 확정 번호가 거의 나오지 않는다(실측 709건 중 1건). 업체가
스스로 "이 번호가 우리 WhatsApp이다"라고 선언해 둔 곳은 홈페이지의 wa.me
링크이며, 그것을 읽는 것이 이 모듈의 역할이다.

본문에 그냥 적힌 번호는 쓰지 않는다. "WA:" 같은 라벨이 옆에 있는지로 추정할
수는 있지만 그것은 추측이고, 이 모듈의 존재 이유는 추측이 아니라 선언을
읽는 것이다.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import replace

import phonenumbers

from sourcing.phone import CONFIRMED, normalize, wa_number_from_url, wa_link
from sourcing.store import (
    SOURCE_SITE_CONFIRMS_MAP,
    SOURCE_SITE_LINK,
    PlaceRecord,
)

#: WhatsApp click-to-chat 링크의 여러 형태. 위젯이 JSON 안에 이스케이프해
#: 넣어두는 경우가 흔해서 DOM 앵커만 봐서는 놓친다(실측: KMC 클리닉).
WA_URL_PATTERN = re.compile(
    r"(?:https?:)?//(?:www\.)?wa\.me/[0-9A-Za-z+%\-]+"
    r"|(?:https?:)?//(?:www\.)?(?:api|web)\.whatsapp\.com/send/?\?[^\"'\s<>]*"
    r"|whatsapp://send\?[^\"'\s<>]*",
    re.IGNORECASE,
)

#: 추가로 찾은 번호를 별개 레코드로 만들 때 CID 뒤에 붙이는 구분자.
#: store.JsonlStore가 place_cid로 중복을 제거하므로 접미사가 없으면
#: 두 번째 번호부터 조용히 사라진다.
BRANCH_SEPARATOR = "#"


def wa_numbers_from_html(html: str, region: str = "") -> list[str]:
    """HTML에서 선언된 WhatsApp 번호를 등장 순서대로. 없으면 빈 리스트.

    두 가지 선언 형태를 읽는다.

    1. wa.me / api.whatsapp.com 링크 — 가장 명확하다. 먼저 나온다.
    region을 주면 그 나라 번호만 남긴다. 다국적 체인은 사이트에 전 지점
    번호를 깔아두기 때문에(실측: 런던 Sisu Clinic에 캐나다·미국 번호),
    수집 지역과 다른 나라 번호는 다른 지점의 것으로 본다.

    2. tel: 링크에 WhatsApp 라벨이 붙은 것 — 실측(런던 Dr Hala)에서 나왔다.
       업체가 링크는 tel:로 걸고 옆에 "WhatsApp"이라고 적어두는 형태다.
       국내 표기(07...)일 수 있어 region이 있어야 읽는다. 없으면 조용히
       틀린 번호를 만드느니 읽지 않는다.

    번호는 모두 phonenumbers 검증을 통과한 것만 남는다.
    """
    if not html or not html.strip():
        return []

    text = _unescape(html)
    numbers: list[str] = []
    seen: set[str] = set()

    for match in WA_URL_PATTERN.findall(text):
        number = wa_number_from_url(_normalize_url(match))
        if number and number not in seen and _belongs_to(number, region):
            seen.add(number)
            numbers.append(number)

    for number in _whatsapp_labelled_tel_numbers(text, region):
        if number not in seen:
            seen.add(number)
            numbers.append(number)

    return numbers


def branch_records(base: PlaceRecord, numbers: list[str]) -> list[PlaceRecord]:
    """찾은 번호마다 레코드 하나씩. 첫 번째는 원본을 confirmed로 승격시키고,
    나머지는 CID에 접미사를 붙여 별개 지점처럼 남긴다.

    맵에 적혀 있던 `phone_raw`는 건드리지 않는다 — 사이트의 상담 번호와
    맵의 대표번호가 다른 경우가 실제로 있고, 둘 다 남기는 편이 유용하다.
    """
    if not numbers:
        return [base]

    return [
        replace(
            base,
            place_cid=base.place_cid if index == 0 else f"{base.place_cid}{BRANCH_SEPARATOR}{index}",
            phone_e164=number,
            whatsapp_status=CONFIRMED,
            wa_link=wa_link(number),
            source=(
                SOURCE_SITE_CONFIRMS_MAP
                if number == base.phone_e164
                else SOURCE_SITE_LINK
            ),
        )
        for index, number in enumerate(numbers)
    ]


#: tel: 링크와 그 앵커 텍스트.
TEL_LINK_PATTERN = re.compile(r'<a[^>]+href="tel:([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)

#: 라벨을 찾을 때 링크 앞쪽으로 훑는 범위. 넓히면 "전화 또는 WhatsApp"처럼
#: 두 링크가 나란한 문장에서 엉뚱한 쪽을 집게 된다.
LABEL_WINDOW = 80


def _whatsapp_labelled_tel_numbers(text: str, region: str) -> list[str]:
    """앵커 텍스트나 바로 앞 라벨이 WhatsApp이라고 말하는 tel: 번호."""
    if not region:
        return []

    found: list[str] = []
    for match in TEL_LINK_PATTERN.finditer(text):
        raw, anchor = match.group(1), _strip_tags(match.group(2))
        if not _labelled_whatsapp(text, match.start(), anchor):
            continue
        e164, _ = normalize(raw, region)
        if e164:
            found.append(e164)
    return found


def _belongs_to(e164: str, region: str) -> bool:
    """이 번호가 수집 지역의 것인가. region이 없으면 걸러내지 않는다."""
    if not region:
        return True
    try:
        parsed = phonenumbers.parse(e164, None)
    except phonenumbers.NumberParseException:
        return False
    return phonenumbers.region_code_for_number(parsed) == region.upper()


def _labelled_whatsapp(text: str, link_start: int, anchor: str) -> bool:
    """이 tel: 링크가 WhatsApp이라고 표시돼 있는가.

    앵커 텍스트가 우선이다. 앞쪽 라벨도 보되, 그 사이에 다른 링크가 끝난
    흔적(`</a>`)이 있으면 남의 라벨이므로 인정하지 않는다.
    """
    if "whatsapp" in anchor.lower():
        return True
    before = text[max(0, link_start - LABEL_WINDOW) : link_start]
    if "</a>" in before:
        return False
    return "whatsapp" in _strip_tags(before).lower()


def _strip_tags(fragment: str) -> str:
    return re.sub(r"<[^>]+>", " ", fragment)


def _unescape(html: str) -> str:
    """HTML 엔티티와 JSON 백슬래시 이스케이프를 풀어 링크를 드러낸다."""
    return (
        html_module.unescape(html)
        .replace("\\/", "/")
        .replace('\\"', '"')
        .replace("\\'", "'")
    )


def _normalize_url(url: str) -> str:
    """링크 형태를 phone.wa_number_from_url이 아는 형태로 맞춘다.

    - 프로토콜 상대(`//wa.me/...`)에는 스킴을 붙인다.
    - 모바일 딥링크(`whatsapp://send?phone=...`)는 호스트가 `send`로 파싱되어
      호스트 검사를 통과하지 못하므로, 같은 의미의 웹 형태로 바꾼다.
    """
    if url.lower().startswith("whatsapp://send"):
        return "https://api.whatsapp.com/send" + url[len("whatsapp://send"):]
    return f"https:{url}" if url.startswith("//") else url
