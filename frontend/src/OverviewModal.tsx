import { useCallback, useEffect, useRef, useState } from "react";
import type { OverviewData, OverviewPhoto } from "./types";
import { errorText } from "./utils";

type Props = {
  buildings: string[];
  materials: string[];
  defaultMaterial: string;
  /** 目前「掃描目前資料夾」使用的路徑；磁碟資料夾來源與自動掃描都用它 */
  scanPath: string;
  initialView: "gallery" | "names";
  onClose: () => void;
};

type Source = "db" | "disk";

async function copyText(text: string, fallback: HTMLTextAreaElement | null): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    if (!fallback) return false;
    fallback.select();
    return document.execCommand("copy");
  }
}

export default function OverviewModal({
  buildings, materials, defaultMaterial, scanPath, initialView, onClose,
}: Props) {
  const [source, setSource] = useState<Source>("db");
  const [material, setMaterial] = useState(defaultMaterial);
  const [building, setBuilding] = useState("");
  const [view, setView] = useState(initialView);
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [size, setSize] = useState(180);
  const [autoScan, setAutoScan] = useState(true);
  const [autoScanLoaded, setAutoScanLoaded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [namesMode, setNamesMode] = useState<"files" | "folders">("files");
  const [exporting, setExporting] = useState("");
  const [lightbox, setLightbox] = useState<{ caseIndex: number; photoIndex: number } | null>(null);
  const namesBox = useRef<HTMLTextAreaElement>(null);
  const scanOnNextLoad = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      if (source === "disk" && !scanPath) throw new Error("請先選擇要掃描的照片根目錄。");
      if (source === "db" && autoScan && scanOnNextLoad.current && scanPath) {
        // 自動掃描只匯入新資料夾與重新連結，prune=false 不會刪除任何案件紀錄
        const scan = await fetch(`/api/cases/rescan?path=${encodeURIComponent(scanPath)}&prune=false`, {
          method: "POST",
        });
        if (scan.ok) {
          const result = (await scan.json()) as { imported?: number; relinked?: number };
          const added = Number(result.imported ?? 0) + Number(result.relinked ?? 0);
          if (added) setNotice(`自動掃描已更新 ${added} 筆案件。`);
        }
      }
      scanOnNextLoad.current = false;
      const params = new URLSearchParams({ source, material, building });
      if (source === "disk") params.set("path", scanPath);
      const response = await fetch(`/api/overview?${params}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      setData(payload as OverviewData);
    } catch (loadError) {
      setData(null);
      setError(loadError instanceof Error ? loadError.message : "無法產生照片總覽。");
    } finally {
      setLoading(false);
    }
  }, [source, material, building, scanPath, autoScan]);

  useEffect(() => {
    fetch("/api/settings/overview-auto-scan")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((payload: { enabled: boolean }) => setAutoScan(payload.enabled))
      .catch(() => undefined)
      .finally(() => setAutoScanLoaded(true));
  }, []);

  useEffect(() => {
    if (autoScanLoaded) void load();
    // 只在來源、材料、棟別改變或設定載入後重新讀取；重新掃描由「重新整理」觸發
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, material, building, autoScanLoaded]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (lightbox) setLightbox(null);
      else onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [lightbox, onClose]);

  function changeAutoScan(enabled: boolean) {
    setAutoScan(enabled);
    fetch("/api/settings/overview-auto-scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }).catch(() => setError("無法儲存自動掃描設定。"));
  }

  function refresh() {
    scanOnNextLoad.current = true;
    void load();
  }

  // 「只列資料夾名稱」：每個案件一行；「含圖檔名稱」：依案件分組，列出每張圖檔名
  const namesText = data
    ? namesMode === "folders"
      ? data.cases.map((item) => item.title).join("\n")
      : data.filenames
    : "";

  async function copyNames() {
    if (!data) return;
    const ok = await copyText(namesText, namesBox.current);
    setCopied(ok);
    if (!ok) setError("無法自動複製，請手動選取文字複製。");
  }

  async function exportHtml(mode: "light" | "standalone") {
    setExporting(mode);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/overview/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, material, building, path: scanPath, mode }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(errorText(payload));
      const megabytes = (Number(payload.size_bytes) / 1024 / 1024).toFixed(1);
      setNotice(`已輸出 ${payload.total} 筆（${megabytes} MB）：${payload.path}`);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "輸出網頁失敗。");
    } finally {
      setExporting("");
    }
  }

  const label = [building, material].filter(Boolean).join(" · ") || "全部";
  const lightboxPhotos: OverviewPhoto[] = lightbox && data ? data.cases[lightbox.caseIndex].photos : [];
  const lightboxPhoto = lightbox ? lightboxPhotos[lightbox.photoIndex] : undefined;

  function stepLightbox(step: number) {
    setLightbox((current) => {
      if (!current) return current;
      const next = current.photoIndex + step;
      return next < 0 || next >= lightboxPhotos.length ? current : { ...current, photoIndex: next };
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <section className="overview-modal" role="dialog" aria-modal="true" aria-label="照片總覽">
        <header className="overview-header">
          <div>
            <span className="eyebrow">OVERVIEW</span>
            <h2>{data ? `${label}共 ${data.total} 筆` : "照片總覽"}</h2>
          </div>
          <button type="button" aria-label="關閉照片總覽" onClick={onClose}>×</button>
        </header>

        <div className="overview-toolbar">
          <label>
            <span>資料來源</span>
            <select aria-label="資料來源" value={source} onChange={(event) => setSource(event.target.value as Source)}>
              <option value="db">案件資料庫</option>
              <option value="disk">磁碟資料夾</option>
            </select>
          </label>
          <label>
            <span>材料</span>
            <select aria-label="總覽材料" value={material} onChange={(event) => setMaterial(event.target.value)}>
              <option value="">全部材料</option>
              {[...new Set([...materials, ...(material && !materials.includes(material) ? [material] : [])])]
                .map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label>
            <span>棟別</span>
            <select aria-label="總覽棟別" value={building} onChange={(event) => setBuilding(event.target.value)}>
              <option value="">全部棟別</option>
              {buildings.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label className="overview-size">
            <span>縮圖大小</span>
            <input type="range" min={90} max={360} value={size} aria-label="縮圖大小" onChange={(event) => setSize(Number(event.target.value))} />
          </label>
          <div className="overview-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={view === "gallery"} className={view === "gallery" ? "active" : ""} onClick={() => setView("gallery")}>照片</button>
            <button type="button" role="tab" aria-selected={view === "names"} className={view === "names" ? "active" : ""} onClick={() => setView("names")}>檔名清單</button>
          </div>
        </div>

        <div className="overview-actions">
          <button type="button" onClick={refresh} disabled={loading}>{loading ? "讀取中…" : "重新整理"}</button>
          <label className="overview-autoscan">
            <input type="checkbox" checked={autoScan} onChange={(event) => changeAutoScan(event.target.checked)} />
            整理前自動掃描新資料夾（不會刪除紀錄）
          </label>
          <span className="overview-spacer" />
          <button type="button" disabled={!data || !!exporting} onClick={() => exportHtml("light")} title="縮圖內嵌，放大檢視讀取本機原始照片；檔案較小">
            {exporting === "light" ? "輸出中…" : "另存網頁（輕量）"}
          </button>
          <button type="button" disabled={!data || !!exporting} onClick={() => exportHtml("standalone")} title="縮圖與放大圖都內嵌，可直接傳給他人；檔案較大">
            {exporting === "standalone" ? "輸出中…" : "另存網頁（獨立）"}
          </button>
        </div>

        {(error || notice) && (
          <div className={`message ${error ? "error" : "success"}`} role={error ? "alert" : "status"}>
            <span>{error || notice}</span>
          </div>
        )}

        <div className="overview-body">
          {data && view === "gallery" && (
            data.cases.length === 0 ? (
              <p className="overview-empty">沒有符合條件的案件。</p>
            ) : (
              <div className="overview-cases" style={{ ["--thumb" as string]: `${size}px` }}>
                {data.cases.map((item, caseIndex) => (
                  <article className="overview-case" key={item.id || `${item.title}-${caseIndex}`}>
                    <h3>{item.title}<small>{item.work_date}</small></h3>
                    <div className="overview-row">
                      {item.photos.map((photo, photoIndex) => (
                        <figure key={photo.name}>
                          <button type="button" aria-label={`放大 ${item.title} ${photo.name}`} onClick={() => setLightbox({ caseIndex, photoIndex })}>
                            <img src={photo.thumb_url} alt={`${item.title} ${photo.name}`} loading="lazy" />
                          </button>
                          <figcaption>{photo.name}</figcaption>
                        </figure>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            )
          )}
          {data && view === "names" && (
            <div className="overview-names">
              <div className="overview-names-mode" role="group" aria-label="檔名清單內容">
                <button type="button" aria-pressed={namesMode === "folders"} className={namesMode === "folders" ? "active" : ""} onClick={() => { setNamesMode("folders"); setCopied(false); }}>
                  只列資料夾名稱
                </button>
                <button type="button" aria-pressed={namesMode === "files"} className={namesMode === "files" ? "active" : ""} onClick={() => { setNamesMode("files"); setCopied(false); }}>
                  含圖檔名稱
                </button>
              </div>
              <textarea ref={namesBox} readOnly aria-label="檔名清單內容" value={namesText} />
              <div>
                <button type="button" className="confirm" onClick={copyNames} disabled={!namesText}>
                  {copied ? "已複製" : "全部複製"}
                </button>
                <span>
                  共 {data.total} 個案件，
                  {namesMode === "folders" ? "只列資料夾名稱。" : "依案件分組，列出每張圖檔名。"}
                </span>
              </div>
            </div>
          )}
        </div>

        {lightbox && lightboxPhoto && (
          <div className="overview-lightbox" role="dialog" aria-modal="true" aria-label="放大檢視" onClick={() => setLightbox(null)}>
            <button type="button" aria-label="上一張" disabled={lightbox.photoIndex === 0} onClick={(event) => { event.stopPropagation(); stepLightbox(-1); }}>‹</button>
            <figure onClick={(event) => event.stopPropagation()}>
              <img src={lightboxPhoto.url} alt={lightboxPhoto.name} />
              <figcaption>{data?.cases[lightbox.caseIndex].title}　{lightboxPhoto.name}</figcaption>
            </figure>
            <button type="button" aria-label="下一張" disabled={lightbox.photoIndex >= lightboxPhotos.length - 1} onClick={(event) => { event.stopPropagation(); stepLightbox(1); }}>›</button>
            <button type="button" className="overview-lightbox-close" aria-label="關閉放大檢視" onClick={() => setLightbox(null)}>×</button>
          </div>
        )}
      </section>
    </div>
  );
}
