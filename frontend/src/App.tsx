import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PhotoPreview from "./PhotoPreview";
import UpdatePanel from "./UpdatePanel";

type ReferenceValues = {
  buildings: string[];
  materials: string[];
  issues: string[];
  photo_roles: string[];
  custom_materials: string[];
  custom_issues: string[];
};

type PhotoDraft = {
  id: string;
  file: File;
  url: string;
  role: string;
};

type SavedPhoto = {
  id: string;
  role: string;
  stored_name: string;
  original_name: string;
  content_url: string;
};

type CaseRecord = {
  id: string;
  work_date: string;
  building: string;
  floor: string;
  address_code: string;
  material: string;
  issues: string[];
  location: string;
  notes: string;
  folder_path: string;
  photo_count: number;
  is_complete: boolean;
  missing_roles: string[];
  photos?: SavedPhoto[];
};

type CustomOptionKind = "material" | "issue";

const FALLBACK_REFERENCES: ReferenceValues = {
  buildings: ["二門診", "三門診", "思源", "致德", "身障", "長青", "立體", "臨床"],
  materials: ["底座", "探頭", "模組", "磁力門扣"],
  issues: ["錯誤設備", "無回應", "火警", "漏水", "自檢異常", "鏽蝕", "故障"],
  photo_roles: ["前", "中", "完成", "樓層", "位置", "設備標籤", "其他"],
  custom_materials: [],
  custom_issues: [],
};

function localDate(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function initialRoles(count: number): string[] {
  if (count === 1) return ["前"];
  if (count === 2) return ["前", "完成"];
  if (count === 3) return ["前", "中", "完成"];
  if (count === 4) return ["前", "中", "中", "完成"];
  if (count === 5) return ["前", "中", "中", "完成", "樓層"];
  return Array.from({ length: count }, (_, index) => {
    if (index === 0) return "前";
    if (index === count - 1) return "完成";
    return "中";
  });
}

function safeName(value: string): string {
  return value.replace(/[<>:"/\\|?*\x00-\x1f]/g, "-").replace(/\s+/g, " ").trim();
}

function roleFileNames(photos: PhotoDraft[]): string[] {
  const totals = new Map<string, number>();
  const seen = new Map<string, number>();
  photos.forEach((photo) => totals.set(photo.role, (totals.get(photo.role) ?? 0) + 1));
  return photos.map((photo, index) => {
    const current = (seen.get(photo.role) ?? 0) + 1;
    seen.set(photo.role, current);
    const suffix = totals.get(photo.role)! > 1 ? `-${String(current).padStart(2, "0")}` : "";
    const extension = photo.file.name.split(".").pop()?.toLowerCase() || "jpg";
    return `${String(index + 1).padStart(2, "0")}_${photo.role}${suffix}.${extension}`;
  });
}

function errorText(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "操作失敗，請稍後再試。";
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return "案件資料格式不正確。";
}

export default function App() {
  const [references, setReferences] = useState(FALLBACK_REFERENCES);
  const [photos, setPhotos] = useState<PhotoDraft[]>([]);
  const [selectedPhotoId, setSelectedPhotoId] = useState("");
  const [workDate, setWorkDate] = useState(localDate());
  const [building, setBuilding] = useState("二門診");
  const [floor, setFloor] = useState("");
  const [addressCode, setAddressCode] = useState("");
  const [material, setMaterial] = useState("底座");
  const [issues, setIssues] = useState<string[]>(["錯誤設備"]);
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [query, setQuery] = useState("");
  const [caseBuilding, setCaseBuilding] = useState("");
  const [caseMaterial, setCaseMaterial] = useState("");
  const [selectedCase, setSelectedCase] = useState<CaseRecord | null>(null);
  const [saving, setSaving] = useState(false);
  const [updateInstalling, setUpdateInstalling] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [storageRoot, setStorageRoot] = useState("");
  const [choosingStorage, setChoosingStorage] = useState(false);
  const [customOptionKind, setCustomOptionKind] = useState<CustomOptionKind | null>(null);
  const [customOptionValue, setCustomOptionValue] = useState("");
  const [savingCustomOption, setSavingCustomOption] = useState(false);
  const [deletingOption, setDeletingOption] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const latestPhotos = useRef<PhotoDraft[]>([]);
  const draftFields = JSON.stringify({ workDate, building, floor, addressCode, material, issues, location, notes });
  const cleanFields = useRef(draftFields);
  const stateSequence = useRef(0);

  useEffect(() => {
    window.matlensDesktopState = {
      dirty: photos.length > 0 || draftFields !== cleanFields.current,
      saving,
    };
    const sendState = () => {
      const state = window.matlensDesktopState!;
      stateSequence.current = Math.max(stateSequence.current + 1, Date.now() * 1000);
      window.pywebview?.api.update_state(stateSequence.current, state.dirty, state.saving)
        .catch(() => setError("無法同步桌面儲存狀態，請先完成儲存再關閉程式。"));
    };
    sendState();
    window.addEventListener("pywebviewready", sendState);
    return () => window.removeEventListener("pywebviewready", sendState);
  }, [photos.length, draftFields, saving]);

  useEffect(() => {
    const preventFileNavigation = (event: DragEvent) => event.preventDefault();
    document.addEventListener("dragover", preventFileNavigation);
    document.addEventListener("drop", preventFileNavigation);
    return () => {
      document.removeEventListener("dragover", preventFileNavigation);
      document.removeEventListener("drop", preventFileNavigation);
      delete window.matlensDesktopState;
    };
  }, []);

  const selectedIndex = photos.findIndex((photo) => photo.id === selectedPhotoId);
  const selectedPhoto = selectedIndex >= 0 ? photos[selectedIndex] : photos[0];
  const generatedNames = useMemo(() => roleFileNames(photos), [photos]);

  const folderPreview = useMemo(() => {
    const [year, month] = workDate.split("-");
    const issueText = issues.map(safeName).join("-");
    const folder = [workDate, building, floor, addressCode, issueText].map(safeName).join("_");
    return `${year || "年份"}\\${month || "月份"}月\\${safeName(material)}\\${folder}`;
  }, [workDate, building, floor, addressCode, material, issues]);

  const missingRoles = ["前", "中", "完成"].filter(
    (role) => !photos.some((photo) => photo.role === role),
  );

  const loadCases = useCallback(async () => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (caseBuilding) params.set("building", caseBuilding);
    if (caseMaterial) params.set("material", caseMaterial);
    try {
      const response = await fetch(`/api/cases?${params}`);
      if (!response.ok) throw new Error();
      const payload = (await response.json()) as { items: CaseRecord[] };
      setCases(payload.items);
    } catch {
      setError("無法讀取案件清單，請確認後端正在執行。");
    }
  }, [query, caseBuilding, caseMaterial]);

  useEffect(() => {
    fetch("/api/reference-values")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((payload: ReferenceValues) => setReferences((current) => ({
        buildings: [...new Set([...payload.buildings, ...current.buildings])],
        materials: [...new Set([...payload.materials, ...current.materials])],
        issues: [...new Set([...payload.issues, ...current.issues])],
        photo_roles: [...new Set([...payload.photo_roles, ...current.photo_roles])],
        custom_materials: [...new Set([...(payload.custom_materials ?? []), ...current.custom_materials])],
        custom_issues: [...new Set([...(payload.custom_issues ?? []), ...current.custom_issues])],
      })))
      .catch(() => undefined);
    fetch("/api/settings/storage")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((payload: { path: string }) => setStorageRoot(payload.path))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(loadCases, 200);
    return () => window.clearTimeout(timer);
  }, [loadCases]);

  useEffect(() => {
    latestPhotos.current = photos;
  }, [photos]);

  useEffect(() => {
    return () => latestPhotos.current.forEach((photo) => URL.revokeObjectURL(photo.url));
  }, []);

  function addFiles(fileList: FileList | File[]) {
    if (updateInstalling) return;
    setError("");
    const accepted = Array.from(fileList).filter((file) =>
      ["image/jpeg", "image/png", "image/webp"].includes(file.type),
    );
    if (!accepted.length) {
      setError("請選擇 JPG、PNG 或 WebP 圖片。");
      return;
    }
    const combinedCount = photos.length + accepted.length;
    if (combinedCount > 30) {
      setError("單一案件最多 30 張照片。");
      return;
    }
    const defaults = initialRoles(combinedCount);
    const currentDefaults = initialRoles(photos.length);
    const rolesAreAutomatic = photos.every(
      (photo, index) => photo.role === currentDefaults[index],
    );
    const additions = accepted.map((file, index) => ({
      id: crypto.randomUUID(),
      file,
      url: URL.createObjectURL(file),
      role: defaults[photos.length + index],
    }));
    setPhotos((current) => [
      ...current.map((photo, index) => (
        rolesAreAutomatic ? { ...photo, role: defaults[index] } : photo
      )),
      ...additions,
    ]);
    setSelectedPhotoId((current) => current || additions[0].id);
  }

  function removePhoto(id: string) {
    const target = photos.find((photo) => photo.id === id);
    if (target) URL.revokeObjectURL(target.url);
    const remaining = photos.filter((photo) => photo.id !== id);
    setPhotos(remaining);
    if (selectedPhotoId === id) setSelectedPhotoId(remaining[0]?.id ?? "");
  }

  function setPhotoRole(id: string, role: string) {
    setPhotos((current) => current.map((photo) => (photo.id === id ? { ...photo, role } : photo)));
  }

  function toggleIssue(issue: string) {
    setIssues((current) => {
      if (current.includes(issue)) {
        return current.length === 1 ? current : current.filter((item) => item !== issue);
      }
      return [...current, issue];
    });
  }

  function clearDraft() {
    cleanFields.current = JSON.stringify({ workDate, building, floor: "", addressCode: "", material, issues, location: "", notes: "" });
    photos.forEach((photo) => URL.revokeObjectURL(photo.url));
    setPhotos([]);
    setSelectedPhotoId("");
    setFloor("");
    setAddressCode("");
    setLocation("");
    setNotes("");
    if (fileInput.current) fileInput.current.value = "";
  }

  async function saveCase(event: React.FormEvent) {
    event.preventDefault();
    if (updateInstalling) return;
    setError("");
    setNotice("");
    if (!photos.length || !floor.trim() || !addressCode.trim()) {
      setError("請加入照片，並填寫樓層與定址碼。");
      return;
    }
    setSaving(true);
    const form = new FormData();
    form.set("work_date", workDate);
    form.set("building", building);
    form.set("floor", floor);
    form.set("address_code", addressCode);
    form.set("material", material);
    form.set("issues", JSON.stringify(issues));
    form.set("location", location);
    form.set("notes", notes);
    form.set("photo_roles", JSON.stringify(photos.map((photo) => photo.role)));
    photos.forEach((photo) => form.append("photos", photo.file, photo.file.name));
    try {
      const response = await fetch("/api/cases", { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      setNotice("案件與照片已安全儲存。");
      clearDraft();
      await loadCases();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "儲存失敗。");
    } finally {
      setSaving(false);
    }
  }

  async function viewCase(id: string) {
    setError("");
    const response = await fetch(`/api/cases/${id}`);
    if (!response.ok) {
      setError("無法開啟案件。");
      return;
    }
    setSelectedCase((await response.json()) as CaseRecord);
  }

  async function openFolder(id: string) {
    const response = await fetch(`/api/cases/${id}/open-folder`, { method: "POST" });
    if (!response.ok) setError("無法開啟案件資料夾。");
  }

  async function chooseStorageRoot() {
    setError("");
    setChoosingStorage(true);
    try {
      const response = await fetch("/api/settings/storage/pick-folder", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      setStorageRoot(String(payload.path));
      if (!payload.cancelled) setNotice("照片儲存目錄已更新。");
    } catch (storageError) {
      setError(storageError instanceof Error ? storageError.message : "無法設定儲存目錄。");
    } finally {
      setChoosingStorage(false);
    }
  }

  async function addCustomOption(kind: CustomOptionKind) {
    const value = customOptionValue.trim();
    if (!value) {
      setError("請輸入自訂選項名稱。");
      return;
    }
    setError("");
    setSavingCustomOption(true);
    try {
      const response = await fetch(`/api/reference-values/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      const savedValue = String(payload.value);
      setReferences((current) => ({
        ...current,
        materials: kind === "material"
          ? [...new Set([...current.materials, savedValue])]
          : current.materials,
        issues: kind === "issue"
          ? [...new Set([...current.issues, savedValue])]
          : current.issues,
        custom_materials: kind === "material"
          ? [...new Set([...current.custom_materials, savedValue])]
          : current.custom_materials,
        custom_issues: kind === "issue"
          ? [...new Set([...current.custom_issues, savedValue])]
          : current.custom_issues,
      }));
      if (kind === "material") {
        setMaterial(savedValue);
      } else {
        setIssues((current) => [...new Set([...current, savedValue])]);
      }
      setCustomOptionKind(null);
      setCustomOptionValue("");
      setNotice(`${kind === "material" ? "材料" : "問題"}選項已新增。`);
    } catch (optionError) {
      setError(optionError instanceof Error ? optionError.message : "新增選項失敗。");
    } finally {
      setSavingCustomOption(false);
    }
  }

  function startCustomOption(kind: CustomOptionKind) {
    setCustomOptionKind(kind);
    setCustomOptionValue("");
    setError("");
  }

  async function deleteCustomOption(kind: CustomOptionKind, value: string) {
    const label = kind === "material" ? "材料" : "問題";
    if (!window.confirm(`確定刪除自訂${label}「${value}」？\n已儲存案件不受影響。`)) return;
    setError("");
    setDeletingOption(`${kind}:${value}`);
    try {
      const response = await fetch(`/api/reference-values/${kind}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      setReferences((current) => ({
        ...current,
        materials: kind === "material" ? current.materials.filter((item) => item !== value) : current.materials,
        issues: kind === "issue" ? current.issues.filter((item) => item !== value) : current.issues,
        custom_materials: kind === "material" ? current.custom_materials.filter((item) => item !== value) : current.custom_materials,
        custom_issues: kind === "issue" ? current.custom_issues.filter((item) => item !== value) : current.custom_issues,
      }));
      if (kind === "material" && material === value) {
        setMaterial(references.materials.find((item) => item !== value) ?? "");
      }
      if (kind === "issue") {
        setIssues((current) => {
          const remaining = current.filter((item) => item !== value);
          return remaining.length ? remaining : [references.issues.find((item) => item !== value) ?? ""];
        });
      }
      setNotice(`自訂${label}「${value}」已刪除。`);
    } catch (optionError) {
      setError(optionError instanceof Error ? optionError.message : "刪除選項失敗。");
    } finally {
      setDeletingOption("");
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar" inert={updateInstalling}>
        <div className="brand-block">
          <div className="brand-mark">ML</div>
          <div>
            <h1>MatLens</h1>
            <p>消防材料更換照片管理</p>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="local-badge">本機離線儲存</span>
          <button className="button secondary" type="button" onClick={() => fileInput.current?.click()}>
            ＋ 匯入照片
          </button>
          <button className="button primary" type="submit" form="case-form" disabled={saving}>
            {saving ? "儲存中…" : "儲存案件"}
          </button>
        </div>
      </header>

      <UpdatePanel onInstalling={setUpdateInstalling} />

      <div className="storage-bar" inert={updateInstalling}>
        <span>照片儲存目錄</span>
        <code title={storageRoot}>{storageRoot || "讀取中…"}</code>
        <button type="button" onClick={chooseStorageRoot} disabled={choosingStorage}>
          {choosingStorage ? "等待選擇…" : "選擇目錄"}
        </button>
      </div>

      {(error || notice) && (
        <div className={`message ${error ? "error" : "success"}`} role={error ? "alert" : "status"}>
          <span>{error || notice}</span>
          <button type="button" aria-label="關閉訊息" onClick={() => { setError(""); setNotice(""); }}>×</button>
        </div>
      )}

      <main inert={updateInstalling}>
        <form id="case-form" className="workspace" onSubmit={saveCase}>
          <section
            className={`photo-rail ${dragging ? "dragging" : ""}`}
            aria-label="本次照片"
            onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setDragging(false);
              }
            }}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              addFiles(event.dataTransfer.files);
            }}
          >
            <div className="section-heading">
              <div><span className="eyebrow">STEP 1</span><h2>本次照片</h2></div>
              <span className="count-label">{photos.length} 張</span>
            </div>
            {!photos.length ? (
              <button
                className={`drop-zone ${dragging ? "dragging" : ""}`}
                type="button"
                onClick={() => fileInput.current?.click()}
              >
                <span className="drop-icon">＋</span>
                <strong>拉入 3～5 張照片</strong>
                <small>或點此選擇 JPG、PNG、WebP</small>
              </button>
            ) : (
              <div className="thumbnail-list">
                {photos.map((photo, index) => (
                  <div className={`thumbnail-item ${photo.id === selectedPhoto?.id ? "selected" : ""}`} key={photo.id}>
                    <button type="button" className="thumbnail-button" onClick={() => setSelectedPhotoId(photo.id)}>
                      <img src={photo.url} alt={`${photo.role}：${photo.file.name}`} />
                      <span className="thumbnail-copy"><strong>{photo.role}</strong><small>{photo.file.name}</small></span>
                    </button>
                    <button type="button" className="remove-photo" aria-label={`移除 ${photo.file.name}`} onClick={() => removePhoto(photo.id)}>×</button>
                    <span className="photo-number">{String(index + 1).padStart(2, "0")}</span>
                  </div>
                ))}
                <button className="add-more" type="button" onClick={() => fileInput.current?.click()}>＋ 加入照片</button>
              </div>
            )}
            <input
              ref={fileInput}
              className="sr-only"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              onChange={(event) => event.target.files && addFiles(event.target.files)}
            />
          </section>

          <section className="preview-panel">
            <div className="section-heading">
              <div><span className="eyebrow">STEP 2</span><h2>照片預覽與命名</h2></div>
              {selectedPhoto && <span className="role-label">{selectedPhoto.role}</span>}
            </div>
            {selectedPhoto ? (
              <PhotoPreview key={selectedPhoto.id} src={selectedPhoto.url} alt={selectedPhoto.file.name} />
            ) : (
              <div className="image-stage">
                <div className="empty-preview"><span>尚未匯入照片</span><small>照片會在這裡放大預覽</small></div>
              </div>
            )}
            {selectedPhoto && (
              <div className="role-editor">
                <label htmlFor="photo-role">這張照片是</label>
                <select id="photo-role" value={selectedPhoto.role} onChange={(event) => setPhotoRole(selectedPhoto.id, event.target.value)}>
                  {references.photo_roles.map((role) => <option key={role}>{role}</option>)}
                </select>
                <div className="generated-name"><span>儲存檔名</span><strong>{generatedNames[selectedIndex]}</strong></div>
              </div>
            )}
            <div className="path-preview">
              <span>案件資料夾</span>
              <code>{folderPreview}</code>
              {storageRoot && <small>{storageRoot}\\{folderPreview}</small>}
            </div>
          </section>

          <section className="case-editor">
            <div className="section-heading">
              <div><span className="eyebrow">STEP 3</span><h2>案件資料</h2></div>
              <span className="autosave-label">常用選項</span>
            </div>
            <div className="field-grid">
              <label><span>維修日期</span><input type="date" value={workDate} onChange={(event) => setWorkDate(event.target.value)} required /></label>
              <label><span>樓層</span><input value={floor} onChange={(event) => setFloor(event.target.value)} placeholder="例如 3F、B2" required /></label>
              <label><span>棟別</span><input list="buildings" value={building} onChange={(event) => setBuilding(event.target.value)} required /></label>
              <label><span>定址碼</span><input value={addressCode} onChange={(event) => setAddressCode(event.target.value)} placeholder="例如 M3-07" required /></label>
              <datalist id="buildings">{references.buildings.map((item) => <option key={item} value={item} />)}</datalist>
              <label className="wide"><span>補充位置</span><input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="例如車位 472 號、走廊東側" /></label>
            </div>

            <fieldset>
              <legend className="option-legend">
                <span>材料</span>
                <button type="button" aria-label="新增材料選項" onClick={() => startCustomOption("material")}>＋ 新增</button>
              </legend>
              <div className="choices single-choice">
                {references.materials.map((item) => {
                  const isCustom = references.custom_materials.includes(item);
                  return (
                    <span key={item} className={`choice-option ${material === item ? "active" : ""}`}>
                      <button type="button" className="choice-value" aria-pressed={material === item} onClick={() => setMaterial(item)}>{item}</button>
                      {isCustom && (
                        <button
                          type="button"
                          className="choice-delete"
                          aria-label={`刪除材料選項 ${item}`}
                          disabled={deletingOption === `material:${item}`}
                          onClick={() => deleteCustomOption("material", item)}
                        >×</button>
                      )}
                    </span>
                  );
                })}
              </div>
              {customOptionKind === "material" && (
                <div className="custom-option-editor">
                  <input
                    aria-label="自訂材料名稱"
                    autoFocus
                    maxLength={40}
                    value={customOptionValue}
                    onChange={(event) => setCustomOptionValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void addCustomOption("material");
                      }
                    }}
                    placeholder="輸入材料名稱"
                  />
                  <button type="button" className="confirm" disabled={savingCustomOption} onClick={() => addCustomOption("material")}>加入材料</button>
                  <button type="button" onClick={() => setCustomOptionKind(null)}>取消</button>
                </div>
              )}
            </fieldset>

            <fieldset>
              <legend className="option-legend">
                <span>問題（可複選）</span>
                <button type="button" aria-label="新增問題選項" onClick={() => startCustomOption("issue")}>＋ 新增</button>
              </legend>
              <div className="choices">
                {references.issues.map((item) => {
                  const isCustom = references.custom_issues.includes(item);
                  return (
                    <span key={item} className={`choice-option ${issues.includes(item) ? "active" : ""}`}>
                      <button type="button" className="choice-value" aria-pressed={issues.includes(item)} onClick={() => toggleIssue(item)}>{item}</button>
                      {isCustom && (
                        <button
                          type="button"
                          className="choice-delete"
                          aria-label={`刪除問題選項 ${item}`}
                          disabled={deletingOption === `issue:${item}`}
                          onClick={() => deleteCustomOption("issue", item)}
                        >×</button>
                      )}
                    </span>
                  );
                })}
              </div>
              {customOptionKind === "issue" && (
                <div className="custom-option-editor">
                  <input
                    aria-label="自訂問題名稱"
                    autoFocus
                    maxLength={40}
                    value={customOptionValue}
                    onChange={(event) => setCustomOptionValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void addCustomOption("issue");
                      }
                    }}
                    placeholder="輸入問題名稱"
                  />
                  <button type="button" className="confirm" disabled={savingCustomOption} onClick={() => addCustomOption("issue")}>加入問題</button>
                  <button type="button" onClick={() => setCustomOptionKind(null)}>取消</button>
                </div>
              )}
            </fieldset>

            <label className="notes-field"><span>備註</span><textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="可記錄漏水原因、缺照原因或其他說明" /></label>

            <div className={`completeness ${missingRoles.length ? "warning" : "ready"}`}>
              <strong>{missingRoles.length ? `缺少：${missingRoles.join("、")}` : "前／中／完成照片齊全"}</strong>
              <span>{photos.length >= 3 && photos.length <= 5 ? "符合建議的 3～5 張照片" : "一般案件建議使用 3～5 張照片"}</span>
            </div>
          </section>
        </form>

        <section className="case-list-section">
          <div className="list-header">
            <div><span className="eyebrow">ARCHIVE</span><h2>案件清單</h2><p>依棟別、定址碼、材料或問題快速尋找</p></div>
            <div className="list-filters">
              <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜尋定址碼或問題…" aria-label="搜尋案件" />
              <select value={caseBuilding} onChange={(event) => setCaseBuilding(event.target.value)} aria-label="依棟別篩選"><option value="">全部棟別</option>{references.buildings.map((item) => <option key={item}>{item}</option>)}</select>
              <select value={caseMaterial} onChange={(event) => setCaseMaterial(event.target.value)} aria-label="依材料篩選"><option value="">全部材料</option>{references.materials.map((item) => <option key={item}>{item}</option>)}</select>
            </div>
          </div>
          <div className="case-table-wrap">
            <table className="case-table">
              <thead><tr><th>日期</th><th>位置</th><th>定址碼</th><th>材料／問題</th><th>照片</th><th>狀態</th><th><span className="sr-only">操作</span></th></tr></thead>
              <tbody>
                {!cases.length ? (
                  <tr><td colSpan={7} className="empty-row">尚無案件。儲存第一筆後會顯示在這裡。</td></tr>
                ) : cases.map((item) => (
                  <tr key={item.id}>
                    <td>{item.work_date}</td><td><strong>{item.building}</strong> {item.floor}</td><td><code>{item.address_code}</code></td>
                    <td><strong>{item.material}</strong><span className="issue-summary">{item.issues.join("／")}</span></td><td>{item.photo_count} 張</td>
                    <td><span className={`status ${item.is_complete ? "complete" : "incomplete"}`}>{item.is_complete ? "完整" : `缺 ${item.missing_roles.join("、")}`}</span></td>
                    <td className="row-actions"><button type="button" onClick={() => viewCase(item.id)}>檢視</button><button type="button" onClick={() => openFolder(item.id)}>開啟資料夾</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {selectedCase && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setSelectedCase(null); }}>
          <section className="case-modal" role="dialog" aria-modal="true" aria-labelledby="case-title">
            <header><div><span className="eyebrow">案件照片</span><h2 id="case-title">{selectedCase.building} {selectedCase.floor} · {selectedCase.address_code}</h2><p>{selectedCase.work_date}　{selectedCase.material}　{selectedCase.issues.join("／")}</p></div><button type="button" aria-label="關閉案件" onClick={() => setSelectedCase(null)}>×</button></header>
            <div className="saved-photo-grid">
              {selectedCase.photos?.map((photo) => <figure key={photo.id}><img src={photo.content_url} alt={`${photo.role} ${photo.original_name}`} /><figcaption><strong>{photo.role}</strong><span>{photo.stored_name}</span></figcaption></figure>)}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
