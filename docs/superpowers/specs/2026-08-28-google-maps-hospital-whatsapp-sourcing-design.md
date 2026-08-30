# 구글 맵 병원 WhatsApp 연락처 소싱 — 설계

- 날짜: 2026-08-28
- 상태: 승인됨 (구현 계획 대기)

## 1. 목적

키워드 하나(예: `rumah sakit`)와 대상 지역을 주면, 구글 맵에서 해당 병원·클리닉을
훑어 **WhatsApp으로 연락 가능한 번호**를 CSV로 뽑아내는 CLI 도구.

1차 타겟 시장은 동남아(인도네시아·베트남·필리핀)다. 이 지역은 병원 대표번호가
모바일이고 그 번호가 곧 WhatsApp인 경우가 대부분이라, 맵 리스팅의 전화번호만으로도
실사용 가능한 리드가 나온다.

## 2. 범위

**포함**

- 구글 맵 검색 결과 수집 (Playwright 직접 스크래핑)
- 지역 격자 타일링으로 단일 검색의 결과 상한 우회
- 전화번호 E.164 정규화 및 모바일/유선 판정
- WhatsApp 상태 3분류 및 `wa.me` 링크 생성
- 중단 후 재개, 중복 제거
- CSV 출력

**미포함 (의도적)**

- 병원 웹사이트 크롤링 — 사용자가 "맵만" 빠른 버전을 선택했다. 향후 확장 지점으로만 남긴다.
- 인스타그램·페이스북 등 SNS 바이오 수집
- 번호가 실제 WhatsApp에 등록됐는지의 능동적 검증 — 합법적인 대량 조회 수단이 없다.
- 메시지 발송. 이 도구는 수집까지만 한다.

## 3. 데이터 소스와 그 한계

구글 맵에는 **WhatsApp 전용 필드가 없다.** 얻을 수 있는 것은 이름·주소·카테고리·
전화번호·웹사이트·평점이다. 따라서 WhatsApp 여부는 추정이며, 그 추정 근거를
레코드마다 명시적으로 남긴다(§6).

알려진 제약:

1. **검색당 결과 상한** — 구글 맵의 단일 검색은 약 100~120건에서 잘린다.
   지역 전수에 근접하려면 격자 타일링이 필요하다(§7).
2. **뷰포트 편향** — 맵 검색 결과는 뷰포트에 강하게 편향되지만 엄격히 경계
   지어지지는 않는다. 타일 간 결과가 겹치므로 CID 기준 중복 제거가 필수다.
3. **차단** — 직접 스크래핑이므로 CAPTCHA(`/sorry/index`)가 뜰 수 있다.
   사용자가 이 리스크를 인지하고 선택했다. 대응은 §9.
4. **DOM 변경** — 구글이 클래스명을 수시로 바꾼다. 셀렉터는 한 곳에 모으고
   의미 기반 속성(`data-item-id`)을 우선한다(§8).

## 4. CLI

```
uv run sourcing <keyword> [options]

  --region CODE       전화번호 정규화 기준 국가 (ISO 3166-1 alpha-2). 필수. 예: ID, VN, PH
  --lang CODE         구글 맵 UI 언어 (hl). 기본값: en
  --out PATH          CSV 출력 경로. 기본값: out/<keyword-slug>.csv

  --center LAT,LNG    격자 중심 좌표. 없으면 단일 검색만 수행
  --radius-km FLOAT   격자가 덮을 반경. 기본값 10
  --grid N            한 변의 타일 수 (N x N). 기본값 3

  --delay MIN,MAX     장소 방문 사이 랜덤 대기 초. 기본값 1.5,3.5
  --limit N           수집할 최대 장소 수 (테스트용)
  --headful           브라우저 창을 띄운다. CAPTCHA 수동 해제용
  --profile PATH      영구 브라우저 프로필 경로. 기본값 .browser-profile/
```

예시:

```bash
uv run sourcing "rumah sakit" --region ID --lang id --out out/jakarta.csv
uv run sourcing "hospital" --region PH --center 14.60,120.98 --radius-km 25 --grid 4
```

## 5. 아키텍처

```
cli.py ── 인자 파싱, 오케스트레이션, 종료 코드
  │
  ├── grid.py    [순수] 중심+반경+N → 타일 (lat, lng, zoom) 목록
  │
  ├── maps.py    [I/O] Playwright. 타일별 검색 → 피드 스크롤 → place URL 수집
  │              → 각 place 상세 패널 열기 → raw dict 반환
  │
  ├── parse.py   [순수] 상세 패널의 속성/텍스트 → PlaceRecord
  │
  ├── phone.py   [순수] 전화번호 정규화·유형판정 → WhatsApp 상태, wa.me 링크
  │
  └── store.py   [I/O] JSONL 추가 기록, CID 집합 로드(재개), CSV 내보내기
```

순수 모듈 4종(`grid`, `parse`, `phone`, `store`의 직렬화 부분)은 네트워크 없이
단위 테스트한다. `maps.py`는 얇게 유지하고 셀렉터 상수만 담아 실제 실행으로 검증한다.

데이터 흐름:

```
타일 목록 ─┐
           ├→ 타일마다: 맵 검색 URL 열기 → 피드 끝까지 스크롤
           │            → place URL 수집 → CID 추출
           │
           ├→ 이미 본 CID는 건너뜀 (재개 + 타일 중복 제거)
           │
           ├→ 새 CID마다: place 페이지 방문 → 필드 추출 → 전화 정규화
           │            → JSONL 한 줄 추가 (즉시 flush)
           │
           └→ 종료 시 JSONL 전체를 읽어 CSV 재생성 (멱등)
```

## 6. 데이터 모델

`PlaceRecord`:

| 필드 | 설명 |
|---|---|
| `place_cid` | 맵 URL의 `0x...:0x...` 16진 쌍. 중복 제거 키 |
| `name` | 상호 |
| `category` | 맵 1차 카테고리 (예: Hospital, Klinik) |
| `address` | 전체 주소 |
| `phone_raw` | 맵에 표시된 원문 전화번호 |
| `phone_e164` | `--region` 기준 정규화 결과. 실패 시 빈 값 |
| `phone_type` | `mobile` / `fixed_line` / `fixed_line_or_mobile` / `unknown` |
| `whatsapp_status` | `confirmed` / `candidate` / `unlikely` (§6.1) |
| `source` | 그 번호를 어디서 얻었는지 (§6.2) |
| `wa_link` | `https://wa.me/<E.164 숫자>`. 상태가 unlikely면 빈 값 |
| `website` | 맵의 웹사이트 필드 원문 |
| `rating`, `reviews` | 평점, 리뷰 수 |
| `maps_url` | 장소 URL |
| `query`, `tile` | 어느 검색·타일에서 나왔는지 (추적용) |
| `scraped_at` | UTC ISO8601 |

CSV 컬럼 순서는 위 표 순서를 따른다.

### 6.2 근거(`source`)

`confirmed` 안에도 신뢰도가 다른 것들이 섞인다. 담당자가 어디부터 걸지
정할 수 있도록 출처를 남긴다.

| 값 | 엑셀 라벨 | 의미 |
|---|---|---|
| `site_confirms_map` | 홈페이지+맵 일치 | 홈페이지의 wa.me가 맵 대표번호와 같다 — 가장 강한 근거 |
| `site_link` | 홈페이지 링크 | 홈페이지에서 찾았고 맵에는 없던 번호 |
| `map_link` | 구글맵 링크 | 맵 웹사이트 필드가 wa.me였다 |
| `map_phone_guess` | 맵 번호 추정 | 맵 대표번호가 모바일이라는 추정뿐 (`candidate`) |
| (빈 값) | 근거 없음 | `unlikely` |

### 6.3 엑셀 출력

CSV는 전체 레코드를 보존하는 원본이고, 엑셀(`.xlsx`)은 실제로 연락할 목록이다.
컬럼은 `병원명 · 위치 · 전화번호 · WhatsApp 링크 · 상태 · 근거` 여섯 개이며,
`unlikely`는 넣지 않고 `confirmed`를 위로 정렬한다. CSV와 나란히 자동 생성된다.

### 6.1 WhatsApp 상태 판정 규칙

순서대로 평가하고 첫 번째로 맞는 것을 채택한다.

1. `website`가 `wa.me` 또는 `api.whatsapp.com` 호스트 → **`confirmed`**.
   링크에서 번호를 추출해 `phone_e164`보다 우선한다.
2. `phone_type`이 `mobile` 또는 `fixed_line_or_mobile` → **`candidate`**.
   단 `+1`(북미번호계획) 번호의 `fixed_line_or_mobile`은 제외한다.
3. 그 외(유선, 정규화 실패, 번호 없음) → **`unlikely`**.

`fixed_line_or_mobile`을 candidate에 넣는 이유: 필리핀·베트남 일부 번호대는
`phonenumbers`가 둘을 구분하지 못하는데, 이 지역에서는 WhatsApp일 확률이 더 높다.

**NANP 예외 (2026-08-30 실측 반영):** 북미번호계획은 지역번호로 회선 종류를
나누지 않아 모든 번호가 `fixed_line_or_mobile`로 나온다 — 마이애미 클리닉
304건 중 267건이 이 유형이었고 `mobile`도 `fixed_line`도 0건이었다. 이 유형이
아무 정보도 담지 않으므로 후보로 올리지 않는다. 미국에서 리드가 되는 것은
`confirmed`뿐이다.

**`wa_link`는 `confirmed`에만 채운다.** `candidate`는 추측이며, 그것을 클릭
가능한 링크로 포장하면 CSV를 받은 사람이 검증된 창구로 오인한다. `candidate`의
`phone_e164`는 그대로 남으므로 번호 자체는 쓸 수 있다.

## 7. 격자 타일링

`--center`가 없으면 타일은 1개(뷰포트 지정 없는 단일 검색)다.

있으면 중심을 기준으로 반경을 덮는 정사각 경계상자를 만들고 `N x N`으로 쪼갠다.

```
deg_lat = km / 111.32
deg_lng = km / (111.32 * cos(radians(lat)))
```

각 셀의 중심 좌표가 검색 뷰포트가 되고, 줌은 셀이 화면을 대략 채우도록 잡는다.

```
zoom = clamp(round(15 - log2(cell_diameter_km)), 10, 17)
```

(셀 지름 1km → 15, 2km → 14, 4km → 13)

검색 URL 형식:

```
https://www.google.com/maps/search/<url-encoded keyword>/@<lat>,<lng>,<zoom>z?hl=<lang>
```

타일은 순차 처리한다. 병렬화하지 않는다 — 차단 위험을 키우고, 이 작업은
지연시간이 아니라 예의(rate limit)에 묶여 있다.

## 8. 스크래핑 세부

**브라우저**: Chromium, 영구 컨텍스트(`--profile`). 쿠키·동의 상태가 유지되어야
매 실행마다 동의 화면을 다시 만나지 않는다. 기본은 headless, `--headful`로 전환.

**피드 스크롤**: 결과 컨테이너를 끝까지 스크롤한다. 종료 조건은 둘 중 먼저 오는 것.
- 목록 끝 안내 문구가 나타남
- `scrollHeight`가 연속 3회 증가하지 않음

**필드 추출**: 클래스명이 아니라 의미 속성을 우선한다.

| 필드 | 1순위 | 대안 |
|---|---|---|
| 전화 | `button[data-item-id^="phone:tel:"]`의 `data-item-id` | 버튼 `aria-label` |
| 주소 | `button[data-item-id="address"]` | `aria-label` 접두사 매칭 |
| 웹사이트 | `a[data-item-id="authority"]`의 `href` | — |
| 이름 | 상세 패널의 `h1` | 문서 `title` |
| 카테고리 | 카테고리 버튼 | — |
| 평점/리뷰 | 평점 블록의 `aria-label` | — |

전화번호를 `data-item-id`에서 직접 읽는 것이 핵심이다. 문자열이 `phone:tel:+62...`
형태라 로케일·표기 변화에 영향받지 않는다.

셀렉터는 전부 `maps.py` 상단 상수 블록에 모은다. 구글이 DOM을 바꾸면 한 곳만 고친다.

**속도 조절**: 장소 방문 사이 `--delay` 범위의 랜덤 대기. 기본 1.5~3.5초.

## 9. 에러 처리

| 상황 | 대응 |
|---|---|
| CAPTCHA / `/sorry/index` 도달 | `--headful`이면 콘솔에 안내 후 사람이 풀 때까지 대기, 풀리면 계속. headless면 JSONL flush 후 종료 코드 2 |
| 개별 장소 파싱 실패 | 경고 로그, 그 장소만 건너뛰고 계속. 전체를 죽이지 않는다 |
| 필드 일부 없음 | 빈 문자열. 필수 필드는 `name`과 `place_cid`뿐 |
| 전화번호 정규화 실패 | `phone_e164` 빈 값, `phone_type=unknown`, 상태 `unlikely`. `phone_raw`는 보존 |
| 네트워크 타임아웃 | 장소당 2회 재시도(지수 백오프), 그래도 실패하면 건너뜀 |
| 중간 강제 종료 | JSONL은 매 레코드 flush되므로 유실 없음. 재실행하면 남은 것부터 |

## 10. 테스트 전략

TDD로 진행한다. 순수 모듈이 먼저다.

- `test_phone.py` — 인니 `08xx`/`+628xx`, 베트남 `09xx`, 필리핀 `+639xx` 모바일 판정,
  자카르타 유선 `021-xxx` 판정, 정규화 실패 입력, `wa.me` URL에서 번호 추출,
  세 가지 상태 각각의 분기
- `test_grid.py` — N x N 셀 개수, 경계상자 덮음, 위도에 따른 경도 스케일링,
  줌 클램프 상하한, `--center` 없을 때 단일 타일
- `test_parse.py` — 저장해 둔 상세 패널 HTML 픽스처에서 레코드 추출,
  전화 없는 케이스, 웹사이트가 `wa.me`인 케이스, 영어/인니어 로케일 두 가지
- `test_store.py` — JSONL 추가 기록, 재개 시 CID 집합 로드, CSV 컬럼 순서,
  같은 JSONL을 두 번 내보내도 동일한 CSV (멱등)

`maps.py`는 단위 테스트하지 않는다. 브라우저 자동화 계층은 실제 실행으로 검증하고,
로직을 두지 않는 것으로 리스크를 줄인다.

## 11. 프로젝트 구조

```
sourcing/
  mise.toml                 python = "3.13"
  pyproject.toml            uv_build, [project.scripts] sourcing = "sourcing.cli:main"
  .gitignore                out/, .browser-profile/, .venv/
  README.md                 설치·사용법·한계
  src/sourcing/
    __init__.py
    cli.py
    grid.py
    maps.py
    parse.py
    phone.py
    store.py
  tests/
    test_grid.py
    test_parse.py
    test_phone.py
    test_store.py
    fixtures/
      place_panel_en.html
      place_panel_id.html
```

의존성: `playwright`, `phonenumbers`. 개발: `pytest`.

## 12. 리스크

- **구글 ToS** — 자동화된 맵 스크래핑은 구글 서비스 약관에 어긋난다. 사용자가
  공식 Places API 대안을 안내받은 뒤 직접 스크래핑을 선택했다. 도구는 낮은 요청
  속도를 기본값으로 두고 병렬화하지 않는 것으로 부하를 최소화한다.
- **연락처의 용도** — 수집되는 것은 공개된 사업체 대표 연락처다. 실제 발송 시에는
  대상국 개인정보·스팸 규제와 WhatsApp Business 정책(옵트인, 템플릿 승인)을
  따로 확인해야 한다. 이 도구의 책임 범위 밖이다.
- **DOM 변경으로 인한 파손** — 셀렉터 집중화와 의미 속성 우선으로 완화하되,
  주기적 픽스처 갱신이 필요하다.

## 13. 향후 확장 지점

지금 만들지 않지만 구조상 열어 둔다.

- 웹사이트 홈·연락처 페이지 크롤로 `candidate` → `confirmed` 승격
- 인스타그램·페이스북 바이오의 `wa.me` 수집
- 구글 시트 출력 (옆 `whatsapp` 프로젝트의 google-sheets MCP 재사용)
- 검색 소스 교체 (Places API 어댑터) — `maps.py`를 인터페이스로 감싸면 된다
