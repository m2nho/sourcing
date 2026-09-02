"""수집 작업의 상태와 결과 읽기.

MCP로 노출할 때 수집이 20~40분 걸린다는 점이 설계를 지배한다. 툴 호출은
즉시 반환하고, 진행 상황은 JSONL 파일에서 읽는다 — store.JsonlStore가
레코드마다 flush하므로 그 파일이 곧 실시간 진행률이다.

이 모듈은 파일만 읽는다. 프로세스를 띄우는 일은 mcp_server가 맡는다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import datetime
from enum import Enum
from pathlib import Path

STATUSES = ("confirmed", "candidate", "unlikely")

#: 툴이 돌려줄 컬럼. 이건 모델이 읽는 응답이라 무게가 곧 비용이다.
#: maps_url은 한 건에 300자가 넘는데 모델이 쓸 일이 없고, place_cid는
#: 내부 식별자다. 둘 다 빼면 같은 정보를 훨씬 적은 토큰으로 전달한다.
#: 두 값이 필요하면 엑셀에 컬럼으로 들어 있다.
LEAD_COLUMNS = (
    "name",
    "phone_e164",
    "whatsapp_status",
    "source",
    "wa_link",
    "website",
    "address",
)


class JobStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"

    @classmethod
    def from_returncode(cls, returncode: int | None) -> JobStatus:
        """CLI 종료 코드를 작업 상태로. None이면 아직 돌고 있다."""
        if returncode is None:
            return cls.RUNNING
        if returncode == 0:
            return cls.DONE
        if returncode == 2:  # cli.EXIT_BLOCKED
            return cls.BLOCKED
        return cls.FAILED


def new_job_id(keyword: str) -> str:
    """사람이 읽을 수 있는 작업 식별자. 키워드와 시각을 담는다."""
    slug = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-") or "job"
    return f"{slug}-{datetime.now().strftime('%H%M%S-%f')[:13]}"


def tally(raw_jsonl: Path) -> dict[str, int]:
    """상태별 집계. 파일이 없으면 전부 0 — 아직 첫 레코드 전이라는 뜻이다."""
    counts = {"total": 0} | dict.fromkeys(STATUSES, 0)
    for record in _records(raw_jsonl):
        counts["total"] += 1
        status = record.get("whatsapp_status", "")
        if status in counts:
            counts[status] += 1
    return counts


def read_leads(raw_jsonl: Path, status: str | None, limit: int) -> list[dict[str, str]]:
    """레코드를 걸러서 최대 limit개. 유용한 컬럼만 남긴다."""
    rows: list[dict[str, str]] = []
    for record in _records(raw_jsonl):
        if status and record.get("whatsapp_status") != status:
            continue
        rows.append({key: record.get(key, "") for key in LEAD_COLUMNS})
        if len(rows) >= limit:
            break
    return rows


def lead_summary(raw_jsonl: Path) -> str:
    """한 줄 요약. 툴 응답의 사람이 읽는 부분."""
    counts = tally(raw_jsonl)
    if not counts["total"]:
        return "아직 수집된 레코드가 없습니다."
    parts = " · ".join(f"{name} {counts[name]}" for name in STATUSES)
    return f"총 {counts['total']}건 ({parts})"


def _records(path: Path) -> Iterator[dict]:
    """JSONL을 한 줄씩. 손상된 줄은 건너뛴다 — 쓰는 도중 읽을 수 있다."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record
