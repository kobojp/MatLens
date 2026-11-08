import { useEffect, useRef } from "react";
import type { PendingImage } from "./useClipboardImages";

export default function PasteConfirmation({ images, onCancel, onConfirm }: {
  images: PendingImage[]; onCancel: () => void; onConfirm: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const focused = document.activeElement;
    panel.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { if (focused instanceof HTMLElement) focused.focus(); };
  }, []);
  return (
    <div className="modal-backdrop paste-backdrop">
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby="paste-title" className="paste-confirmation"
        onKeyDown={(event) => {
          if (event.key === "Escape") { event.preventDefault(); onCancel(); }
          if (event.key === "Tab") {
            const buttons = panel.current?.querySelectorAll<HTMLButtonElement>("button");
            if (!buttons?.length) return;
            if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons[buttons.length - 1].focus(); }
            else if (!event.shiftKey && document.activeElement === buttons[buttons.length - 1]) { event.preventDefault(); buttons[0].focus(); }
          }
        }}>
        <h2 id="paste-title">確認貼上圖片</h2>
        <p>共 {images.length} 張，確認後將加入本次照片。</p>
        <div className="paste-previews">{images.map((item, index) => (
          <figure key={item.id}><img src={item.url} alt={`待貼上圖片 ${index + 1}`} /><figcaption>{item.file.name}</figcaption></figure>
        ))}</div>
        <div className="paste-actions">
          <button type="button" className="button secondary" onClick={onCancel}>取消</button>
          <button type="button" className="button primary" onClick={onConfirm}>加入本次照片</button>
        </div>
      </div>
    </div>
  );
}
