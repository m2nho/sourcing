import contextlib
import csv

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from sourcing import cli, maps
from sourcing.store import PlaceRecord
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


def test_args_region_is_uppercased():
    args = parse_args(["rumah sakit", "--region", "id"])
    assert args.region == "ID"


@pytest.mark.parametrize("value", ["idn", "zz", "XX"])
def test_args_reject_unknown_region(value):
    with pytest.raises(SystemExit):
        parse_args(["rumah sakit", "--region", value])


def test_args_defaults():
    args = parse_args(["rumah sakit", "--region", "ID"])
    assert args.keyword == "rumah sakit"
    assert args.region == "ID"
    assert args.lang == "en"
    assert args.center is None
    assert args.grid == 0          # 0이면 cell_km에서 자동 계산
    assert args.cell_km == 4.0
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


# --- main() 오케스트레이션: maps.browser/collect_place_urls/open_place를
# monkeypatch하여 네트워크 없이 검증한다. -------------------------------------

HTML_WITH_NAME = "<div role='main'><h1>OK Clinic</h1></div>"
HTML_WITHOUT_NAME = "<div role='main'></div>"

TIMEOUT_URL = (
    "https://www.google.com/maps/place/TimeoutClinic/@0,0,17z/"
    "data=!1s0x111111111111:0x222222222222"
)
OK_URL = (
    "https://www.google.com/maps/place/OkClinic/@0,0,17z/"
    "data=!1s0x333333333333:0x444444444444"
)
EMPTY_NAME_URL = (
    "https://www.google.com/maps/place/EmptyClinic/@0,0,17z/"
    "data=!1s0x555555555555:0x666666666666"
)


@contextlib.contextmanager
def _fake_browser(profile, headful, lang):
    yield object()


def _base_argv(out_path) -> list[str]:
    return ["klinik", "--region", "ID", "--out", str(out_path), "--delay", "0,0"]


def test_main_skips_place_that_times_out_and_still_writes_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "RETRY_BACKOFF_BASE", 0)
    monkeypatch.setattr(maps, "browser", _fake_browser)
    monkeypatch.setattr(
        maps, "collect_place_urls", lambda page, url: [TIMEOUT_URL, OK_URL]
    )

    def fake_open_place(page, url):
        if url == TIMEOUT_URL:
            raise PlaywrightTimeout("no h1")
        return HTML_WITH_NAME

    monkeypatch.setattr(maps, "open_place", fake_open_place)

    out_path = tmp_path / "out.csv"
    exit_code = cli.main(_base_argv(out_path))

    assert exit_code == cli.EXIT_OK
    with out_path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    # 헤더 1행 + 타임아웃난 장소를 건너뛴 나머지 1행만 남아야 한다.
    assert len(rows) == 2
    assert rows[1][1] == "OK Clinic"


def test_main_does_not_store_empty_name_and_retries_it_on_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "RETRY_BACKOFF_BASE", 0)
    monkeypatch.setattr(maps, "browser", _fake_browser)
    monkeypatch.setattr(maps, "collect_place_urls", lambda page, url: [EMPTY_NAME_URL])

    calls = []

    def fake_open_place(page, url):
        calls.append(url)
        return HTML_WITHOUT_NAME

    monkeypatch.setattr(maps, "open_place", fake_open_place)

    out_path = tmp_path / "out2.csv"
    argv = _base_argv(out_path)

    cli.main(argv)
    assert len(calls) == 1

    cli.main(argv)
    # seen에 등록되지 않았으므로 재실행이 같은 장소를 다시 시도한다.
    assert len(calls) == 2

    raw_path = out_path.with_suffix(".raw.jsonl")
    assert not raw_path.exists() or raw_path.read_text(encoding="utf-8").strip() == ""


class _FakeSitePage:
    """maps.fetch_site_html이 반환할 HTML을 URL별로 흉내 낸다."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.visited: list[str] = []


def _install_site_stubs(monkeypatch, pages: dict[str, str]) -> _FakeSitePage:
    site = _FakeSitePage(pages)

    def fake_open_site_page(page):
        return site

    def fake_fetch_site_html(site_page, url):
        site_page.visited.append(url)
        if url not in site_page.pages:
            raise RuntimeError("사이트 열기 실패")
        return site_page.pages[url]

    monkeypatch.setattr(maps, "open_site_page", fake_open_site_page)
    monkeypatch.setattr(maps, "fetch_site_html", fake_fetch_site_html)
    return site


def test_site_wa_link_promotes_record_to_confirmed(monkeypatch):
    site = _install_site_stubs(
        monkeypatch, {"https://klinik.co.id": '<a href="https://wa.me/6281100000001">Chat</a>'}
    )
    record = cli.build_record(
        {
            "place_cid": "0xa:0xb",
            "name": "Klinik Contoh",
            "category": "",
            "address": "",
            "phone_raw": "(021) 3915-000",
            "website": "https://klinik.co.id",
            "rating": "",
            "reviews": "",
            "maps_url": "",
        },
        region="ID",
        query="klinik",
        tile_label="",
    )
    assert record.whatsapp_status == "unlikely"

    [promoted] = cli._confirm_from_site(site, record, enabled=True)
    assert promoted.whatsapp_status == "confirmed"
    assert promoted.phone_e164 == "+6281100000001"
    assert site.visited == ["https://klinik.co.id"]


def test_site_with_several_numbers_yields_branch_records(monkeypatch):
    html = (
        '<a href="https://wa.me/6281100000001">진료</a>'
        '<a href="https://wa.me/6281100000002">특진</a>'
    )
    site = _install_site_stubs(monkeypatch, {"https://klinik.co.id": html})
    record = PlaceRecord(
        place_cid="0xa:0xb", name="Klinik Contoh", website="https://klinik.co.id"
    )

    records = cli._confirm_from_site(site, record, enabled=True)
    assert [r.place_cid for r in records] == ["0xa:0xb", "0xa:0xb#1"]
    assert [r.phone_e164 for r in records] == ["+6281100000001", "+6281100000002"]


def test_site_failure_keeps_the_map_record(monkeypatch):
    site = _install_site_stubs(monkeypatch, {})  # 어떤 URL도 열리지 않는다
    record = PlaceRecord(
        place_cid="0xa:0xb",
        name="Klinik Contoh",
        phone_e164="+62213915000",
        whatsapp_status="unlikely",
        website="https://dead-domain.example",
    )
    assert cli._confirm_from_site(site, record, enabled=True) == [record]


def test_crawl_disabled_never_touches_the_site(monkeypatch):
    site = _install_site_stubs(
        monkeypatch, {"https://klinik.co.id": '<a href="https://wa.me/6281100000001">x</a>'}
    )
    record = PlaceRecord(
        place_cid="0xa:0xb", name="Klinik Contoh", website="https://klinik.co.id"
    )
    assert cli._confirm_from_site(site, record, enabled=False) == [record]
    assert site.visited == []


def test_place_without_website_is_not_crawled(monkeypatch):
    site = _install_site_stubs(monkeypatch, {})
    record = PlaceRecord(place_cid="0xa:0xb", name="Klinik Contoh", website="")
    assert cli._confirm_from_site(site, record, enabled=True) == [record]
    assert site.visited == []
