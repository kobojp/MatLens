# MatLens 正式版操作

所有命令從選定的 repository 根目錄執行。每個外部指令完成後確認 exit code，
非零即停止該階段；不要讓後面的成功命令掩蓋前面的失敗。長時間建置與測試使用短時間 yield，
在等待期間持續提供進度。

## 1. 確認來源、版本與簽章

```powershell
git status --short
git worktree list
git remote -v
gh auth status
gh release list --repo kobojp/MatLens --limit 5
```

檢查使用者要發布的修正確實在目前 checkout。不要只因另一個目錄有同名 EXE，
就認定它來自目前提交。未提交的無關修改先保留，不混入版本提交。

先記下升級測試的上一個公開版本，再選擇新版本。先改 `desktop/version.py`，
只同步其餘版本欄位，不順便升級依賴。補上 `docs/release-v<版本>.md`，描述本版行為與安裝方式。

改版後取得所有路徑，避免寫死版本或帳號：

```powershell
$repoRoot = (git rev-parse --show-toplevel).Trim()
$version = (uv run --locked python -c "from desktop.version import VERSION; print(VERSION)").Trim()
$tag = "v$version"
$checks = '.agents\skills\matlens-release\scripts\release_checks.py'
$reportRoot = Join-Path $repoRoot "build\release-$version"
New-Item -ItemType Directory -Path $reportRoot -Force | Out-Null
$signingKeyPath = (uv run --locked python $checks key | ConvertFrom-Json).path
```

必要時以 `--key` 或本機環境變數 `MATLENS_SIGNING_KEY_PATH` 指定既有私鑰。
`key` 會先驗證公鑰，只輸出本機路徑與匹配結果，不輸出私鑰內容。
預設位置找不到時，它也會檢查 LocalAppData 下 `Packages/OpenAI.Codex_*` 的
`LocalCache/Local/MatLens-Signing/release.key`；這是本專案實際遇過的重新導向情形。
若仍缺失或不匹配，詢問既有私鑰位置；不執行 `--init-key`。

## 2. 驗證與打包

```powershell
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest
npm --prefix frontend test
npm --prefix frontend run build
PowerShell -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Installer
```

沒有 `node_modules` 時，先用 `npm --prefix frontend ci`，再執行前端測試。
`build.ps1` 本身會重建前端，並產生：

```text
dist/
├─ MatLens/MatLens.exe
├─ MatLens/MatLensUpdater.exe
├─ MatLens/_internal/
├─ MatLens-<版本>-win-x64.zip
└─ MatLens-<版本>-update-win-x64.zip
```

完整安裝 ZIP 另外包含 `install.ps1` 與 `Install-MatLens.cmd`。
0.5.5 起另外產生 `dist/MatLens-Setup-<版本>-x64.exe`，作為主要安裝方式。
Inno Setup 6.7.3 編譯器可由 `-CompilerPath` 或 `MATLENS_ISCC_PATH` 指定。
如需準備工具，可使用官方簽章已驗證的 Inno Setup `/PORTABLE=1` 模式，
只放在忽略的 `build/tools/`，不修改系統安裝與檔案關聯。

## 3. 原始碼與 EXE 自測

```powershell
uv run --locked python -m desktop.main --self-test --report "$reportRoot\source.json"

$exePath = Join-Path $repoRoot 'dist\MatLens\MatLens.exe'
$exeReport = Join-Path $reportRoot 'exe.json'
$exeProcess = Start-Process -FilePath $exePath -ArgumentList @('--self-test', '--report', ('"' + $exeReport + '"')) -WorkingDirectory (Split-Path -Parent $exePath) -WindowStyle Hidden -PassThru -Wait
if ($exeProcess.ExitCode -ne 0) { throw 'EXE 自測失敗，請查看報告。' }
$result = Get-Content -LiteralPath $exeReport -Raw | ConvertFrom-Json
if (-not $result.ok -or $result.version -ne $version) { throw 'EXE 自測報告不符。' }
```

自測使用新暫存資料庫與合成照片。讀報告中的 `persisted_cases`、`persisted_photos`，
核對 `desktop/main.py` 現行自測預期，並依此次功能查看測試資料或增加相應回歸驗證。
失敗後保留 `exe.json` 與其 `data_dir/logs/desktop.log`；重跑使用不同報告檔名。
WebView2 關閉時的已處置物件回呼訊息不能單獨代替判定，仍須核對 exit code 與完整報告。

## 4. 簽章與附件稽核

`desktop.release` 使用排他建立輸出檔；每次簽章用新路徑，避免舊的 `dist/stable.json` 造成失敗。

```powershell
$signedManifest = Join-Path $reportRoot ('stable-' + [Guid]::NewGuid().ToString('N') + '.json')
uv run --locked python -m desktop.release --key $signingKeyPath --package "dist\MatLens-$version-update-win-x64.zip" --url "https://github.com/kobojp/MatLens/releases/download/$tag/MatLens-$version-update-win-x64.zip" --notes "docs\release-$tag.md" --output $signedManifest
```

確認簽章指令成功。若 `dist/stable.json` 已存在，先複製到 `$reportRoot` 的唯一備份檔名，
再將這次產物複製為該別名，然後執行檢查：

```powershell
Copy-Item -LiteralPath $signedManifest -Destination dist\stable.json -Force
uv run --locked python $checks local
```

檢查腳本輸出 JSON，證據在新的 `build/release-<版本>-local-*`。
它會比對兩個 ZIP 的程式內容，實際呼叫安全 ZIP 解壓縮驗證；
0.5.5 起只能把 Setup EXE、完整 ZIP、更新 ZIP 與 `stable.json` 上傳為正式附件。

## 5. 隔離更新與回復

優先使用上一個公開版 ZIP 裡的原版 `MatLensUpdater.exe`：

1. 在 `$reportRoot` 建立新 baseline 目錄。
2. 用 `desktop.update_core.download` 從上一個版本的 tag URL 下載 `stable.json`，
   以目前內建公鑰呼叫 `verify_manifest`，核對舊版、平台與資料相容性。
3. 依該 manifest 下載舊更新 ZIP，用 `verify_package` 核對 SHA-256／大小，
   再用 `extract_package` 解到新的子目錄。不要拿未驗證的同名本機 ZIP 當基準。
4. 記錄基準版本、舊 manifest 與 helper 的 SHA-256，將原版 helper 路徑放入 `$oldUpdater`。

```powershell
uv run --locked python -m tests.run_update_smoke --package "dist\MatLens-$version-update-win-x64.zip" --manifest dist\stable.json --report "$reportRoot\upgrade.json" --helper $oldUpdater
uv run --locked python -m tests.run_update_smoke --package "dist\MatLens-$version-update-win-x64.zip" --manifest dist\stable.json --layout installed --report "$reportRoot\upgrade-installed.json"
uv run --locked python -m tests.run_installer_smoke --compiler $env:MATLENS_ISCC_PATH --report "$reportRoot\installer.json"
```

核對 `ok`、版本、`sqlite_preserved`、`photos_preserved`、`backup_verified`、`startup_verified`。
`tests/test_updates.py` 的真實檔案系統回復及 SQLite WAL backup 測試也須通過。

測試邊界要如實記錄：`run_update_smoke` 的舊主程式是測試標記；
不傳 helper 時只模擬 updater 版本，傳上一版原版 helper 時才測到真正的舊更新器。
報告的 `old_worker_version_simulated` 為是否省略 helper；同時核對 `frozen_worker` 與基準來源。
若為 `tests/updater_baseline.py` 編譯的測試 helper，須傳入 `--helper-version-simulated`，
不將該測試當成上一公開版原版更新器的驗證。
此測試不等於驗證了上一版完整主程式中的「按更新」UI，也不會操作使用者的正式安裝。

## 6. 來源提交與 GitHub 草稿

只提交已審查的相關原始碼、版本欄位與發行說明。不得加入 `dist/`、`build/` 或簽章私鑰。
將預備發行 commit 推送到專案預定分支，取得完整 SHA：

```powershell
$releaseCommit = (git rev-parse HEAD).Trim()
gh release create $tag "dist\MatLens-Setup-$version-x64.exe" "dist\MatLens-$version-win-x64.zip" "dist\MatLens-$version-update-win-x64.zip" dist\stable.json --repo kobojp/MatLens --draft --target $releaseCommit --title "MatLens $version" --notes-file "docs\release-$tag.md"
uv run --locked python $checks draft --commit $releaseCommit
```

建立前先查同 tag。若在接續既有草稿，只上傳缺少且已驗證的附件，不使用 `--clobber` 掩蓋差異。
草稿下載 URL 可能顯示 `untagged-*`，以 `tagName` 與 `targetCommitish` 判斷預定版本，
正式 manifest 仍使用最終的 `releases/download/v<版本>/...` URL。

## 7. 公開與公開下載驗證

確認使用者授權包含發布，且前述關卡全部通過：

```powershell
gh release edit $tag --repo kobojp/MatLens --draft=false --latest
gh api "repos/kobojp/MatLens/commits/$tag" --jq .sha
uv run --locked python $checks public
```

tag 解析後的 SHA 必須等於 `$releaseCommit`。`public` 從正常 `latest/download` URL 下載
manifest、安裝精靈、完整安裝 ZIP 與更新 ZIP，比對本機檔案及簽章，最後以 `UpdateService` 再做正常更新檢查。
它不使用 GitHub 登入資訊下載附件，也不修改 Release。

剛公開時 `latest` 下載可能短暫落後 GitHub API。腳本只對有效的較舊 manifest 最多確認六次，
每次間隔 10 秒。超出後回報「已公開，公開下載驗證尚未完成」，保留證據並稍後接續檢查。
任何簽章、SHA-256、平台或資料相容性失敗立即停止，不重發同一版掩蓋問題。

最後提供 Release 與 Setup EXE 連結，說明執行後按「下一步」，資料位於 `%LOCALAPPDATA%/MatLens`。
保留本機測試報告，不把實際機器路徑或測試資料夾寫入公開發行說明。
