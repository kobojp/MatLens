# MatLens 0.3.1：原倉庫公開與更新來源遷移

- 原始碼及 Windows 下載統一放在公開 `kobojp/MatLens` 倉庫。
- 新版改從本倉庫的 Releases 檢查並下載後續更新。
- 保留 v0.3.0 的舊下載入口作為一次性轉接，已安裝的 v0.3.0 仍可自動升級。
- 沿用簽章驗證、SHA-256、未儲存保護、SQLite 備份、新版試跑與失敗回復。

## 安裝

第一次安裝或手動升級，下載 `MatLens-0.3.1-win-x64.zip`，完整解壓縮後執行
`Install-MatLens.cmd`。已安裝 v0.3.0 可在「關於與更新」下載並安裝。

案件資料庫、現場照片、簽章私鑰與開發虛擬環境不包含在原始碼或下載包中。

## 已知限制

- Windows 11 x64 已實測；Windows 10 仍待實機驗證。
- EXE 尚未使用 Windows Authenticode 簽章，SmartScreen 仍可能提出警告。
- 需要 Microsoft Edge WebView2 Runtime。
- 本版不包含月份資料夾掃描功能。
