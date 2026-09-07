import { useEffect, useRef, useState } from "react";

export type UpdateState = {
  current: string;
  phase: string;
  channel: string;
  progress: number;
  message: string;
  version: string;
  notes: string;
  installable: boolean;
  last_result?: { ok: boolean; message: string };
};

export default function UpdatePanel({ onInstalling }: { onInstalling?: (value: boolean) => void }) {
  const [state, setState] = useState<UpdateState | null>(null);
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState("stable");
  const [error, setError] = useState("");
  const [installing, setInstalling] = useState(false);
  const initialized = useRef(false);

  useEffect(() => {
    let disposed = false;
    let pending = false;
    const refresh = async () => {
      const api = window.pywebview?.api;
      if (!api?.update_status || pending) return;
      pending = true;
      try {
        const next = await api.update_status();
        if (!disposed) setState(next);
        if (!disposed && !initialized.current) {
          initialized.current = true;
          await api.check_update("stable");
        }
      } catch {
        if (!disposed) setError("無法取得桌面更新狀態，請重新開啟程式。 ");
      } finally {
        pending = false;
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 1000);
    window.addEventListener("pywebviewready", refresh);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      window.removeEventListener("pywebviewready", refresh);
    };
  }, []);

  async function action(kind: "check" | "download" | "install") {
    const api = window.pywebview?.api;
    if (!api) return;
    setError("");
    try {
      let result;
      if (kind === "install") {
        const draft = window.matlensDesktopState;
        if (!draft || draft.dirty || draft.saving) {
          setError("請先儲存或清除目前案件，再安裝更新。");
          return;
        }
        if (!window.confirm("即將關閉 MatLens 並安裝更新，完成後自動重新開啟。確定繼續？")) return;
        setInstalling(true);
        onInstalling?.(true);
        result = await api.install_update(draft.dirty, draft.saving);
      } else {
        result = kind === "check" ? await api.check_update(channel) : await api.download_update();
      }
      if ("error" in result) {
        setError(result.error);
        setInstalling(false);
        onInstalling?.(false);
      } else if ("phase" in result) {
        setState(result);
      }
    } catch {
      setInstalling(false);
      onInstalling?.(false);
      setError("更新操作失敗，請重試；原有案件不受影響。");
    }
  }

  if (!state) return null;
  const busy = ["checking", "downloading", "installing"].includes(state.phase);
  return (
    <section className="update-section" aria-label="程式更新">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}>
        關於與更新 · v{state.current}{state.phase === "available" ? " · 有新版本" : ""}
      </button>
      {open && (
        <div className="update-panel">
          <h2>程式更新</h2>
          <p>目前版本 {state.current}{state.version ? ` ／ 線上版本 ${state.version}` : ""}</p>
          <label>更新頻道
            <select aria-label="更新頻道" value={channel} disabled={busy || installing}
              onChange={(event) => setChannel(event.target.value)}>
              <option value="stable">正式版（預設）</option>
              <option value="preview">測試版</option>
            </select>
          </label>
          <button type="button" disabled={busy || installing} onClick={() => action("check")}>檢查更新</button>
          <p role="status">{state.message}</p>
          {state.notes && <pre className="update-notes">{state.notes}</pre>}
          {state.phase === "downloading" && <progress aria-label="更新下載進度" value={state.progress} max={100} />}
          {!state.installable && <p>目前為開發版或可攜版。請執行 Install-MatLens.cmd 安裝後使用自動更新。</p>}
          {state.phase === "available" && <button type="button" disabled={!state.installable}
            onClick={() => action("download")}>下載更新</button>}
          {state.phase === "ready" && <button type="button" disabled={installing}
            onClick={() => action("install")}>安裝並重新啟動</button>}
          {error && <p role="alert">{error}</p>}
          {state.last_result && <p>上次更新：{state.last_result.message}</p>}
          <p>更新不會上傳或移動照片；安裝前會備份案件資料庫。</p>
        </div>
      )}
      {installing && <div className="modal-backdrop" role="alertdialog" aria-modal="true" aria-label="正在安裝更新">
        <div className="update-panel"><h2>正在安裝更新</h2><p>請稍候，新版會自動開啟。請勿關機。</p></div>
      </div>}
    </section>
  );
}
