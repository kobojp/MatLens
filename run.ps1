$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "找不到 uv。請先安裝 uv，再重新執行。"
}

if (-not (Test-Path -LiteralPath "frontend\dist\index.html")) {
    Write-Host "正在建置前端..."
    npm --prefix frontend ci
    npm --prefix frontend run build
}

Write-Host "MatLens 啟動於 http://127.0.0.1:8000"
uv sync --locked
uv run --locked uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
