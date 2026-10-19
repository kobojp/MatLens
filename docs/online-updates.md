# 線上更新維護與復原

重複執行發佈工作時，使用專案內的
[matlens-release skill](../.agents/skills/matlens-release/SKILL.md)。
技能包含實際操作順序與可執行的私鑰、ZIP、草稿及公開下載檢查。

## 程式結構

- `desktop/update_core.py`：HTTPS、已簽章 manifest、版本與 ZIP 驗證。
- `desktop/updates.py`：非同步檢查與下載狀態。
- `desktop/bridge.py`：桌面操作與未儲存保護。
- `desktop/updater.py`：獨立更新器、資料庫備份、預先測試、替換及回復。
- `desktop/update-source.json`：公開更新資訊網址及內建驗證公鑰；不可放入 Token。
- `desktop/release.py`：維護者簽章工具。
- `frontend/src/UpdatePanel.tsx`：更新操作介面。

## 發佈

原始碼與程式下載都位於公開 `kobojp/MatLens`。舊 `kobojp/MatLens-Releases`
已於 2026-10-05 刪除；仍停在 v0.3.0 的安裝無法自動更新，需手動安裝一次新版完整 ZIP。
0.5.5 起只上傳下列四個檔案與發行說明，不能上傳開發資料夾：

1. 完整安裝 ZIP（含安裝腳本）。
2. 更新專用 ZIP（只有 `MatLens/`）。
3. `stable.json`：包含 Base64 payload 及 Ed25519 signature。payload 內有版本、頻道、
   URL、SHA-256、大小、平台、資料相容版本及更新說明。
4. `MatLens-Setup-<版本>-x64.exe`：主要安裝精靈，繁體中文、目前使用者安裝，
   自動使用 `%LOCALAPPDATA%\MatLens`，並可選擇桌面捷徑。

版本來源是 `desktop/version.py`，也須同步 pyproject.toml／uv.lock 與 Inno Setup 版本。
正式版本格式例如 `0.4.0`；測試版本可用 `0.5.0-rc.1`。
正式頻道拒絕 rc 版本。測試頻道網址為固定 `preview` release 的 `preview.json`，
尚未發佈該資產時顯示可重試的更新錯誤，不影響正式版。

私鑰在 `%LOCALAPPDATA%\MatLens-Signing\release.key`，存放於專案之外，
資料夾 ACL 僅授權目前帳號與 SYSTEM；請另外離線備份，絕不能上傳。
公鑰固定在程式內；不要每次發行重新產生金鑰。
若預設位置不存在，也可能位於 Codex 應用程式重新導向的 LocalCache；
先用 skill 的 `release_checks.py key` 驗證定位，或以 `MATLENS_SIGNING_KEY_PATH` 指定現有路徑。
不要把實際機器路徑或私鑰內容寫回本文件。

```powershell
PowerShell -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Installer
uv run --locked python -m desktop.release `
  --key "$env:LOCALAPPDATA\MatLens-Signing\release.key" `
  --package .\dist\MatLens-0.4.0-update-win-x64.zip `
  --url "https://github.com/kobojp/MatLens/releases/download/v0.4.0/MatLens-0.4.0-update-win-x64.zip" `
  --notes .\docs\release-v0.4.0.md `
  --output .\dist\stable.json
```

先建立 draft release，上傳並核對附件，最後一次公開發佈。正式 release 才會被
GitHub `releases/latest` 選到；不要將正式更新 manifest 只放在 prerelease。
這是下載更新，不會將照片或案件上傳；更新請求會讓 GitHub 得知一般下載連線資訊。

## 安全邊界與限制

更新器接受預設 `%LOCALAPPDATA%/MatLens/app` 與舊 `Programs/MatLens` 程式目錄。
新安裝精靈將程式與資料集中於 `MatLens` 根目錄，但只替換 `app` 子目錄；
資料庫 `MatLens/matlens.db` 不搬移，既有案件的照片根目錄保持不變。
解除安裝只移除安裝的程式及捷徑，資料庫、照片、備份與紀錄保留。
非預期的頂層檔案、
目錄重新導向、舊版本、簽章錯誤、資料相容版本不同時拒絕更新。
每次更新使用獨立 staging，先完全驗證 ZIP，再解壓縮，不能寫出暫存目錄。
資料庫與使用者照片不屬於程式替換範圍。

`DATA_COMPATIBILITY = 1` 代表自動更新版本必須維持既有資料結構及意義相容；
不相容 schema 更新需先設計遷移／復原，不可僅增加 manifest 數字後繼續自動更新。
啟動失敗僅回復程式，不自動覆寫使用者資料庫；備份供人工確認後復原。

更新器會保留程式目錄同層的 `app.previous-*`／`app.next-*`；舊路徑使用 `MatLens.previous-*`／`MatLens.next-*`。
暫存下載、測試資料與舊程式目前不自動刪除，會累積磁碟空間；清理前需確認精確目錄。

如果斷電或強制結束更新器，可能留下 `MatLens/updates/install.lock`，
原程式會拒絕啟動以免使用半完成安裝。請先確認更新器與 MatLens 都未執行，
讀取對應工作目錄的 `recovery.json`、`last-result.json`：

- 原程式仍完整：移除確認已失效的 lock 後再啟動。
- 程式已被移至 `previous`：保留所有目錄，將精確紀錄的 previous 恢復為原安裝名稱，
  或使用完整安裝包重新安裝；不可刪除案件資料庫或照片。
- 回復不確定時請保留現場與備份，交由維護者處理，不盲目刪除資料。

目前不支援私有更新登入、不相容 schema 自動降版、差分更新、無人值守強制更新。
更新包已有 Ed25519 發行驗證，但 EXE 尚無 Windows Authenticode 簽章。

## 更新診斷與安裝驗證

「關於與更新」顯示目前執行版本、程式完整路徑、資料庫路徑及安裝方式。
清冊上的「開啟資料庫位置」永遠選取目前後端正在使用的資料庫，不假定網頁與桌面相同。
更新交接先寫入 `updates/pending.json`，獨立更新器以相同工作識別碼寫入 `last-result.json`。
若重開後執行版本仍低於成功紀錄的目標版本，畫面會提示尚未生效；舊成功紀錄不能掩蓋新工作尚待確認。

```powershell
uv run --locked python -m tests.run_installer_smoke --compiler $env:MATLENS_ISCC_PATH --report build/installer-smoke.json
```

測試會編譯獨立 QA 身分與暫存捷徑路徑，驗證執行中拒絕安裝、更新鎖定、安裝、重裝、
捷徑目標、EXE 實際儲存流程與解除安裝保留資料；不更動正式安裝與使用者捷徑。
