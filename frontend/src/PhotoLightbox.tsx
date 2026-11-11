import { useEffect, useRef } from "react";
import PhotoPreview from "./PhotoPreview";
import { photoName } from "./utils";
import type { PhotoDraft } from "./types";

export default function PhotoLightbox({ photos, selectedId, names, onSelect, onClose }: {
  photos: PhotoDraft[]; selectedId: string; names: string[];
  onSelect: (id: string) => void; onClose: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const index = Math.max(0, photos.findIndex(photo => photo.id === selectedId));
  const photo = photos[index];
  useEffect(() => {
    const focused = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      document.body.style.overflow = overflow;
      if (focused instanceof HTMLElement && focused.isConnected) focused.focus({ preventScroll: true });
    };
  }, []);
  useEffect(() => {
    const active = document.activeElement;
    if (!panel.current?.contains(active) || (active instanceof HTMLButtonElement && active.disabled)) {
      panel.current?.querySelector<HTMLElement>(".interactive-preview")?.focus();
    }
  }, [photo?.id]);
  if (!photo) return null;
  const move = (offset: number) => {
    const next = photos[index + offset];
    if (next) onSelect(next.id);
  };
  return <div className="modal-backdrop lightbox-backdrop">
    <div ref={panel} className="photo-lightbox" role="dialog" aria-modal="true" aria-labelledby="lightbox-title"
      onKeyDownCapture={event => {
        if (event.key === "Escape") { event.preventDefault(); onClose(); }
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          event.preventDefault(); event.stopPropagation(); move(event.key === "ArrowLeft" ? -1 : 1);
        }
        if (event.key === "Tab") {
          const controls = panel.current?.querySelectorAll<HTMLElement>("button:not(:disabled), [tabindex='0']");
          if (!controls?.length) return;
          const first = controls[0], last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      }}>
      <header><div><h2 id="lightbox-title">{photo.role}・{names[index]}</h2><p>{index + 1}／{photos.length} 張 · {photoName(photo)}</p></div>
        <button type="button" className="lightbox-close" aria-label="關閉放大圖片" onClick={onClose}>×</button></header>
      <div className="lightbox-content"><button className="lightbox-prev" type="button" aria-label="上一張照片" disabled={index === 0} onClick={() => move(-1)}>‹</button>
        <PhotoPreview key={photo.id} src={photo.url} alt={photoName(photo)} />
        <button className="lightbox-next" type="button" aria-label="下一張照片" disabled={index === photos.length - 1} onClick={() => move(1)}>›</button></div>
      <p className="lightbox-help">左右鍵換圖 · 滾輪縮放 · 拖曳移動 · Esc 關閉</p>
    </div>
  </div>;
}
