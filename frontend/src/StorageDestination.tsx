import type { FreeScanResult, StorageMode, StorageMonth, StorageTree } from "./types";

type Props = {
  storageMode: StorageMode;
  setStorageMode: (mode: StorageMode) => void;
  storageTree: StorageTree | null;
  selectedMonth: string;
  selectedMonthEntry: StorageMonth | undefined;
  selectedSubfolder: string;
  setSelectedSubfolder: (value: string) => void;
  chooseMonth: (name: string) => void;
  loadingFolders: boolean;
  loadStorageTree: (date: string, month?: string, subfolder?: string, material?: string) => Promise<void>;
  workDate: string;
  material: string;
  materials: string[];
  showFolderCreator: boolean;
  setShowFolderCreator: (value: boolean) => void;
  folderPresets: string[];
  toggleFolderPreset: (name: string) => void;
  customFolderName: string;
  setCustomFolderName: (value: string) => void;
  creatingFolders: boolean;
  createFolders: () => void;
  freeScanPath: string;
  setFreeScanPath: (value: string) => void;
  scanFreeDirectory: (path: string) => Promise<void>;
  freeLoadingFolders: boolean;
  chooseFreeFolder: () => void;
  freeScanResult: FreeScanResult | null;
  freeSelectedSubfolder: string;
  setFreeSelectedSubfolder: (value: string) => void;
  freeWithDate: boolean;
  setFreeWithDate: (value: boolean) => void;
};

export default function StorageDestination({
    storageMode,
    setStorageMode,
    storageTree,
    selectedMonth,
    selectedMonthEntry,
    selectedSubfolder,
    setSelectedSubfolder,
    chooseMonth,
    loadingFolders,
    loadStorageTree,
    workDate,
    material,
    showFolderCreator,
    setShowFolderCreator,
    folderPresets,
    toggleFolderPreset,
    customFolderName,
    setCustomFolderName,
    creatingFolders,
    createFolders,
    freeScanPath,
    setFreeScanPath,
    scanFreeDirectory,
    freeLoadingFolders,
    chooseFreeFolder,
    freeScanResult,
    freeSelectedSubfolder,
    setFreeSelectedSubfolder,
    freeWithDate,
    setFreeWithDate,
    materials,
}: Props) {
  return (
      <fieldset className="storage-destination">
        <legend>案件儲存位置</legend>
        <div className="storage-mode-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={storageMode === "month"}
            className={`mode-tab ${storageMode === "month" ? "active" : ""}`}
            onClick={() => setStorageMode("month")}
          >
            月份模式
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={storageMode === "free"}
            className={`mode-tab ${storageMode === "free" ? "active" : ""}`}
            onClick={() => setStorageMode("free")}
          >
            自由路徑
          </button>
        </div>

        {storageMode === "month" ? (
          <>
            <div className="destination-selects">
              <label>
                <span>月份資料夾</span>
                <select
                  aria-label="月份資料夾"
                  value={selectedMonth}
                  disabled={loadingFolders || !storageTree}
                  onChange={(event) => chooseMonth(event.target.value)}
                >
                  {[...new Set([
                    ...(storageTree?.target_month ? [storageTree.target_month] : []),
                    ...(storageTree?.months.map((item) => item.name) ?? []),
                  ])].map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
              <label>
                <span>子目錄</span>
                <select
                  aria-label="儲存子目錄"
                  value={selectedSubfolder}
                  disabled={loadingFolders || !selectedMonthEntry?.subfolders.length}
                  onChange={(event) => setSelectedSubfolder(event.target.value)}
                >
                  {!selectedMonthEntry?.subfolders.length && <option value="">尚無子目錄</option>}
                  {selectedMonthEntry?.subfolders.map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="scan-button"
                disabled={loadingFolders}
                onClick={() => loadStorageTree(workDate, selectedMonth, selectedSubfolder, material)}
              >
                {loadingFolders ? "掃描中…" : "重新掃描"}
              </button>
            </div>

            {!selectedMonthEntry && storageTree && (
              <div className="folder-warning" role="status">
                找不到「{selectedMonth}」資料夾，請先選擇要一起建立的子目錄。
              </div>
            )}

            {(showFolderCreator || !selectedMonthEntry) ? (
              <div className="folder-creator">
                <span>常用子目錄（可複選）</span>
                <div className="folder-presets">
                  {materials.map((name) => (
                    <label key={name}>
                      <input
                        type="checkbox"
                        checked={folderPresets.includes(name)}
                        onChange={() => toggleFolderPreset(name)}
                      />
                      {name}
                    </label>
                  ))}
                </div>
                <div className="folder-custom-row">
                  <input
                    aria-label="自訂子目錄名稱"
                    maxLength={80}
                    value={customFolderName}
                    onChange={(event) => setCustomFolderName(event.target.value)}
                    placeholder="例如 模組、其他設備"
                  />
                  <button type="button" disabled={creatingFolders} onClick={createFolders}>
                    {creatingFolders ? "建立中…" : `建立 ${selectedMonth || "月份"}與子目錄`}
                  </button>
                  {selectedMonthEntry && (
                    <button type="button" onClick={() => setShowFolderCreator(false)}>取消</button>
                  )}
                </div>
              </div>
            ) : (
              <button type="button" className="add-folder-button" onClick={() => setShowFolderCreator(true)}>
                ＋ 新增子目錄
              </button>
            )}
          </>
        ) : (
          <div className="free-path-panel">
            <div className="free-path-row">
              <input
                aria-label="掃描路徑"
                className="free-path-input"
                value={freeScanPath}
                onChange={(event) => setFreeScanPath(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void scanFreeDirectory(freeScanPath);
                  }
                }}
                placeholder="貼上完整路徑，例如 H:\桃隆消防\材料更換照片"
                disabled={freeLoadingFolders}
              />
              <button
                type="button"
                onClick={chooseFreeFolder}
                disabled={freeLoadingFolders}
              >
                選擇
              </button>
              <button
                type="button"
                className="scan-button"
                onClick={() => scanFreeDirectory(freeScanPath)}
                disabled={freeLoadingFolders}
              >
                {freeLoadingFolders ? "掃描中…" : "掃描"}
              </button>
            </div>

            {freeScanResult && (
              <>
                {freeScanResult.subfolders.length === 0 ? (
                  <div className="folder-warning" role="status">此路徑沒有子目錄。</div>
                ) : (
                  <div className="free-subfolder-list" role="radiogroup" aria-label="選擇子目錄">
                    {freeScanResult.subfolders.map((name) => (
                      <label key={name} className={`free-subfolder-item ${freeSelectedSubfolder === name ? "active" : ""}`}>
                        <input
                          type="radio"
                          name="free-subfolder"
                          value={name}
                          checked={freeSelectedSubfolder === name}
                          onChange={() => setFreeSelectedSubfolder(name)}
                        />
                        {name}
                      </label>
                    ))}
                  </div>
                )}
                <label className="free-date-toggle">
                  <input
                    type="checkbox"
                    checked={freeWithDate}
                    onChange={(event) => setFreeWithDate(event.target.checked)}
                  />
                  加入今日日期前綴
                </label>
                {freeSelectedSubfolder && (
                  <div className="free-subfolder-preview">
                    <span>將存入子目錄</span>
                    <code>{freeSelectedSubfolder}</code>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </fieldset>
  );
}
