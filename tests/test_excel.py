from openpyxl import load_workbook

from sourcing.excel import EXCEL_HEADERS, write_xlsx
from sourcing.store import (
    SOURCE_MAP_PHONE_GUESS,
    SOURCE_SITE_CONFIRMS_MAP,
    SOURCE_SITE_LINK,
    PlaceRecord,
)


def rec(name, status, source, phone="+6281510032464", address="Jl. Contoh 1", wa=""):
    return PlaceRecord(
        place_cid="0xa:0xb",
        name=name,
        address=address,
        phone_e164=phone,
        whatsapp_status=status,
        source=source,
        wa_link=wa,
    )


def sheet(path):
    return load_workbook(path).active


def test_headers_are_the_slim_set(tmp_path):
    out = tmp_path / "leads.xlsx"
    write_xlsx([rec("Klinik A", "confirmed", SOURCE_SITE_LINK)], out)
    header = [c.value for c in sheet(out)[1]]
    assert header == EXCEL_HEADERS
    assert header == ["병원명", "위치", "전화번호", "WhatsApp 링크", "상태", "근거"]


def test_source_is_written_as_a_human_label(tmp_path):
    out = tmp_path / "leads.xlsx"
    write_xlsx(
        [
            rec("A", "confirmed", SOURCE_SITE_CONFIRMS_MAP),
            rec("B", "confirmed", SOURCE_SITE_LINK),
            rec("C", "candidate", SOURCE_MAP_PHONE_GUESS),
        ],
        out,
    )
    labels = [row[5].value for row in sheet(out).iter_rows(min_row=2)]
    assert labels == ["홈페이지+맵 일치", "홈페이지 링크", "맵 번호 추정"]


def test_rows_carry_name_and_location(tmp_path):
    out = tmp_path / "leads.xlsx"
    write_xlsx([rec("Klinik Contoh", "confirmed", SOURCE_SITE_LINK, address="Jl. Sudirman 5")], out)
    row = [c.value for c in sheet(out)[2]]
    assert row[0] == "Klinik Contoh"
    assert row[1] == "Jl. Sudirman 5"


def test_confirmed_rows_come_first(tmp_path):
    out = tmp_path / "leads.xlsx"
    write_xlsx(
        [
            rec("추정", "candidate", SOURCE_MAP_PHONE_GUESS),
            rec("확정", "confirmed", SOURCE_SITE_LINK),
        ],
        out,
    )
    names = [row[0].value for row in sheet(out).iter_rows(min_row=2)]
    assert names == ["확정", "추정"]


def test_unlikely_rows_are_left_out(tmp_path):
    out = tmp_path / "leads.xlsx"
    write_xlsx(
        [rec("연락가능", "confirmed", SOURCE_SITE_LINK), rec("근거없음", "unlikely", "")], out
    )
    names = [row[0].value for row in sheet(out).iter_rows(min_row=2)]
    assert names == ["연락가능"]


def test_empty_input_still_writes_a_header(tmp_path):
    out = tmp_path / "leads.xlsx"
    assert write_xlsx([], out) == 0
    assert [c.value for c in sheet(out)[1]] == EXCEL_HEADERS


def test_returns_written_row_count(tmp_path):
    out = tmp_path / "leads.xlsx"
    written = write_xlsx(
        [rec("A", "confirmed", SOURCE_SITE_LINK), rec("B", "candidate", SOURCE_MAP_PHONE_GUESS)],
        out,
    )
    assert written == 2
