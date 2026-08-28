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
