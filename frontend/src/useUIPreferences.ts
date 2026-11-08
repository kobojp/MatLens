import { useCallback, useEffect, useRef, useState } from "react";
import { errorText } from "./utils";

export type UIPreferences = {
  layout: "classic" | "tiles";
  panel_position: "right" | "top";
  tile_size: "medium" | "large";
  panel_collapsed: boolean;
};
export const DEFAULT_UI: UIPreferences = {
  layout: "tiles", panel_position: "right", tile_size: "large", panel_collapsed: false,
};

function parse(value: UIPreferences): UIPreferences {
  if (!["classic", "tiles"].includes(value.layout) || !["right", "top"].includes(value.panel_position)
    || !["medium", "large"].includes(value.tile_size) || typeof value.panel_collapsed !== "boolean") {
    throw new Error("介面設定格式不正確，請重新讀取或恢復預設版面。");
  }
  return { layout: value.layout, panel_position: value.panel_position,
    tile_size: value.tile_size, panel_collapsed: value.panel_collapsed };
}

export default function useUIPreferences() {
  const [value, setValue] = useState(DEFAULT_UI);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("讀取介面設定中…");
  const current = useRef(DEFAULT_UI);
  const mounted = useRef(false);
  const loadId = useRef(0);
  const saveId = useRef(0);
  const queue = useRef(Promise.resolve());

  const load = useCallback(async () => {
    const id = ++loadId.current;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/settings/ui-preferences");
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      const saved = parse(payload);
      if (!mounted.current || id !== loadId.current) return;
      current.current = saved;
      setValue(saved);
      setStatus("已儲存，下次開啟沿用");
    } catch (cause) {
      if (mounted.current && id === loadId.current) {
        setError(cause instanceof Error ? cause.message : "無法讀取介面設定。");
        setStatus("介面設定讀取失敗");
      }
    } finally { if (mounted.current && id === loadId.current) setLoading(false); }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; ++loadId.current; };
  }, [load]);

  function persist(next: UIPreferences) {
    const id = ++saveId.current;
    current.current = next;
    setValue(next);
    setStatus("儲存中…");
    queue.current = queue.current.then(async () => {
      try {
        const response = await fetch("/api/settings/ui-preferences", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(next),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(errorText(payload));
        parse(payload);
        if (mounted.current && id === saveId.current) {
          setError("");
          setStatus("已儲存，下次開啟沿用");
        }
      } catch (cause) {
        if (mounted.current && id === saveId.current) {
          setStatus(`儲存失敗：${cause instanceof Error ? cause.message : "請重試"}`);
        }
      }
    });
  }

  return { value, loading, error, status, ready: !loading && !error,
    saving: status === "儲存中…", failed: status.startsWith("儲存失敗"),
    update: (patch: Partial<UIPreferences>) => { if (!loading && !error) persist({ ...current.current, ...patch }); },
    reset: () => { if (!loading) persist({ ...DEFAULT_UI }); },
    retry: () => persist(current.current), reload: load,
  };
}
