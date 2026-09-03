import json

from sourcing.merge import merge_jsonl


def write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def rec(cid, name, status="confirmed", query="q"):
    return {
        "place_cid": cid, "name": name, "whatsapp_status": status,
        "phone_e164": "+447700000001", "query": query,
    }


def test_merges_records_from_several_files(tmp_path):
    write(tmp_path / "a.raw.jsonl", [rec("1", "A"), rec("2", "B")])
    write(tmp_path / "b.raw.jsonl", [rec("3", "C")])
    out = tmp_path / "all.raw.jsonl"
    assert merge_jsonl([tmp_path / "a.raw.jsonl", tmp_path / "b.raw.jsonl"], out) == 3


def test_same_clinic_found_in_two_districts_appears_once(tmp_path):
    # 지구가 겹치면 같은 곳이 두 번 나온다. 하나로 합친다.
    write(tmp_path / "a.raw.jsonl", [rec("1", "A", query="Mayfair")])
    write(tmp_path / "b.raw.jsonl", [rec("1", "A", query="Soho")])
    out = tmp_path / "all.raw.jsonl"
    assert merge_jsonl([tmp_path / "a.raw.jsonl", tmp_path / "b.raw.jsonl"], out) == 1


def test_the_stronger_grade_wins_when_a_clinic_repeats(tmp_path):
    # 한 지구에서는 추정, 다른 지구에서는 확정으로 잡혔다면 확정을 남긴다.
    write(tmp_path / "a.raw.jsonl", [rec("1", "A", status="candidate")])
    write(tmp_path / "b.raw.jsonl", [rec("1", "A", status="confirmed")])
    out = tmp_path / "all.raw.jsonl"
    merge_jsonl([tmp_path / "a.raw.jsonl", tmp_path / "b.raw.jsonl"], out)
    [row] = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert row["whatsapp_status"] == "confirmed"


def test_branch_numbers_are_kept_separate(tmp_path):
    write(tmp_path / "a.raw.jsonl", [rec("1", "A"), rec("1#1", "A")])
    out = tmp_path / "all.raw.jsonl"
    assert merge_jsonl([tmp_path / "a.raw.jsonl"], out) == 2


def test_missing_files_are_skipped(tmp_path):
    write(tmp_path / "a.raw.jsonl", [rec("1", "A")])
    out = tmp_path / "all.raw.jsonl"
    assert merge_jsonl([tmp_path / "a.raw.jsonl", tmp_path / "nope.jsonl"], out) == 1
