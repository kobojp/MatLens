param([switch]$Installer)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
npm --prefix frontend ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
uv run --locked pyinstaller --noconfirm --windowed --onedir --name MatLens --paths . --add-data "frontend/dist;frontend/dist" --add-data "desktop/smoke.js;desktop" --collect-all webview --hidden-import uvicorn.logging --hidden-import uvicorn.loops.asyncio --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.lifespan.on desktop/main.py
if ($LASTEXITCODE -ne 0) { throw "EXE build failed" }
Copy-Item -LiteralPath packaging/install.ps1,packaging/Install-MatLens.cmd -Destination dist -Force
Compress-Archive -Path dist/MatLens,dist/install.ps1,dist/Install-MatLens.cmd -DestinationPath dist/MatLens-0.2.0-win-x64.zip -Force
if ($Installer) {
    $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    $compilerPath = if ($compiler) { $compiler.Source } else { "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
    if (-not (Test-Path -LiteralPath $compilerPath)) { throw "請安裝 Inno Setup 6 後重試 -Installer" }
    & $compilerPath packaging/MatLens.iss
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
}
