# sourcing

구글 맵에서 병원·클리닉의 WhatsApp 연락처를 수집하는 CLI.

## 설치

```
mise install
uv sync
uv run playwright install chromium
```

## 사용

```
uv run sourcing "rumah sakit" --region ID --lang id --out out/jakarta.csv
```

자세한 옵션은 `uv run sourcing --help`.
