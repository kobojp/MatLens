import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CaseListSection from "./CaseListSection";
import CaseModal from "./CaseModal";
import OptionField from "./OptionField";
import OverviewModal from "./OverviewModal";
import PhotoPreview from "./PhotoPreview";
import StorageDestination from "./StorageDestination";
import UpdatePanel from "./UpdatePanel";
import type {
  CaseRecord,
  CustomOptionKind,
  FreeScanResult,
  PhotoDraft,
  ReferenceValues,
  StorageMode,
  StorageTree,
} from "./types";
import { FALLBACK_REFERENCES, errorText, initialRoles, localDate, roleFileNames, safeName } from "./utils";

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
  const [casePage, setCasePage] = useState(1);
  const [caseTotal, setCaseTotal] = useState(0);
  const [casePages, setCasePages] = useState(1);
  const [scanningCases, setScanningCases] = useState(false);
  const [overviewView, setOverviewView] = useState<"gallery" | "names" | null>(null);
  const [selectedCase, setSelectedCase] = useState<CaseRecord | null>(null);
  const [saving, setSaving] = useState(false);
  const [updateInstalling, setUpdateInstalling] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [storageRoot, setStorageRoot] = useState("");
  const [choosingStorage, setChoosingStorage] = useState(false);
  const [storageTree, setStorageTree] = useState<StorageTree | null>(null);
  const [selectedMonth, setSelectedMonth] = useState("");
  const [selectedSubfolder, setSelectedSubfolder] = useState("");
  const [loadingFolders, setLoadingFolders] = useState(false);
  const [creatingFolders, setCreatingFolders] = useState(false);
  const [showFolderCreator, setShowFolderCreator] = useState(false);
  const [folderPresets, setFolderPresets] = useState<string[]>(["底座", "探頭"]);
  const [customFolderName, setCustomFolderName] = useState("");
  const [storageMode, setStorageMode] = useState<StorageMode>("month");
  const [freeScanPath, setFreeScanPath] = useState("");
  const [freeScanResult, setFreeScanResult] = useState<FreeScanResult | null>(null);
  const [freeSelectedSubfolder, setFreeSelectedSubfolder] = useState("");
  const [freeLoadingFolders, setFreeLoadingFolders] = useState(false);
  const [freeWithDate, setFreeWithDate] = useState(true);
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
    const issueText = issues.map(safeName).join("-");
    // 棟別與樓層連寫（二門診1F），其餘欄位以空白分隔
    const buildingFloor = `${safeName(building)}${safeName(floor)}`;
    if (storageMode === "free") {
      const subfolder = freeSelectedSubfolder || "請選子目錄";
      // 日期受 freeWithDate 控制，放在案件資料夾名稱中
      const caseParts = freeWithDate
        ? [workDate, buildingFloor, addressCode, issueText]
        : [buildingFloor, addressCode, issueText];
      const caseFolder = caseParts.map(safeName).join(" ");
      return `${subfolder}\\${caseFolder}`;
    }
    // 月份模式：日期永遠在案件資料夾名稱，空白分隔
    const caseFolder = [workDate, buildingFloor, addressCode, issueText].map(safeName).join(" ");
    return `${selectedMonth || "請選月份"}\\${selectedSubfolder || "請選子目錄"}\\${caseFolder}`;
  }, [workDate, building, floor, addressCode, issues, selectedMonth, selectedSubfolder, storageMode, freeSelectedSubfolder, freeWithDate]);


  const destinationSubfolder = storageMode === "free" ? freeSelectedSubfolder : selectedSubfolder;
  const overviewDefaultMaterial = references.materials.includes(destinationSubfolder)
    ? destinationSubfolder
    : material;

  const selectedMonthEntry = storageTree?.months.find((item) => item.name === selectedMonth);

  const missingRoles = ["前", "中"].filter(
    (role) => !photos.some((photo) => photo.role === role),
  );
  if (!photos.some((photo) => photo.role === "後" || photo.role === "完成")) {
    missingRoles.push("後／完成");
  }

  const loadCases = useCallback(async () => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (caseBuilding) params.set("building", caseBuilding);
    if (caseMaterial) params.set("material", caseMaterial);
    params.set("page", String(casePage));
    params.set("page_size", "20");
    try {
      const response = await fetch(`/api/cases?${params}`);
      if (!response.ok) throw new Error();
      const payload = (await response.json()) as {
        items: CaseRecord[];
        total: number;
        pages: number;
      };
      setCases(payload.items);
      setCaseTotal(payload.total);
      setCasePages(payload.pages);
      if (casePage > payload.pages) setCasePage(payload.pages);
    } catch {
      setError("無法讀取案件清單，請確認後端正在執行。");
    }
  }, [query, caseBuilding, caseMaterial, casePage]);

  const loadStorageTree = useCallback(async (
    date: string,
    preferredMonth = "",
    preferredSubfolder = "",
    preferredMaterial = "",
  ) => {
    setLoadingFolders(true);
    try {
      const response = await fetch(`/api/settings/storage/tree?work_date=${encodeURIComponent(date)}`);
      const payload = (await response.json()) as StorageTree;
      if (!response.ok) throw new Error(errorText(payload));
      setStorageTree(payload);
      const monthName = preferredMonth || payload.target_month;
      const month = payload.months.find((item) => item.name === monthName);
      const subfolder = month?.subfolders.includes(preferredSubfolder)
        ? preferredSubfolder
        : month?.subfolders.includes(preferredMaterial)
          ? preferredMaterial
          : month?.subfolders[0] ?? "";
      setSelectedMonth(monthName);
      setSelectedSubfolder(subfolder);
      setShowFolderCreator(!month || !month.subfolders.length);
    } catch (treeError) {
      setStorageTree(null);
      setSelectedMonth("");
      setSelectedSubfolder("");
      setError(treeError instanceof Error ? treeError.message : "無法掃描儲存目錄。");
    } finally {
      setLoadingFolders(false);
    }
  }, []);

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
    fetch("/api/settings/free-scan-path")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((payload: { path: string }) => { if (payload.path) setFreeScanPath(payload.path); })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (storageRoot) void loadStorageTree(workDate, "", "", material);
  }, [storageRoot, workDate, loadStorageTree]);

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
    if (storageMode === "month") {
      if (!selectedMonthEntry || !selectedSubfolder) {
        setError("請先選擇已存在的月份資料夾與子目錄。");
        return;
      }
    } else {
      if (!freeScanResult || !freeSelectedSubfolder) {
        setError("請先掃描目錄並選擇子目錄。");
        return;
      }
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
    if (storageMode === "month") {
      form.set("storage_month", selectedMonth);
      form.set("storage_subfolder", selectedSubfolder);
      form.set("free_scan_root", "");
      form.set("free_with_date", "true");
    } else {
      // 自由路徑模式：子目錄原名不動，日期前綴由後端加到案件資料夾名稱
      form.set("storage_month", "");
      form.set("storage_subfolder", freeSelectedSubfolder);
      form.set("free_scan_root", freeScanResult!.root);
      form.set("free_with_date", freeWithDate ? "true" : "false");
    }
    photos.forEach((photo) => form.append("photos", photo.file, photo.file.name));
    try {
      const response = await fetch("/api/cases", { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      setNotice("案件與照片已安全儲存。");
      clearDraft();
      if (casePage === 1) {
        await loadCases();
      } else {
        setCasePage(1);
      }
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

  function currentScanPath(): string {
    if (storageMode !== "free") return storageRoot;
    let scanPath = freeScanResult?.root || freeScanPath.trim();
    if (freeScanResult && freeSelectedSubfolder) {
      const separator = scanPath.includes("\\") ? "\\" : "/";
      scanPath = `${scanPath.replace(/[\\/]$/, "")}${separator}${freeSelectedSubfolder}`;
    }
    return scanPath;
  }

  async function rescanCases() {
    const scanPath = currentScanPath();
    if (!scanPath) {
      setError("請先選擇要掃描的照片根目錄。");
      return;
    }
    setError("");
    setNotice("");
    setScanningCases(true);
    try {
      const response = await fetch(`/api/cases/rescan?path=${encodeURIComponent(scanPath)}`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      const relinked = Number(payload.relinked ?? 0);
      const imported = Number(payload.imported ?? 0);
      const removed = Number(payload.removed ?? 0);
      const pending = Number(payload.unresolved ?? 0) + Number(payload.ambiguous ?? 0) + Number(payload.skipped ?? 0);
      if (relinked || imported || removed) {
        const changes = [
          relinked ? `重新連結 ${relinked} 筆案件` : "",
          imported ? `新增 ${imported} 筆案件` : "",
          removed ? `清除 ${removed} 筆失效紀錄` : "",
        ].filter(Boolean).join("、");
        setNotice(`掃描完成，已${changes}${pending ? `，另有 ${pending} 筆無法自動確認` : ""}。`);
      } else if (pending) {
        setNotice(`掃描完成，有 ${pending} 筆失效路徑找不到唯一符合的資料夾。`);
      } else {
        setNotice("掃描完成，案件路徑皆為最新狀態。");
      }
      await loadCases();
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : "無法掃描案件資料夾。");
    } finally {
      setScanningCases(false);
    }
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

  function chooseMonth(monthName: string) {
    const month = storageTree?.months.find((item) => item.name === monthName);
    setSelectedMonth(monthName);
    setSelectedSubfolder(
      month?.subfolders.includes(material) ? material : month?.subfolders[0] ?? "",
    );
    setShowFolderCreator(!month || !month.subfolders.length);
  }

  async function scanFreeDirectory(path: string) {
    const trimmed = path.trim();
    if (!trimmed) { setError("請輸入或選擇要掃描的路徑。"); return; }
    setError("");
    setFreeLoadingFolders(true);
    setFreeScanResult(null);
    setFreeSelectedSubfolder("");
    try {
      const response = await fetch(`/api/settings/storage/scan?path=${encodeURIComponent(trimmed)}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      const result = payload as FreeScanResult;
      setFreeScanResult(result);
      setFreeSelectedSubfolder(result.subfolders[0] ?? "");
      // 掃描成功後靜默儲存路徑
      fetch("/api/settings/free-scan-path", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: trimmed }),
      }).catch(() => undefined);
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : "無法掃描目錄。");
    } finally {
      setFreeLoadingFolders(false);
    }
  }


  async function chooseFreeFolder() {
    setError("");
    setFreeLoadingFolders(true);
    try {
      const response = await fetch("/api/settings/storage/pick-folder", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      if (!payload.cancelled) {
        const selectedPath = String(payload.path);
        setFreeScanPath(selectedPath);
        await scanFreeDirectory(selectedPath);
      }
    } catch (pickError) {
      setError(pickError instanceof Error ? pickError.message : "無法開啟資料夾選擇器。");
    } finally {
      setFreeLoadingFolders(false);
    }
  }


  function toggleFolderPreset(name: string) {
    setFolderPresets((current) => (
      current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name]
    ));
  }

  async function createFolders() {
    const customName = customFolderName.trim();
    const subfolders = [...new Set([...folderPresets, ...(customName ? [customName] : [])])];
    if (!selectedMonth || !subfolders.length) {
      setError("請至少選擇或輸入一個子目錄名稱。");
      return;
    }
    setError("");
    setCreatingFolders(true);
    try {
      const response = await fetch("/api/settings/storage/folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ month: selectedMonth, subfolders }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      const preferred = customName || (subfolders.includes(material) ? material : subfolders[0]);
      setCustomFolderName("");
      setShowFolderCreator(false);
      await loadStorageTree(workDate, selectedMonth, preferred, material);
      setNotice(`${selectedMonth}及子目錄已準備完成。`);
    } catch (folderError) {
      setError(folderError instanceof Error ? folderError.message : "無法建立資料夾。");
    } finally {
      setCreatingFolders(false);
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
        setIssues([savedValue]);
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
        setIssues((current) => (
          current[0] === value
            ? [references.issues.find((item) => item !== value) ?? ""]
            : current.filter((item) => item !== value)
        ));
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
            <StorageDestination
              storageMode={storageMode}
              setStorageMode={setStorageMode}
              storageTree={storageTree}
              selectedMonth={selectedMonth}
              selectedMonthEntry={selectedMonthEntry}
              selectedSubfolder={selectedSubfolder}
              setSelectedSubfolder={setSelectedSubfolder}
              chooseMonth={chooseMonth}
              loadingFolders={loadingFolders}
              loadStorageTree={loadStorageTree}
              workDate={workDate}
              material={material}
              materials={references.materials}
              showFolderCreator={showFolderCreator}
              setShowFolderCreator={setShowFolderCreator}
              folderPresets={folderPresets}
              toggleFolderPreset={toggleFolderPreset}
              customFolderName={customFolderName}
              setCustomFolderName={setCustomFolderName}
              creatingFolders={creatingFolders}
              createFolders={createFolders}
              freeScanPath={freeScanPath}
              setFreeScanPath={setFreeScanPath}
              scanFreeDirectory={scanFreeDirectory}
              freeLoadingFolders={freeLoadingFolders}
              chooseFreeFolder={chooseFreeFolder}
              freeScanResult={freeScanResult}
              freeSelectedSubfolder={freeSelectedSubfolder}
              setFreeSelectedSubfolder={setFreeSelectedSubfolder}
              freeWithDate={freeWithDate}
              setFreeWithDate={setFreeWithDate}
            />

            <div className="field-grid">
              <label><span>維修日期</span><input type="date" value={workDate} onChange={(event) => setWorkDate(event.target.value)} required /></label>
              <label><span>樓層</span><input value={floor} onChange={(event) => setFloor(event.target.value)} placeholder="例如 3F、B2" required /></label>
              <label><span>棟別</span><input list="buildings" value={building} onChange={(event) => setBuilding(event.target.value)} required /></label>
              <label><span>定址碼</span><input value={addressCode} onChange={(event) => setAddressCode(event.target.value)} placeholder="例如 M3-07" required /></label>
              <datalist id="buildings">{references.buildings.map((item) => <option key={item} value={item} />)}</datalist>
              <label className="wide"><span>補充位置</span><input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="例如車位 472 號、走廊東側" /></label>
            </div>

            <OptionField
              kind="material"
              noun="材料"
              legend="材料"
              single
              items={references.materials}
              customItems={references.custom_materials}
              isActive={(item) => material === item}
              onSelect={setMaterial}
              deletingOption={deletingOption}
              editing={customOptionKind === "material"}
              editorValue={customOptionValue}
              saving={savingCustomOption}
              onStartAdd={() => startCustomOption("material")}
              onEditorChange={setCustomOptionValue}
              onAdd={() => addCustomOption("material")}
              onCancel={() => setCustomOptionKind(null)}
              onDelete={(item) => deleteCustomOption("material", item)}
            />

            <OptionField
              kind="issue"
              noun="問題"
              legend="問題"
              single
              items={references.issues}
              customItems={references.custom_issues}
              isActive={(item) => issues[0] === item}
              onSelect={(item) => setIssues([item])}
              deletingOption={deletingOption}
              editing={customOptionKind === "issue"}
              editorValue={customOptionValue}
              saving={savingCustomOption}
              onStartAdd={() => startCustomOption("issue")}
              onEditorChange={setCustomOptionValue}
              onAdd={() => addCustomOption("issue")}
              onCancel={() => setCustomOptionKind(null)}
              onDelete={(item) => deleteCustomOption("issue", item)}
            />


            {issues[0] === "火警" && (
              <fieldset>
                <legend className="option-legend"><span>火警細項（單選，可不選）</span></legend>
                <div className="choices single-choice">
                  {references.issues.filter((item) => item !== "火警").map((item) => {
                    const active = issues[1] === item;
                    return (
                      <span key={item} className={`choice-option ${active ? "active" : ""}`}>
                        <button
                          type="button"
                          className="choice-value"
                          aria-pressed={active}
                          aria-label={`火警細項 ${item}`}
                          onClick={() => setIssues(active ? ["火警"] : ["火警", item])}
                        >{item}</button>
                      </span>
                    );
                  })}
                </div>
              </fieldset>
            )}

            <label className="notes-field"><span>備註</span><textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="可記錄漏水原因、缺照原因或其他說明" /></label>

            <div className={`completeness ${missingRoles.length ? "warning" : "ready"}`}>
              <strong>{missingRoles.length ? `缺少：${missingRoles.join("、")}` : "前／中／後（或完成）照片齊全"}</strong>
              <span>{photos.length >= 3 && photos.length <= 5 ? "符合建議的 3～5 張照片" : "一般案件建議使用 3～5 張照片"}</span>
            </div>
          </section>
        </form>

        <CaseListSection
          cases={cases}
          buildings={references.buildings}
          materials={references.materials}
          query={query}
          caseBuilding={caseBuilding}
          caseMaterial={caseMaterial}
          casePage={casePage}
          casePages={casePages}
          caseTotal={caseTotal}
          scanning={scanningCases}
          onQueryChange={(value) => { setQuery(value); setCasePage(1); }}
          onBuildingChange={(value) => { setCaseBuilding(value); setCasePage(1); }}
          onMaterialChange={(value) => { setCaseMaterial(value); setCasePage(1); }}
          onPageChange={setCasePage}
          onRescan={rescanCases}
          onOpenOverview={setOverviewView}
          onView={viewCase}
          onOpenFolder={openFolder}
        />
      </main>

      {overviewView && (
        <OverviewModal
          buildings={references.buildings}
          materials={references.materials}
          defaultMaterial={overviewDefaultMaterial}
          scanPath={currentScanPath()}
          initialView={overviewView}
          onClose={() => setOverviewView(null)}
        />
      )}

      {selectedCase && <CaseModal selectedCase={selectedCase} onClose={() => setSelectedCase(null)} />}
    </div>
  );
}
