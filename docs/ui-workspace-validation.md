# 新版照片工作區驗證

日期：2026-11-08。0.5.6 工作區驗證；公開狀態與附件以 GitHub Release 為準。

## 版面及檔案

預設為照片圖塊、右側案件資料、大圖塊、資料展開。設定頁可選原版三欄、新版右側、新版上方；
原版保留原有配色。新版使用藍白色，色碼集中於 `frontend/src/workspace.css`。

- `backend/app/schemas.py`、`main.py`：UI 偏好驗證及 GET／POST API，沿用 SQLite settings，不變更 schema。
- `frontend/src/useUIPreferences.ts`、`UISettings.tsx`：唯讀載入、依序保存、重試、四項版面偏好重設。
- `frontend/src/App.tsx`：共用案件與照片草稿，集中照片操作，三種配置及上方收合。
- `frontend/src/PhotoLightbox.tsx`：重用 PhotoPreview 縮放／平移，換圖、焦點限制、Esc 及焦點還原。
- `tests/test_ui_preferences.py`、`frontend/src/WorkspaceUI.test.tsx`：真實 SQLite 與使用者操作回歸。
- `desktop/smoke.js`、`diagnostics.py`：Windows WebView2 的照片／儲存／重載／最小視窗驗證。

## 已驗證

Ruff、162 個 pytest、56 個 Vitest、TypeScript 與 Vite 正式建置通過。
UI 偏好不影響既有案件與照片；恢復預設版面保留其他 settings、自訂選項及目前草稿。
設定初次載入、快速切換、保存失敗與重試都有測試；設定保存中沿用桌面未儲存保護。

來源 WebView2 自測以合成直式照片及超長檔名實際匯入、貼上確認、取消、排序／角色、放大縮放／平移、
換圖、原版／新版切換、儲存案件及三張照片，重新載入還原資料與配置。
1000×760 視窗內測上方收合／展開、原版、新版右側及長目的地：CSS viewport 986、document 971，沒有水平溢出。
橫式合成圖片另由 Windows 原生檔案視窗匯入，實際點圖、Esc、設定切換並截圖。

同一獨立資料庫的正常桌面程序關閉再啟動，還原上方及收合設定；收合中按儲存遇到必填欄位，
Windows 原生驗證會展開並定位欄位。資料欄位的 DOM 與上方視覺順序一致。

藍色 #2563EB 在白底對比約 5.17:1，深藍 #17345C 在淺藍 #E8F1FF 約 10.97:1；
狀態另有文字，照片不套用色彩濾鏡。

最終打包 EXE 自測與安裝後 EXE 自測通過，皆保存一個案件、三張照片及新版配置；
安裝／重裝、執行中阻擋、更新鎖、捷徑及解除安裝保留資料通過。
原版 0.5.4 客戶端／更新器（舊路徑）與 0.5.5（新路徑）經完整 UI 下載、安裝、重啟至 0.5.6，
核對 startup.ready、執行位置、案件／照片雜湊與 SQLite 備份。此輪傳輸使用本機已簽章更新包。

現行來源更新器正向驗證通過，該測試明確模擬基準版本；打包更新器以 QA 簽章版本不符觸發預先測試失敗，
實際留下 worker.log，原程式、資料、照片及備份完整保留。回復、鎖及啟動失敗另由 pytest 受控案例涵蓋。
這些是本機隔離驗證，不是出問題電腦的故障重現。

主專案原始碼與產物經檔案雜湊核對後同步，保留原檔備份；主專案 run-desktop.ps1 的 uv 同步、
前端重建及隔離桌面自測通過，JS／CSS 資產與安裝包一致。簽章與 ZIP 雜湊本機稽核通過。
原始碼、[v0.5.6 安裝包及線上更新](https://github.com/kobojp/MatLens/releases/tag/v0.5.6) 已發布，公開下載、簽章及正常更新檢查驗證通過。本機 JSON、log 與合成資料只留忽略的 build／暫存目錄。

## 操作與界線

執行 `PowerShell -ExecutionPolicy Bypass -File .\run-desktop.ps1`，進入「設定 → 介面配置」。
「恢復預設版面」只重設 UI 四項設定。新版照片區可匯入、拖放或貼上，點圖開啟看圖視窗。

其他電腦的 0.5.4 更新問題仍為 [UPD-001](../ISSUES.md#upd-001)，本機測試不能替代該機驗收；
LINE、Chrome／Edge 真正複製圖片仍待外部來源驗收。
