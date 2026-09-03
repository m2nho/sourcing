"""여러 번의 수집을 하나로 합친다.

넓은 도시는 구·지구 단위로 나눠 여러 번 돌리는 것이 맞다(구글이 넓은
뷰포트에서는 같은 곳만 돌려주기 때문). 그러면 파일이 여럿이 되고, 지구가
겹치는 곳은 같은 클리닉이 두 번 나온다. 영업용으로는 하나로 합쳐야 한다.

같은 곳이 여러 번 나오면 근거가 더 강한 쪽을 남긴다 — 한 지구에서는
추정이었지만 다른 지구에서 확정으로 잡혔다면 확정이 맞다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

#: 등급의 강도. 같은 곳이 여러 번 나오면 높은 쪽을 남긴다.
_GRADE_RANK = {"confirmed": 3, "verified": 2, "candidate": 1, "unlikely": 0}


def merge_jsonl(sources: Iterable[Path], out_path: Path) -> int:
    """여러 원장을 하나로 합친다. 합쳐진 레코드 수를 돌려준다."""
    best: dict[str, dict] = {}
    for source in sources:
        source = Path(source)
        if not source.exists():
            continue
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            cid = record.get("place_cid", "")
            if not cid:
                continue
            current = best.get(cid)
            if current is None or _rank(record) > _rank(current):
                best[cid] = record

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for record in best.values():
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(best)


def _rank(record: dict) -> int:
    return _GRADE_RANK.get(record.get("whatsapp_status", ""), 0)


def main(argv: list[str] | None = None) -> int:
    """여러 수집 결과를 합쳐 엑셀 하나로 만든다.

    사용: uv run sourcing-merge out/*.raw.jsonl --out out/all.xlsx
    """
    import argparse

    from sourcing.excel import write_xlsx_from_jsonl

    parser = argparse.ArgumentParser(
        prog="sourcing-merge",
        description="여러 지역·키워드 수집 결과를 하나의 엑셀로 합친다.",
    )
    parser.add_argument("sources", nargs="+", type=Path, help="합칠 .raw.jsonl 파일들")
    parser.add_argument("--out", type=Path, required=True, help="만들 .xlsx 경로")
    args = parser.parse_args(argv)

    merged_jsonl = args.out.with_suffix(".raw.jsonl")
    sources = [s for s in args.sources if s.resolve() != merged_jsonl.resolve()]
    records = merge_jsonl(sources, merged_jsonl)
    leads = write_xlsx_from_jsonl(merged_jsonl, args.out)
    print(f"{len(sources)}개 파일 · 고유 {records}건 → 연락 가능 {leads}건 → {args.out}")
    return 0
