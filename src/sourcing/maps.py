"""구글 맵 브라우저 드라이버. 여기에는 파싱·판정 로직을 두지 않는다."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

FEED_SELECTOR = 'div[role="feed"]'
PLACE_LINK_SELECTOR = 'a[href*="/maps/place/"]'
PANEL_SELECTOR = 'div[role="main"]'
NAME_SELECTOR = "h1"

#: URL에 이 조각이 들어오면 구글이 자동화를 감지해 막은 것이다.
BLOCK_MARKERS = ("/sorry/", "consent.google.com")

#: 외부 사이트는 구글 맵보다 느리고 죽어 있는 경우도 많아 짧게 끊는다.
SITE_LOAD_TIMEOUT_MS = 20_000

#: 렌더링 후 위젯이 DOM에 붙을 시간. WhatsApp 버튼은 JS로 나중에 삽입되는
#: 경우가 흔해서 domcontentloaded 직후에는 아직 없다.
SITE_SETTLE_MS = 2_000

#: wa.me 프로필 조회. 페이지가 가벼워 짧게 잡는다.
WA_TIMEOUT_MS = 25_000
WA_SETTLE_MS = 2_000

#: 스크롤 높이가 이만큼 연속으로 그대로면 목록 끝으로 본다.
STAGNANT_LIMIT = 3


class Blocked(RuntimeError):
    """구글이 CAPTCHA나 동의 화면으로 막은 상태."""


@contextmanager
def browser(profile: Path, headful: bool, lang: str) -> Iterator[Page]:
    """영구 프로필 브라우저. 프로필을 유지해야 동의·세션을 매번 다시 통과하지 않는다."""
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=not headful,
            locale=lang,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            yield context.pages[0] if context.pages else context.new_page()
        finally:
            context.close()


def guard_blocked(page: Page) -> None:
    """차단 화면이면 Blocked를 던진다."""
    current = page.url or ""
    if any(marker in current for marker in BLOCK_MARKERS):
        raise Blocked(current)


def wait_for_human(page: Page, timeout_ms: int = 300_000) -> None:
    """headful 모드에서 사람이 CAPTCHA를 풀 때까지 기다린다."""
    print("\n>>> 구글이 확인 절차를 요구합니다. 열린 창에서 직접 해결해 주세요.")
    print(">>> 해결되면 자동으로 계속합니다 (최대 5분 대기).\n")
    page.wait_for_url(
        lambda url: not any(marker in url for marker in BLOCK_MARKERS),
        timeout=timeout_ms,
    )


def collect_place_urls(
    page: Page,
    url: str,
    scroll_pause: float = 1.2,
    max_scrolls: int = 40,
) -> list[str]:
    """검색 결과 피드를 끝까지 스크롤하고 장소 URL을 순서대로 돌려준다."""
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    guard_blocked(page)

    try:
        page.wait_for_selector(FEED_SELECTOR, timeout=15_000)
    except PlaywrightTimeout:
        # 결과가 하나뿐이면 구글이 목록 없이 장소 페이지로 바로 보낸다.
        return [page.url] if "/maps/place/" in page.url else []

    previous_height = -1
    stagnant = 0
    for _ in range(max_scrolls):
        page.eval_on_selector(FEED_SELECTOR, "el => el.scrollTo(0, el.scrollHeight)")
        page.wait_for_timeout(int(scroll_pause * 1000))
        height = page.eval_on_selector(FEED_SELECTOR, "el => el.scrollHeight")
        stagnant = stagnant + 1 if height == previous_height else 0
        previous_height = height
        if stagnant >= STAGNANT_LIMIT:
            break

    hrefs = page.eval_on_selector_all(
        f"{FEED_SELECTOR} {PLACE_LINK_SELECTOR}", "els => els.map(el => el.href)"
    )
    return list(dict.fromkeys(hrefs))


def open_place(page: Page, url: str) -> str:
    """장소 페이지를 열고 상세 패널의 innerHTML을 돌려준다."""
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    guard_blocked(page)
    page.wait_for_selector(NAME_SELECTOR, timeout=20_000)
    return page.inner_html(PANEL_SELECTOR)


def open_site_page(page: Page) -> Page:
    """외부 사이트 방문용 페이지를 같은 브라우저 컨텍스트에 연다.

    구글 맵 페이지와 분리해 두어야 사이트 방문이 맵 쪽 상태를 흔들지 않는다.
    """
    return page.context.new_page()


def fetch_site_html(page: Page, url: str) -> str:
    """웹사이트를 렌더링해 HTML을 돌려준다.

    정적 요청이 아니라 브라우저로 받는 이유: WhatsApp 버튼을 JS 위젯으로
    삽입하는 사이트가 흔해서, 원본 HTML만 봐서는 링크가 보이지 않는다.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=SITE_LOAD_TIMEOUT_MS)
    page.wait_for_timeout(SITE_SETTLE_MS)
    return page.content()


#: wa.me 페이지 상단의 고정 메뉴. 프로필 이름을 읽을 때 걷어낸다.
WA_CHROME = "Features Privacy Blog Apps Help Center For Business Log In Download"


def fetch_wa_profile(page: Page, e164: str) -> str:
    """wa.me에서 이 번호의 WhatsApp 프로필 이름을 읽는다. 없으면 "".

    등록된 비즈니스 계정이면 상호가 보이고, 미등록이거나 개인 계정이면
    "Chat on WhatsApp with <번호>"만 보인다. 메시지는 보내지 않는다 -
    공개 페이지를 여는 것뿐이다.
    """
    page.goto(
        f"https://wa.me/{e164.lstrip('+')}", wait_until="networkidle", timeout=WA_TIMEOUT_MS
    )
    page.wait_for_timeout(WA_SETTLE_MS)
    body = page.evaluate("document.body.innerText") or ""
    text = " ".join(body.split())
    if text.startswith(WA_CHROME):
        text = text[len(WA_CHROME) :].strip()
    head = text.split("Open app")[0].strip().lstrip("\u200e")
    if not head or head.lower().startswith("chat on whatsapp with"):
        return ""
    return head
