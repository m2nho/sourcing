"""영업 담당자가 바로 여는 엑셀 파일을 만든다.

CSV는 전체 레코드를 보존하는 원본이고, 엑셀은 실제로 연락할 목록이다.
그래서 컬럼이 다르다 — 병원명과 위치, 연락 수단, 그리고 그 번호를 어디서
얻었는지(근거)만 남긴다.

근거를 남기는 이유: confirmed 안에도 성격이 다른 것들이 섞여 있다. 홈페이지가
맵 번호를 확인해준 것과, 홈페이지에만 있던 번호와, 맵 링크에서 나온 것은
신뢰도가 다르다. 담당자가 어디부터 걸지 정할 수 있어야 한다.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from sourcing.store import SOURCE_LABELS, JsonlStore, PlaceRecord

EXCEL_HEADERS = [
    "병원명", "위치", "전화번호", "WhatsApp 링크", "상태", "근거", "홈페이지", "구글맵",
]

#: 연락할 수 없는 곳은 목록에 넣지 않는다. 원본은 CSV에 그대로 남아 있다.
EXPORTED_STATUSES = ("confirmed", "candidate")

#: 확정을 먼저 보여준다. 담당자가 위에서부터 걸면 된다.
_STATUS_ORDER = {"confirmed": 0, "candidate": 1}

_STATUS_LABELS = {"confirmed": "확정", "candidate": "추정"}

_COLUMN_WIDTHS = (38, 52, 18, 30, 8, 16, 42, 42)

_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")


def write_xlsx(records: Iterable[PlaceRecord], path: Path) -> int:
    """연락 가능한 레코드를 엑셀로 쓴다. 쓴 행 수를 돌려준다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = sorted(
        (r for r in records if r.whatsapp_status in EXPORTED_STATUSES),
        key=lambda r: (_STATUS_ORDER.get(r.whatsapp_status, 9), r.name),
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "리드"
    sheet.append(EXCEL_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL

    for record in rows:
        sheet.append(
            [
                record.name,
                record.address,
                record.phone_e164,
                record.wa_link,
                _STATUS_LABELS.get(record.whatsapp_status, record.whatsapp_status),
                SOURCE_LABELS.get(record.source, record.source),
                record.website,
                record.maps_url,
            ]
        )

    for index, width in enumerate(_COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(EXCEL_HEADERS))}{sheet.max_row}"
    workbook.save(path)
    return len(rows)


def write_xlsx_from_jsonl(raw_jsonl: Path, out_path: Path) -> int:
    """재개 원장(JSONL)에서 엑셀을 다시 만든다. 쓴 행 수를 돌려준다.

    수집이 취소되면 CLI의 마무리 코드에 도달하지 못해 엑셀이 남지 않는다.
    JSONL은 레코드마다 flush되므로 그것만 있으면 언제든 복원할 수 있다.
    """
    return write_xlsx(JsonlStore(Path(raw_jsonl)).records(), out_path)
