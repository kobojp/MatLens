import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CaseListSection from "./CaseListSection";
import CaseModal from "./CaseModal";
import EditConfirmation from "./EditConfirmation";
import type { EditPreview } from "./EditConfirmation";
import useFireNaming from "./useFireNaming";
import OptionField from "./OptionField";
import OverviewModal from "./OverviewModal";
import RoleOrderEditor from "./RoleOrderEditor";
import PhotoPreview from "./PhotoPreview";
import PhotoLightbox from "./PhotoLightbox";
import UISettings from "./UISettings";
import useUIPreferences from "./useUIPreferences";
import StorageDestination from "./StorageDestination";
import UpdatePanel from "./UpdatePanel";
import useStorageSelection from "./useStorageSelection";
import useClipboardImages from "./useClipboardImages";
import PasteConfirmation from "./PasteConfirmation";
import type {
  CaseRecord,
  EditableCase,
  CustomOptionKind,
  PhotoDraft,
  ReferenceValues,
} from "./types";
import {
  DEFAULT_ROLE_ORDER,
  FALLBACK_REFERENCES,
  errorText,
  initialRoles,
  localDate,
  moveItem,
  roleFileNames,
  safeName,
  photoName,
  photoSignature,
  releasePhotos,
} from "./utils";

export default function App() {
  const [editing, setEditing] = useState<EditableCase | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editConfirmation, setEditConfirmation] = useState<EditPreview | null>(null);
  const confirmationResolve = useRef<((confirmed: boolean) => void) | null>(null);
  const saveButton = useRef<HTMLButtonElement>(null);
  const [applyNewNaming, setApplyNewNaming] = useState(false);
  const [editNaming, setEditNaming] = useState({ include_date: true, include_material: true });
  const editRequest = useRef(0);
  const cleanPhotoSignature = useRef("");
  const newDraft = useRef<null | { fields: string; clean: string; photos: PhotoDraft[];
    selected: string; sequence: boolean }>(null);
  const fireNaming = useFireNaming();
  const optionGeneration = useRef(0);
  const issuesNow = useRef<string[]>([]);
  const [databasePath, setDatabasePath] = useState("");
  const [references, setReferences] = useState(FALLBACK_REFERENCES);
  const [photos, setPhotos] = useState<PhotoDraft[]>([]);
  const [selectedPhotoId, setSelectedPhotoId] = useState("");
  const [workDate, setWorkDate] = useState(localDate());
  const [building, setBuilding] = useState("二門診");
  const [floor, setFloor] = useState("");
  const [addressCode, setAddressCode] = useState("");
  const [material, setMaterial] = useState("底座");
  const [issues, setIssues] = useState<string[]>(["錯誤設備"]);
  issuesNow.current = issues;
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
  const [nameWithSequence, setNameWithSequence] = useState(false);
  const [roleOrder, setRoleOrder] = useState<string[]>(DEFAULT_ROLE_ORDER);
  const [draggedPhotoId, setDraggedPhotoId] = useState("");
  const [dragOverPhotoId, setDragOverPhotoId] = useState("");
  const draggedPhoto = useRef("");
  const [overviewView, setOverviewView] = useState<"gallery" | "names" | null>(null);
  const [selectedCase, setSelectedCase] = useState<CaseRecord | null>(null);
  const [saving, setSaving] = useState(false);
  const [updateInstalling, setUpdateInstalling] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [page, setPage] = useState<"workspace" | "settings">("workspace");
  const [viewerId, setViewerId] = useState("");
  const ui = useUIPreferences();
  const tiles = ui.value.layout === "tiles";
  const topPanel = tiles && ui.value.panel_position === "top";
  const collapsed = topPanel && ui.value.panel_collapsed;
  const clipboard = useClipboardImages(photos.length,
    updateInstalling || saving || page !== "workspace" || !!viewerId || editLoading, setError);
  const modalOpen = !!viewerId || clipboard.pending.length > 0 || !!editConfirmation;
  const ignorePhotoClick = useRef(false);
  const expandingPanel = useRef(false);
  const [dragging, setDragging] = useState(false);
  const storage = useStorageSelection();
  const storageRoot = storage.result?.root || "";
  const freeSelectedSubfolder = storage.valid ? storage.selection.subfolder : "";
  const freeWithDate = storage.selection.with_date;
  const settingsSaving = storage.saveStatus === "儲存中…" || ui.saving;
  const [customOptionKind, setCustomOptionKind] = useState<CustomOptionKind | null>(null);
  const [customOptionValue, setCustomOptionValue] = useState("");
  const [savingCustomOption, setSavingCustomOption] = useState(false);
  const [deletingOption, setDeletingOption] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const header = useRef<HTMLElement>(null);
  const latestPhotos = useRef<PhotoDraft[]>([]);
  const draftFields = JSON.stringify({ workDate, building, floor, addressCode, material, issues, location, notes });
  const cleanFields = useRef(draftFields);
  const stateSequence = useRef(0);
  const currentPhotoSignature = photoSignature(photos, nameWithSequence);
  const backgroundDirty = !!newDraft.current && (newDraft.current.photos.length > 0 || newDraft.current.fields !== newDraft.current.clean);
  const contentDirty = draftFields !== cleanFields.current || (editing
    ? currentPhotoSignature !== cleanPhotoSignature.current || applyNewNaming
    : photos.length > 0);


  useEffect(() => {
    const element = header.current;
    if (!element) return;
    const resize = () => element.parentElement?.style.setProperty("--topbar-height", `${element.offsetHeight || 74}px`);
    resize();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    observer?.observe(element);
    return () => observer?.disconnect();
  }, []);

  useEffect(() => {
    window.matlensDesktopState = {
      dirty: contentDirty || backgroundDirty || storage.saveStatus.startsWith("儲存失敗") || ui.failed || fireNaming.failed,
      saving: saving || settingsSaving || fireNaming.saving || editLoading || savingCustomOption || !!deletingOption,
    };
    const sendState = () => {
      const state = window.matlensDesktopState!;
      stateSequence.current = Math.max(stateSequence.current + 1, Date.now() * 1000);
      window.pywebview?.api.update_state?.(stateSequence.current, state.dirty, state.saving)
        .catch(() => setError("無法同步桌面儲存狀態，請先完成儲存再關閉程式。"));
    };
    sendState();
    window.addEventListener("pywebviewready", sendState);
    return () => window.removeEventListener("pywebviewready", sendState);
  }, [contentDirty, backgroundDirty, saving, settingsSaving, storage.saveStatus, ui.failed, fireNaming.failed, fireNaming.saving, editLoading, savingCustomOption, deletingOption]);

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
  const generatedNames = useMemo(
    () => editing && currentPhotoSignature === cleanPhotoSignature.current
      ? photos.map(photo => photo.saved?.stored_name ?? "") : roleFileNames(photos, nameWithSequence),
    [photos, nameWithSequence, editing, currentPhotoSignature],
  );

  const folderPreview = useMemo(() => {
    const buildingFloor = `${safeName(building)}${safeName(floor)}`;
    const naming = editing ? (applyNewNaming ? { ...editNaming, separator: " " } : editing.naming)
      : { include_date: freeWithDate, include_material: fireNaming.includeMaterial, separator: " " };
    const parent = editing ? editing.folder_path.replace(/\\/g, "/").split("/").slice(0, -1).join("\\") : freeSelectedSubfolder || "請選子目錄";
    const unchanged = editing && !applyNewNaming && workDate === editing.work_date && building === editing.building
      && floor === editing.floor && addressCode === editing.address_code && material === editing.material
      && JSON.stringify(issues) === JSON.stringify(editing.issues);
    if (unchanged) return editing.folder_path.replace(/\//g, "\\");
    const issueText = issues.map(safeName).join(naming.separator);
    const parts = [ ...(naming.include_date ? [workDate] : []), buildingFloor, addressCode,
      ...(issues[0] !== "火警" || naming.include_material ? [material] : []), issueText ];
    return [parent, parts.map(safeName).join(" ")].filter(Boolean).join("\\");
  }, [workDate, building, floor, addressCode, material, issues, freeSelectedSubfolder, freeWithDate,
      fireNaming.includeMaterial, editing, applyNewNaming, editNaming]);
  const previewRoot = editing?.storage_root || storageRoot;
  const destinationSubfolder = freeSelectedSubfolder;
  const overviewDefaultMaterial = references.materials.includes(destinationSubfolder)
    ? destinationSubfolder
    : material;


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

  useEffect(() => {
    fetch("/api/settings/database")
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((payload: { path: string }) => setDatabasePath(payload.path || ""))
      .catch(() => setError("無法取得目前資料庫位置，請重新整理。"));
    fetch("/api/reference-values")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((payload: ReferenceValues) => setReferences((current) => ({
        fire_details: payload.fire_details ?? current.fire_details,
        custom_fire_details: payload.custom_fire_details ?? current.custom_fire_details,
        buildings: [...new Set([...payload.buildings, ...current.buildings])],
        materials: [...new Set([...payload.materials, ...current.materials])],
        issues: [...new Set([...payload.issues, ...current.issues])],
        photo_roles: [...new Set([...payload.photo_roles, ...current.photo_roles])],
        custom_materials: [...new Set([...(payload.custom_materials ?? []), ...current.custom_materials])],
        custom_issues: [...new Set([...(payload.custom_issues ?? []), ...current.custom_issues])],
      })))
      .catch(() => undefined);
    fetch("/api/settings/role-order")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((payload: { roles: string[] }) => { if (payload.roles?.length) setRoleOrder(payload.roles); })
      .catch(() => undefined);
    fetch("/api/settings/name-sequence")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((payload: { enabled: boolean }) => {
        if (newDraft.current) newDraft.current.sequence = Boolean(payload.enabled);
        else setNameWithSequence(Boolean(payload.enabled));
      })
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
    return () => { releasePhotos(latestPhotos.current); if (newDraft.current) releasePhotos(newDraft.current.photos); ++editRequest.current; confirmationResolve.current?.(false); confirmationResolve.current = null; };
  }, []);

  function addFiles(fileList: FileList | File[]) {
    if (updateInstalling || saving || editLoading) return;
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
    const defaults = initialRoles(combinedCount, roleOrder);
    const currentDefaults = initialRoles(photos.length, roleOrder);
    const rolesAreAutomatic = !editing && photos.every(
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

  function changeRoleOrder(roles: string[]) {
    setRoleOrder(roles);
    fetch("/api/settings/role-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ roles }),
    }).catch(() => setError("無法儲存預設角色順序。"));
  }

  function movePhoto(from: number, to: number) {
    setPhotos((current) => moveItem(current, from, to));
  }

  function endPhotoDrag() {
    setTimeout(() => { ignorePhotoClick.current = false; }, 0);
    draggedPhoto.current = "";
    setDraggedPhotoId("");
    setDragOverPhotoId("");
  }

  function removePhoto(id: string) {
    const target = photos.find((photo) => photo.id === id);
    if (target) releasePhotos([target]);
    const remaining = photos.filter((photo) => photo.id !== id);
    setPhotos(remaining);
    if (selectedPhotoId === id) setSelectedPhotoId(remaining[0]?.id ?? "");
  }

  function setPhotoRole(id: string, role: string) {
    setPhotos((current) => current.map((photo) => (photo.id === id ? { ...photo, role } : photo)));
  }

  function clearDraft() {
    cleanFields.current = JSON.stringify({ workDate, building, floor: "", addressCode: "", material, issues, location: "", notes: "" });
    releasePhotos(photos);
    setPhotos([]);
    setSelectedPhotoId("");
    setViewerId("");
    setFloor("");
    setAddressCode("");
    setLocation("");
    setNotes("");
    if (fileInput.current) fileInput.current.value = "";
  }

  async function saveCase(event: React.FormEvent) {
    event.preventDefault();
    if (updateInstalling || saving || editLoading) return;
    if (editing) { await saveEditedCase(); return; }
    if (issues[0] === "火警" && (!fireNaming.ready || fireNaming.saving || fireNaming.failed)) { setError("請先完成火警命名設定保存，失敗時請重試。"); return; }
    setError("");
    setNotice("");
    if (!photos.length || !floor.trim() || !addressCode.trim()) {
      if (collapsed) ui.update({ panel_collapsed: false });
      setError("請加入照片，並填寫樓層與定址碼。");
      return;
    }
    if (!storage.valid) {
      setError("請先掃描目錄並選擇有效的子目錄。");
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
    form.set("fire_include_material", String(fireNaming.includeMaterial));
    form.set("name_with_sequence", nameWithSequence ? "true" : "false");
    form.set("storage_month", "");
    form.set("storage_subfolder", freeSelectedSubfolder);
    form.set("free_scan_root", storage.result!.root);
    form.set("free_with_date", freeWithDate ? "true" : "false");
    photos.forEach((photo) => { if (photo.file) form.append("photos", photo.file, photoName(photo)); });
    try {
      const response = await fetch("/api/cases", { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      setNotice(`案件與照片已安全儲存。資料夾：${payload.folder_path || "請於清冊檢視實際位置"}`);
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


  function applyFields(fields: { workDate: string; building: string; floor: string; addressCode: string;
    material: string; issues: string[]; location: string; notes: string }) {
    setWorkDate(fields.workDate); setBuilding(fields.building); setFloor(fields.floor);
    setAddressCode(fields.addressCode); setMaterial(fields.material); setIssues(fields.issues);
    setLocation(fields.location); setNotes(fields.notes);
  }

  function applyEditedCase(record: EditableCase) {
    const loaded: PhotoDraft[] = (record.photos || []).map(photo => ({
      id: photo.id, file: null, saved: photo, url: `${photo.content_url}?edit=${record.edit_token}`, role: photo.role,
    }));
    const fields = { workDate: record.work_date, building: record.building, floor: record.floor,
      addressCode: record.address_code, material: record.material, issues: record.issues,
      location: record.location, notes: record.notes };
    cleanFields.current = JSON.stringify(fields);
    cleanPhotoSignature.current = photoSignature(loaded, record.name_with_sequence);
    setEditing(record); applyFields(fields); setPhotos(loaded); setNameWithSequence(record.name_with_sequence);
    setSelectedPhotoId(current => loaded.some(photo => photo.id === current) ? current : loaded[0]?.id || "");
    setApplyNewNaming(false); setEditNaming(record.naming); setViewerId("");
    setCustomOptionKind(null); ++optionGeneration.current;
    if (fileInput.current) fileInput.current.value = "";
  }

  function restoreNewDraft() {
    const snapshot = newDraft.current;
    if (snapshot) {
      applyFields(JSON.parse(snapshot.fields)); cleanFields.current = snapshot.clean;
      setPhotos(snapshot.photos); setSelectedPhotoId(snapshot.selected); setNameWithSequence(snapshot.sequence);
    }
    newDraft.current = null; setEditing(null); setApplyNewNaming(false); setViewerId("");
    setCustomOptionKind(null); ++optionGeneration.current;
    if (fileInput.current) fileInput.current.value = "";
  }

  async function startEditing(id: string) {
    if (saving || updateInstalling || editLoading) return;
    if (editing && contentDirty && !window.confirm("放棄目前尚未儲存的更正並重新載入案件？")) return;
    if (!newDraft.current) newDraft.current = { fields: draftFields, clean: cleanFields.current,
      photos, selected: selectedPhotoId, sequence: nameWithSequence };
    const request = ++editRequest.current;
    setEditLoading(true); setError(""); setNotice(""); setPage("workspace");
    try {
      const response = await fetch(`/api/cases/${id}/edit`);
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      if (request !== editRequest.current) return;
      if (editing) releasePhotos(photos);
      applyEditedCase(payload);
      if (collapsed) ui.update({ panel_collapsed: false });
      requestAnimationFrame(() => document.querySelector(".workspace-edit-banner")?.scrollIntoView?.({ block: "start", behavior: "smooth" }));
    } catch (cause) {
      if (request !== editRequest.current) return;
      if (!editing) restoreNewDraft();
      setError(cause instanceof Error ? cause.message : "無法載入案件。");
    } finally { if (request === editRequest.current) setEditLoading(false); }
  }

  function endEditing() {
    if (saving) return;
    if (editing && contentDirty && !window.confirm("放棄本次未儲存的更正？已儲存的案件不受影響。")) return;
    ++editRequest.current; setEditLoading(false);
    if (editing) releasePhotos(photos);
    restoreNewDraft(); setError("");
  }

  async function saveEditedCase() {
    if (!editing || editLoading || saving) return;
    if (!photos.length || !floor.trim() || !addressCode.trim()) {
      setError("請至少保留一張照片，並填寫樓層與定址碼。"); return;
    }
    const uploads: File[] = [];
    const selection = photos.map(photo => photo.saved
      ? { photo_id: photo.saved.id, role: photo.role }
      : { upload_index: uploads.push(photo.file!) - 1, role: photo.role });
    const change = { work_date: workDate, building, floor, address_code: addressCode, material,
      issues, location, notes, token: editing.edit_token, apply_naming: applyNewNaming,
      include_material: editNaming.include_material, include_date: editNaming.include_date,
      name_with_sequence: nameWithSequence, photos: selection, confirm_managed: false };
    setSaving(true); setError(""); setNotice("");
    try {
      const preview = await fetch(`/api/cases/${editing.id}/edit-preview`, { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(change) });
      const plan = await preview.json();
      if (!preview.ok) throw new Error(errorText(plan));
      if (plan.rename || plan.photos_changed) {
        const confirmed = await new Promise<boolean>(resolve => {
          confirmationResolve.current = resolve; setEditConfirmation(plan);
        });
        if (!confirmed) return;
        change.confirm_managed = true;
      }
      const form = new FormData(); form.set("change", JSON.stringify(change));
      uploads.forEach(file => form.append("photos", file, file.name));
      const response = await fetch(`/api/cases/${editing.id}/save`, { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      releasePhotos(photos); applyEditedCase(payload);
      setNotice(payload.edit_warning || `案件更正已儲存。${payload.photo_backup ? "原照片已保留備份。" : ""}資料夾：${payload.folder_path}`);
      await loadCases();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "案件更正儲存失敗。"); }
    finally {
      setSaving(false);
      requestAnimationFrame(() => saveButton.current?.focus({ preventScroll: true }));
    }
  }

  function chooseEditConfirmation(confirmed: boolean) {
    const resolve = confirmationResolve.current;
    confirmationResolve.current = null; setEditConfirmation(null); resolve?.(confirmed);
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

  async function openDatabaseFolder() {
    try {
      const response = await fetch("/api/settings/database/open-folder", { method: "POST" });
      if (!response.ok) throw new Error(errorText(await response.json()));
    } catch (error) {
      setError(error instanceof Error ? error.message : "無法開啟資料庫位置。");
    }
  }

  function currentScanPath(): string {
    return storage.valid ? storage.destination : storage.result?.root || "";
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
      const renamedPhotos = Number(payload.photos_renamed ?? 0);
      const addedPhotos = Number(payload.photos_added ?? 0);
      const updatedPhotos = Number(payload.photos_updated ?? 0);
      const removedPhotos = Number(payload.photos_removed ?? 0);
      const pending = Number(payload.unresolved ?? 0) + Number(payload.ambiguous ?? 0) + Number(payload.skipped ?? 0);
      if (relinked || imported || removed || renamedPhotos || addedPhotos || updatedPhotos || removedPhotos) {
        const changes = [
          relinked ? `重新連結 ${relinked} 筆案件` : "",
          imported ? `新增 ${imported} 筆案件` : "",
          removed ? `清除 ${removed} 筆失效紀錄` : "",
          renamedPhotos ? `更新 ${renamedPhotos} 張照片檔名` : "",
          addedPhotos ? `加入 ${addedPhotos} 張新照片` : "",
          updatedPhotos ? `更新 ${updatedPhotos} 張被編修的照片` : "",
          removedPhotos ? `移除 ${removedPhotos} 筆找不到檔案的照片紀錄` : "",
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

  function changeNameSequence(enabled: boolean) {
    setNameWithSequence(enabled);
    if (editing) return;
    fetch("/api/settings/name-sequence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }).catch(() => setError("無法儲存檔名序號設定。"));
  }

  async function addCustomOption(kind: CustomOptionKind) {
    const value = customOptionValue.trim();
    if (!value) {
      setError("請輸入自訂選項名稱。");
      return;
    }
    const generation = optionGeneration.current;
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
        fire_details: kind === "fire-detail" ? [...new Set([...current.fire_details, savedValue])] : current.fire_details,
        custom_fire_details: kind === "fire-detail" ? [...new Set([...current.custom_fire_details, savedValue])] : current.custom_fire_details,
        custom_materials: kind === "material"
          ? [...new Set([...current.custom_materials, savedValue])]
          : current.custom_materials,
        custom_issues: kind === "issue"
          ? [...new Set([...current.custom_issues, savedValue])]
          : current.custom_issues,
      }));
      if (generation === optionGeneration.current) {
        if (kind === "material") setMaterial(savedValue);
        else if (kind === "issue") setIssues([savedValue]);
        else if (issuesNow.current[0] === "火警") setIssues(["火警", savedValue]);
        setCustomOptionKind(null); setCustomOptionValue("");
      }
      setNotice(`${kind === "material" ? "材料" : kind === "issue" ? "問題" : "火警細項"}選項已新增。`);
    } catch (optionError) {
      setError(optionError instanceof Error ? optionError.message : "新增選項失敗。");
    } finally {
      setSavingCustomOption(false);
    }
  }

  function startCustomOption(kind: CustomOptionKind) {
    ++optionGeneration.current;
    setCustomOptionKind(kind);
    setCustomOptionValue("");
    setError("");
  }

  async function deleteCustomOption(kind: CustomOptionKind, value: string) {
    const label = kind === "material" ? "材料" : kind === "issue" ? "問題" : "火警細項";
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
        fire_details: kind === "fire-detail" ? current.fire_details.filter(item => item !== value) : current.fire_details,
        custom_fire_details: kind === "fire-detail" ? current.custom_fire_details.filter(item => item !== value) : current.custom_fire_details,
        custom_materials: kind === "material" ? current.custom_materials.filter((item) => item !== value) : current.custom_materials,
        custom_issues: kind === "issue" ? current.custom_issues.filter((item) => item !== value) : current.custom_issues,
      }));
      if (kind === "material" && material === value) {
        setMaterial(references.materials.find((item) => item !== value) ?? "");
      }
      if (kind === "fire-detail") setIssues(current => current[0] === "火警" && current[1] === value ? ["火警"] : current);
      if (kind === "issue") {
        setIssues((current) => (
          current[0] === value
            ? [references.issues.find((item) => item !== value) ?? ""]
            : current
        ));
      }
      setNotice(`自訂${label}「${value}」已刪除。`);
    } catch (optionError) {
      setError(optionError instanceof Error ? optionError.message : "刪除選項失敗。");
    } finally {
      setDeletingOption("");
    }
  }

  const caseEditor = (
          <section className="case-editor" key="case-editor">
            <div className="section-heading">
              <div><span className="eyebrow">STEP 3</span><h2>案件資料</h2></div>
              {topPanel ? <button className="button secondary collapse-editor" type="button" disabled={!ui.ready}
                aria-expanded={!collapsed} aria-controls="case-editor-fields" onClick={() => ui.update({ panel_collapsed: !ui.value.panel_collapsed })}>
                {collapsed ? "展開案件資料" : "收合案件資料"}</button> : <span className="autosave-label">常用選項</span>}
            </div>
            {collapsed && <p className="case-summary">{building}{floor || "（未填樓層）"} · {addressCode || "未填定址碼"} · {material || "未選材料"}</p>}
            <div id="case-editor-fields" className="editor-fields" hidden={collapsed}>
            {editing ? <div className="edit-storage-card"><strong>此案件儲存位置（固定）</strong>
              <code>{editing.original_path}</code><small>沿用此案原目錄，取消編輯後還原新增案件的儲存設定。</small></div>
              : <StorageDestination storage={storage} />}

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
              items={editing ? [...new Set([material, ...references.materials])] : references.materials}
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
              onCancel={() => { ++optionGeneration.current; setCustomOptionKind(null); }}
              onDelete={(item) => deleteCustomOption("material", item)}
            />

            <OptionField
              kind="issue"
              noun="問題"
              legend="問題"
              single
              items={editing ? [...new Set([issues[0], ...references.issues])] : references.issues}
              customItems={references.custom_issues}
              isActive={(item) => issues[0] === item}
              onSelect={(item) => { ++optionGeneration.current; setCustomOptionKind(null); setIssues([item]); }}
              deletingOption={deletingOption}
              editing={customOptionKind === "issue"}
              editorValue={customOptionValue}
              saving={savingCustomOption}
              onStartAdd={() => startCustomOption("issue")}
              onEditorChange={setCustomOptionValue}
              onAdd={() => addCustomOption("issue")}
              onCancel={() => { ++optionGeneration.current; setCustomOptionKind(null); }}
              onDelete={(item) => deleteCustomOption("issue", item)}
            />


            {issues[0] === "火警" && (
              <OptionField kind="fire-detail" noun="火警細項" legend="火警細項（單選，可不選）" optionPrefix="火警細項" single
                items={editing && issues[1] ? [...new Set([issues[1], ...references.fire_details])] : references.fire_details} customItems={references.custom_fire_details}
                isActive={item => issues[1] === item}
                onSelect={item => { ++optionGeneration.current; setIssues(issues[1] === item ? ["火警"] : ["火警", item]); }}
                deletingOption={deletingOption} editing={customOptionKind === "fire-detail"} editorValue={customOptionValue}
                saving={savingCustomOption} onStartAdd={() => startCustomOption("fire-detail")} onEditorChange={setCustomOptionValue}
                onAdd={() => addCustomOption("fire-detail")} onCancel={() => { ++optionGeneration.current; setCustomOptionKind(null); }}
                onDelete={item => deleteCustomOption("fire-detail", item)} />
            )}

            <label className="notes-field"><span>備註</span><textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="可記錄漏水原因、缺照原因或其他說明" /></label>

            <div className={`completeness ${missingRoles.length ? "warning" : "ready"}`}>
              <strong>{missingRoles.length ? `缺少：${missingRoles.join("、")}` : "前／中／後（或完成）照片齊全"}</strong>
              <span>{photos.length >= 3 && photos.length <= 5 ? "符合建議的 3～5 張照片" : "一般案件建議使用 3～5 張照片"}</span>
            </div>
            </div>
          </section>
  );

  return (
    <div className={`app-shell ${tiles ? "theme-blue" : "theme-classic"}`}>
      <header ref={header} className="topbar" inert={updateInstalling || modalOpen || saving || editLoading}>
        <div className="brand-block">
          <div className="brand-mark">ML</div>
          <div>
            <h1>MatLens</h1>
            <p>消防材料更換照片管理</p>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="local-badge">本機離線儲存</span>
          {!tiles && page === "workspace" && <button className="button secondary" type="button" onClick={() => fileInput.current?.click()}>
            ＋ 匯入照片
          </button>}
          {!tiles && page === "workspace" && <button className="button secondary" type="button" onClick={() => void clipboard.read()}
            disabled={clipboard.reading || clipboard.pending.length > 0 || saving}>
            {clipboard.reading ? "讀取剪貼簿…" : "貼上圖片"}
          </button>}
          <button ref={saveButton} className="button primary" type="submit" form="case-form" disabled={page !== "workspace" || saving || editLoading || (!editing && !storage.valid) || clipboard.pending.length > 0}>
            {saving ? "儲存中…" : editing ? "儲存變更" : "儲存案件"}
          </button>
        </div>
        <nav className="workspace-nav" role="tablist" aria-label="主頁籤" onKeyDown={event => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "Home" ? "workspace" : event.key === "End" ? "settings" : page === "workspace" ? "settings" : "workspace";
          setPage(next);
          event.currentTarget.querySelector<HTMLButtonElement>(`[id=tab-${next}]`)?.focus();
        }}>
          {([ ["workspace", "工作區"], ["settings", "設定"] ] as const).map(([id, label]) =>
            <button key={id} id={`tab-${id}`} type="button" role="tab" aria-selected={page === id}
              aria-controls={`panel-${id}`} tabIndex={page === id ? 0 : -1} onClick={() => setPage(id)}>{label}</button>)}
        </nav>
      </header>

      <div inert={modalOpen}><UpdatePanel onInstalling={setUpdateInstalling} /></div>

      <div className={`storage-bar ${editing || storage.valid ? "has-destination" : "needs-destination"}`} inert={updateInstalling || modalOpen || saving || editLoading || !!editing}>
        <strong className="destination-badge" role="status">
          {editing ? "目前編輯案件原資料夾" : storage.valid ? `目前儲存資料夾：${freeSelectedSubfolder}` : "尚未確認儲存資料夾"}
        </strong>
        <code title={editing?.original_path || storage.destination || storage.path}>{editing?.original_path || storage.destination || storage.path || "請選擇照片根目錄"}</code>
        <button type="button" onClick={() => void storage.choose()} disabled={storage.loading}>
          選擇目錄
        </button>
      </div>

      {(error || notice) && (
        <div className={`message ${error ? "error" : "success"}`} role={error ? "alert" : "status"}>
          <span>{error || notice}</span>
          <button type="button" aria-label="關閉訊息" onClick={() => { setError(""); setNotice(""); }}>×</button>
        </div>
      )}

      <main id="panel-settings" role="tabpanel" aria-labelledby="tab-settings" hidden={page !== "settings"} inert={updateInstalling || modalOpen || saving || editLoading}>
        <UISettings preferences={ui} />
      </main>
      <main id="panel-workspace" role="tabpanel" aria-labelledby="tab-workspace" hidden={page !== "workspace"} inert={updateInstalling || modalOpen || saving}>
        {(editing || editLoading) && <section className="workspace-edit-banner" aria-label="編輯模式">
          <div><strong>{editLoading ? "載入既有案件中…" : `正在編輯：${editing!.building}${editing!.floor} ${editing!.address_code}`}</strong>
            <p>欄位與照片已載入目前工作區，可修改、增減照片、排序及調整角色；儲存會更新同一筆案件。</p>
            {backgroundDirty && <p>原新增草稿已暫存，取消編輯後可接續；關閉前仍需處理未儲存內容。</p>}
            {editing && <code>{editing.original_path}</code>}</div>
          <div className="workspace-edit-actions"><button className="button secondary" type="button" disabled={saving || editLoading}
            onClick={() => { if (editing) void startEditing(editing.id); }}>重新載入案件</button>
            <button className="button secondary" type="button" disabled={saving} onClick={() => endEditing()}>取消編輯</button></div>
        </section>}
        {ui.error && <p role="alert" className="preferences-error">{ui.error} 請開啟設定頁重試。</p>}
        <form id="case-form" inert={editLoading} className={`workspace layout-${ui.value.layout} panel-${tiles ? ui.value.panel_position : "right"} tiles-${ui.value.tile_size}`}
          onSubmit={saveCase} onInvalidCapture={event => {
            if (!collapsed) return;
            event.preventDefault();
            if (expandingPanel.current) return;
            expandingPanel.current = true;
            const target = event.target as HTMLInputElement;
            ui.update({ panel_collapsed: false });
            setError("請完成案件必填欄位後再儲存。");
            requestAnimationFrame(() => { target.focus(); expandingPanel.current = false; });
          }}>
          {topPanel && caseEditor}
          <section
            className={`photo-rail ${dragging ? "dragging" : ""}`}
            aria-label="本次照片"
            onDragEnter={(event) => { event.preventDefault(); if (!draggedPhoto.current) setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setDragging(false);
              }
            }}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              if (draggedPhoto.current) return; // 縮圖排序，不是新增檔案
              addFiles(event.dataTransfer.files);
            }}
          >
            <div className="section-heading">
              <div><span className="eyebrow">STEP 1</span><h2>本次照片</h2></div>
              <span className="count-label">{photos.length} 張</span>
              {tiles && <div className="photo-actions">
                <button className="button secondary" type="button" onClick={() => fileInput.current?.click()}>匯入照片</button>
                <button className="button secondary" type="button" onClick={() => void clipboard.read()} disabled={clipboard.reading || saving || clipboard.pending.length > 0}>
                  {clipboard.reading ? "讀取剪貼簿…" : "貼上圖片"}</button>
              </div>}
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
                  <div
                    className={`thumbnail-item ${photo.id === selectedPhoto?.id ? "selected" : ""} ${draggedPhotoId === photo.id ? "dragging" : ""} ${dragOverPhotoId === photo.id ? "drop-target" : ""}`}
                    key={photo.id}
                    draggable
                    onDragStart={event => {
                      if ((event.target as Element).closest("select, input, .remove-photo, .move-photo")) { event.preventDefault(); return; }
                      ignorePhotoClick.current = true;
                      draggedPhoto.current = photo.id; setDraggedPhotoId(photo.id);
                    }}
                    onDragOver={(event) => {
                      if (!draggedPhoto.current) return;
                      event.preventDefault();
                      setDragOverPhotoId(photo.id);
                    }}
                    onDragEnd={endPhotoDrag}
                    onDrop={(event) => {
                      if (!draggedPhoto.current) return;
                      event.preventDefault();
                      event.stopPropagation();
                      movePhoto(photos.findIndex((item) => item.id === draggedPhoto.current), index);
                      endPhotoDrag();
                    }}
                  >
                    <button type="button" className="thumbnail-button" aria-label={tiles ? `放大 ${photoName(photo)}` : undefined}
                      onClick={event => {
                        if (ignorePhotoClick.current || draggedPhoto.current) return;
                        setSelectedPhotoId(photo.id);
                        if (tiles) { event.currentTarget.focus({ preventScroll: true }); setViewerId(photo.id); }
                      }}>
                      <img src={photo.url} alt={`${photo.role}：${photoName(photo)}`} draggable={false} />
                      <span className="thumbnail-copy"><strong>{photo.role}</strong><small>{photoName(photo)}</small></span>
                    </button>
                    {tiles && <div className="tile-footer">
                      <select aria-label={`${photoName(photo)} 的角色`} value={photo.role} onChange={event => setPhotoRole(photo.id, event.target.value)}>
                        {references.photo_roles.map(role => <option key={role}>{role}</option>)}
                      </select><code title={generatedNames[index]}>{generatedNames[index]}</code>
                    </div>}
                    <button type="button" className="remove-photo" aria-label={`移除 ${photoName(photo)}`} onClick={() => removePhoto(photo.id)}>×</button>
                    <span className="photo-number">{String(index + 1).padStart(2, "0")}</span>
                    <span className="move-photo">
                      <button type="button" aria-label={`將 ${photoName(photo)} 往前移`} disabled={index === 0} onClick={() => movePhoto(index, index - 1)}>◀</button>
                      <button type="button" aria-label={`將 ${photoName(photo)} 往後移`} disabled={index === photos.length - 1} onClick={() => movePhoto(index, index + 1)}>▶</button>
                    </span>
                  </div>
                ))}
                <button className="add-more" type="button" onClick={() => fileInput.current?.click()}>＋ 加入照片</button>
              </div>
            )}
            <RoleOrderEditor roles={roleOrder} allRoles={references.photo_roles} onChange={changeRoleOrder} />
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
              <div><span className="eyebrow">STEP 2</span><h2>{tiles ? "案件命名" : "照片預覽與命名"}</h2></div>
              {selectedPhoto && <span className="role-label">{selectedPhoto.role}</span>}
            </div>
            {!tiles && <>
            {selectedPhoto ? (
              <PhotoPreview key={selectedPhoto.id} src={selectedPhoto.url} alt={photoName(selectedPhoto)} />
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
            </>}
            <label className="name-sequence-toggle">
              <input
                type="checkbox"
                checked={nameWithSequence}
                onChange={(event) => changeNameSequence(event.target.checked)}
              />
              檔名加上序號（01_、02_…）
            </label>
            {editing && <div className="edit-naming-options">
              <label><input type="checkbox" checked={applyNewNaming} onChange={event => {
                setApplyNewNaming(event.target.checked); if (!event.target.checked) setEditNaming(editing.naming);
              }} />本案套用新版命名（空白分隔）</label>
              <label><input type="checkbox" checked={applyNewNaming ? editNaming.include_date : editing.naming.include_date}
                onChange={event => { setApplyNewNaming(true); setEditNaming(current => ({ ...current, include_date: event.target.checked })); }} />本案名稱包含日期</label>
              <small>預設保留此案原命名方式；變更後先確認原／新路徑，不影響新增案件的預設設定。</small>
            </div>}
            {issues[0] === "火警" && <div className="fire-naming">
              <label><input type="checkbox" checked={editing ? (applyNewNaming ? editNaming.include_material : editing.naming.include_material) : fireNaming.includeMaterial}
                disabled={!editing && !fireNaming.ready} onChange={event => {
                  if (editing) { setApplyNewNaming(true); setEditNaming(current => ({ ...current, include_material: event.target.checked })); }
                  else fireNaming.save(event.target.checked);
                }} />火警資料夾名稱包含材料</label>
              <small>{editing ? "調整本案名稱，材料資料與原儲存目錄不變。" : "只調整新案件名稱，材料資料及上層資料夾不變。"}</small>
              {!editing && <><p role={fireNaming.failed || !fireNaming.ready ? "alert" : "status"}>{fireNaming.status}</p>
                {fireNaming.failed && <button type="button" onClick={fireNaming.retry}>重試火警命名設定</button>}
                {!fireNaming.ready && <button type="button" onClick={() => void fireNaming.reload()}>重新讀取火警命名設定</button>}</>}
            </div>}
            <div className="path-preview">
              <span>案件資料夾</span>
              <code>{folderPreview}</code>
              {previewRoot && <small>{previewRoot}{"\\"}{folderPreview}</small>}
            </div>
          </section>

          {!topPanel && caseEditor}
        </form>

        <CaseListSection
          databasePath={databasePath}
          onOpenDatabaseFolder={openDatabaseFolder}
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
          onEdit={id => { void startEditing(id); }}
          editingDisabled={saving || editLoading}
          rescanDisabled={!!editing || editLoading}
          onView={viewCase}
          onOpenFolder={openFolder}
        />
      </main>

      {editConfirmation && <EditConfirmation plan={editConfirmation} returnFocus={saveButton.current} onChoose={chooseEditConfirmation} />}
      {viewerId && photos.length > 0 && <PhotoLightbox photos={photos} selectedId={viewerId} names={generatedNames}
        onSelect={id => { setViewerId(id); setSelectedPhotoId(id); }} onClose={() => setViewerId("")} />}
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
      {clipboard.pending.length > 0 && <PasteConfirmation images={clipboard.pending}
        onCancel={clipboard.close} onConfirm={() => {
          addFiles(clipboard.pending.map((item) => item.file));
          clipboard.close();
        }} />}
    </div>
  );
}
