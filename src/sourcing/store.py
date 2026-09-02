"""수집 레코드의 정의, 재개 가능한 JSONL 저장, CSV 내보내기."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, fields
from pathlib import Path


#: 번호를 어디서 얻었는지. CSV/엑셀의 "근거" 컬럼이 되고, 영업 담당자가
#: 이 리드를 얼마나 믿을지 판단하는 근거다.
SOURCE_MAP_LINK = "map_link"                    # 구글맵 웹사이트 필드가 wa.me였다
SOURCE_SITE_LINK = "site_link"                  # 홈페이지에서 찾았고 맵에는 없던 번호
SOURCE_SITE_CONFIRMS_MAP = "site_confirms_map"  # 홈페이지가 맵 대표번호를 확인해줬다
SOURCE_MAP_PHONE_GUESS = "map_phone_guess"      # 맵 대표번호가 모바일이라는 추정뿐
SOURCE_PROFILE = "profile"                      # WhatsApp 프로필 조회로 확인
SOURCE_PROFILE_MISMATCH = "profile_mismatch"    # 프로필은 있으나 이름이 상호와 다름
SOURCE_NONE = ""                                # 근거 없음

#: 사람이 읽는 라벨. 엑셀에 이 문구가 그대로 들어간다.
SOURCE_LABELS = {
    SOURCE_MAP_LINK: "구글맵 링크",
    SOURCE_SITE_LINK: "홈페이지 링크",
    SOURCE_SITE_CONFIRMS_MAP: "홈페이지+맵 일치",
    SOURCE_MAP_PHONE_GUESS: "맵 번호 추정",
    SOURCE_PROFILE: "프로필 확인",
    SOURCE_PROFILE_MISMATCH: "프로필 이름 불일치",
    SOURCE_NONE: "근거 없음",
}


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
    source: str = ""
    profile_name: str = ""
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
