# MatLens Windows 桌面預覽版

提供獨立 Windows 桌面視窗，沿用照片整理、案件清單、材料／問題快速選項與本機 SQLite 資料。
照片預覽支援完整顯示、滾輪／按鈕縮放、左鍵拖曳與雙擊還原。

## 使用方式

1. 下載並解壓縮 `MatLens-0.2.0-win-x64.zip`。
2. 雙擊 `MatLens/MatLens.exe`；或執行 `Install-MatLens.cmd` 安裝並建立捷徑。
3. 更新前先儲存照片並關閉 MatLens。保留整個程式資料夾，不要只複製 EXE。

不需要安裝 Python 或 Node.js，但需要 Microsoft Edge WebView2 Runtime。
桌面案件資料位於 `%LOCALAPPDATA%/MatLens/`，照片儲存目錄可自訂。
舊版資料接續會先備份，桌面版與舊網頁版的案件不會雙向同步。

## 驗證與限制

- Windows 11 x64 已實測，15 項後端與 7 項前端測試通過。
- EXE 已通過真實 WebView2 的連續照片匯入、直向圖片完整顯示、縮放、平移、儲存與回看自測。
- Windows 10 尚待實機驗證，因此此版本標記為預覽版。
- EXE 尚未進行數位簽章；未附 WebView2 Runtime 安裝程式。
- ZIP 不含使用者案件資料庫、現場照片或開發虛擬環境。
