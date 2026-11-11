import { useEffect, useRef, useState } from "react";
import { errorText } from "./utils";

export default function useFireNaming() {
  const [includeMaterial, setValue] = useState(true);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState("讀取火警命名設定中…");
  const current = useRef(true), mounted = useRef(false), sequence = useRef(0), loadSequence = useRef(0);
  const queue = useRef(Promise.resolve());
  function read(payload: { include_material?: unknown }): boolean {
    if (typeof payload.include_material !== "boolean") throw new Error("火警命名設定格式不正確");
    return payload.include_material;
  }
  async function reload() {
    const loadId = ++loadSequence.current;
    setReady(false);
    try {
      const response = await fetch("/api/settings/fire-naming");
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      const value = read(payload);
      if (!mounted.current || loadId !== loadSequence.current) return;
      current.current = value; setValue(value); setReady(true); setStatus("火警命名設定已儲存");
    } catch (error) {
      if (mounted.current && loadId === loadSequence.current) setStatus(`讀取失敗：${error instanceof Error ? error.message : "請重試"}`);
    }
  }
  useEffect(() => { mounted.current = true; void reload(); return () => { mounted.current = false; ++loadSequence.current; }; }, []);
  function save(value: boolean) {
    if (!ready) return;
    current.current = value; setValue(value); setStatus("火警命名設定儲存中…");
    const id = ++sequence.current;
    queue.current = queue.current.then(async () => {
      try {
        const response = await fetch("/api/settings/fire-naming", { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ include_material: value }) });
        const payload = await response.json();
        if (!response.ok) throw new Error(errorText(payload));
        read(payload);
        if (mounted.current && id === sequence.current) setStatus("火警命名設定已儲存");
      } catch (error) {
        if (mounted.current && id === sequence.current) setStatus(`儲存失敗：${error instanceof Error ? error.message : "請重試"}`);
      }
    });
  }
  return { includeMaterial, ready, status, saving: status.includes("儲存中"),
    failed: status.startsWith("儲存失敗"), save, retry: () => save(current.current), reload };
}
