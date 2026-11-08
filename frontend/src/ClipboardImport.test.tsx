import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App";
import { FALLBACK_REFERENCES } from "./utils";

const image = () => new File(["synthetic"], "貼上測試.png", { type: "image/png" });
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => ({ ok: true,
    json: async () => String(input).includes("ui-preferences")
      ? { layout: "classic", panel_position: "right", tile_size: "large", panel_collapsed: false }
      : String(input).includes("reference-values") ? FALLBACK_REFERENCES : ({ items: [], total: 0, pages: 1, path: "", subfolders: [] }) })));
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: {
    read: vi.fn(async () => [{ types: ["text/html", "image/png"], getType: vi.fn(async () => image()) }]),
  } });
});
afterEach(() => { cleanup(); delete window.pywebview; vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("貼上按鈕先顯示確認窗，取消不新增照片且釋放預覽", async () => {
  const revoke = vi.spyOn(URL, "revokeObjectURL");
  const { container } = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "貼上圖片" }));
  const dialog = await screen.findByRole("dialog", { name: "確認貼上圖片" });
  expect(within(dialog).getByRole("img")).toBeInTheDocument();
  expect(container.querySelectorAll(".thumbnail-item")).toHaveLength(0);
  expect(window.matlensDesktopState?.dirty).toBe(false);
  fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(container.querySelectorAll(".thumbnail-item")).toHaveLength(0);
  expect(revoke).toHaveBeenCalled();
});

it("確認後追加照片且不改原照片角色，同一次多種格式只加入一張", async () => {
  const { container } = render(<App />);
  fireEvent.drop(screen.getByRole("button", { name: /拉入 3～5 張照片/ }), {
    dataTransfer: { files: [new File(["old"], "original.jpg", { type: "image/jpeg" })] },
  });
  await screen.findByText("original.jpg");
  fireEvent.change(screen.getByLabelText("這張照片是"), { target: { value: "完成" } });
  fireEvent.click(screen.getByRole("button", { name: "貼上圖片" }));
  fireEvent.click(await screen.findByRole("button", { name: "加入本次照片" }));
  await waitFor(() => expect(container.querySelectorAll(".thumbnail-item")).toHaveLength(2));
  expect(container.querySelector(".thumbnail-copy strong")).toHaveTextContent("完成");
  expect(window.matlensDesktopState?.dirty).toBe(true);
});

it("匯入區 Ctrl+V 開確認窗，備註的文字貼上不被攔截", async () => {
  render(<App />);
  const notes = screen.getByLabelText("備註");
  const editable = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(editable, "clipboardData", { value: { files: [image()] } });
  notes.dispatchEvent(editable);
  expect(editable.defaultPrevented).toBe(false);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.paste(screen.getByRole("region", { name: "本次照片" }), { clipboardData: { files: [image()] } });
  expect(await screen.findByRole("dialog", { name: "確認貼上圖片" })).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("拒絕讀取、空剪貼簿與超大圖片不新增照片", async () => {
  vi.mocked(navigator.clipboard.read).mockRejectedValueOnce(new Error("NotAllowedError"));
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "貼上圖片" }));
  expect(await screen.findByText(/無法讀取剪貼簿/)).toBeInTheDocument();
  vi.mocked(navigator.clipboard.read).mockResolvedValueOnce([]);
  fireEvent.click(screen.getByRole("button", { name: "貼上圖片" }));
  expect(await screen.findByText(/沒有可貼上的圖片/)).toBeInTheDocument();
  const huge = image();
  Object.defineProperty(huge, "size", { value: 26 * 1024 * 1024 });
  fireEvent.paste(screen.getByRole("region", { name: "本次照片" }), { clipboardData: { files: [huge] } });
  expect(await screen.findByText(/25 MiB/)).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("桌面版按鈕使用原生剪貼簿橋接，仍需確認才匯入", async () => {
  const state = { current: "0.5.6", version: "", phase: "idle", channel: "stable", progress: 0,
    message: "可檢查更新", notes: "", installable: false };
  window.pywebview = { api: {
    update_state: vi.fn(async () => undefined), update_status: vi.fn(async () => state),
    check_update: vi.fn(async () => state), download_update: vi.fn(async () => state),
    install_update: vi.fn(async () => ({ ok: false })),
    read_clipboard_images: vi.fn(async () => ({ images: [{ name: "LINE圖片.png", mime: "image/png", data: btoa("test") }] })),
  } };
  const { container } = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "貼上圖片" }));
  const dialog = await screen.findByRole("dialog", { name: "確認貼上圖片" });
  expect(window.pywebview.api.read_clipboard_images).toHaveBeenCalledTimes(1);
  expect(navigator.clipboard.read).not.toHaveBeenCalled();
  expect(container.querySelectorAll(".thumbnail-item")).toHaveLength(0);
  fireEvent.click(within(dialog).getByRole("button", { name: "加入本次照片" }));
  await screen.findByText("LINE圖片.png");
  expect(container.querySelectorAll(".thumbnail-item")).toHaveLength(1);
});
