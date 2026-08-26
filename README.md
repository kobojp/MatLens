# MatLens

消防材料更換照片整理與案件管理系統。第一版以 Windows 10/11 本機離線使用為目標，照片與案件資料不會上傳到雲端。

## 第一版功能

- 一次匯入或拖放多張 JPG、PNG、WebP 照片。
- 大圖預覽，以及「前／中／完成／樓層／位置／設備標籤」快速分類。
- 記錄維修日期、棟別、樓層、定址碼、材料、問題、位置及備註。
- 材料與問題提供快速選項；問題可複選，兩者都能新增及刪除自訂選項（內建選項受保護）。
- 依規則自動建立年份、月份、材料與案件資料夾。
- 產生 `01_前.jpg`、`02_中.jpg`、`03_完成.jpg` 等一致檔名。
- SQLite 案件清單、搜尋、篩選及照片回看。
- 缺少前／中／完成照片提醒。
- SHA-256 完全相同照片檢查，避免照片重複放入不同案件。
- 可透過 Windows 資料夾選擇器指定照片儲存目錄；既有案件仍保留原路徑。
- 照片加入後仍可繼續拖放更多照片。
- 所有匯入均採複製方式，不修改來源照片。

## Windows 執行

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
├─ tests/             API 與照片儲存測試
├─ data/              執行後建立的本機資料
├─ pyproject.toml     uv 專案與 Python 依賴
├─ uv.lock            鎖定依賴版本
└─ run.ps1            Windows 啟動腳本
```
