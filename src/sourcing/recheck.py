"""이미 수집한 결과의 WhatsApp 프로필을 다시 조회한다.

프로필 조회는 수집보다 훨씬 자주 막힌다. 막힌 구간은 '확인 실패'로 남고,
감지가 발동하기 전 구간에는 잘못된 '개인/미등록'이 섞인다. 수집을 다시
할 이유는 없으므로 프로필만 따로 다시 본다.

도시 하나가 20분 안팎이다. 연달아 돌리면 또 막히므로 사이를 띄운다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from sourcing.store import CSV_COLUMNS, PROFILE_ERROR, PlaceRecord

#: 조회 사이 간격(초). 너무 빠르면 금세 막힌다.
LOOKUP_DELAY = 0.6


def needs_lookup(record: PlaceRecord, only_errors: bool) -> bool:
    """이 레코드를 조회할 것인가.

    번호가 없거나 연락 불가로 분류된 곳은 건너뛴다 - 엑셀에도 나오지 않으므로
    한정된 조회 한도를 쓸 이유가 없다.
    """
    if not record.phone_e164 or record.whatsapp_status == "unlikely":
        return False
    if not only_errors:
        return True
    return record.profile_checked in ("", PROFILE_ERROR)


def main(argv: list[str] | None = None) -> int:
    from sourcing import maps
    from sourcing.excel import write_xlsx_from_jsonl
    from sourcing.throttle import ThrottleWatch
    from sourcing.verify import apply_profile, mark_lookup_failed

    parser = argparse.ArgumentParser(
        prog="sourcing-recheck",
        description="수집 결과의 WhatsApp 프로필을 다시 조회한다.",
    )
    parser.add_argument("source", type=Path, help="다시 볼 .raw.jsonl")
    parser.add_argument(
        "--only-errors",
        action="store_true",
        help="'확인 실패'와 미조회만 다시 본다. 조회 한도를 아낀다",
    )
    args = parser.parse_args(argv)

    records = [
        PlaceRecord(**{key: data.get(key, "") for key in CSV_COLUMNS})
        for data in (
            json.loads(line)
            for line in args.source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    ]
    targets = [r for r in records if needs_lookup(r, args.only_errors)]
    print(f"조회 대상 {len(targets)}건 / 전체 {len(records)}건")
    if not targets:
        return 0

    watch = ThrottleWatch()
    updated: dict[str, PlaceRecord] = {}
    with maps.browser(Path(".browser-profile"), headful=False, lang="en") as page:
        site = maps.open_site_page(page)
        for index, record in enumerate(targets, start=1):
            if watch.throttled:
                updated[record.place_cid] = mark_lookup_failed(record)
                continue
            try:
                name = maps.fetch_wa_profile(site, record.phone_e164)
            except Exception:  # noqa: BLE001
                updated[record.place_cid] = mark_lookup_failed(record)
                continue

            watch.record(record.phone_e164, name)
            if watch.should_check_canary():
                try:
                    again = maps.fetch_wa_profile(site, watch.canary)
                except Exception:  # noqa: BLE001
                    again = ""
                watch.canary_result(again)
                if watch.throttled:
                    print(f"  ! {index}건째에서 조회가 막혔습니다. 나머지는 '확인 실패'로 남깁니다.",
                          file=sys.stderr)
                    updated[record.place_cid] = mark_lookup_failed(record)
                    continue

            updated[record.place_cid] = apply_profile(record, name)
            if index % 75 == 0:
                print(f"  {index}/{len(targets)}")
            time.sleep(LOOKUP_DELAY)

    merged = [updated.get(r.place_cid, r) for r in records]
    with args.source.open("w", encoding="utf-8") as fh:
        for record in merged:
            fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    xlsx = args.source.with_name(args.source.name.replace(".raw.jsonl", ".xlsx"))
    leads = write_xlsx_from_jsonl(args.source, xlsx)
    print(f"→ {xlsx} · 연락 가능 {leads}건" + (" · 도중에 막힘" if watch.throttled else ""))
    return 0
