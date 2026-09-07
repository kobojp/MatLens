# MatLens

消防材料更換照片整理與案件管理系統。第一版以 Windows 10/11 本機離線使用為目標，照片與案件資料不會上傳到雲端。

## 第一版功能

- 一次匯入或拖放多張 JPG、PNG、WebP 照片。
- 大圖預覽，以及「前／中／完成／樓層／位置／設備標籤」快速分類。
- 預覽預設完整顯示；滾輪或 ＋／− 縮放、左鍵拖曳平移、雙擊或「顯示完整圖片」還原。
  縮放範圍 25%～800%（相對完整顯示比例）；切換照片自動還原。
- 記錄維修日期、棟別、樓層、定址碼、材料、問題、位置及備註。
- 材料與問題提供快速選項；問題可複選，兩者都能新增及刪除自訂選項（內建選項受保護）。
- 掃描使用者指定目錄內的月份資料夾（例如 `8月`、`9月`）及其子目錄。
- 依維修日期預選當月，再由使用者選擇 `底座`、`模組`、`探頭` 等實際儲存位置。
- 當月份不存在時會提示，可一次建立月份與多個常用／自訂子目錄；系統只在選定位置建立案件資料夾。
- 產生 `01_前.jpg`、`02_中.jpg`、`03_完成.jpg` 等一致檔名。
- SQLite 案件清單、搜尋、篩選及照片回看。
- 缺少前／中／完成照片提醒。
- SHA-256 完全相同照片檢查，避免照片重複放入不同案件。
- 可透過 Windows 資料夾選擇器指定照片儲存目錄；既有案件仍保留原路徑。
- 照片加入後仍可繼續拖放更多照片。
- 所有匯入均採複製方式，不修改來源照片。

## Windows 執行

### 桌面版（Windows 10／11 x64）

解壓縮 `MatLens-0.3.1-win-x64.zip` 後：

- 直接雙擊 `MatLens/MatLens.exe` 啟動免安裝版，必須保留整個資料夾。
- 或雙擊 `Install-MatLens.cmd` 安裝至使用者程式目錄並建立桌面／開始選單捷徑。
- 使用者不必安裝 Python、uv 或 Node.js；需要 Microsoft Edge WebView2 Runtime。
- 已有 WebView2 的電腦可離線使用。缺少時可從 [Microsoft 官方網站](https://developer.microsoft.com/microsoft-edge/webview2/) 安裝 Evergreen Runtime。

桌面版資料庫存於 `%LOCALAPPDATA%/MatLens/matlens.db`，紀錄位於同目錄的 `logs/`。
照片目錄可自訂；更新安裝不會清除案件或照片。
第一次從原始碼啟動時，會備份並複製專案 `data/matlens.db`，保留原照片路徑。
之後桌面版與舊網頁版的案件資料各自獨立，不會雙向同步；完成轉換後請統一使用桌面版。
在其他位置首次啟動時，可指定舊資料庫（目的地已有資料時會拒絕覆蓋）：

```powershell
.\MatLens.exe --import-from "D:\舊版MatLens\data\matlens.db"
```

開發啟動（仍使用 uv 虛擬環境）：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\run-desktop.ps1
```

產生 EXE 與 ZIP：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\packaging\build.ps1
```

`packaging/MatLens.iss` 另提供 Inno Setup 6 安裝設定，已安裝編譯器後可加 `-Installer`。
目前交付物是免安裝 ZIP 與捷徑安裝腳本；Inno Setup 安裝包尚未驗證。
測試範圍與限制請見 [桌面驗證紀錄](docs/desktop-validation.md)。

### 線上更新（0.3.0 起）

從 [MatLens Releases](https://github.com/kobojp/MatLens/releases) 取得完整安裝 ZIP，
執行 `Install-MatLens.cmd` 一次後，往後可使用「關於與更新」。原始碼與下載都在同一個公開倉庫。
啟動時只檢查正式版，不自動下載或強制安裝；下載驗證完成後，先儲存案件，再選擇安裝重啟。
開發版／可攜版只能檢查更新。沒有網路仍可整理及儲存案件。
更新採簽章驗證、SQLite 備份與保留前一版程式，詳見 [更新維護與復原](docs/online-updates.md)。

### 原有網頁版

需要先安裝：

- [uv](https://docs.astral.sh/uv/)
- Node.js（目前僅在第一次建置前端時需要）

在專案資料夾開啟 PowerShell：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\run.ps1
```

看到啟動訊息後，以瀏覽器開啟：

```text
http://127.0.0.1:8000
```

按 `Ctrl+C` 可停止程式。

案件資料預設儲存在：

```text
data/
├─ matlens.db
└─ photos/
```

原始的 `材料更換照片/` 資料夾不會被系統修改。

## 開發模式

後端：

```powershell
uv sync
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

前端使用另一個 PowerShell：

```powershell
cd frontend
npm install
npm run dev
```

開發介面位於 `http://127.0.0.1:5173`，Vite 會將 `/api` 轉送至 FastAPI。

## 驗證

```powershell
uv run ruff check .
uv run pytest
npm --prefix frontend test
npm --prefix frontend run build
```

## 專案結構

```text
MatLens/
├─ backend/app/       FastAPI、SQLite 與照片儲存
├─ frontend/src/      React 操作介面
├─ desktop/           Windows 桌面入口、視窗與資料接續
├─ packaging/         EXE／ZIP 建置與安裝腳本
├─ docs/              驗證紀錄
├─ tests/             API 與照片儲存測試
├─ data/              執行後建立的本機資料
├─ pyproject.toml     uv 專案與 Python 依賴
├─ uv.lock            鎖定依賴版本
└─ run.ps1            Windows 啟動腳本
```
