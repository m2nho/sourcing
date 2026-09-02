import json

from sourcing.store import CSV_COLUMNS, JsonlStore, PlaceRecord, export_csv


def make_record(cid: str, name: str = "RS Contoh") -> PlaceRecord:
    return PlaceRecord(place_cid=cid, name=name, phone_e164="+6281234567890")


def test_csv_columns_are_the_agreed_order():
    assert CSV_COLUMNS == [
        "place_cid",
        "name",
        "category",
        "address",
        "phone_raw",
        "phone_e164",
        "phone_type",
        "whatsapp_status",
        "source",
        "profile_name",
        "wa_link",
        "website",
        "rating",
        "reviews",
        "maps_url",
        "query",
        "tile",
        "scraped_at",
    ]


def test_seen_cids_is_empty_for_missing_file(tmp_path):
    store = JsonlStore(tmp_path / "missing" / "raw.jsonl")
    assert store.seen_cids() == set()


def test_append_then_seen_cids_round_trips(tmp_path):
    store = JsonlStore(tmp_path / "raw.jsonl")
    store.append(make_record("0xa:0xb"))
    store.append(make_record("0xc:0xd"))
    assert store.seen_cids() == {"0xa:0xb", "0xc:0xd"}


def test_append_writes_one_json_object_per_line(tmp_path):
    path = tmp_path / "raw.jsonl"
    store = JsonlStore(path)
    store.append(make_record("0xa:0xb", name="RS Ünïcode 베트남"))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["name"] == "RS Ünïcode 베트남"


def test_records_skips_duplicate_cids_keeping_the_first(tmp_path):
    store = JsonlStore(tmp_path / "raw.jsonl")
    store.append(make_record("0xa:0xb", name="첫번째"))
    store.append(make_record("0xa:0xb", name="두번째"))
    records = list(store.records())
    assert len(records) == 1
    assert records[0].name == "첫번째"


def test_records_skips_corrupt_lines(tmp_path):
    path = tmp_path / "raw.jsonl"
    store = JsonlStore(path)
    store.append(make_record("0xa:0xb"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")
        fh.write("\n")
    assert len(list(store.records())) == 1


def test_export_csv_writes_header_and_rows(tmp_path):
    store = JsonlStore(tmp_path / "raw.jsonl")
    store.append(make_record("0xa:0xb"))
    store.append(make_record("0xc:0xd"))
    out = tmp_path / "out" / "result.csv"
    assert export_csv(store, out) == 2
    text = out.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(text.strip().splitlines()) == 3


def test_export_csv_is_idempotent(tmp_path):
    store = JsonlStore(tmp_path / "raw.jsonl")
    store.append(make_record("0xa:0xb"))
    out = tmp_path / "result.csv"
    export_csv(store, out)
    first = out.read_bytes()
    export_csv(store, out)
    assert out.read_bytes() == first
