# 0.5.6 本機實作與驗證

日期：2026-11-08。正式公開版本仍為 0.5.5；0.5.6 本輪交付原始碼至 GitHub；安裝包與線上更新尚未發布。

## 實作位置

- `backend/app/main.py`、`schemas.py`：儲存選擇 API；沿用 SQLite settings，原子保存根路徑、子資料夾及日期前綴，不更動既有案件。
- `frontend/src/useStorageSelection.ts`、`StorageDestination.tsx`、`App.tsx`：唯讀還原、依序保存、儲存狀態、青綠色目的地標示、移除新增案件月份切換。
- `desktop/clipboard.py`、`frontend/src/useClipboardImages.ts`、`PasteConfirmation.tsx`：Windows／網頁讀取、預覽確認、取消清理及追加。
- `desktop/updater.py`、`updates.py`、`frontend/src/UpdatePanel.tsx`：更新階段、工作識別碼、失敗原因及本機診斷。
- `tests/`、`frontend/src/*.test.tsx`、`desktop/smoke.js`：資料保存、相容性、操作、桌面與更新驗證。

新版配置及逐項驗收另見 [UI 工作區驗證](ui-workspace-validation.md)。

## 驗證範圍

- Ruff、162 個 pytest、56 個 Vitest、TypeScript 與 Vite 正式建置通過。
- 原始碼與打包 EXE：使用合成照片及獨立 SQLite，驗證貼上先確認、取消不產生草稿、追加、預覽、儲存、案件回看；重新整理後底座與日期前綴仍還原。
- 安裝精靈：QA 安裝身份與獨立目錄，驗證阻止執行中安裝、更新鎖、安裝／重裝、桌面與開始選單捷徑、解除安裝保留資料。
- 公開 0.5.5 manifest 與更新 ZIP 重新下載後驗證既有 Ed25519 公鑰、SHA-256 及安全解壓；使用其中原版更新器測試新 `MatLens/app` 與舊 `Programs/MatLens` 位置。
- 完整舊版介面：由提交 `69c542b246c55317383825bbedaebb17453a2c0d` 的原始碼與公開 0.5.5 前端建立 QA 客戶端；保留舊版 bridge、版本、更新服務及原版更新器。只注入操作與本機下載傳輸，簽章、雜湊、預先測試、替換及新版啟動均實際執行。
- 依使用者補充，另以 0.5.4 封存提交 `e3af2ed`、公開前端與原版更新器測試升到公開 0.5.5；本機傳輸與原版 HTTPS 下載兩次皆成功，重啟版本、位置、案件、照片與備份均核對。只有 QA 入口／操作注入，版本與更新邏輯未模擬。仍未重現出問題電腦的故障。
- 自動回歸涵蓋預先測試退出／逾時／報告失敗、啟動失敗回復及資料保留；這些失敗測試使用受控注入，不等同另一台電腦的真實故障。
- Windows 視窗人工操作確認青綠色標示、完整路徑、切換磁力門扣與捲動後固定可見。
- 更新 log 回歸：斷線、損壞更新包、更新器啟動失敗、非法工作、預先測試失敗均留下階段與例外；重啟不覆寫舊 log，URL query 隱藏，無法寫入 log 時介面可見警告。
- 打包更新器刻意使用「版本高於 EXE 的 QA 簽章資訊」，實際執行 EXE 預先測試後拒絕替換，驗證 `worker.log`、SQLite 備份、原程式及照片保留。這是受控的紀錄驗證，不是重現另一台電腦的故障；QA manifest 只留在本機忽略的 `build/`，不得公開。
- 原版 0.5.4 客戶端交接至新版的測試，另核對 `startup.log` 的 `startup.ready` 與重啟版本；完整 client／worker 新紀錄需先手動安裝新版，不能回補舊更新器過去的失敗。

原始 JSON 報告及合成資料留在本機忽略的 `build/` 與自建暫存目錄，不提交機器路徑、資料庫或照片。

## 可重跑指令

```powershell
uv run --locked ruff check .
uv run --locked pytest
npm --prefix frontend test
npm --prefix frontend run build
PowerShell -ExecutionPolicy Bypass -File .\run-desktop.ps1 --self-test --report build\source-0.5.6.json
PowerShell -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Installer -CompilerPath <Inno-Setup-ISCC.exe>
uv run --locked python -m tests.run_installer_smoke --compiler <Inno-Setup-ISCC.exe> --report build\installer-0.5.6.json
```

完整介面測試入口為 `tests/qa_update_client.py`，必須在舊版封存 checkout 下打包，不能用目前 0.5.6 原始碼假裝舊版。
以舊版原始碼目錄為工作目錄、專案 uv 環境執行 PyInstaller，加入已驗證公開 ZIP 的 `frontend/dist`、該版本 `desktop/smoke.js` 與 `update-source.json`，並採用與 `packaging/build.ps1` 相同的 webview／uvicorn 收集選項。
QA 入口及本機 fixture 不得放入正式安裝包。
`--baseline-version` 可指定 0.5.4；其原版更新器僅支援舊安裝路徑，使用 `--layout legacy`。
`--live-download` 保留舊版原始 HTTPS 實作，先核對公開 stable 與預期 manifest 相同才開始；不修改更新來源，也不替換遠端附件。

```powershell
uv run --locked python -m tests.run_client_update_smoke --qa-client <QA-MatLens-目錄> --original-worker <已驗證公開更新器> --manifest <新版簽章-manifest> --package <新版更新-ZIP> --layout installed --report build\client-installed.json
uv run --locked python -m tests.run_client_update_smoke --qa-client <QA-MatLens-目錄> --original-worker <已驗證公開更新器> --manifest <新版簽章-manifest> --package <新版更新-ZIP> --layout legacy --report build\client-legacy.json
```

## 本輪新版 UI 最終交付驗證

來源、打包 EXE 與安裝後 EXE 通過新版圖塊、放大看圖、長檔名、三種配置、重設、收合及持久化測試。
0.5.4 舊位置與 0.5.5 新位置的完整舊介面交接原版更新器至本機 0.5.6 均通過，重啟與 startup.log 已核對；
本輪使用本機傳輸，沒有公開 0.5.6。打包更新器的受控預先測試失敗保留 log、程式、照片與 SQLite 備份。
主專案 run-desktop.ps1 重建前端及隔離桌面自測通過；Setup／完整 ZIP／更新 ZIP 與原始碼已同步並核對。
最終報告分別為本機 build 中的 source／exe／installer-workspace-complete、client-v0.5.4／v0.5.5-workspace-complete、
workspace-update-failure-complete，以及主專案 main-workspace-complete；原始報告不提交。

## 尚待驗收

1. 出問題的另一台電腦：取得更新前版本、目標版本、同一工作紀錄與啟動位置，使用真實網路及原捷徑核對更新結果。UPD-001 仍開啟。
2. 從 LINE 與 Chrome／Edge 實際「複製圖片」到 Windows 剪貼簿再貼上；目前已驗證合成事件、橋接及圖片讀取，不聲稱跨程式已驗收。
窄視窗與長路徑已補入三種配置的實際 WebView2 自測；新版外觀已提供桌面截圖，仍可依使用者回饋微調。

開發啟動使用 `run-desktop.ps1`，會同步 uv、重建前端後開啟本輪程式。安裝測試使用本機 `dist/MatLens-Setup-0.5.6-x64.exe` 按「下一步」。
