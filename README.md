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

`--center` 없이 실행하면 구글이 실행 위치의 IP를 기준으로 뷰포트를 잡는다.
특정 지역을 노리려면 `--center`로 좌표를 주거나 키워드에 지역명을 넣어라.
음수 좌표는 `--center=-6.2,106.8`처럼 `=` 로 값을 붙여야 argparse가
옵션 플래그로 오인하지 않는다.

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
