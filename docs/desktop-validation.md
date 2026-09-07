# Windows 桌面版驗證紀錄

驗證日期：2026-09-06。此版本提供 Windows x64 EXE、ZIP 與捷徑安裝腳本。

## 架構與資料

- 桌面：pywebview 6.2.1／Edge WebView2；保留 React、FastAPI 與 SQLite。
- Python：使用專案 uv 虛擬環境；目前 Python 3.12.9。
- 本機服務：127.0.0.1 隨機埠，使用隨機 session token、HttpOnly cookie、Host／Origin 驗證。
- 程式安裝目錄：`%LOCALAPPDATA%/Programs/MatLens/`。
- 案件資料目錄：`%LOCALAPPDATA%/MatLens/`。
- 舊版匯入使用 SQLite backup 建立快照，再產生桌面資料庫；來源照片不搬移。
- 原網頁版與桌面版資料庫彼此獨立，後續案件不會雙向同步。

## 已完成驗證

| 項目 | 結果 |
| --- | --- |
| Windows 11 Pro x64，版本 10.0.26200 | 實機啟動成功 |
| Ruff | 通過 |
| pytest | 15 項通過 |
| Vitest | 7 項通過，含完整預覽、縮放、平移、還原與切換圖片 |
| TypeScript／Vite 正式建置 | 通過 |
| 原始碼桌面入口自測 | 通過 |
| 打包 EXE 自測 | 通過，退出碼 0 |
| 安裝後 EXE 自測 | 通過，退出碼 0 |
| 真實 WebView2 操作流程 | 連續 3 次 drop、中文檔名、預覽、編輯、儲存、案件清單與照片回看通過 |
| 資料持久化 | 新連線讀取 SQLite：1 筆測試案件、3 張測試照片 |
| 關閉生命週期 | 自測完成後正常關閉；本機 socket 釋放測試通過 |
| 原生目錄選擇器 | 實機開啟與取消成功；選擇後持久化另有 API 測試 |
| 單一實例 | Windows mutex／通知事件測試通過；再次啟動不建立第二份服務 |
| 舊資料 | 1 筆原有案件、3 張既有照片路徑可讀；保留原始資料库與接續備份 |
| 安裝腳本 | 安裝成功，桌面與開始選單捷徑指向已安裝 EXE |
| ZIP 檢查 | 包含 EXE、執行依賴、前端及安裝腳本；未夾帶案件資料庫／現場照片 |

自動化 WebView2 的 drop 使用真正的 DOM File／DataTransfer／DragEvent，
但不等同於已在所有 Windows 版本完成檔案總管滑鼠拖放測試。

## 自我審查與已修正事項

1. SQLite `with connection` 只管理交易，不會關閉連線。舊資料接續測試重現 Windows
   資料庫鎖定；初始化已改成明確關閉連線，確認快照完成後才發佈目的資料庫。
2. WinForms 關閉事件在 UI 執行緒讀取 JavaScript，會和 WebView2 的回傳互相等待。
   已改成介面主動同步草稿狀態；關閉事件只讀取 Python 狀態。
3. 狀態回報可能亂序，重新載入也可能讓序號重置。回報使用跨重新載入遞增時間序號，
   Python 忽略過期狀態；測試涵蓋未儲存、取消關閉、儲存進行中與完成後關閉。
4. 匯入只建立新的桌面資料庫；已有桌面資料時拒絕以舊資料覆蓋。
5. 桌面內部 API 必須通過 session、Host 與 Origin 檢查，禁止其他網頁呼叫原生功能。
6. 直向照片會被 Grid 的圖片固有尺寸撐高而截斷，已讓預覽圖片以絕對定位填滿固定視窗，
   並使用 `object-fit: contain`。加入滾輪／按鈕縮放、拖曳平移、範圍限制與一鍵還原。

## 重跑方式

```powershell
uv run --locked ruff check .
uv run --locked pytest
npm --prefix frontend test
npm --prefix frontend run build
uv run --locked python -m desktop.main --self-test --report build/source-self-test.json
```

打包後執行（PowerShell）：

```powershell
$report = Join-Path (Get-Location) 'build/exe-self-test.json'
$process = Start-Process .\dist\MatLens\MatLens.exe -ArgumentList '--self-test','--report',('"' + $report + '"') -PassThru -Wait
$process.ExitCode
Get-Content $report
```

`--self-test` 一律在新的 Windows 暫存目錄建立合成照片與測試資料庫，
不會匯入或寫入使用者案件。報告包含測試資料目錄，可供人工檢查。

## 尚未驗證與限制

- 沒有 Windows 10 實機／VM；不能宣稱已完成 Windows 10 實測。
- 尚未在完全沒有開發工具的乾淨 Windows 環境實測所有執行依賴。
- 尚未驗證 Windows 10 的檔案總管連續拖放、不同 DPI 與多螢幕配置。
- EXE 尚未購買簽章憑證或進行數位簽章。
- 需有 Microsoft Edge WebView2 Runtime；本版沒有將 Runtime 安裝程式包入 ZIP。
- Inno Setup 編譯器下載／安裝被環境審核阻擋，`.iss` 是未驗證的備用建置設定。
  本版已驗證的安裝方式為 ZIP 內的 `Install-MatLens.cmd`，尚未提供控制台解除安裝項目。
- 自訂選項、案件資料庫與現場照片不會上傳 GitHub。

## 參考

- [pywebview API](https://pywebview.flowrl.com/api/)：原生對話框、視窗事件與 JavaScript 回報。
- [pywebview 使用指南](https://pywebview.flowrl.com/guide/usage.html)。
- [Microsoft WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)：Runtime 下載。

## 線上更新驗證（2026-09-07，0.3.0）

- Ruff 通過；pytest 54 項、Vitest 12 項通過；正式前端 build 通過。
- 新增簽章／雜湊／版本頻道／不相容資料版本／ZIP 路徑及連結／下載大小限制測試。
- 驗證離線與損壞下載可重試、未儲存／正在儲存阻止更新、安裝失敗解除 UI 鎖定。
- 原始碼與打包 EXE 的真實 WebView2 匯入、完整預覽、縮放平移、儲存回看通過。
- 隔離 LOCALAPPDATA 中執行獨立 PyInstaller 更新器：驗證已簽章更新包、SQLite backup、
  新版預先自測、程式目錄替換與新版啟動健康檢查成功；既有材料選項及照片內容不變。
- 上述更新演練的舊程式為測試標記，僅舊更新器版本模擬為 0.2.0；使用真實 0.3.0 EXE。
  不是宣稱原來沒有更新功能的 0.2.0 能自行更新。首次升級仍須手動執行安裝腳本。
- 替換／啟動失敗回復使用真實檔案系統回歸測試；沒有在正式使用者目錄注入故障。
- 更新 ZIP 314 個項目，包含主程式及更新器，未發現照片資料目錄、DB、私鑰、測試更新器。
- 報告在忽略的 `build/update-source-self-test.json`、`build/update-worker-self-test.json`、
  `build/update-frozen-worker-self-test.json`；測試資料在具 `matlens-update-qa-` 前綴的 TEMP。
- Windows 11 已實測；Windows 10、斷電過程、各家防毒鎖檔情境仍待實機驗證。
- EXE 尚無 Authenticode 簽章；更新包另外有 Ed25519 驗證，兩者不可混為一談。
- 公開發佈後以真正的 UpdateService 取得 `releases/latest/download/stable.json`，
  確認目前版本 0.3.0，再實際下載 43,725,673 bytes 的更新包；簽章及 SHA-256 驗證通過。
  可用 `uv run --locked python -m tests.check_update_release` 重跑。
- 原始碼自測關閉時偶有 pywebview 的已處置 WebView2 回呼警告；報告與 exit code 皆成功，
  未影響照片持久化。這項關閉時序的第三方回呼警告仍需後續追蹤。

## 原倉庫公開與更新來源遷移（0.3.1）

- 公開前掃描完整 Git 歷史與目前內容，未發現常見 Token、私鑰、照片、資料庫或 `.env`。
- 0.3.1 內建更新網址改為 `kobojp/MatLens`，舊下載倉庫只保留 v0.3.0 過渡 manifest。
- 遷移演練使用測試專用的凍結 0.3.0 更新器與真實 0.3.1 EXE，全程在隔離 LOCALAPPDATA。
- 0.3.1 原始碼與打包 EXE 的真實 WebView2 自測通過；隔離升級確認 SQLite、照片、
  備份及舊程式均保留，新版啟動版本為 0.3.1。
