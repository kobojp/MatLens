import { useCallback, useEffect, useRef, useState } from "react";
import type { FreeScanResult } from "./types";
import { errorText } from "./utils";

type Selection = { path: string; subfolder: string; with_date: boolean };
const initial: Selection = { path: "", subfolder: "", with_date: true };

export default function useStorageSelection() {
  const [selection, setSelection] = useState(initial);
  const [path, setPath] = useState("");
  const [result, setResult] = useState<FreeScanResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState("讀取設定中…");
  const current = useRef(initial);
  const scanId = useRef(0);
  const saveId = useRef(0);
  const mounted = useRef(false);
  const saves = useRef(Promise.resolve());

  const persist = useCallback((next: Selection) => {
    const id = ++saveId.current;
    setSaveStatus("儲存中…");
    saves.current = saves.current.then(async () => {
      try {
        const response = await fetch("/api/settings/storage-selection", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(next),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(errorText(data));
        if (mounted.current && id === saveId.current) setSaveStatus("已儲存");
      } catch {
        if (mounted.current && id === saveId.current) setSaveStatus("儲存失敗，請重試");
      }
    });
  }, []);

  const scan = useCallback(async (requested: string, restore = false) => {
    const id = ++scanId.current;
    const previous = current.current;
    setResult(null);
    setLoading(true);
    setError("");
    try {
      if (!requested.trim()) throw new Error("請輸入或選擇要掃描的路徑。");
      const response = await fetch(`/api/settings/storage/scan?path=${encodeURIComponent(requested.trim())}`);
      const data = await response.json();
      if (!response.ok) throw new Error(errorText(data));
      if (!data.root || !Array.isArray(data.subfolders)) throw new Error("無法讀取目錄清單。");
      if (!mounted.current || id !== scanId.current) return;
      const root = data as FreeScanResult;
      const sameRoot = previous.path === root.root;
      const subfolder = sameRoot && root.subfolders.includes(previous.subfolder) ? previous.subfolder : "";
      if (sameRoot && previous.subfolder && !subfolder) {
        setError("原選擇的子資料夾已不存在，請重新選擇子資料夾。");
      }
      const next = { ...previous, path: root.root, subfolder };
      current.current = next;
      setSelection(next);
      setPath(root.root);
      setResult(root);
      if (!restore) persist(next);
    } catch (cause) {
      if (mounted.current && id === scanId.current) {
        setError(cause instanceof Error ? cause.message : "無法掃描儲存目錄。");
      }
    } finally {
      if (mounted.current && id === scanId.current) setLoading(false);
    }
  }, [persist]);

  useEffect(() => {
    mounted.current = true;
    let disposed = false;
    void (async () => {
      try {
        const response = await fetch("/api/settings/storage-selection");
        const data = await response.json();
        if (!response.ok) throw new Error(errorText(data));
        if (disposed) return;
        const saved = { path: data.path || "", subfolder: data.subfolder || "", with_date: data.with_date !== false };
        current.current = saved;
        setSelection(saved);
        setPath(saved.path);
        setSaveStatus(saved.subfolder ? "已儲存" : "尚未選擇子資料夾");
        await scan(saved.path, true);
      } catch (cause) {
        if (!disposed) {
          setError(cause instanceof Error ? cause.message : "無法載入儲存設定。");
          setSaveStatus("設定讀取失敗");
          setLoading(false);
        }
      }
    })();
    return () => { disposed = true; mounted.current = false; ++scanId.current; };
  }, [scan]);

  function update(next: Selection) {
    current.current = next;
    setSelection(next);
    persist(next);
  }

  async function choose() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/settings/storage/pick-folder?persist=false", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(errorText(data));
      if (!data.cancelled) await scan(String(data.path));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "無法開啟資料夾選擇器。");
    } finally { if (mounted.current) setLoading(false); }
  }

  const valid = !loading && result !== null && path.trim() === result.root
    && result.subfolders.includes(selection.subfolder);
  const separator = result?.root.includes("\\") ? "\\" : "/";
  return {
    path, selection, result, loading, error, saveStatus, valid,
    destination: valid ? `${result!.root.replace(/[\\/]+$/, "")}${separator}${selection.subfolder}` : "",
    scan: () => scan(path), choose,
    editPath: (value: string) => { ++scanId.current; setLoading(false); setPath(value); setResult(null); setError(""); },
    select: (subfolder: string) => update({ ...current.current, subfolder }),
    setWithDate: (with_date: boolean) => update({ ...current.current, with_date }),
    retrySave: () => persist(current.current),
  };
}
