# sourcing 설치 스크립트.
#
# exe로 만들지 않는 이유: PyInstaller onefile은 실행 시 자기를 임시폴더에 풀어
# 실행하는데, 이것이 악성코드 패커와 행위가 같아 AhnLab·Defender가 오탐한다.
# 이 스크립트가 하는 일(내려받기, 압축풀기, 명령 실행, 설정 파일 쓰기)은 전부
# PowerShell이 기본으로 하는 일이라 애초에 포장할 이유가 없었다.

$ErrorActionPreference = "Stop"

$RepoZip     = "https://github.com/m2nho/sourcing/archive/refs/heads/master.zip"
$InstallDir  = Join-Path $env:USERPROFILE "sourcing"
$CodexConfig = Join-Path $env:USERPROFILE ".codex\config.toml"
$TotalSteps  = 7

function Say([string]$Text = "") { Write-Host $Text }
function Step([int]$N, [string]$Title) { Write-Host ""; Write-Host "[$N/$TotalSteps] $Title" -ForegroundColor Cyan }
function Ok([string]$Text) { Write-Host "  $Text" -ForegroundColor Green }
function Info([string]$Text) { Write-Host "  $Text" }

function Fail([string]$Message) {
    Write-Host ""
    Write-Host ("=" * 58) -ForegroundColor Red
    Write-Host "  설치를 마치지 못했습니다" -ForegroundColor Red
    Write-Host ("=" * 58) -ForegroundColor Red
    Write-Host ""
    Write-Host $Message
    Write-Host ""
    Read-Host "엔터를 누르면 창이 닫힙니다"
    exit 1
}

function Refresh-Path {
    # 방금 설치한 프로그램은 현재 창의 PATH에 아직 없다.
    $user    = [Environment]::GetEnvironmentVariable("Path", "User")
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $env:Path = "$env:USERPROFILE\.local\bin;$user;$machine"
}

function Have([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Run([string]$Exe, [string[]]$Arguments) {
    # 파라미터를 $Args로 두면 안 된다. PowerShell의 자동 변수와 겹쳐서
    # @Args가 내 인자가 아니라 빈 자동 변수를 펼친다 - 명령이 인자 없이
    # 실행되고 도움말만 뱉는다.
    # uv 같은 도구는 진행 상황을 stderr로 쓴다. ErrorActionPreference가
    # Stop이면 그 출력만으로 던져버리므로, 이 안에서는 종료 코드로만 판단한다.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $Exe @Arguments 2>&1
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($LASTEXITCODE -ne 0) {
        $tail = ($out | Select-Object -Last 6) -join "`n"
        throw $tail
    }
    # 출력을 돌려주지 않는다. 호출부가 받지 않으면 파이프라인으로 흘러
    # 그대로 화면에 찍히는데, uv의 stderr 진행 메시지가 빨간 오류처럼 보여
    # 설치가 실패한 줄 알게 된다.
}

# ── 1. Codex 확인 ────────────────────────────────────────────────
# 2026년 7월부터 ChatGPT 데스크탑 앱이 Codex를 품었고, 앱·CLI·IDE 확장이
# 같은 ~/.codex/config.toml 을 공유한다. 그래서 codex CLI가 없어도 앱만으로
# 쓸 수 있다. 확인이 틀릴 수 있는 검사로 설치를 막지 않는다 - 감지해서
# 알려주되, 설정은 어느 쪽이든 같은 파일에 쓰면 되므로 계속 진행한다.
function Ensure-Codex {
    if (Have "codex") {
        Ok "Codex CLI를 찾았습니다."
        return
    }
    if (Test-Path (Split-Path $CodexConfig -Parent)) {
        Ok "Codex 설정 폴더를 찾았습니다. (ChatGPT 앱 또는 IDE 확장)"
        return
    }
    Info "Codex를 찾지 못했습니다. 설치는 계속합니다."
    Info ""
    Info "  ChatGPT 데스크탑 앱을 쓰신다면 그대로 두시면 됩니다."
    Info "  설정이 같은 파일을 쓰므로, 설치가 끝나면 앱에서 바로 잡힙니다."
    Info ""
    Info "  아직 아무것도 없다면 둘 중 하나를 설치해 주세요:"
    Info "    - ChatGPT 데스크탑 앱  (쉬움, 권장)"
    Info "    - Codex CLI            (Node.js 설치 후 npm install -g @openai/codex)"
    $script:CodexMissing = $true
}

# ── 2. uv 준비 ───────────────────────────────────────────────────
function Ensure-Uv {
    if (Have "uv") { Ok "uv가 이미 설치되어 있습니다."; return }
    Info "uv를 설치합니다. 30초쯤 걸립니다..."
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Fail "uv를 설치하지 못했습니다. 인터넷 연결을 확인해 주세요.`n  ($_)"
    }
    Refresh-Path
    if (-not (Have "uv")) {
        Fail "uv를 설치했지만 아직 인식되지 않습니다.`n  컴퓨터를 다시 시작한 뒤 이 프로그램을 한 번 더 실행해 주세요."
    }
    Ok "uv 설치 완료."
}

# ── 3. 코드 내려받기 ─────────────────────────────────────────────
function Get-Code {
    Info "받는 위치: $InstallDir"
    $zip = Join-Path $env:TEMP "sourcing.zip"
    try {
        Invoke-WebRequest -Uri $RepoZip -OutFile $zip -UseBasicParsing
    } catch {
        Fail "코드를 내려받지 못했습니다. 인터넷 연결을 확인해 주세요.`n  ($_)"
    }
    if (Test-Path $InstallDir) {
        Info "기존 폴더가 있어 최신 내용으로 덮어씁니다."
        Remove-Item $InstallDir -Recurse -Force
    }
    Expand-Archive -Path $zip -DestinationPath $env:USERPROFILE -Force
    Rename-Item (Join-Path $env:USERPROFILE "sourcing-master") $InstallDir
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Ok "코드 준비 완료."
}

# ── 4. 라이브러리와 브라우저 ─────────────────────────────────────
function Install-Dependencies {
    Push-Location $InstallDir
    try {
        Info "라이브러리를 설치합니다..."
        Run "uv" @("sync")
        Info "브라우저를 내려받습니다. 200MB 정도라 몇 분 걸립니다..."
        Run "uv" @("run", "playwright", "install", "chromium")
        Ok "설치 완료."
    } catch {
        Pop-Location
        Fail "설치 중 문제가 생겼습니다.`n`n$_"
    }
    Pop-Location
}

# ── 5. Codex에 연결 ──────────────────────────────────────────────
function Register-Codex {
    $dir = Split-Path $CodexConfig -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    $existing = if (Test-Path $CodexConfig) { Get-Content $CodexConfig -Raw -Encoding UTF8 } else { "" }
    if ($null -eq $existing) { $existing = "" }

    if ($existing -match '\[mcp_servers\.sourcing\]') {
        Ok "이미 Codex에 등록되어 있습니다. 그대로 둡니다."
        return
    }

    # TOML에서 역슬래시는 이스케이프 문자라 슬래시로 바꾼다.
    $tomlPath = $InstallDir -replace '\\', '/'
    $block = @"

[mcp_servers.sourcing]
command = "uv"
args = ["--directory", "$tomlPath", "run", "sourcing-mcp"]
"@

    if ($existing.Trim()) {
        Copy-Item $CodexConfig "$CodexConfig.bak" -Force
        Info "기존 설정을 백업했습니다: config.toml.bak"
    }
    # 기존 내용은 그대로 두고 뒤에 덧붙인다. 다시 써넣으면 주석과 서식이 사라진다.
    [System.IO.File]::WriteAllText($CodexConfig, $existing + $block, (New-Object System.Text.UTF8Encoding $false))
    Ok "Codex에 등록했습니다."
}

# ── 6. 첫 접속 확인 ──────────────────────────────────────────────
function Warm-Up {
    Info "구글 지도에 처음 접속합니다. 브라우저 창이 열립니다."
    Info "동의 화면이나 '로봇이 아닙니다' 확인이 나오면 직접 넘겨 주세요."
    Info "창이 저절로 닫히면 정상입니다."
    Push-Location $InstallDir
    try {
        Run "uv" @("run", "sourcing", "klinik", "--region", "ID", "--lang", "id",
                   "--limit", "2", "--headful", "--out", "out/설치확인.csv")
        Ok "접속 확인 완료."
    } catch {
        Info "! 첫 접속을 마치지 못했습니다. 설치는 계속됩니다."
        Info "  나중에 수집이 막히면 이 프로그램을 다시 실행해 주세요."
    }
    Pop-Location
}

# ── 7. 동작 확인 ─────────────────────────────────────────────────
function Verify {
    Push-Location $InstallDir
    try {
        Run "uv" @("run", "sourcing", "--help")
        Ok "정상 동작을 확인했습니다."
    } catch {
        Pop-Location
        Fail "설치는 됐지만 실행 확인에 실패했습니다.`n`n$_"
    }
    Pop-Location
}

# ── 실행 ─────────────────────────────────────────────────────────
Write-Host ("=" * 58)
Write-Host "  병원 WhatsApp 연락처 수집 도구 설치"
Write-Host ("=" * 58)
Say ""
Say "설치하는 동안 컴퓨터를 켜 두세요. 5~10분쯤 걸립니다."

Step 1 "Codex 확인";                Ensure-Codex
Step 2 "uv 준비";                   Ensure-Uv
Step 3 "코드 내려받기";              Get-Code
Step 4 "라이브러리와 브라우저 설치";  Install-Dependencies
Step 5 "Codex에 연결";              Register-Codex
Step 6 "첫 접속 확인";               Warm-Up
Step 7 "동작 확인";                  Verify

Write-Host ""
Write-Host ("=" * 58) -ForegroundColor Green
Write-Host "  설치가 끝났습니다" -ForegroundColor Green
Write-Host ("=" * 58) -ForegroundColor Green
Say ""
if ($script:CodexMissing) {
    Say "! Codex를 찾지 못했지만 설정은 저장해 뒀습니다."
    Say "  ChatGPT 데스크탑 앱이나 Codex를 설치하면 자동으로 잡힙니다."
    Say ""
}
Say "ChatGPT 앱이나 Codex가 이미 열려 있으면 한 번 껐다 켜 주세요."
Say "설정을 다시 읽어야 새 기능이 보입니다."
Say ""
Say "그다음 이렇게 말해 보세요:"
Say ""
Say '  "자카르타 클리닉 WhatsApp 연락처 수집해줘"'
Say '  "지금까지 결과 엑셀로 뽑아줘"'
Say ""
Say "결과 엑셀은 여기에 저장됩니다:"
Say "  $InstallDir\out"
Say ""
Say "수집은 20~40분 걸립니다. 시작한 뒤 다른 일을 하셔도 됩니다."
Say ""
Read-Host "엔터를 누르면 창이 닫힙니다"
