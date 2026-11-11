# 0.5.7 實作與發布前驗證

日期：2026-11-10～11。本文件記錄發布前的本機實作與隔離驗證；以下「尚未發布」為當時狀態，公開驗證完成後另記錄發布結果。

## 實作範圍

- `backend/app/db.py`：新增獨立火警細項表；首次去重接續原自訂問題，保留原清單，重開不重新加入已刪細項。案件增量新增四個有預設值的欄位，原資料不重建。
- `main.py`、`schemas.py`：細項 CRUD、嚴格布林命名偏好、編輯載入／預覽／更新 API。舊建立案件請求預設包含材料，資料相容性維持 1。
- `storage/cases.py`、`rescan.py`、`photo_sync.py`：火警命名空白分隔、材料可省略、新舊格式辨識及編輯欄位保護；掃描不更動磁碟檔案。
- `storage/editing.py`：案件及照片／磁碟內容 token、精確原新路徑、原根目錄邊界、來源確認、同名拒絕、SQLite backup、持久化更名紀錄與中斷恢復。
- `frontend/src/App.tsx`、`CaseListSection.tsx`：編輯直接載入原主工作區，沿用圖塊、貼上、移除、排序、角色與縮放。保留背景新增草稿，結束編輯還原；同案儲存後留在編輯模式。
- `storage/workspace_edit.py`：multipart POST 更新同 id，只上傳新增照片；原照片用保存的 id 引用。先準備新內容，再保存完整原案檔案並交換；SQL 失敗／中斷依 journal 與 edit_revision 恢復，恢復期間保持寫入鎖。
- `useFireNaming.ts`、`App.tsx`：唯讀載入命名偏好、依序保存與重試、獨立細項新增／刪除、請求取消後不覆蓋選擇。三種配置沿用同一流程。

## 已完成驗證

- Ruff、199 個 pytest、72 個 Vitest、TypeScript 與正式前端 build。
- 真實 SQLite：舊 13 欄案件升級且原值不變、細項接續可重複執行、保存／重開、兩份選項獨立、命名偏好與舊請求預設。
- 真實檔案系統：同案件 id，保留照片 id／內容不變；新增／移除／排序／角色保存後 URL 可讀，移除檔案仍在原案備份。純備註不更名、全域儲存根目錄變更不搬舊案；既有跨案重複照片不阻擋單純角色調整。
- 受控失敗：目標同名、過期 token、外部檔案變動、越界路徑、權限失敗、SQL 更新失敗後回復；中斷前／後的提交恢復，兩個路徑均存在或內容改變時保留紀錄並停止猜測。
- 新舊火警格式、細項含空白／連字號與材料／火警文字重疊；歧義回傳無法辨識，不任意拆分。
- Testing Library：三種配置載入主工作區、精確路徑確認、拒絕更名不送儲存、儲存衝突／重載、圖片角色／新增／排序／縮放、背景草稿與預覽 URL 保留、命名失敗重試、晚到請求及兩區同名刪除不連動。編輯儲存後背景草稿仍觸發桌面未儲存保護。
- Windows WebView2 來源隔離自測：火警自訂、命名保存、載入主工作區編輯／更名，新增一張、移除一張、排序及改角色，儲存同 id／保留照片 id、三張照片可讀；重載後火警偏好與細項還原、三種配置最小視窗無橫向溢出。

原始碼／打包／安裝與更新的 JSON 報告只留忽略的 build／暫存目錄，全部使用合成照片與自建資料庫。
本次 CUA 桌面擷取工具連線失敗，未另作原生目視截圖；不以此宣稱已完成使用者外觀驗收。
T-019 另以 Edge 的隔離 API fixture 截圖並核對實際 CSS 外觀，詳見下節；不將 fixture 當作 SQLite 整合驗證。

## 使用與限制

在主專案執行 `PowerShell -ExecutionPolicy Bypass -File .\run-desktop.ps1`。
火警區可自訂細項，案件命名處切換「火警資料夾名稱包含材料」；案件清單每列按「編輯」。
編輯模式保留原命名方式；需要時勾選「本次套用新版命名」，再確認原／新完整路徑。

可新增／移除／排序照片及調整角色，不跨根目錄／父目錄搬移。
原始匯入照片來源不動；未知來源要更名或改照片必須確認是整理結果。同名不覆蓋。
SQLite 備份位於資料庫同層 backups，未完成紀錄位於 case-edits。
照片異動原案檔案保存於該根目錄 `.matlens-history/<作業 id>`，準備區為 `.staging`；掃描略過隱藏目錄，復原不確定時保留資料與紀錄。
UPD-001 的另一台電腦更新及 LINE／瀏覽器跨程式實際貼上驗收仍未結案。


## 最終本機交付

- 打包 EXE 與安裝後 EXE 的隔離自測均完成火警自訂、命名保存、案件更正／更名與三張照片核對。
- 安裝／重裝、執行中阻擋、更新鎖、捷徑目標及解除安裝保留資料通過。
- 使用公開 0.5.6 更新器（既有簽章及 SHA-256 驗證）分別在舊 Programs/MatLens 與新 MatLens/app 測試本機 0.5.7 更新包：啟動、SQLite 備份、使用者資料／照片及原程式保留均通過。舊主程式為測試標記，不宣稱完整 0.5.6 UI 或另一台電腦已驗收。
- 新打包更新器以 QA 版本資訊不符觸發預先測試拒絕，實際留下失敗 log，原程式、資料、照片及備份均保留。QA manifest 只留忽略的 build，不發布。
- 本機簽章／ZIP 內容稽核通過；完整安裝與更新 ZIP 程式相同且不含案件、資料庫或私鑰。
- 主專案來源、前端資產及 Setup／兩個 ZIP 經雜湊核對後同步，原檔備份保留；該目錄 run-desktop.ps1 的 uv 同步、正式前端建置及隔離桌面自測通過。

本機安裝精靈為 dist/MatLens-Setup-0.5.7-x64.exe，更新 manifest 為本機準備檔。
正式 GitHub latest 仍是 0.5.6；此輪沒有提交、推送或新增 Release。

## 主工作區編輯修正的驗證報告

本次重新建置後使用新報告，不沿用舊獨立編輯視窗的測試結果：

| 範圍 | 忽略目錄內的報告 |
| --- | --- |
| 來源 WebView2 | `build/workspace-edit-source-final.json` |
| 打包 EXE | `build/exe-workspace-corrected.json` |
| 安裝及安裝後 EXE | `build/installer-workspace-corrected.json` |
| 公開 0.5.6 更新器／舊路徑 | `build/upgrade-workspace-corrected-legacy.json` |
| 公開 0.5.6 更新器／新路徑 | `build/upgrade-workspace-corrected-installed.json` |
| 受控更新失敗與 log | `build/update-failure-workspace-corrected.json` |
| 本機簽章及附件稽核 | `build/local-audit-workspace-corrected.json` |
| 主專案啟動腳本 | 主專案的 `build/main-workspace-corrected.json` |

以上皆通過；所有案件與照片均為隔離測試資料。主專案來源與 Setup／ZIP 同步有 SHA-256 收據及原檔備份。
使用者原本已開啟的程式需關閉後重新啟動，才會載入新工作區；本次沒有自動替換其正在執行的安裝。

## T-019：置中儲存更正確認窗

- `EditConfirmation.tsx`／`workspace.css`：主題配色、固定置中、原新路徑、照片摘要與來源確認；長路徑完整換行，捲動內容與固定底部操作分開。
- `App.tsx`：等待明確選擇後才儲存，確認期間保留 saving 狀態、背景 inert；取消／Esc 不寫入，草稿及照片保留，單次確認只送一份更新。
- Testing Library：確認、取消、Esc、循環焦點、恢復焦點、遮罩不儲存、長路徑完整文字、重複確認與儲存衝突保留草稿。
- 真實 WebView2／SQLite：頁面捲至下方後驗證視窗中心位置、取消未更動案件，重新確認後更新同 id，照片異動及備份流程正常；報告 `build/confirm-modal-source-first.json`。
- Headless Edge 外觀驗證使用隔離 fixture：藍白右側、原版三欄、藍白上方小視窗（680×580）與極長路徑。核對水平／垂直中心、無橫向溢出、底部可見、初始焦點及 Esc 保留草稿，未發任何更新請求。
- 外觀截圖及量測：`build/confirm-modal-visual/blue-right.png`、`classic.png`、`blue-top-small-long-path.png`、`report.json`；已逐張檢視，未包含使用者真實資料。
- 初次將測試與打包同時執行造成 npm ci 與測試套件檔案鎖衝突；改為依序執行後重新建置。此為建置流程錯誤，首份失敗 log 留存，不以重跑隱藏。

本輪維持未發布的本機 0.5.7，不自動更新目前正在執行的安裝；未提交或推送 GitHub。

T-019 重打安裝包後的報告以本輪檔名區分：`build/exe-confirm-modal.json`、
`build/installer-confirm-modal.json`、`build/upgrade-confirm-modal-legacy.json`、
`build/upgrade-confirm-modal-installed.json`、`build/update-failure-confirm-modal.json`、
`build/local-audit-confirm-modal.json`，主專案啟動腳本報告為該專案的 `build/main-confirm-modal.json`。
本輪來源、打包及主專案自測另外檢查 `centered_edit_confirmation`，不沿用前次主工作區修正的證據。
