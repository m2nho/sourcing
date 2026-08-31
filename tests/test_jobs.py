import json

import pytest

from sourcing.jobs import JobStatus, lead_summary, new_job_id, read_leads, tally


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def rec(cid, status, name="Klinik", phone="+6281234567890", wa=""):
    return {
        "place_cid": cid,
        "name": name,
        "whatsapp_status": status,
        "phone_e164": phone,
        "wa_link": wa,
        "website": "",
        "address": "",
        "maps_url": "",
    }


def test_job_ids_are_unique_and_readable():
    a, b = new_job_id("rumah sakit"), new_job_id("rumah sakit")
    assert a != b
    assert a.startswith("rumah-sakit-")


def test_tally_counts_each_status(tmp_path):
    path = tmp_path / "raw.jsonl"
    write_jsonl(path, [rec("1", "confirmed"), rec("2", "candidate"), rec("3", "unlikely"), rec("4", "confirmed")])
    assert tally(path) == {"total": 4, "confirmed": 2, "candidate": 1, "unlikely": 1}


def test_tally_of_missing_file_is_all_zero(tmp_path):
    assert tally(tmp_path / "nope.jsonl") == {"total": 0, "confirmed": 0, "candidate": 0, "unlikely": 0}


def test_tally_ignores_corrupt_lines(tmp_path):
    path = tmp_path / "raw.jsonl"
    write_jsonl(path, [rec("1", "confirmed")])
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{ broken\n\n")
    assert tally(path)["total"] == 1


def test_read_leads_filters_by_status(tmp_path):
    path = tmp_path / "raw.jsonl"
    write_jsonl(path, [rec("1", "confirmed"), rec("2", "candidate"), rec("3", "confirmed")])
    got = read_leads(path, status="confirmed", limit=10)
    assert [r["place_cid"] for r in got] == ["1", "3"]


def test_read_leads_caps_at_limit(tmp_path):
    path = tmp_path / "raw.jsonl"
    write_jsonl(path, [rec(str(i), "confirmed") for i in range(50)])
    assert len(read_leads(path, status=None, limit=5)) == 5


def test_read_leads_returns_only_useful_columns(tmp_path):
    path = tmp_path / "raw.jsonl"
    write_jsonl(path, [rec("1", "confirmed", wa="https://wa.me/6281234567890")])
    [row] = read_leads(path, status=None, limit=1)
    assert set(row) == {
        "place_cid",
        "name",
        "phone_e164",
        "whatsapp_status",
        "source",
        "wa_link",
        "website",
        "address",
        "maps_url",
    }


def test_lead_summary_is_compact(tmp_path):
    path = tmp_path / "raw.jsonl"
    write_jsonl(path, [rec("1", "confirmed"), rec("2", "candidate")])
    text = lead_summary(path)
    assert "2" in text and "confirmed" in text


@pytest.mark.parametrize(
    "returncode,expected",
    [(None, JobStatus.RUNNING), (0, JobStatus.DONE), (2, JobStatus.BLOCKED), (1, JobStatus.FAILED)],
)
def test_status_from_return_code(returncode, expected):
    assert JobStatus.from_returncode(returncode) is expected


def test_terminate_uses_process_group_on_posix(monkeypatch):
    """POSIX에서는 프로세스 그룹째 죽여야 자식 브라우저까지 정리된다."""
    from sourcing import mcp_server

    killed = {}
    monkeypatch.setattr(mcp_server.os, "name", "posix")
    monkeypatch.setattr(mcp_server.os, "getpgid", lambda pid: 999)
    monkeypatch.setattr(mcp_server.os, "killpg", lambda pgid, sig: killed.update(pgid=pgid))

    class FakeProcess:
        pid = 123

        def terminate(self):
            killed["terminate"] = True

    mcp_server._terminate(FakeProcess())
    assert killed == {"pgid": 999}


def test_terminate_falls_back_to_terminate_off_posix(monkeypatch):
    """Windows에는 프로세스 그룹이 없다. terminate()로 떨어져야 한다."""
    from sourcing import mcp_server

    killed = {}
    monkeypatch.setattr(mcp_server.os, "name", "nt")

    class FakeProcess:
        pid = 123

        def terminate(self):
            killed["terminate"] = True

    mcp_server._terminate(FakeProcess())
    assert killed == {"terminate": True}
