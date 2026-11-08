import { useCallback, useEffect, useRef, useState } from "react";

const supported = ["image/png", "image/jpeg", "image/webp"];
const extension: Record<string, string> = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp" };
export type PendingImage = { file: File; url: string; id: string };

export default function useClipboardImages(count: number, disabled: boolean, notify: (message: string) => void) {
  const [pending, setPending] = useState<PendingImage[]>([]);
  const [reading, setReading] = useState(false);
  const state = useRef({ count, disabled, pending: false, reading: false });
  const staged = useRef<PendingImage[]>([]);
  const mounted = useRef(true);
  state.current.count = count;
  state.current.disabled = disabled;

  const close = useCallback(() => {
    staged.current.forEach((item) => URL.revokeObjectURL(item.url));
    staged.current = [];
    state.current.pending = false;
    setPending([]);
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; staged.current.forEach((item) => URL.revokeObjectURL(item.url)); };
  }, []);

  const stage = useCallback((files: File[]) => {
    if (!mounted.current || state.current.disabled || state.current.pending) return;
    if (!files.length) { notify("剪貼簿沒有可貼上的圖片，請使用「複製圖片」後再試。"); return; }
    if (files.some((file) => !supported.includes(file.type))) { notify("僅支援 JPG、PNG 或 WebP 圖片。"); return; }
    if (files.some((file) => file.size > 25 * 1024 * 1024)) { notify("單張圖片不可超過 25 MiB。"); return; }
    if (files.reduce((sum, file) => sum + file.size, 0) > 75 * 1024 * 1024) { notify("一次貼上圖片總大小不可超過 75 MiB，請分批貼上。"); return; }
    if (files.length + state.current.count > 30) { notify("單一案件最多 30 張照片。"); return; }
    staged.current = files.map((file) => ({ file, url: URL.createObjectURL(file), id: crypto.randomUUID() }));
    state.current.pending = true;
    setPending(staged.current);
    notify("");
  }, [notify]);

  useEffect(() => {
    function onPaste(event: ClipboardEvent) {
      const target = event.target;
      if (target instanceof Element && target.closest("input, textarea, [contenteditable]:not([contenteditable='false'])")) return;
      const files = Array.from(event.clipboardData?.files || []);
      if (!files.length) return;
      event.preventDefault();
      stage(files);
    }
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [stage]);

  async function read() {
    if (state.current.disabled || state.current.pending || state.current.reading) return;
    state.current.reading = true;
    setReading(true);
    notify("");
    try {
      const files: File[] = [];
      const nativeRead = window.pywebview?.api.read_clipboard_images;
      if (nativeRead) {
        const result = await nativeRead();
        if ("error" in result) throw new Error(result.error);
        for (const item of result.images) {
          const bytes = Uint8Array.from(atob(item.data), (char) => char.charCodeAt(0));
          files.push(new File([bytes], item.name, { type: item.mime }));
        }
      } else {
        if (!navigator.clipboard?.read) throw new Error("此環境無法讀取剪貼簿，請在照片區按 Ctrl+V 或使用匯入照片。");
        const items = await navigator.clipboard.read();
        for (const item of items) {
          const type = supported.find((mime) => item.types.includes(mime));
          if (type) {
            const blob = await item.getType(type);
            files.push(new File([blob], `貼上-${Date.now()}-${files.length + 1}.${extension[type]}`, { type }));
          }
        }
      }
      stage(files);
    } catch (cause) {
      if (mounted.current) notify(cause instanceof Error && !["NotAllowedError", "NotFoundError"].includes(cause.name)
        && !cause.message.includes("NotAllowedError") ? cause.message : "無法讀取剪貼簿，請允許存取、重新複製，或在照片區按 Ctrl+V。");
    } finally {
      state.current.reading = false;
      if (mounted.current) setReading(false);
    }
  }
  return { pending, reading, read, close };
}
