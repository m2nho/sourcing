"""구글 맵 상세 패널 HTML에서 필드를 뽑는다.

셀렉터는 전부 이 파일에 모여 있다. 구글이 DOM을 바꾸면 여기만 고치고
tests/fixtures/ 의 픽스처를 새로 캡처한 것으로 갈아끼우면 된다.
"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

#: 장소 URL에 박혀 있는 안정적인 식별자. 예: !1s0x2e69f5...:0x123abc...
CID_PATTERN = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", re.IGNORECASE)

#: 전화번호가 들어 있는 버튼 속성의 접두사.
PHONE_ITEM_PREFIX = "phone:tel:"

NAME_SELECTOR = "h1"
CATEGORY_SELECTOR = 'button[jsaction*="category"]'
ADDRESS_SELECTOR = 'button[data-item-id="address"]'
WEBSITE_SELECTOR = 'a[data-item-id="authority"]'
RATING_BLOCK_SELECTOR = "div.F7nice"
PHONE_BUTTON_SELECTOR = "button[data-item-id]"
RATING_VALUE_SELECTOR = "span[aria-hidden]"

EMPTY_FIELDS = (
    "place_cid",
    "name",
    "category",
    "address",
    "phone_raw",
    "website",
    "rating",
    "reviews",
    "maps_url",
)


def cid_from_url(url: str) -> str:
    """장소 URL에서 CID를 뽑는다. 없으면 URL 자체를 식별자로 쓴다."""
    match = CID_PATTERN.search(url or "")
    return match.group(1) if match else (url or "")


def parse_panel(html: str, maps_url: str) -> dict[str, str]:
    """상세 패널 HTML을 필드 dict로. 없는 값은 빈 문자열."""
    result = dict.fromkeys(EMPTY_FIELDS, "")
    result["maps_url"] = maps_url or ""
    result["place_cid"] = cid_from_url(maps_url)
    if not html or not html.strip():
        return result

    tree = HTMLParser(html)
    result["name"] = _text(tree, NAME_SELECTOR)
    result["category"] = _text(tree, CATEGORY_SELECTOR)
    result["address"] = _text(tree, ADDRESS_SELECTOR)
    result["phone_raw"] = _phone(tree)
    result["website"] = _website(tree)
    rating, reviews = _rating_and_reviews(tree)
    result["rating"] = rating
    result["reviews"] = reviews
    return result


def _text(tree: HTMLParser, selector: str) -> str:
    node = tree.css_first(selector)
    return node.text(strip=True) if node else ""


def _phone(tree: HTMLParser) -> str:
    """data-item-id 속성에서 번호를 읽는다. 화면 텍스트와 달리 로케일 영향이 없다."""
    for button in tree.css(PHONE_BUTTON_SELECTOR):
        item_id = button.attributes.get("data-item-id") or ""
        if item_id.startswith(PHONE_ITEM_PREFIX):
            return item_id[len(PHONE_ITEM_PREFIX) :].strip()
    return ""


def _website(tree: HTMLParser) -> str:
    node = tree.css_first(WEBSITE_SELECTOR)
    return (node.attributes.get("href") or "").strip() if node else ""


def _rating_and_reviews(tree: HTMLParser) -> tuple[str, str]:
    """평점 블록에서 (평점, 리뷰수). 로케일마다 소수점·천단위 기호가 달라 숫자만 남긴다."""
    block = tree.css_first(RATING_BLOCK_SELECTOR)
    if block is None:
        return "", ""

    values = [node.text(strip=True) for node in block.css(RATING_VALUE_SELECTOR)]
    rating = ""
    reviews = ""
    for value in values:
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            continue
        if value.startswith("(") and not reviews:
            reviews = digits
        elif not rating:
            rating = value.replace(",", ".")
    return rating, reviews
