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

from sourcing.phone import CONFIRMED, wa_number_from_url, wa_link
from sourcing.store import PlaceRecord

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


def wa_numbers_from_html(html: str) -> list[str]:
    """HTML에서 선언된 WhatsApp 번호를 등장 순서대로. 없으면 빈 리스트.

    번호는 phone.wa_number_from_url의 검증 관문을 통과한 것만 남는다 —
    wa.me/message/<코드> 같은 단축링크와 유효하지 않은 번호는 걸러진다.
    """
    if not html or not html.strip():
        return []

    text = _unescape(html)
    numbers: list[str] = []
    seen: set[str] = set()
    for match in WA_URL_PATTERN.findall(text):
        number = wa_number_from_url(_normalize_url(match))
        if number and number not in seen:
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
        )
        for index, number in enumerate(numbers)
    ]


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
