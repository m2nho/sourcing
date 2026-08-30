"""Claude Desktop·Codex 등 MCP 클라이언트에 수집 기능을 노출한다.

설계를 지배하는 사실: 수집 한 번이 20~40분 걸린다. MCP 툴 호출은 몇 초를
전제하므로, 수집은 작업(job)으로 띄우고 즉시 반환한다. 진행 상황은
JSONL 파일에서 읽는다 — 레코드마다 flush되므로 그것이 곧 실시간 진행률이다.

수집 본체는 기존 CLI를 서브프로세스로 띄워 재사용한다. 브라우저를 이 서버
프로세스 안에서 돌리지 않으므로 취소가 확실하고, 수집이 죽어도 서버는 산다.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from mcp.server import MCPServer

from sourcing.crawl import wa_numbers_from_html
from sourcing.jobs import JobStatus, lead_summary, new_job_id, read_leads, tally

#: 결과 파일을 두는 곳. 환경변수로 바꿀 수 있다.
OUTPUT_DIR = Path(os.environ.get("SOURCING_OUTPUT_DIR", "out")).resolve()

#: 프로젝트 루트. 서브프로세스를 여기서 띄워야 uv가 이 프로젝트를 찾는다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

mcp = MCPServer("sourcing")


@dataclass
class Job:
    job_id: str
    keyword: str
    out_csv: Path
    raw_jsonl: Path
    log_path: Path
    process: subprocess.Popen
    started_at: float = field(default_factory=time.time)

    @property
    def status(self) -> JobStatus:
        return JobStatus.from_returncode(self.process.poll())

    def snapshot(self) -> dict:
        counts = tally(self.raw_jsonl)
        payload = {
            "job_id": self.job_id,
            "keyword": self.keyword,
            "status": self.status.value,
            "elapsed_seconds": round(time.time() - self.started_at),
            "counts": counts,
            "summary": lead_summary(self.raw_jsonl),
            "csv_path": str(self.out_csv),
        }
        if self.status in (JobStatus.FAILED, JobStatus.BLOCKED):
            payload["log_tail"] = _tail(self.log_path)
        return payload


_jobs: dict[str, Job] = {}


@mcp.tool()
def start_collection(
    keyword: str,
    region: str,
    lat: float,
    lng: float,
    radius_km: float = 12.0,
    grid: int = 3,
    limit: int = 0,
    lang: str = "en",
    crawl: bool = True,
) -> dict:
    """구글 맵에서 병원·클리닉을 수집하고 WhatsApp 연락처를 찾는 작업을 시작한다.

    즉시 반환한다. 실제 수집은 20~40분 걸리므로 check_collection으로 진행을 확인하라.

    Args:
        keyword: 검색어. 현지어가 훨씬 잘 나온다 (인니 'klinik', 베트남 'phòng khám').
            실측상 종합병원('rumah sakit')보다 클리닉('klinik')의 수확률이 5배 높다.
        region: 전화번호 정규화 기준 ISO 국가코드 (ID, VN, PH, US ...).
        lat: 검색 중심 위도. 도시명을 좌표로 바꿔서 넘겨라.
        lng: 검색 중심 경도.
        radius_km: 격자가 덮을 반경.
        grid: 한 변의 타일 수. 구글 맵은 검색당 약 120건에서 잘리므로 넓은 지역은 격자로 쪼갠다.
        limit: 수집할 최대 장소 수. 0이면 제한 없음.
        lang: 구글 맵 UI 언어.
        crawl: 웹사이트를 훑어 WhatsApp 링크를 찾을지. 끄면 훨씬 빠르지만
            confirmed가 거의 나오지 않는다 (실측 0.5% 대 47%).
    """
    running = _running_job()
    if running is not None:
        return {
            "started": False,
            "reason": "이미 수집이 돌고 있습니다. 브라우저가 하나뿐이고 동시 접속은 차단 위험을 키웁니다.",
            "running_job": running.snapshot(),
        }

    job_id = new_job_id(keyword)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUTPUT_DIR / f"{job_id}.csv"
    log_path = OUTPUT_DIR / f"{job_id}.log"

    command = [
        "uv", "run", "sourcing", keyword,
        "--region", region,
        "--lang", lang,
        f"--center={lat:.6f},{lng:.6f}",
        "--radius-km", str(radius_km),
        "--grid", str(grid),
        "--out", str(out_csv),
    ]
    if limit:
        command += ["--limit", str(limit)]
    if not crawl:
        command.append("--no-crawl")

    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # 취소할 때 자식 브라우저까지 함께 정리한다
    )
    job = Job(
        job_id=job_id,
        keyword=keyword,
        out_csv=out_csv,
        raw_jsonl=out_csv.with_suffix(".raw.jsonl"),
        log_path=log_path,
        process=process,
    )
    _jobs[job_id] = job
    return {
        "started": True,
        "job_id": job_id,
        "note": "수집이 시작됐습니다. check_collection(job_id)로 진행을 확인하세요. 20~40분 걸립니다.",
        "csv_path": str(out_csv),
    }


@mcp.tool()
def check_collection(job_id: str) -> dict:
    """수집 작업의 진행 상황과 현재까지의 집계를 돌려준다."""
    job = _jobs.get(job_id)
    if job is None:
        return {"error": f"모르는 작업입니다: {job_id}", "known_jobs": list(_jobs)}
    return job.snapshot()


@mcp.tool()
def list_collections() -> dict:
    """이 세션에서 시작한 수집 작업들."""
    return {"jobs": [job.snapshot() for job in _jobs.values()]}


@mcp.tool()
def cancel_collection(job_id: str) -> dict:
    """돌고 있는 수집을 중단한다. 그때까지 수집한 레코드는 그대로 남는다."""
    job = _jobs.get(job_id)
    if job is None:
        return {"error": f"모르는 작업입니다: {job_id}"}
    if job.status is not JobStatus.RUNNING:
        return {"cancelled": False, "reason": "이미 끝난 작업입니다.", "job": job.snapshot()}
    os.killpg(os.getpgid(job.process.pid), signal.SIGTERM)
    return {"cancelled": True, "note": "수집한 레코드는 JSONL에 남아 있어 같은 조건으로 재개할 수 있습니다."}


@mcp.tool()
def get_leads(job_id: str = "", csv_path: str = "", status: str = "", limit: int = 20) -> dict:
    """수집 결과를 읽는다. 레코드 전체가 아니라 필요한 만큼만 돌려준다.

    Args:
        job_id: start_collection이 준 작업 id. csv_path 대신 쓸 수 있다.
        csv_path: 결과 CSV 경로. 이전 세션의 결과를 읽을 때 쓴다.
        status: 'confirmed'(업체가 선언한 확정 번호) / 'candidate'(모바일 번호 추측) /
            'unlikely'. 비우면 전부.
        limit: 최대 반환 건수.
    """
    raw = _resolve_raw_path(job_id, csv_path)
    if raw is None:
        return {"error": "job_id 또는 csv_path 중 하나가 필요합니다."}
    if not raw.exists():
        return {"error": f"결과 파일이 없습니다: {raw}"}
    return {
        "summary": lead_summary(raw),
        "counts": tally(raw),
        "leads": read_leads(raw, status or None, max(1, limit)),
        "source": str(raw),
    }


@mcp.tool()
def check_site_whatsapp(url: str) -> dict:
    """웹사이트 한 곳을 열어 선언된 WhatsApp 번호를 찾는다. 몇 초면 끝난다.

    업체가 href에 넣어둔 wa.me / api.whatsapp.com 링크만 읽는다. 본문에 적힌
    맨 번호는 WhatsApp인지 알 수 없으므로 쓰지 않는다.
    """
    from sourcing import maps  # 브라우저는 필요할 때만 띄운다

    profile = PROJECT_ROOT / ".browser-profile"
    try:
        with maps.browser(profile, headful=False, lang="en") as page:
            site = maps.open_site_page(page)
            html = maps.fetch_site_html(site, url)
    except Exception as exc:  # noqa: BLE001 - 사이트 실패를 그대로 알려준다
        return {"url": url, "error": f"열지 못했습니다: {exc}"}

    numbers = wa_numbers_from_html(html)
    return {
        "url": url,
        "numbers": numbers,
        "wa_links": [f"https://wa.me/{n.lstrip('+')}" for n in numbers],
        "found": bool(numbers),
    }


def _running_job() -> Job | None:
    return next((job for job in _jobs.values() if job.status is JobStatus.RUNNING), None)


def _resolve_raw_path(job_id: str, csv_path: str) -> Path | None:
    if job_id:
        job = _jobs.get(job_id)
        return job.raw_jsonl if job else None
    if csv_path:
        return Path(csv_path).with_suffix(".raw.jsonl")
    return None


def _tail(path: Path, lines: int = 12) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:])


def main() -> None:
    """stdio로 MCP 서버를 띄운다. Claude Desktop·Codex 둘 다 이 방식을 쓴다."""
    mcp.run()


if __name__ == "__main__":
    sys.exit(main())
