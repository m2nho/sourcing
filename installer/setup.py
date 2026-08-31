"""sourcing 설치 프로그램.

컴퓨터를 잘 모르는 사람이 더블클릭 한 번으로 Codex에 연결하는 것이 목표다.
그래서 표준 라이브러리만 쓴다 — 이 파일은 단일 exe로 묶여 배포되고, 대상
컴퓨터에는 Python도 uv도 없다는 전제다.

모든 메시지는 한국어 평문이고, 실패하면 무엇이 잘못됐고 무엇을 하면 되는지
알려준다. 창이 곧바로 닫히면 사용자가 아무것도 못 읽으므로 마지막에 기다린다.
"""

from __future__ import annotations

import tomllib

REPO_ZIP_URL = "https://github.com/m2nho/sourcing/archive/refs/heads/master.zip"
SERVER_NAME = "sourcing"


def to_toml_path(path: str) -> str:
    """Windows 경로를 TOML에 넣을 수 있게 바꾼다.

    TOML에서 역슬래시는 이스케이프 문자다. `C:\\Users`를 그대로 쓰면
    `\\U`가 유니코드 이스케이프로 해석돼 파일 전체가 깨진다.
    """
    return path.replace("\\", "/")


def codex_config_block(install_dir: str) -> str:
    """Codex의 config.toml에 넣을 서버 등록 블록."""
    return (
        f"\n[mcp_servers.{SERVER_NAME}]\n"
        'command = "uv"\n'
        f'args = ["--directory", "{to_toml_path(install_dir)}", "run", "sourcing-mcp"]\n'
    )


def merge_codex_config(existing: str, install_dir: str) -> str | None:
    """기존 설정 뒤에 서버 등록을 덧붙인다.

    이미 등록돼 있으면 None을 돌려준다 — 경로가 다르더라도 덮어쓰지 않는다.
    사용자가 직접 고쳐뒀을 수 있고, 그 판단이 우리 것보다 우선이다.

    설정을 통째로 다시 쓰지 않고 텍스트로 덧붙이는 이유: 파싱 후 재작성하면
    주석과 서식이 전부 사라진다. 남의 설정 파일에 할 짓이 아니다.

    Raises:
        ValueError: 기존 파일이 올바른 TOML이 아닐 때. 덮어쓰면 사용자의 다른
            설정을 잃으므로 손대지 않고 사람에게 넘긴다.
    """
    try:
        parsed = tomllib.loads(existing)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"기존 Codex 설정을 읽을 수 없습니다: {exc}") from exc

    if SERVER_NAME in parsed.get("mcp_servers", {}):
        return None

    separator = "" if existing.endswith("\n") or not existing else "\n"
    return existing + separator + codex_config_block(install_dir)


# ─────────────────────────────────────────────────────────────────────────
# 아래는 실제 설치 절차. Windows에서 돌며, 위의 순수 로직을 사용한다.
# ─────────────────────────────────────────────────────────────────────────

import io
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

INSTALL_DIR = Path(os.environ.get("USERPROFILE", Path.home())) / "sourcing"
CODEX_CONFIG = Path(os.environ.get("USERPROFILE", Path.home())) / ".codex" / "config.toml"
UV_INSTALL_PS1 = "https://astral.sh/uv/install.ps1"


class SetupError(Exception):
    """사용자에게 그대로 보여줄 수 있는 실패."""


def enable_utf8_console() -> None:
    """콘솔이 한글을 찍을 수 있게 만든다.

    한국어 Windows는 cp949라 그대로도 되지만, 영문 Windows(cp437)에서는
    한글 출력이 UnicodeEncodeError로 죽는다. 받는 분이 어떤 Windows를 쓰는지
    알 수 없으므로 코드페이지를 UTF-8로 올리고, 그래도 안 되면 글자를
    대체 문자로 바꿔서라도 안내가 보이게 한다.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:  # noqa: BLE001 - 콘솔 설정 실패로 설치를 멈출 이유는 없다
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def say(message: str = "") -> None:
    print(message, flush=True)


def step(number: int, total: int, title: str) -> None:
    say(f"\n[{number}/{total}] {title}")


def run(command: list[str], cwd: Path | None = None, quiet: bool = True) -> str:
    """명령을 실행하고 출력을 돌려준다. 실패하면 SetupError."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
    except FileNotFoundError as exc:
        raise SetupError(f"'{command[0]}' 을(를) 찾을 수 없습니다.") from exc
    if result.returncode != 0:
        tail = (result.stdout + result.stderr).strip().splitlines()[-6:]
        raise SetupError("\n".join(tail) or f"명령이 실패했습니다: {' '.join(command)}")
    if not quiet:
        say(result.stdout.strip())
    return result.stdout


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def add_user_paths() -> None:
    """uv를 방금 설치했으면 현재 프로세스의 PATH에는 아직 없다."""
    for extra in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        if extra.is_dir():
            os.environ["PATH"] = f"{extra};{os.environ.get('PATH', '')}"


def ensure_codex() -> None:
    if has_command("codex"):
        say("  Codex가 설치되어 있습니다.")
        return
    raise SetupError(
        "Codex가 설치되어 있지 않습니다.\n\n"
        "  이 프로그램은 Codex에 기능을 연결해 주는 역할만 합니다.\n"
        "  Codex를 먼저 설치해 주세요:\n\n"
        "    1) https://nodejs.org 에서 Node.js를 설치합니다 (LTS 버튼)\n"
        "    2) 설치 후 컴퓨터를 다시 시작합니다\n"
        "    3) 시작 메뉴에서 'PowerShell'을 열고 다음을 붙여넣습니다:\n"
        "         npm install -g @openai/codex\n"
        "    4) 'codex' 를 입력해 로그인까지 마칩니다\n\n"
        "  그 다음 이 프로그램을 다시 실행해 주세요."
    )


def ensure_uv() -> None:
    if has_command("uv"):
        say("  uv가 이미 설치되어 있습니다.")
        return
    say("  uv를 설치합니다. 잠시 걸립니다...")
    run(["powershell", "-NoProfile", "-Command", f"irm {UV_INSTALL_PS1} | iex"])
    add_user_paths()
    if not has_command("uv"):
        raise SetupError(
            "uv를 설치했지만 아직 인식되지 않습니다.\n"
            "  컴퓨터를 다시 시작한 뒤 이 프로그램을 한 번 더 실행해 주세요."
        )
    say("  uv 설치 완료.")


def download_code() -> None:
    say(f"  받는 위치: {INSTALL_DIR}")
    try:
        with urllib.request.urlopen(REPO_ZIP_URL, timeout=120) as response:
            payload = response.read()
    except urllib.error.URLError as exc:
        raise SetupError(f"코드를 내려받지 못했습니다. 인터넷 연결을 확인해 주세요.\n  ({exc})") from exc

    if INSTALL_DIR.exists():
        say("  기존 폴더가 있어 최신 내용으로 덮어씁니다.")
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        archive.extractall(INSTALL_DIR.parent)
    extracted = INSTALL_DIR.parent / "sourcing-master"
    extracted.rename(INSTALL_DIR)
    say("  코드 준비 완료.")


def install_dependencies() -> None:
    say("  라이브러리를 설치합니다...")
    run(["uv", "sync"], cwd=INSTALL_DIR)
    say("  브라우저를 내려받습니다. 200MB 정도라 몇 분 걸립니다...")
    run(["uv", "run", "playwright", "install", "chromium"], cwd=INSTALL_DIR)
    say("  설치 완료.")


def register_with_codex() -> None:
    CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    existing = CODEX_CONFIG.read_text(encoding="utf-8") if CODEX_CONFIG.exists() else ""
    try:
        merged = merge_codex_config(existing, str(INSTALL_DIR))
    except ValueError as exc:
        raise SetupError(
            f"{exc}\n"
            f"  설정 파일을 직접 확인해 주세요: {CODEX_CONFIG}\n"
            "  (이 프로그램은 파일을 건드리지 않았습니다.)"
        ) from exc

    if merged is None:
        say("  이미 Codex에 등록되어 있습니다. 그대로 둡니다.")
        return
    if existing:
        backup = CODEX_CONFIG.with_suffix(".toml.bak")
        backup.write_text(existing, encoding="utf-8")
        say(f"  기존 설정을 백업했습니다: {backup.name}")
    CODEX_CONFIG.write_text(merged, encoding="utf-8")
    say("  Codex에 등록했습니다.")


def warm_up_browser() -> None:
    say("  구글 지도에 처음 접속합니다. 브라우저 창이 열립니다.")
    say("  동의 화면이나 '로봇이 아닙니다' 확인이 나오면 직접 넘겨 주세요.")
    say("  창이 저절로 닫히면 정상입니다. (최대 5분)")
    try:
        run(
            ["uv", "run", "sourcing", "klinik", "--region", "ID", "--lang", "id",
             "--limit", "2", "--headful", "--out", "out/설치확인.csv"],
            cwd=INSTALL_DIR,
        )
        say("  접속 확인 완료.")
    except SetupError as exc:
        say("  ! 첫 접속을 마치지 못했습니다. 설치는 계속됩니다.")
        say(f"    ({str(exc).splitlines()[-1]})")
        say("    나중에 Codex에서 수집이 막히면 이 프로그램을 다시 실행해 주세요.")


def verify() -> None:
    run(["uv", "run", "sourcing", "--help"], cwd=INSTALL_DIR)
    say("  정상 동작을 확인했습니다.")


def main() -> int:
    enable_utf8_console()
    say("=" * 58)
    say("  병원 WhatsApp 연락처 수집 도구 설치")
    say("=" * 58)
    say("\n설치하는 동안 컴퓨터를 켜 두세요. 5~10분쯤 걸립니다.")

    steps = [
        ("Codex 확인", ensure_codex),
        ("uv 준비", ensure_uv),
        ("코드 내려받기", download_code),
        ("라이브러리와 브라우저 설치", install_dependencies),
        ("Codex에 연결", register_with_codex),
        ("첫 접속 확인", warm_up_browser),
        ("동작 확인", verify),
    ]
    try:
        for index, (title, action) in enumerate(steps, start=1):
            step(index, len(steps), title)
            action()
    except SetupError as exc:
        say("\n" + "=" * 58)
        say("  설치를 마치지 못했습니다")
        say("=" * 58)
        say(f"\n{exc}\n")
        input("엔터를 누르면 창이 닫힙니다... ")
        return 1

    say("\n" + "=" * 58)
    say("  설치가 끝났습니다")
    say("=" * 58)
    say("\n이제 Codex를 열고 이렇게 말해 보세요:")
    say('\n  "자카르타 클리닉 WhatsApp 연락처 수집해줘"')
    say('  "지금까지 결과 엑셀로 뽑아줘"')
    say(f"\n결과 엑셀은 여기에 저장됩니다:\n  {INSTALL_DIR / 'out'}")
    say("\n수집은 20~40분 걸립니다. 시작한 뒤 다른 일을 하셔도 됩니다.")
    input("\n엔터를 누르면 창이 닫힙니다... ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
