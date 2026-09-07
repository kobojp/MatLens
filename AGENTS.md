# AGENTS.md

## 專案目標

MatLens 是供 Windows 10／11 使用的消防材料更換照片整理與案件管理系統。
現場照片匯入後，使用者可記錄棟別、樓層、定址碼、材料、問題、位置、日期與備註，
再依一致的資料夾及檔名規則儲存在本機。

本檔案適用於整個 repository。

## Repository 與發佈現況

- 原始碼倉庫：公開 `https://github.com/kobojp/MatLens`。
- Windows 安裝包與線上更新檔：同一倉庫的 GitHub Releases。
- 目前正式版本：`v0.3.1`；版本唯一來源為 `desktop/version.py`。
- `kobojp/MatLens-Releases` 僅保留 v0.3.0 的過渡更新入口，不再放置新版本安裝包。
- 不得刪除或破壞舊倉庫的 `stable.json` 過渡入口，否則已安裝 v0.3.0 無法自動移轉。
- 公開 repository 不代表可提交現場照片、案件資料、機器路徑、憑證或簽章私鑰。

## 技術棧

- Backend：Python 3.12、FastAPI、SQLite、Pillow
- Frontend：React、Vite、TypeScript
- Python 環境與套件管理：`uv`
- Backend tests：pytest
- Frontend tests：Vitest、Testing Library
- Python lint：Ruff
- 執行平台：Windows 10／11、PowerShell
- 桌面視窗：pywebview（Edge WebView2）；打包：PyInstaller x64

## 專案結構

```text
MatLens/
├─ backend/app/       FastAPI、SQLite、照片儲存邏輯
├─ frontend/src/      React 使用者介面
├─ frontend/dist/     正式前端建置結果，由 FastAPI 提供
├─ tests/             後端 API 與儲存測試
├─ desktop/           桌面入口、單一實例、本機服務與資料接續
│  ├─ update_core.py  更新資訊簽章、下載與 ZIP 安全驗證
│  ├─ updates.py      更新狀態與背景下載
│  ├─ updater.py      獨立更新器、備份、替換與失敗回復
│  └─ version.py      正式版本唯一來源
├─ packaging/         EXE／ZIP 建置與捷徑安裝腳本
├─ docs/              桌面驗證與交付說明
├─ data/              執行時 SQLite 與預設照片目錄
├─ pyproject.toml     Python 專案與 Ruff／pytest 設定
├─ uv.lock            Python 鎖定依賴
└─ run.ps1            Windows 正式啟動腳本
```

## 不可違反的資料安全規則

- 不得修改、重新命名、搬移或刪除使用者的來源照片。
- 照片匯入一律採複製方式。
- 不得刪除或重建 `data/matlens.db`，除非使用者明確要求並確認備份。
- 不得清空使用者指定的照片儲存目錄。
- 既有案件必須繼續使用建立案件時記錄的 `storage_root`；變更預設目錄不可破壞舊案件。
- SQLite schema 變更必須採向後相容、可重複執行的增量方式。
- 刪除自訂快速選項不得刪除或改寫既有案件資料。
- 內建材料與問題選項受到保護，不可由一般刪除功能移除。
- 任何具破壞性的資料操作都必須先確認精確目標與使用者授權。
- 桌面資料庫位於 `%LOCALAPPDATA%/MatLens/`，必須與安裝檔案分離。
- 接續舊資料前使用 SQLite backup 建立一致性快照，不覆蓋已有桌面資料庫。
- 桌面版與舊網頁版使用獨立資料庫，不能假設兩者自動同步。
- 桌面內部服務僅綁定 loopback 隨機埠，保留 session cookie、Host 與 Origin 檢查。
- 線上更新只能替換預設安裝位置的程式檔，不得覆寫案件資料庫或照片；更新前建立 SQLite backup。
- 更新資訊必須驗證內建 Ed25519 公鑰簽章，更新包必須驗證 SHA-256 與安全 ZIP 路徑。
- 簽章私鑰與 Token 不得寫入專案或公開發佈；公開 MatLens Releases 不得包含使用者資料。
- 未儲存／正在儲存時不得安裝更新；不相容的資料庫版本不得自動更新或直接降版。

## Python 與 uv 規則

- 必須使用專案的 `uv` 虛擬環境，不可改用全域 Python 或手動建立其他 venv。
- Python 版本以 `.python-version` 與 `pyproject.toml` 為準。
- 安裝或同步依賴使用 `uv sync --locked`。
- 執行 Python 指令使用 `uv run --locked ...`；開發時確需更新 lockfile 才可省略 `--locked`。
- 新增 Python 依賴後必須更新並提交 `pyproject.toml` 與 `uv.lock`。

## 常用指令

正式啟動：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\run.ps1
```

桌面版開發啟動：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\run-desktop.ps1
```

後端開發：

```powershell
uv sync --locked
uv run --locked uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

前端開發：

```powershell
cd frontend
npm ci
npm run dev
```

完整驗證：

```powershell
uv run --locked ruff check .
uv run --locked pytest
npm --prefix frontend test
npm --prefix frontend run build
```

建立 Windows 安裝包與更新包：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\packaging\build.ps1
```

## 開發流程

1. 先理解需求與目前行為，檢查相關程式和既有資料結構。
2. 修正錯誤時，先建立能重現問題的測試。
3. 只實作需求所需的最小完整功能，不重構無關程式。
4. Backend API、Frontend UI 與持久化資料格式要一起考量。
5. 修改後執行與風險相稱的測試；交付前執行完整驗證。
6. 前端變更必須重新產生 `frontend/dist/`，因正式服務直接提供此目錄。
7. 若服務原本正在執行，完成建置後重新啟動並確認 `http://127.0.0.1:8000/` 可用。

## 版本與線上更新規則

- 修改版本時，先改 `desktop/version.py`，並同步 `pyproject.toml`、`uv.lock` 與
  `packaging/MatLens.iss`；檔名與 Release tag 必須一致。
- 正式版使用 `x.y.z`；測試版可使用 `x.y.z-rc.n`，不得把測試版放進正式頻道。
- `desktop/update-source.json` 的正式更新網址必須指向
  `kobojp/MatLens/releases/latest/download/stable.json`。
- 每個正式 Release 必須包含完整安裝 ZIP、更新專用 ZIP 與 `stable.json`。
- 更新 manifest 必須使用既有 Ed25519 私鑰簽署；私鑰位於 repository 之外，
  不得重新產生後直接取代內建公鑰，也不得加入 Git、Release 或紀錄輸出。
- 發佈前先建立 draft Release，核對 tag、目標 commit、資產名稱、大小與 SHA-256，
  完成打包 EXE 自測及隔離升級測試後才公開。
- 發佈後必須從公開 `releases/latest` URL 實際下載 manifest 與更新包，驗證簽章、
  SHA-256、版本與平台；不能只測試本機檔案。
- 線上更新不得自動強制安裝。沒有網路、簽章錯誤或下載損壞時，原版本仍須可使用。
- `DATA_COMPATIBILITY` 不可隨意變更；資料結構不相容時，必須先設計可驗證的遷移與復原。
- Release ZIP、manifest、PyInstaller build 與自測報告保持在忽略的 `dist/`、`build/`，
  不提交二進位產物到 Git。
- 詳細發佈與復原流程以 `docs/online-updates.md` 為準。

## Backend 規則

- 保持 FastAPI route 簡單，資料驗證放在 Pydantic schema。
- 所有 SQL 使用參數化查詢，不拼接使用者輸入。
- SQLite connection 必須啟用既有的 foreign keys 與 busy timeout 設定。
- 只有實際查詢需要時才新增 index，避免無必要的 schema 複雜度。
- API 錯誤應回傳使用者可理解的繁體中文訊息與合適 HTTP status。
- 檔案路徑必須正規化、驗證，且限制在案件記錄的儲存根目錄內。
- 新增或修改 API 行為時，在 `tests/` 增加成功、驗證失敗及資料持久化測試。

## Frontend 規則

- 介面文字使用台灣繁體中文，操作應適合現場快速整理照片。
- 保持鍵盤、滑鼠與拖放操作可用，互動元件提供可辨識的 accessible name。
- 照片預覽建立的 object URL 必須在移除照片或卸載時釋放。
- 自訂材料／問題可以新增和刪除；問題維持可複選。
- 自訂選項刪除前必須確認，並提示既有案件不受影響。
- 不得只更新畫面狀態而未同步後端；SQLite 是自訂選項與案件的資料來源。
- UI 行為修正需使用 Testing Library 加入使用者操作層級的回歸測試。

## 程式碼原則

- 優先採用直接、容易維護的做法，避免過度抽象與提前最佳化。
- 保留現有架構、命名與格式，不做無關的整檔格式化。
- 不隱藏例外或靜默忽略資料錯誤；提供明確錯誤處理。
- 不提交秘密、機器專屬憑證、暫存檔、測試照片、資料庫或 `node_modules`。
- 不以測試替身取代關鍵持久化驗證；重要資料流程必須測試真實 SQLite 行為。

## 完成條件

功能只有在下列條件全部成立時才算完成：

- 使用者要求的流程可從介面完整操作。
- 重新整理或重新啟動後，應保存的資料仍存在。
- 既有案件與照片仍可讀取。
- Ruff、pytest、Vitest 與正式前端 build 通過。
- Windows 啟動腳本仍可使用 `uv` 成功啟動服務。
- 影響桌面版或更新器時，打包 EXE 自測與隔離更新／回復測試必須通過。
- 發佈新版本時，原倉庫 Release 可公開下載，manifest 簽章與套件 SHA-256 驗證通過。
- 回覆使用者時簡要說明完成內容、驗證結果及必要的操作方式。
