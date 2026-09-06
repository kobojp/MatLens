$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw "Python 環境同步失敗" }
npm --prefix frontend ci
if ($LASTEXITCODE -ne 0) { throw "前端依賴安裝失敗" }
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw "前端建置失敗" }
uv run --locked python -m desktop.main @args
if ($LASTEXITCODE -ne 0) { throw "桌面版啟動失敗，請查看 MatLens 紀錄" }
