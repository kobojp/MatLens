import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

type View = { zoom: number; x: number; y: number };
const FIT: View = { zoom: 1, x: 0, y: 0 };

export default function PhotoPreview({ src, alt }: { src: string; alt: string }) {
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; x: number; y: number } | null>(null);
  const [view, setView] = useState<View>(FIT);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  const [dragging, setDragging] = useState(false);
  const [failed, setFailed] = useState(false);

  useLayoutEffect(() => {
    const measure = () => {
      const rect = stage.current?.getBoundingClientRect();
      if (rect) setSize({ width: rect.width, height: rect.height });
    };
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    if (stage.current) observer?.observe(stage.current);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, []);

  const constrain = useCallback((next: View): View => {
    if (!natural.width || !natural.height) return { ...next, x: 0, y: 0 };
    const fit = Math.min(size.width / natural.width, size.height / natural.height);
    const limitX = Math.max(0, (natural.width * fit * next.zoom - size.width) / 2);
    const limitY = Math.max(0, (natural.height * fit * next.zoom - size.height) / 2);
    return { ...next, x: Math.max(-limitX, Math.min(limitX, next.x)), y: Math.max(-limitY, Math.min(limitY, next.y)) };
  }, [size, natural]);

  useEffect(() => { setView(current => constrain(current)); }, [constrain]);

  const zoomBy = useCallback((factor: number, focusX = 0, focusY = 0) => {
    setView(current => {
      const zoom = Math.max(0.25, Math.min(8, current.zoom * factor));
      const ratio = zoom / current.zoom;
      return constrain({ zoom, x: focusX - (focusX - current.x) * ratio, y: focusY - (focusY - current.y) * ratio });
    });
  }, [constrain]);

  useEffect(() => {
    const element = stage.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
      zoomBy(Math.exp(-Math.max(-500, Math.min(500, delta)) * 0.002),
             event.clientX - rect.left - rect.width / 2, event.clientY - rect.top - rect.height / 2);
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [zoomBy]);

  const endDrag = () => { drag.current = null; setDragging(false); };

  return (
    <div className="photo-preview">
      <div className="preview-toolbar" role="group" aria-label="圖片預覽工具">
        <button type="button" aria-label="縮小圖片" disabled={view.zoom <= 0.25} onClick={() => zoomBy(1 / 1.25)}>−</button>
        <output aria-label="預覽縮放比例" title="相對於完整顯示的比例">{Math.round(view.zoom * 100)}%</output>
        <button type="button" aria-label="放大圖片" disabled={view.zoom >= 8} onClick={() => zoomBy(1.25)}>＋</button>
        <button type="button" onClick={() => setView(FIT)}>顯示完整圖片</button>
        {natural.width > 0 && <small>{natural.width} × {natural.height}</small>}
      </div>
      <div
        ref={stage}
        className={`image-stage interactive-preview ${dragging ? "is-dragging" : ""}`}
        role="region"
        aria-label="可縮放圖片預覽"
        tabIndex={0}
        onDoubleClick={() => setView(FIT)}
        onPointerDown={event => {
          if (event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.focus({ preventScroll: true });
          event.currentTarget.setPointerCapture?.(event.pointerId);
          drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
          setDragging(true);
        }}
        onPointerMove={event => {
          if (!drag.current || drag.current.id !== event.pointerId) return;
          const dx = event.clientX - drag.current.x;
          const dy = event.clientY - drag.current.y;
          drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
          setView(current => constrain({ ...current, x: current.x + dx, y: current.y + dy }));
        }}
        onPointerUp={event => {
          if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
          endDrag();
        }}
        onPointerCancel={endDrag}
        onLostPointerCapture={endDrag}
        onKeyDown={event => {
          if (["+", "=", "-", "0", "Home", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) event.preventDefault();
          if (event.key === "+" || event.key === "=") zoomBy(1.25);
          else if (event.key === "-") zoomBy(1 / 1.25);
          else if (event.key === "0" || event.key === "Home") setView(FIT);
          else if (event.key.startsWith("Arrow")) setView(current => constrain({
            ...current,
            x: current.x + (event.key === "ArrowLeft" ? -40 : event.key === "ArrowRight" ? 40 : 0),
            y: current.y + (event.key === "ArrowUp" ? -40 : event.key === "ArrowDown" ? 40 : 0),
          }));
        }}
      >
        <img
          src={src} alt={alt} draggable={false}
          onDragStart={event => event.preventDefault()}
          onLoad={event => setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
          onError={() => setFailed(true)}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain", transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})` }}
        />
        {failed && <span className="preview-error" role="alert">無法預覽這張圖片，請重新匯入。</span>}
      </div>
      <p className="preview-help">滾輪縮放 · 按住左鍵拖曳 · 雙擊顯示完整圖片</p>
    </div>
  );
}
