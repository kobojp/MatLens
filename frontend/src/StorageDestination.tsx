import type useStorageSelection from "./useStorageSelection";

export default function StorageDestination({ storage }: { storage: ReturnType<typeof useStorageSelection> }) {
  return (
    <fieldset className="storage-destination">
      <legend>案件儲存位置</legend>
      <div className="free-path-panel">
        <div className="free-path-row">
          <input aria-label="掃描路徑" className="free-path-input" value={storage.path} disabled={storage.loading}
            onChange={(event) => storage.editPath(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void storage.scan(); } }}
            placeholder="選擇或貼上照片根目錄" />
          <button type="button" onClick={() => void storage.choose()} disabled={storage.loading}>選擇</button>
          <button type="button" className="scan-button" onClick={() => void storage.scan()} disabled={storage.loading}>
            {storage.loading ? "掃描中…" : "掃描"}
          </button>
        </div>
        {storage.error && <p role="alert" className="folder-warning">{storage.error}</p>}
        {storage.result && <>
          {storage.result.subfolders.length ? (
            <div className="free-subfolder-list" role="radiogroup" aria-label="選擇子目錄">
              {storage.result.subfolders.map((name) => (
                <label key={name} className={`free-subfolder-item ${storage.selection.subfolder === name ? "active" : ""}`}>
                  <input type="radio" name="storage-subfolder" value={name}
                    checked={storage.selection.subfolder === name} onChange={() => storage.select(name)} />
                  {name}
                </label>
              ))}
            </div>
          ) : <p className="folder-warning">此路徑沒有子目錄，請先建立子資料夾或選擇其他目錄。</p>}
          <label className="free-date-toggle">
            <input type="checkbox" checked={storage.selection.with_date}
              onChange={(event) => storage.setWithDate(event.target.checked)} />
            加入日期前綴
          </label>
          <p className="storage-save-status" role="status">{storage.saveStatus}</p>
          {storage.saveStatus.startsWith("儲存失敗") && <button type="button" onClick={storage.retrySave}>重試儲存設定</button>}
          {storage.valid && <div className="free-subfolder-preview">
            <span>將存入子目錄</span><code>{storage.selection.subfolder}</code>
          </div>}
        </>}
      </div>
    </fieldset>
  );
}
