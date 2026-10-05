# MatLens

消防材料更換照片整理與案件管理系統，供 Windows 10／11 本機離線使用。
現場照片匯入後，記錄棟別、樓層、定址碼、材料與問題，再依一致的資料夾與檔名規則存到本機。
照片與案件資料都不會上傳到雲端。

## 下載與安裝

到 [Releases](https://github.com/kobojp/MatLens/releases) 下載最新的 `MatLens-<版本>-win-x64.zip`，解壓縮後：

- 雙擊 `Install-MatLens.cmd`：安裝到使用者程式目錄，並建立桌面與開始選單捷徑（建議）。
- 或直接執行 `MatLens/MatLens.exe`：免安裝，必須保留整個資料夾。

不需要安裝 Python、uv 或 Node.js，但需要 Microsoft Edge WebView2 Runtime。
多數 Windows 10／11 已內建；缺少時請從
[Microsoft 官方網站](https://developer.microsoft.com/microsoft-edge/webview2/) 安裝 Evergreen Runtime。

資料庫在 `%LOCALAPPDATA%\MatLens\matlens.db`，紀錄在同目錄的 `logs\`，與程式檔案分離。
照片存放位置可自訂，更新安裝不會動到案件或照片。

## 使用流程

1. **加入照片**：拖放或點選匯入 JPG、PNG、WebP，可連續加入更多張（單一案件最多 30 張）。
2. **整理照片**：
   - 縮圖可**拖曳排序**，或用縮圖右下角的 ◀ ▶ 按鈕移動；角色留在原照片上，只改順序。
   - 每張照片用「這張照片是」選單選角色：前、中、後、完成、樓層、位置、設備標籤、其他。
   - 大圖預覽可滾輪或 ＋／− 縮放（25%～800%）、拖曳平移、雙擊還原。
3. **填寫案件**：維修日期、棟別、樓層、定址碼、材料、問題、補充位置與備註。
   - 材料與問題有快速選項，可新增與刪除自訂選項（內建選項受保護）。
   - 問題為**單選**；選「火警」時可再選一個細項，例如 `火警-無回應`。
4. **選擇儲存位置**，按「儲存案件」。

系統會提醒缺少的照片（需要前、中，以及後或完成其中之一），並以 SHA-256 檢查完全相同的照片，
避免同一張照片被放進不同案件。所有匯入都是**複製**，不會修改來源照片。

### 儲存位置的兩種模式

- **月份模式**：掃描照片儲存目錄內的月份資料夾（`8月`、`9月`…），依維修日期預選當月，
  再選 `底座`、`模組`、`探頭` 等子目錄。月份不存在時可一次建立月份與多個子目錄。
- **自由路徑模式**：指定任意目錄，掃描其子目錄後選擇存入位置，可選擇是否在資料夾名稱前加日期。

### 資料夾與檔名規則

案件資料夾，棟別與樓層連寫，其餘以空白分隔：

```text
2026-09-21 二門診1F M3-07 錯誤設備
2026-09-22 二門診3F M3-08 火警-無回應
```

照片檔名預設不加序號；同類型多張會編號。可勾選「檔名加上序號」，設定會被記住：

| 預設 | 勾選「檔名加上序號」 |
|---|---|
| `前-1.jpg`、`前-2.jpg`、`中.jpg`、`後.jpg` | `01_前-1.jpg`、`02_前-2.jpg`、`03_中.jpg`、`04_後.jpg` |

### 預設角色順序

「本次照片」下方的「預設角色順序」可拖曳排序、拖到「不使用」區移除。
拉進照片時依此順序從第一個角色開始分配，照片比角色多時沿用最後一個角色。預設為 `前 → 中 → 後`，
設定存在資料庫，重開後仍有效。

## 案件清單、掃描與同步

案件清單支援搜尋、依棟別與材料篩選、分頁、檢視照片，以及開啟案件資料夾。

「**掃描目前資料夾**」會讓資料庫與磁碟保持一致，並以**檔案內容（SHA-256）**辨識，不依賴檔名：

| 你在磁碟上做的事 | 掃描結果 |
|---|---|
| 搬動案件資料夾 | 重新連結路徑 |
| 改了案件資料夾名稱 | 依照片內容找到新資料夾並重新連結；備註與補充位置保留，棟別、樓層、定址碼、問題、日期、材料依新名稱更新 |
| 改了圖檔名稱 | 更新檔名與路徑；檔名含已知角色（前、中、後…）時角色跟著更新 |
| 新增圖檔 | 加入該案件（內容重複者略過） |
| 用修圖軟體編修照片 | 更新雜湊與尺寸 |
| 手動新增整個案件資料夾 | 匯入為新案件 |
| 刪除檔案或資料夾 | 手動掃描時移除找不到檔案的紀錄 |

掃描只讀取照片，不會改名、搬移或刪除磁碟上的任何檔案。有多個候選資料夾時會略過並回報，不猜測。

## 照片總覽與檔名清單

案件清單上方有兩個按鈕：

- **照片總覽**：依材料與棟別列出案件，標題如 `二門診3F M3-07 錯誤設備`，
  下方由左到右排列每張照片與圖檔名，上方顯示「底座共 N 筆」。縮圖大小可調，點縮圖可放大，並可上一張、下一張。
- **檔名清單**：依案件分組列出，可一鍵複製。可切換「只列資料夾名稱」或「含圖檔名稱」。

資料來源可選「案件資料庫」或「磁碟資料夾」（直接掃描，涵蓋尚未登錄的資料夾）。
「整理前自動掃描新資料夾」預設開啟，只匯入新資料夾與重新連結，**絕不刪除任何紀錄**。

**另存網頁**會輸出單一 HTML 檔到 `%LOCALAPPDATA%\MatLens\exports\`，並在檔案總管中選取：

- **輕量版**：縮圖內嵌，放大時讀取本機原始照片；檔案小，只能在這台電腦看完整大圖。
- **獨立版**：縮圖與放大圖（約 1000 像素）都內嵌，可直接傳給他人；檔案較大。

## 線上更新

啟動時只檢查正式版，**不會自動下載或強制安裝**。到「關於與更新」可下載並驗證，
儲存目前案件後再選擇安裝並重新啟動。沒有網路時仍可正常整理與儲存。

更新資訊以內建公鑰驗證 Ed25519 簽章，更新包再驗證 SHA-256 與 ZIP 路徑；
安裝前會先建立 SQLite 備份並保留前一版程式。開發版與免安裝版只能檢查更新。
詳見 [更新維護與復原](docs/online-updates.md)。

## 資料安全

- 匯入照片一律複製，不修改來源照片。
- 既有案件沿用建立時記錄的儲存目錄，變更預設目錄不影響舊案件。
- 資料庫位於 `%LOCALAPPDATA%\MatLens\`，與程式分離；更新前自動備份。
- 桌面內部服務只綁定本機 loopback 隨機埠，並檢查 session cookie、Host 與 Origin。
- 桌面版與舊網頁版使用各自獨立的資料庫，不會自動同步。第一次從原始碼啟動時，
  會以 SQLite 備份複製專案 `data/matlens.db`，不覆蓋既有桌面資料庫。
  也可指定舊資料庫：

  ```powershell
  .\MatLens.exe --import-from "D:\舊版MatLens\data\matlens.db"
  ```

## 開發

環境：Python 3.12（以 [uv](https://docs.astral.sh/uv/) 管理）與 Node.js。

```powershell
uv sync --locked
npm --prefix frontend ci
```

桌面版開發啟動：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\run-desktop.ps1
```

網頁版（先建置前端，開啟 <http://127.0.0.1:8000>）：

```powershell
npm --prefix frontend run build
PowerShell -ExecutionPolicy Bypass -File .\run.ps1
```

前後端分開開發：

```powershell
uv run --locked uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
npm --prefix frontend run dev    # http://127.0.0.1:5173，Vite 轉送 /api
```

完整驗證：

```powershell
uv run --locked ruff check .
uv run --locked pytest
npm --prefix frontend test
npm --prefix frontend run build
```

建立 EXE 與 ZIP（桌面版）：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\packaging\build.ps1
uv run --locked python -m desktop.main --self-test --report build/source-self-test.json
```

測試範圍與限制見 [桌面驗證紀錄](docs/desktop-validation.md)；
發佈流程見 [更新維護與復原](docs/online-updates.md)。

## 專案結構

```text
MatLens/
├─ backend/app/       FastAPI、SQLite、照片總覽
│  └─ storage/        路徑、案件、命名、掃描與照片同步
├─ frontend/src/      React 操作介面
├─ desktop/           Windows 桌面入口、本機服務、資料接續與線上更新
├─ packaging/         EXE／ZIP 建置與安裝腳本
├─ docs/              驗證紀錄、更新維護與各版發行說明
├─ tests/             後端 API、更新與桌面測試
├─ data/              網頁版執行後建立的本機資料（不提交）
├─ pyproject.toml     uv 專案與 Python 依賴
├─ uv.lock            鎖定依賴版本
└─ run.ps1            網頁版啟動腳本
```
