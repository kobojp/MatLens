---
name: matlens-release
description: "發布 MatLens Windows 安裝包與線上更新到 GitHub Releases，處理版本同步、EXE 自測、既有私鑰簽章、草稿附件核對及公開下載驗證。適用於發布安裝包、發布新版或驗證發佈流程；單純提交或推送 Git 不使用本 skill。"
---

# MatLens 發佈

將當前 MatLens 修正發布為可安裝、可驗證的 Windows x64 正式版。

## 起點與授權範圍

1. 從本 skill 往上找到 repository，先讀根目錄 `AGENTS.md`、
   `docs/online-updates.md`，再讀本 skill 的 [發佈操作](references/workflow.md)。
2. 確認目前 checkout、`git worktree list`、HEAD、遠端及工作目錄修改。
   本專案可能同時有原始碼主目錄與代理工作區；建置、版本提交及附件必須來自同一份修正。
   不覆蓋其他 checkout 的未提交工作。
3. 使用者明確要求「發布安裝包／發布新版」時，可依此流程完成打包、簽章、草稿及正式發布，
   不重複詢問相同授權。只要求準備、檢查、dry run 或撰寫 skill 時，停在對應範圍，
   不推送、不新增 Release，也不改動既有公開附件。此 skill 本身不授予額外的外部操作權限。
4. 若相同 tag 已存在，先檢查 draft／公開狀態與附件。可接續相符的草稿；
   不覆寫已公開版本或重建同一 tag 的不同內容。修正已公開的程式要使用新版本。

## 發佈關卡

依序完成，前一關未通過不得公開：

- **版本與來源**：版本唯一來源為 `desktop/version.py`；同步 `pyproject.toml`、`uv.lock`、
  `packaging/MatLens.iss`、`AGENTS.md` 版本及 `docs/release-v<版本>.md`。
  未指定版本的一般修正可採下一個 patch，但先核對公開版本與 tag。正式頻道不接受 rc。
- **簽章可用**：用 `scripts/release_checks.py key` 尋找並驗證既有私鑰。
  支援明確路徑、`MATLENS_SIGNING_KEY_PATH`、一般 LocalAppData 與 Codex 應用程式重新導向位置。
  公鑰必須匹配 `desktop/update-source.json`。缺失時只詢問路徑，不要求貼私鑰內容；
  可以繼續已授權的打包與測試，簽章與公開發布須等問題解決。
- **驗證與建置**：Ruff、pytest、Vitest、前端 build 通過，使用 `packaging/build.ps1 -Installer`
  產生安裝精靈 EXE、完整 ZIP 與更新 ZIP。自 0.5.5 起安裝精靈為主要安裝方式。
  編譯器可由 `-CompilerPath` 或 `MATLENS_ISCC_PATH` 指定，工具不提交到 Git。
- **執行驗證**：原始碼及打包 EXE 的隔離 `--self-test` 成功；檢查 exit code、報告的 `ok`、
  版本、案件與照片筆數。執行隔離更新及回復測試，驗證備份、資料與照片保留。
  確認此次修正也進入打包結果；不能只以啟動成功代替功能驗證。
- **本機附件**：簽署後執行 `scripts/release_checks.py local`，核對版本、簽章、更新 URL、
  ZIP 路徑、安裝腳本、內容一致性與敏感檔案排除。0.5.5 起只上傳安裝精靈、兩個版本 ZIP 與 `stable.json`。
  執行 `tests.run_installer_smoke` 驗證安裝、重裝、捷徑及解除安裝保留資料；
  同時驗證舊路徑與新 `MatLens/app` 路徑的隔離更新，保留各自報告。
- **草稿**：來源提交並推送後，以精確 commit 建立 draft；執行
  `scripts/release_checks.py draft --commit <完整 SHA>`，核對 tag、commit、附件名稱、大小與 SHA-256。
- **公開**：所有關卡通過且在使用者授權內，才公開並設為 latest。
  執行 `scripts/release_checks.py public`，由未登入的公開 `releases/latest/download` 實際下載
  manifest、安裝精靈與兩個 ZIP，並確認正常更新檢查讀到新版本。

## 失敗與重跑

- 所有 Python 指令使用專案的 `uv run --locked`，依賴同步使用 `uv sync --locked`。
- 不產生替代發行私鑰、不更換內建公鑰、不把 Token／私鑰／機器專屬路徑加入 Git 或附件。
  私鑰可以只在本機從已知目錄辨識；不要把實際找到的位置寫回公開文件。
- `DATA_COMPATIBILITY` 沿用現值；本流程不自動決定資料遷移或降版。
  使用者的安裝目錄、資料庫與照片不屬於發佈自測目標；隔離測試只使用其自建的資料與程序。
- EXE 自測失敗時保留首份報告並診斷，不無限重試到綠燈。
  若確認為暫時性啟動問題，可有限重跑，另保留通過報告並交叉檢查隔離更新中的 EXE 自測。
  原因或風險仍未釐清時保留草稿，不能宣稱全部驗證完成。
- `latest` 指向舊版時先核對 GitHub API。只有簽章有效、版本較舊的回應可有限等待快取更新；
  簽章、雜湊、平台或相容版本錯誤立即停止。不能用帶 query 的成功結果取代正常更新網址的驗證，
  也不因快取延遲重發 Release 或改動更新來源。
- 中斷後先查現況與報告再接續，不重複公開、不清空 `dist/`／`build/`，
  不自動刪除舊測試目錄或回復備份。檔案與報告按版本留在忽略的目錄。

## 完成回覆

提供版本、公開 Release 與安裝精靈連結，說明執行 Setup EXE 後按「下一步」，
簡述測試、隔離升級及公開下載驗證結果。若只完成草稿，明確說明尚缺哪一關，不宣稱已發布。
