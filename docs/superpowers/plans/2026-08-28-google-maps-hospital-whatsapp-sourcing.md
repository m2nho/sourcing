# 구글 맵 병원 WhatsApp 소싱 도구 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 키워드와 지역을 받아 구글 맵에서 병원을 훑고, WhatsApp 연락 가능 번호를 CSV로 뽑는 CLI를 만든다.

**Architecture:** Playwright가 구글 맵을 열어 상세 패널 HTML만 캡처하고, 파싱·번호정규화·격자계산·저장은 전부 네트워크 없는 순수 모듈이 맡는다. 브라우저 계층에 로직을 두지 않는 것으로 DOM 변경 리스크와 테스트 불가능 영역을 동시에 줄인다. 레코드는 JSONL에 즉시 flush하고 CSV는 JSONL에서 매번 재생성해 멱등성과 재개를 얻는다.

**Tech Stack:** Python 3.13, uv, mise, Playwright(Chromium), phonenumbers, selectolax, pytest

**Spec:** `docs/superpowers/specs/2026-08-28-google-maps-hospital-whatsapp-sourcing-design.md`

## Global Constraints

- Python `>=3.13`. `mise.toml`에 `python = "3.13"` 고정. 툴체인은 프로젝트 단위로만 잡는다 (전역 설치 금지).
- 의존성은 `uv add`로만 추가한다. 런타임 의존성은 `playwright`, `phonenumbers`, `selectolax` 셋뿐. 개발 의존성은 `pytest`.
- 패키지 레이아웃은 `src/sourcing/`. 빌드 백엔드는 `uv_build`.
- 커밋 메시지에 `Co-Authored-By` 트레일러나 생성도구 문구를 넣지 않는다. 커밋 신원은 저장소 설정값을 그대로 쓴다.
- 순수 모듈(`grid`, `parse`, `phone`, `store`)은 네트워크·브라우저 없이 테스트 가능해야 한다. `maps.py`에는 분기 로직을 두지 않는다.
- CSV 컬럼 순서는 고정이다: `place_cid, name, category, address, phone_raw, phone_e164, phone_type, whatsapp_status, wa_link, website, rating, reviews, maps_url, query, tile, scraped_at`
- WhatsApp 상태 값은 `confirmed` / `candidate` / `unlikely` 세 개뿐이다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `mise.toml` | Python 3.13 고정 |
| `pyproject.toml` | 패키지 메타, 의존성, `sourcing` 콘솔 스크립트 |
| `src/sourcing/phone.py` | [순수] 전화번호 정규화·유형판정, wa.me URL에서 번호 추출, WhatsApp 상태 분류 |
| `src/sourcing/grid.py` | [순수] 중심+반경+N → 타일 목록, 타일 → 구글 맵 검색 URL |
| `src/sourcing/store.py` | [순수+파일] `PlaceRecord` 정의, JSONL 추가/재개, CSV 내보내기 |
| `src/sourcing/parse.py` | [순수] 상세 패널 HTML → 필드 dict |
| `src/sourcing/maps.py` | [I/O] Playwright 브라우저 컨텍스트, 피드 스크롤, 패널 HTML 캡처, 차단 감지 |
| `src/sourcing/cli.py` | 인자 파싱, 오케스트레이션, 종료 코드 |
| `tests/test_phone.py` 등 | 순수 모듈 단위 테스트 |
| `tests/fixtures/*.html` | 상세 패널 HTML 픽스처 |
| `README.md` | 설치·사용법·한계 |

**설계 문서 대비 변경 2가지 (의도적):**

1. 셀렉터를 `maps.py`가 아니라 `parse.py`에 둔다. `maps.py`가 패널의 `innerHTML`만 넘기고 `parse.py`가 selectolax로 추출하면, 셀렉터 로직 전체가 픽스처로 단위 테스트된다. 이 때문에 `selectolax` 의존성이 하나 늘어난다.
2. `search_url()`을 `grid.py`에 둔다. 순수 함수라 테스트 가능하고, `maps.py`를 I/O 전용으로 유지할 수 있다.

---

## Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `mise.toml`, `pyproject.toml`, `README.md`, `src/sourcing/__init__.py`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Consumes: 없음
- Produces: `uv run pytest`가 도는 프로젝트. 콘솔 스크립트 이름 `sourcing`.

- [ ] **Step 1: 툴체인 고정 및 프로젝트 초기화**

```bash
cd /home/ubuntu/doublej/sourcing
mise use python@3.13
uv init --lib --name sourcing --python 3.13
```

`uv init --lib`가 `src/sourcing/`을 만든다. 만들어진 `src/sourcing/py.typed`나 샘플 함수는 남겨둬도 무방하다.

- [ ] **Step 2: 의존성 추가**

```bash
uv add playwright phonenumbers selectolax
uv add --dev pytest
uv run playwright install chromium
```

`playwright install`은 Chromium 바이너리를 받는다. 수백 MB이고 시간이 걸린다.

- [ ] **Step 3: pyproject에 콘솔 스크립트와 pytest 설정 추가**

`pyproject.toml`에 다음 블록을 추가한다 (`[project]`와 `[build-system]`은 `uv init`이 만든 것을 유지):

```toml
[project.scripts]
sourcing = "sourcing.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: 스캐폴딩 확인 테스트를 쓴다**

`tests/test_scaffold.py`:

```python
def test_package_imports():
    import sourcing

    assert sourcing is not None


def test_dependencies_available():
    import phonenumbers
    import selectolax.parser

    assert phonenumbers.parse("+6281234567890", None) is not None
    assert selectolax.parser.HTMLParser("<h1>x</h1>").css_first("h1").text() == "x"
```

- [ ] **Step 5: 테스트 실행**

Run: `uv run pytest -v`
Expected: 2 passed

- [ ] **Step 6: README 초안**

`README.md`:

```markdown
# sourcing

구글 맵에서 병원·클리닉의 WhatsApp 연락처를 수집하는 CLI.

## 설치

```
mise install
uv sync
uv run playwright install chromium
```

## 사용

```
uv run sourcing "rumah sakit" --region ID --lang id --out out/jakarta.csv
```

자세한 옵션은 `uv run sourcing --help`.
```

- [ ] **Step 7: 커밋**

```bash
git add -A
git commit -m "프로젝트 스캐폴딩: uv 패키지, 의존성, pytest 설정"
```

---

## Task 2: 전화번호 정규화와 WhatsApp 상태 분류

**Files:**
- Create: `src/sourcing/phone.py`
- Test: `tests/test_phone.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `CONFIRMED = "confirmed"`, `CANDIDATE = "candidate"`, `UNLIKELY = "unlikely"`
  - `normalize(raw: str, region: str) -> tuple[str, str]` — `(E.164, 유형명)`. 실패 시 `("", "unknown")`
  - `wa_number_from_url(url: str) -> str` — WhatsApp 링크에서 `+E164`. 아니면 `""`
  - `classify(raw_phone: str, website: str, region: str) -> PhoneVerdict`
  - `@dataclass(frozen=True) PhoneVerdict(e164: str, type: str, status: str, wa_link: str)`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_phone.py`:

```python
import pytest

from sourcing.phone import (
    CANDIDATE,
    CONFIRMED,
    UNLIKELY,
    classify,
    normalize,
    wa_number_from_url,
)


@pytest.mark.parametrize(
    "raw,region,expected_e164,expected_type",
    [
        ("0812-3456-7890", "ID", "+6281234567890", "mobile"),
        ("+62 812 3456 7890", "ID", "+6281234567890", "mobile"),
        ("(021) 3915-000", "ID", "+62213915000", "fixed_line"),
        ("021-29962888", "ID", "+622129962888", "fixed_line"),
        ("0912 345 678", "VN", "+84912345678", "mobile"),
        ("028 3822 5052", "VN", "+842838225052", "fixed_line"),
        ("0917 123 4567", "PH", "+639171234567", "mobile"),
        ("(02) 8888 8888", "PH", "+63288888888", "fixed_line"),
        ("(415) 555-2671", "US", "+14155552671", "fixed_line_or_mobile"),
    ],
)
def test_normalize_valid_numbers(raw, region, expected_e164, expected_type):
    assert normalize(raw, region) == (expected_e164, expected_type)


@pytest.mark.parametrize("raw", ["", "   ", "not a phone", "123"])
def test_normalize_rejects_garbage(raw):
    assert normalize(raw, "ID") == ("", "unknown")


def test_normalize_service_number_is_not_mobile():
    # 인니 UAN(1500-135)은 유효하지만 모바일이 아니다
    e164, ntype = normalize("1500-135", "ID")
    assert e164 == "+621500135"
    assert ntype == "unknown"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://wa.me/6281234567890", "+6281234567890"),
        ("https://wa.me/6281234567890?text=Halo", "+6281234567890"),
        ("wa.me/6281234567890", "+6281234567890"),
        ("https://api.whatsapp.com/send?phone=6281234567890", "+6281234567890"),
        ("https://api.whatsapp.com/send/?phone=%2B6281234567890", "+6281234567890"),
        ("https://rscontoh.co.id/kontak", ""),
        ("", ""),
        ("https://chat.whatsapp.com/AbCdEf123", ""),
    ],
)
def test_wa_number_from_url(url, expected):
    assert wa_number_from_url(url) == expected


def test_classify_website_wa_link_is_confirmed():
    v = classify("(021) 3915-000", "https://wa.me/6281234567890", "ID")
    assert v.status == CONFIRMED
    assert v.e164 == "+6281234567890"
    assert v.type == "mobile"
    assert v.wa_link == "https://wa.me/6281234567890"


def test_classify_mobile_is_candidate():
    v = classify("0812-3456-7890", "https://rscontoh.co.id", "ID")
    assert v.status == CANDIDATE
    assert v.e164 == "+6281234567890"
    assert v.wa_link == "https://wa.me/6281234567890"


def test_classify_fixed_line_or_mobile_is_candidate():
    v = classify("(415) 555-2671", "", "US")
    assert v.status == CANDIDATE


def test_classify_fixed_line_is_unlikely():
    v = classify("(021) 3915-000", "https://rscontoh.co.id", "ID")
    assert v.status == UNLIKELY
    assert v.e164 == "+62213915000"
    assert v.wa_link == ""


def test_classify_no_phone_is_unlikely():
    v = classify("", "", "ID")
    assert v.status == UNLIKELY
    assert v.e164 == ""
    assert v.type == "unknown"
    assert v.wa_link == ""
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_phone.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sourcing.phone'`

- [ ] **Step 3: 구현**

`src/sourcing/phone.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_phone.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/sourcing/phone.py tests/test_phone.py
git commit -m "전화번호 정규화와 WhatsApp 상태 분류 추가"
```

---

## Task 3: 격자 타일링과 검색 URL

**Files:**
- Create: `src/sourcing/grid.py`
- Test: `tests/test_grid.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `@dataclass(frozen=True) Tile(lat: float, lng: float, zoom: int)` — `.label` 프로퍼티는 `"-6.20000,106.80000,13z"` 형식
  - `zoom_for(cell_diameter_km: float) -> int`
  - `plan_tiles(center: tuple[float, float] | None, radius_km: float, n: int) -> list[Tile | None]` — center가 None이면 `[None]`
  - `search_url(keyword: str, tile: Tile | None, lang: str) -> str`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_grid.py`:

```python
import math

import pytest

from sourcing.grid import Tile, plan_tiles, search_url, zoom_for


def test_no_center_yields_single_viewportless_tile():
    assert plan_tiles(None, 10.0, 3) == [None]


def test_grid_produces_n_squared_tiles():
    tiles = plan_tiles((-6.2, 106.8), 10.0, 3)
    assert len(tiles) == 9
    assert all(isinstance(t, Tile) for t in tiles)


def test_odd_grid_center_tile_matches_center():
    tiles = plan_tiles((-6.2, 106.8), 10.0, 3)
    centers = [(round(t.lat, 6), round(t.lng, 6)) for t in tiles]
    assert (-6.2, 106.8) in centers


def test_longitude_spacing_widens_with_latitude():
    # cos(60도) = 0.5 이므로 경도 간격은 위도 간격의 정확히 2배여야 한다
    tiles = plan_tiles((60.0, 10.0), 10.0, 3)
    lats = sorted({round(t.lat, 9) for t in tiles})
    lngs = sorted({round(t.lng, 9) for t in tiles})
    dlat = lats[1] - lats[0]
    dlng = lngs[1] - lngs[0]
    assert dlng == pytest.approx(dlat * 2, rel=1e-6)


def test_tiles_cover_the_bounding_box():
    tiles = plan_tiles((0.0, 0.0), 10.0, 2)
    # 반경 10km -> 한 변 20km, 셀 10km. 셀 중심은 중심에서 +-5km 떨어진다.
    half_cell_deg = 5.0 / 111.32
    lats = sorted({round(t.lat, 9) for t in tiles})
    assert lats[0] == pytest.approx(-half_cell_deg, rel=1e-9)
    assert lats[1] == pytest.approx(half_cell_deg, rel=1e-9)


def test_grid_size_must_be_positive():
    with pytest.raises(ValueError):
        plan_tiles((0.0, 0.0), 10.0, 0)


@pytest.mark.parametrize(
    "cell_km,expected",
    [(1.0, 15), (2.0, 14), (4.0, 13), (0.01, 17), (5000.0, 10), (0.0, 14)],
)
def test_zoom_for(cell_km, expected):
    assert zoom_for(cell_km) == expected


def test_search_url_without_tile_has_no_viewport():
    url = search_url("rumah sakit", None, "id")
    assert url == "https://www.google.com/maps/search/rumah+sakit?hl=id"


def test_search_url_with_tile_embeds_viewport():
    url = search_url("rumah sakit", Tile(-6.2, 106.8, 13), "id")
    assert url == (
        "https://www.google.com/maps/search/rumah+sakit/@-6.200000,106.800000,13z?hl=id"
    )


def test_search_url_escapes_keyword():
    assert "b%E1%BB%87nh+vi%E1%BB%87n" in search_url("bệnh viện", None, "vi")


def test_tile_label_is_stable():
    assert Tile(-6.2, 106.8, 13).label == "-6.20000,106.80000,13z"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_grid.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sourcing.grid'`

- [ ] **Step 3: 구현**

`src/sourcing/grid.py`:

```python
"""검색 지역을 격자로 쪼개고 구글 맵 검색 URL을 만든다."""

from __future__ import annotations

import math
from dataclasses import dataclass
from urllib.parse import quote_plus

#: 위도 1도의 거리(km). 경도는 여기에 cos(위도)를 곱해 보정한다.
KM_PER_DEGREE = 111.32

#: 셀 크기를 특정할 수 없을 때 쓰는 줌.
DEFAULT_ZOOM = 14

MIN_ZOOM = 10
MAX_ZOOM = 17


@dataclass(frozen=True)
class Tile:
    lat: float
    lng: float
    zoom: int

    @property
    def label(self) -> str:
        """레코드 추적용 짧은 식별자."""
        return f"{self.lat:.5f},{self.lng:.5f},{self.zoom}z"


def zoom_for(cell_diameter_km: float) -> int:
    """셀이 뷰포트를 대략 채우는 줌 레벨. 1km -> 15, 2km -> 14, 4km -> 13."""
    if cell_diameter_km <= 0:
        return DEFAULT_ZOOM
    raw = round(15 - math.log2(cell_diameter_km))
    return max(MIN_ZOOM, min(MAX_ZOOM, raw))


def plan_tiles(
    center: tuple[float, float] | None, radius_km: float, n: int
) -> list[Tile | None]:
    """중심과 반경을 덮는 n x n 타일. center가 없으면 뷰포트 없는 단일 검색."""
    if center is None:
        return [None]
    if n < 1:
        raise ValueError("grid must be >= 1")

    lat, lng = center
    cell_km = (2 * radius_km) / n
    dlat = cell_km / KM_PER_DEGREE
    dlng = cell_km / (KM_PER_DEGREE * math.cos(math.radians(lat)))
    zoom = zoom_for(cell_km)
    offset = (n - 1) / 2

    return [
        Tile(lat + (row - offset) * dlat, lng + (col - offset) * dlng, zoom)
        for row in range(n)
        for col in range(n)
    ]


def search_url(keyword: str, tile: Tile | None, lang: str) -> str:
    """구글 맵 검색 URL. 타일이 있으면 뷰포트를 좌표로 고정한다."""
    query = quote_plus(keyword)
    if tile is None:
        return f"https://www.google.com/maps/search/{query}?hl={lang}"
    return (
        f"https://www.google.com/maps/search/{query}"
        f"/@{tile.lat:.6f},{tile.lng:.6f},{tile.zoom}z?hl={lang}"
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_grid.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/sourcing/grid.py tests/test_grid.py
git commit -m "격자 타일링과 구글 맵 검색 URL 생성 추가"
```

---

## Task 4: 레코드 저장, 재개, CSV 내보내기

**Files:**
- Create: `src/sourcing/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `@dataclass PlaceRecord` — 필드 순서가 곧 CSV 컬럼 순서 (Global Constraints 참조). `place_cid`, `name` 외 전부 기본값 있음
  - `CSV_COLUMNS: list[str]`
  - `JsonlStore(path: Path)` — `.seen_cids() -> set[str]`, `.append(record) -> None`, `.records() -> Iterator[PlaceRecord]`
  - `export_csv(store: JsonlStore, out_path: Path) -> int` — 쓴 행 수를 돌려준다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_store.py`:

```python
import json

from sourcing.store import CSV_COLUMNS, JsonlStore, PlaceRecord, export_csv


def make_record(cid: str, name: str = "RS Contoh") -> PlaceRecord:
    return PlaceRecord(place_cid=cid, name=name, phone_e164="+6281234567890")


def test_csv_columns_are_the_agreed_order():
    assert CSV_COLUMNS == [
        "place_cid",
        "name",
        "category",
        "address",
        "phone_raw",
        "phone_e164",
        "phone_type",
        "whatsapp_status",
        "wa_link",
        "website",
        "rating",
        "reviews",
        "maps_url",
        "query",
        "tile",
        "scraped_at",
    ]


def test_seen_cids_is_empty_for_missing_file(tmp_path):
    store = JsonlStore(tmp_path / "missing" / "raw.jsonl")
    assert store.seen_cids() == set()


def test_append_then_seen_cids_round_trips(tmp_path):
    store = JsonlStore(tmp_path / "raw.jsonl")
    store.append(make_record("0xa:0xb"))
    store.append(make_record("0xc:0xd"))
    assert store.seen_cids() == {"0xa:0xb", "0xc:0xd"}


def test_append_writes_one_json_object_per_line(tmp_path):
    path = tmp_path / "raw.jsonl"
    store = JsonlStore(path)
    store.append(make_record("0xa:0xb", name="RS Ünïcode 베트남"))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["name"] == "RS Ünïcode 베트남"


def test_records_skips_duplicate_cids_keeping_the_first(tmp_path):
    store = JsonlStore(tmp_path / "raw.jsonl")
    store.append(make_record("0xa:0xb", name="첫번째"))
    store.append(make_record("0xa:0xb", name="두번째"))
    records = list(store.records())
    assert len(records) == 1
    assert records[0].name == "첫번째"


def test_records_skips_corrupt_lines(tmp_path):
    path = tmp_path / "raw.jsonl"
    store = JsonlStore(path)
    store.append(make_record("0xa:0xb"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")
        fh.write("\n")
    assert len(list(store.records())) == 1


def test_export_csv_writes_header_and_rows(tmp_path):
    store = JsonlStore(tmp_path / "raw.jsonl")
    store.append(make_record("0xa:0xb"))
    store.append(make_record("0xc:0xd"))
    out = tmp_path / "out" / "result.csv"
    assert export_csv(store, out) == 2
    text = out.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(text.strip().splitlines()) == 3


def test_export_csv_is_idempotent(tmp_path):
    store = JsonlStore(tmp_path / "raw.jsonl")
    store.append(make_record("0xa:0xb"))
    out = tmp_path / "result.csv"
    export_csv(store, out)
    first = out.read_bytes()
    export_csv(store, out)
    assert out.read_bytes() == first
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sourcing.store'`

- [ ] **Step 3: 구현**

`src/sourcing/store.py`:

```python
"""수집 레코드의 정의, 재개 가능한 JSONL 저장, CSV 내보내기."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class PlaceRecord:
    """맵 장소 하나. 필드 선언 순서가 CSV 컬럼 순서다."""

    place_cid: str
    name: str
    category: str = ""
    address: str = ""
    phone_raw: str = ""
    phone_e164: str = ""
    phone_type: str = "unknown"
    whatsapp_status: str = "unlikely"
    wa_link: str = ""
    website: str = ""
    rating: str = ""
    reviews: str = ""
    maps_url: str = ""
    query: str = ""
    tile: str = ""
    scraped_at: str = ""


CSV_COLUMNS: list[str] = [f.name for f in fields(PlaceRecord)]


class JsonlStore:
    """레코드마다 즉시 flush하는 append-only 저장소. 중단해도 유실이 없다."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def seen_cids(self) -> set[str]:
        """이미 수집한 CID 집합. 재개와 타일 간 중복 제거에 쓴다."""
        return {rec.place_cid for rec in self.records()}

    def append(self, record: PlaceRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            fh.flush()

    def records(self) -> Iterator[PlaceRecord]:
        """CID 기준 중복을 제거한 레코드. 같은 CID는 처음 것만 남는다."""
        if not self.path.exists():
            return
        seen: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            cid = data.get("place_cid", "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            yield PlaceRecord(**{key: data.get(key, "") for key in CSV_COLUMNS})


def export_csv(store: JsonlStore, out_path: Path) -> int:
    """JSONL 전체에서 CSV를 다시 만든다. 몇 번 호출해도 결과가 같다."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    # utf-8-sig: 엑셀이 인니어/베트남어 상호를 깨뜨리지 않게 BOM을 붙인다.
    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for record in store.records():
            writer.writerow(asdict(record))
            written += 1
    return written
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_store.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/sourcing/store.py tests/test_store.py
git commit -m "재개 가능한 JSONL 저장소와 CSV 내보내기 추가"
```

---

## Task 5: 상세 패널 HTML 파싱

**Files:**
- Create: `src/sourcing/parse.py`, `tests/fixtures/place_panel_id.html`, `tests/fixtures/place_panel_en_minimal.html`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `parse_panel(html: str, maps_url: str) -> dict[str, str]` — 키: `place_cid`, `name`, `category`, `address`, `phone_raw`, `website`, `rating`, `reviews`, `maps_url`
  - `cid_from_url(url: str) -> str`

파싱 전략의 핵심: 전화번호를 화면 텍스트가 아니라 `data-item-id="phone:tel:+62 812-..."`
속성에서 읽는다. 이 속성은 UI 언어나 표기 형식이 바뀌어도 그대로다. 주소도 같은 이유로
`data-item-id="address"` 버튼을 쓰되, 값은 로케일 접두사가 붙는 `aria-label`이 아니라
버튼의 텍스트에서 가져온다.

- [ ] **Step 1: 픽스처를 만든다**

`tests/fixtures/place_panel_id.html` — 인니어 UI, 웹사이트가 wa.me인 클리닉:

```html
<div role="main" aria-label="Klinik Contoh">
  <h1 class="DUwDvf">Klinik Contoh Jakarta</h1>
  <button jsaction="pane.wfvdle17.category" class="DkEaL">Klinik Umum</button>
  <div class="F7nice">
    <span><span aria-hidden="true">4,3</span></span>
    <span><span aria-label="1.234 ulasan"><span aria-hidden="true">(1.234)</span></span></span>
  </div>
  <button data-item-id="address" aria-label="Alamat: Jl. Contoh No. 1, Jakarta Selatan">
    <div class="Io6YTe">Jl. Contoh No. 1, Jakarta Selatan</div>
  </button>
  <a data-item-id="authority" href="https://wa.me/6281234567890">wa.me</a>
  <button data-item-id="phone:tel:+62 812-3456-7890" aria-label="Telepon: +62 812-3456-7890">
    <div class="Io6YTe">+62 812-3456-7890</div>
  </button>
</div>
```

`tests/fixtures/place_panel_en_minimal.html` — 영어 UI, 전화·웹사이트·평점이 전부 없는 병원:

```html
<div role="main" aria-label="Contoh General Hospital">
  <h1 class="DUwDvf">Contoh General Hospital</h1>
  <button jsaction="pane.wfvdle17.category" class="DkEaL">General hospital</button>
  <button data-item-id="address" aria-label="Address: 12 Example Road, Manila">
    <div class="Io6YTe">12 Example Road, Manila</div>
  </button>
</div>
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_parse.py`:

```python
from pathlib import Path

import pytest

from sourcing.parse import cid_from_url, parse_panel

FIXTURES = Path(__file__).parent / "fixtures"

PLACE_URL = (
    "https://www.google.com/maps/place/Klinik+Contoh/"
    "@-6.2,106.8,17z/data=!3m1!4b1!4m6!3m5!1s0x2e69f5d1a2b3c4d5:0x123abc456def7890!8m2"
)


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_cid_from_url_extracts_hex_pair():
    assert cid_from_url(PLACE_URL) == "0x2e69f5d1a2b3c4d5:0x123abc456def7890"


def test_cid_from_url_falls_back_to_url_when_absent():
    url = "https://www.google.com/maps/place/Klinik+Contoh/@-6.2,106.8,17z"
    assert cid_from_url(url) == url


def test_parses_indonesian_panel():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["name"] == "Klinik Contoh Jakarta"
    assert result["category"] == "Klinik Umum"
    assert result["address"] == "Jl. Contoh No. 1, Jakarta Selatan"
    assert result["place_cid"] == "0x2e69f5d1a2b3c4d5:0x123abc456def7890"
    assert result["maps_url"] == PLACE_URL


def test_phone_comes_from_the_data_item_id_attribute():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["phone_raw"] == "+62 812-3456-7890"


def test_website_href_is_taken_verbatim():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["website"] == "https://wa.me/6281234567890"


def test_rating_is_normalised_to_a_dot_decimal():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["rating"] == "4.3"


def test_review_count_strips_locale_separators():
    result = parse_panel(load("place_panel_id.html"), PLACE_URL)
    assert result["reviews"] == "1234"


def test_missing_fields_become_empty_strings():
    result = parse_panel(load("place_panel_en_minimal.html"), PLACE_URL)
    assert result["name"] == "Contoh General Hospital"
    assert result["address"] == "12 Example Road, Manila"
    assert result["phone_raw"] == ""
    assert result["website"] == ""
    assert result["rating"] == ""
    assert result["reviews"] == ""


def test_empty_html_yields_all_empty_but_keeps_url():
    result = parse_panel("", PLACE_URL)
    assert result["name"] == ""
    assert result["maps_url"] == PLACE_URL
    assert set(result) == {
        "place_cid",
        "name",
        "category",
        "address",
        "phone_raw",
        "website",
        "rating",
        "reviews",
        "maps_url",
    }
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sourcing.parse'`

- [ ] **Step 4: 구현**

`src/sourcing/parse.py`:

```python
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
    for button in tree.css("button[data-item-id]"):
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

    values = [node.text(strip=True) for node in block.css("span[aria-hidden]")]
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_parse.py -v`
Expected: 전부 PASS

- [ ] **Step 6: 전체 테스트 실행**

Run: `uv run pytest -v`
Expected: 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add src/sourcing/parse.py tests/test_parse.py tests/fixtures
git commit -m "상세 패널 HTML 파서 추가"
```

---

## Task 6: Playwright 브라우저 드라이버

**Files:**
- Create: `src/sourcing/maps.py`
- Test: 단위 테스트 없음. Task 7에서 실제 실행으로 검증한다.

**Interfaces:**
- Consumes: `sourcing.grid.Tile`, `sourcing.grid.search_url`
- Produces:
  - `class Blocked(RuntimeError)`
  - `browser(profile: Path, headful: bool, lang: str)` — `Page`를 내주는 컨텍스트 매니저
  - `collect_place_urls(page, url: str, scroll_pause: float = 1.2, max_scrolls: int = 40) -> list[str]`
  - `open_place(page, url: str) -> str` — 상세 패널 innerHTML
  - `wait_for_human(page) -> None` — headful에서 CAPTCHA 수동 해제 대기

이 파일에는 분기 로직을 두지 않는다. 셀렉터 상수, 스크롤, 네비게이션, 차단 감지가 전부다.

- [ ] **Step 1: 구현**

`src/sourcing/maps.py`:

```python
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
```

- [ ] **Step 2: 임포트가 되는지만 확인**

Run: `uv run python -c "from sourcing import maps; print(maps.FEED_SELECTOR)"`
Expected: `div[role="feed"]`

- [ ] **Step 3: 커밋**

```bash
git add src/sourcing/maps.py
git commit -m "구글 맵 Playwright 드라이버 추가"
```

---

## Task 7: CLI 오케스트레이션과 실제 실행 검증

**Files:**
- Create: `src/sourcing/cli.py`
- Modify: `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `grid.plan_tiles`, `grid.search_url`, `grid.Tile`, `maps.browser`, `maps.collect_place_urls`, `maps.open_place`, `maps.wait_for_human`, `maps.Blocked`, `parse.parse_panel`, `parse.cid_from_url`, `phone.classify`, `store.JsonlStore`, `store.PlaceRecord`, `store.export_csv`
- Produces: `main(argv: list[str] | None = None) -> int`, `parse_args(argv) -> argparse.Namespace`, `parse_center(value: str) -> tuple[float, float]`, `build_record(fields: dict, region: str, query: str, tile_label: str) -> PlaceRecord`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_cli.py`:

```python
import pytest

from sourcing.cli import build_record, parse_args, parse_center


def test_parse_center_accepts_lat_lng():
    assert parse_center("-6.2,106.8") == (-6.2, 106.8)


def test_parse_center_tolerates_spaces():
    assert parse_center(" -6.2 , 106.8 ") == (-6.2, 106.8)


@pytest.mark.parametrize("value", ["-6.2", "a,b", "", "1,2,3"])
def test_parse_center_rejects_bad_input(value):
    with pytest.raises(Exception):
        parse_center(value)


def test_args_require_region():
    with pytest.raises(SystemExit):
        parse_args(["rumah sakit"])


def test_args_defaults():
    args = parse_args(["rumah sakit", "--region", "ID"])
    assert args.keyword == "rumah sakit"
    assert args.region == "ID"
    assert args.lang == "en"
    assert args.center is None
    assert args.grid == 3
    assert args.radius_km == 10.0


def test_build_record_marks_wa_website_confirmed():
    fields = {
        "place_cid": "0xa:0xb",
        "name": "Klinik Contoh",
        "category": "Klinik",
        "address": "Jl. Contoh 1",
        "phone_raw": "(021) 3915-000",
        "website": "https://wa.me/6281234567890",
        "rating": "4.3",
        "reviews": "1234",
        "maps_url": "https://maps.google.com/x",
    }
    record = build_record(fields, region="ID", query="rumah sakit", tile_label="t1")
    assert record.whatsapp_status == "confirmed"
    assert record.phone_e164 == "+6281234567890"
    assert record.wa_link == "https://wa.me/6281234567890"
    assert record.phone_raw == "(021) 3915-000"
    assert record.query == "rumah sakit"
    assert record.tile == "t1"
    assert record.scraped_at.endswith("+00:00")


def test_build_record_marks_mobile_candidate():
    fields = {
        "place_cid": "0xa:0xb",
        "name": "RS Contoh",
        "category": "",
        "address": "",
        "phone_raw": "0812-3456-7890",
        "website": "https://rscontoh.co.id",
        "rating": "",
        "reviews": "",
        "maps_url": "",
    }
    record = build_record(fields, region="ID", query="q", tile_label="")
    assert record.whatsapp_status == "candidate"
    assert record.phone_type == "mobile"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sourcing.cli'`

- [ ] **Step 3: 구현**

`src/sourcing/cli.py`:

```python
"""CLI 진입점. 타일을 돌며 장소를 수집하고 CSV로 내보낸다."""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sourcing import maps
from sourcing.grid import plan_tiles, search_url
from sourcing.parse import cid_from_url, parse_panel
from sourcing.phone import classify
from sourcing.store import JsonlStore, PlaceRecord, export_csv

EXIT_OK = 0
EXIT_BLOCKED = 2


def parse_center(value: str) -> tuple[float, float]:
    parts = [part.strip() for part in (value or "").split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--center 형식은 LAT,LNG 입니다")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--center 좌표를 숫자로 읽을 수 없습니다") from exc


def parse_delay(value: str) -> tuple[float, float]:
    parts = [part.strip() for part in (value or "").split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--delay 형식은 MIN,MAX 입니다")
    try:
        low, high = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--delay 값을 숫자로 읽을 수 없습니다") from exc
    if low < 0 or high < low:
        raise argparse.ArgumentTypeError("--delay 는 0 <= MIN <= MAX 여야 합니다")
    return low, high


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "sourcing"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sourcing",
        description="구글 맵에서 병원·클리닉의 WhatsApp 연락처를 수집한다.",
    )
    parser.add_argument("keyword", help='검색 키워드. 예: "rumah sakit"')
    parser.add_argument(
        "--region", required=True, help="전화번호 정규화 기준 국가코드. 예: ID, VN, PH"
    )
    parser.add_argument("--lang", default="en", help="구글 맵 UI 언어 (기본값: en)")
    parser.add_argument("--out", type=Path, default=None, help="CSV 출력 경로")
    parser.add_argument("--center", type=parse_center, default=None, help="격자 중심 LAT,LNG")
    parser.add_argument("--radius-km", type=float, default=10.0, help="격자 반경 km")
    parser.add_argument("--grid", type=int, default=3, help="한 변의 타일 수 (N x N)")
    parser.add_argument("--delay", type=parse_delay, default=(1.5, 3.5), help="대기 MIN,MAX 초")
    parser.add_argument("--limit", type=int, default=0, help="수집할 최대 장소 수 (0=제한 없음)")
    parser.add_argument("--headful", action="store_true", help="브라우저 창을 띄운다")
    parser.add_argument(
        "--profile", type=Path, default=Path(".browser-profile"), help="브라우저 프로필 경로"
    )
    return parser.parse_args(argv)


def build_record(
    fields: dict[str, str], region: str, query: str, tile_label: str
) -> PlaceRecord:
    """파싱 결과에 번호 판정을 붙여 저장 레코드로 만든다."""
    verdict = classify(fields.get("phone_raw", ""), fields.get("website", ""), region)
    return PlaceRecord(
        place_cid=fields.get("place_cid", ""),
        name=fields.get("name", ""),
        category=fields.get("category", ""),
        address=fields.get("address", ""),
        phone_raw=fields.get("phone_raw", ""),
        phone_e164=verdict.e164,
        phone_type=verdict.type,
        whatsapp_status=verdict.status,
        wa_link=verdict.wa_link,
        website=fields.get("website", ""),
        rating=fields.get("rating", ""),
        reviews=fields.get("reviews", ""),
        maps_url=fields.get("maps_url", ""),
        query=query,
        tile=tile_label,
        scraped_at=datetime.now(UTC).isoformat(),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    slug = slugify(args.keyword)
    out_path = args.out or Path("out") / f"{slug}.csv"
    store = JsonlStore(out_path.with_suffix(".raw.jsonl"))
    seen = store.seen_cids()
    if seen:
        print(f"기존 {len(seen)}건을 이어받아 재개합니다.")

    tiles = plan_tiles(args.center, args.radius_km, args.grid)
    delay_min, delay_max = args.delay
    collected = 0
    exit_code = EXIT_OK

    try:
        with maps.browser(args.profile, args.headful, args.lang) as page:
            for index, tile in enumerate(tiles, start=1):
                label = tile.label if tile else ""
                url = search_url(args.keyword, tile, args.lang)
                print(f"[타일 {index}/{len(tiles)}] {label or '뷰포트 없음'}")

                place_urls = _with_block_retry(page, args, lambda: maps.collect_place_urls(page, url))
                print(f"  결과 {len(place_urls)}건")

                for place_url in place_urls:
                    if args.limit and collected >= args.limit:
                        print("  --limit 도달, 중단합니다.")
                        raise _Done
                    if cid_from_url(place_url) in seen:
                        continue
                    html = _with_block_retry(page, args, lambda: maps.open_place(page, place_url))
                    fields = parse_panel(html, place_url)
                    record = build_record(fields, args.region, args.keyword, label)
                    store.append(record)
                    seen.add(record.place_cid)
                    collected += 1
                    print(f"  + {record.name} [{record.whatsapp_status}] {record.phone_e164}")
                    time.sleep(random.uniform(delay_min, delay_max))
    except _Done:
        pass
    except maps.Blocked as blocked:
        print(f"\n구글에 차단되었습니다: {blocked}", file=sys.stderr)
        print("--headful 로 다시 실행해 확인 절차를 직접 통과하세요.", file=sys.stderr)
        exit_code = EXIT_BLOCKED
    except KeyboardInterrupt:
        print("\n중단됨. 지금까지 수집한 것은 저장되어 있습니다.", file=sys.stderr)

    rows = export_csv(store, out_path)
    print(f"\n이번 실행 {collected}건 신규 · 누적 {rows}건 → {out_path}")
    return exit_code


class _Done(Exception):
    """--limit 도달 시 중첩 루프를 빠져나오기 위한 내부 신호."""


def _with_block_retry(page, args, action):
    """차단되면 headful일 때 한 번 사람 개입을 기다렸다가 재시도한다."""
    try:
        return action()
    except maps.Blocked:
        if not args.headful:
            raise
        maps.wait_for_human(page)
        return action()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 전체 테스트 실행**

Run: `uv run pytest -v`
Expected: 전부 PASS

- [ ] **Step 6: 실제 실행으로 드라이버를 검증한다**

먼저 창을 띄우고 소량만 받아 셀렉터가 실제 DOM과 맞는지 본다.

```bash
uv run sourcing "rumah sakit" --region ID --lang id --headful --limit 5 --out out/smoke.csv
```

확인할 것:
- 이름·주소가 채워지는가
- 모바일 번호가 `candidate`로, 유선이 `unlikely`로 찍히는가
- `out/smoke.raw.jsonl`에 줄이 쌓이는가
- 재실행하면 "기존 N건을 이어받아 재개합니다"가 뜨고, 이미 받은 장소는 페이지를 열지도
  않고 건너뛰는가 (재개의 핵심)

셀렉터가 안 맞으면 `src/sourcing/parse.py`의 상수만 고치고, 실제 패널 HTML을
`tests/fixtures/`에 저장한 뒤 `tests/test_parse.py`를 그 픽스처로 갱신한다.

- [ ] **Step 7: README를 사용법으로 채운다**

`README.md`를 다음 내용으로 교체한다:

```markdown
# sourcing

구글 맵에서 병원·클리닉의 WhatsApp 연락처를 수집하는 CLI.

## 설치

```
mise install
uv sync
uv run playwright install chromium
```

## 사용

```
uv run sourcing "rumah sakit" --region ID --lang id --out out/jakarta.csv
uv run sourcing "hospital" --region PH --center 14.60,120.98 --radius-km 25 --grid 4
```

주요 옵션은 `uv run sourcing --help`.

## WhatsApp 상태

구글 맵에는 WhatsApp 필드가 없다. 이 도구는 근거를 밝힌 세 단계로 표시한다.

| 상태 | 근거 |
|---|---|
| `confirmed` | 맵의 웹사이트 링크가 `wa.me` / `api.whatsapp.com` — 번호가 확정된다 |
| `candidate` | 대표번호가 모바일 번호대 — 동남아에서는 대부분 WhatsApp이다 |
| `unlikely` | 유선이거나 번호가 없다 |

## 한계

- 구글 맵 검색 하나는 100~120건에서 잘린다. 지역 전수에 가깝게 가려면
  `--center`/`--radius-km`/`--grid`로 격자를 쪼개야 한다.
- 자동화된 스크래핑이라 구글이 확인 절차를 요구할 수 있다. 그때는 `--headful`로
  실행해 창에서 직접 통과하면 세션이 프로필에 남는다.
- 중단해도 `*.raw.jsonl`에 즉시 기록되므로 같은 명령을 다시 실행하면 이어서 받는다.

## 개발

```
uv run pytest
```

`maps.py`(브라우저 계층)를 뺀 나머지는 전부 네트워크 없이 테스트된다.
구글이 DOM을 바꾸면 `parse.py`의 셀렉터 상수와 `tests/fixtures/`만 갱신하면 된다.
```

- [ ] **Step 8: 커밋**

```bash
git add -A
git commit -m "CLI 오케스트레이션과 사용 문서 추가"
```

---

## Self-Review

**스펙 커버리지**

| 스펙 항목 | 담당 |
|---|---|
| §4 CLI 옵션 전체 | Task 7 `parse_args` |
| §5 모듈 분리 | Task 2~7 |
| §6 데이터 모델·CSV 컬럼 | Task 4 |
| §6.1 상태 판정 3규칙 | Task 2 `classify` |
| §7 격자·줌·검색 URL | Task 3 |
| §8 셀렉터·스크롤·rate limit | Task 5(셀렉터), Task 6(스크롤), Task 7(delay) |
| §9 에러 처리 (차단·파싱실패·재개) | Task 6 `Blocked`, Task 7 `_with_block_retry`, Task 4 JSONL flush |
| §10 테스트 전략 | Task 2~5, 7 |
| §11 프로젝트 구조 | Task 1 |

**미해결 사항 없음.** 스펙의 §8 "셀렉터를 maps.py에 모은다"는 파일 구조 절에
적어둔 이유로 parse.py로 옮겼다. 이 변경 외에 스펙과 계획의 차이는 없다.
