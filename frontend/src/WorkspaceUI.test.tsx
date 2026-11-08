import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App";
import { DEFAULT_UI, type UIPreferences } from "./useUIPreferences";
import { FALLBACK_REFERENCES } from "./utils";

let saved: UIPreferences;
let failSave: boolean;
beforeEach(() => {
  saved = { ...DEFAULT_UI };
  failSave = false;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    let data: unknown = { items: [], total: 0, pages: 1 };
    if (url === "/api/settings/ui-preferences") {
      if (init?.method === "POST") {
        if (failSave) return { ok: false, json: async () => ({ detail: "寫入失敗" }) } as Response;
        saved = JSON.parse(String(init.body));
      }
      data = { ...saved };
    } else if (url.includes("storage-selection")) data = { path: "C:\\照片", subfolder: "底座", with_date: false };
    else if (url.includes("storage/scan")) data = { root: "C:\\照片", subfolders: ["底座"] };
    else if (url.includes("reference-values")) data = FALLBACK_REFERENCES;
    else if (url.includes("database")) data = { path: "C:\\MatLens\\matlens.db" };
    return { ok: true, json: async () => data } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function upload() {
  await screen.findByRole("radio", { name: "底座" });
  fireEvent.drop(screen.getByRole("region", { name: "本次照片" }), { dataTransfer: { files: [
    new File(["first"], "first.jpg", { type: "image/jpeg" }),
    new File(["second"], "second.jpg", { type: "image/jpeg" }),
  ] } });
  await screen.findByText("first.jpg");
}
async function settings() { fireEvent.click(screen.getByRole("tab", { name: "設定" })); }
function workspace() { fireEvent.click(screen.getByRole("tab", { name: "工作區" })); }

it("預設藍白圖塊，點圖才放大，換圖還原縮放並在關閉後還原焦點", async () => {
  const revoke = vi.spyOn(URL, "revokeObjectURL");
  const { container } = render(<App />);
  await upload();
  expect(container.querySelector(".app-shell")).toHaveClass("theme-blue");
  expect(container.querySelector(".interactive-preview")).toBeNull();
  const open = screen.getByRole("button", { name: "放大 first.jpg" });
  fireEvent.click(open);
  const dialog = await screen.findByRole("dialog", { name: /前/ });
  fireEvent.click(within(dialog).getByRole("button", { name: "放大圖片" }));
  expect(within(dialog).getByLabelText("預覽縮放比例")).toHaveTextContent("125%");
  fireEvent.click(within(dialog).getByRole("button", { name: "下一張照片" }));
  expect(within(dialog).getByLabelText("預覽縮放比例")).toHaveTextContent("100%");
  fireEvent.keyDown(dialog, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(open);
  expect(revoke).not.toHaveBeenCalled();
  revoke.mockRestore();
});

it("切換原版與新版、尺寸和位置後，草稿及照片角色仍存在，偏好重掛載還原", async () => {
  const app = render(<App />);
  await upload();
  fireEvent.change(screen.getByLabelText("樓層"), { target: { value: "3F" } });
  fireEvent.change(screen.getByLabelText("備註"), { target: { value: "保留草稿" } });
  fireEvent.change(screen.getByLabelText("first.jpg 的角色"), { target: { value: "中" } });
  await settings();
  fireEvent.click(screen.getByRole("radio", { name: "原版三欄" }));
  workspace();
  expect(screen.getByLabelText("樓層")).toHaveValue("3F");
  expect(screen.getByLabelText("備註")).toHaveValue("保留草稿");
  expect(screen.getByRole("region", { name: "可縮放圖片預覽" })).toBeInTheDocument();
  await settings();
  fireEvent.click(screen.getByRole("radio", { name: "照片圖塊（新版）" }));
  fireEvent.click(screen.getByRole("radio", { name: "上方" }));
  fireEvent.click(screen.getByRole("radio", { name: "中" }));
  await waitFor(() => expect(saved).toEqual({ ...DEFAULT_UI, panel_position: "top", tile_size: "medium" }));
  workspace();
  expect(screen.getByLabelText("first.jpg 的角色")).toHaveValue("中");
  expect(screen.getByLabelText("備註")).toHaveValue("保留草稿");
  app.unmount();
  const reopened = render(<App />);
  await waitFor(() => expect(reopened.container.querySelector(".workspace")).toHaveClass("panel-top", "tiles-medium"));
});

it("上方資料收合顯示摘要，隱藏必填欄位出錯時展開並聚焦", async () => {
  saved.panel_position = "top";
  render(<App />);
  await upload();
  const firstSection = document.querySelector(".workspace")!.firstElementChild as HTMLElement;
  expect(within(firstSection).getByRole("button", { name: "收合案件資料" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("定址碼"), { target: { value: "M2-5" } });
  fireEvent.click(screen.getByRole("button", { name: "收合案件資料" }));
  expect(document.querySelector(".case-summary")).toHaveTextContent(/二門診.*M2-5.*底座/);
  await waitFor(() => expect(saved.panel_collapsed).toBe(true));
  const floor = document.querySelector<HTMLInputElement>('input[placeholder="例如 3F、B2"]')!;
  fireEvent.invalid(floor);
  await waitFor(() => expect(screen.getByLabelText("樓層")).toBeVisible());
  await waitFor(() => expect(document.activeElement).toBe(floor));
  await waitFor(() => expect(saved.panel_collapsed).toBe(false));
});

it("恢復預設僅重設介面，失敗提示可重試且不清除正在整理的照片", async () => {
  render(<App />);
  await upload();
  fireEvent.change(screen.getByLabelText("樓層"), { target: { value: "B2" } });
  await settings();
  failSave = true;
  fireEvent.click(screen.getByRole("radio", { name: "上方" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("儲存失敗");
  expect(window.matlensDesktopState?.dirty).toBe(true);
  failSave = false;
  fireEvent.click(screen.getByRole("button", { name: "重試儲存介面設定" }));
  await waitFor(() => expect(saved.panel_position).toBe("top"));
  fireEvent.click(screen.getByRole("button", { name: "恢復預設版面" }));
  await waitFor(() => expect(saved).toEqual(DEFAULT_UI));
  workspace();
  expect(screen.getByLabelText("樓層")).toHaveValue("B2");
  expect(screen.getByText("first.jpg")).toBeInTheDocument();
  expect(screen.getByText("目前儲存資料夾：底座")).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.filter(([url, init]) =>
    String(url).includes("storage-selection") && init?.method === "POST")).toHaveLength(0);
});

it("初次載入不寫入，快速切換依序保存最後選擇並同步桌面儲存保護", async () => {
  const original = globalThis.fetch;
  let finishLoad: (() => void) | undefined;
  let finishWrite: (() => void) | undefined;
  let writes = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) === "/api/settings/ui-preferences") {
      if (!init?.method) await new Promise<void>(resolve => { finishLoad = resolve; });
      else if (++writes === 1) await new Promise<void>(resolve => { finishWrite = resolve; });
    }
    return original(input, init);
  }));
  render(<App />);
  await settings();
  expect(screen.getByRole("radio", { name: "原版三欄" })).toBeDisabled();
  expect(writes).toBe(0);
  finishLoad!();
  await waitFor(() => expect(screen.getByRole("radio", { name: "原版三欄" })).toBeEnabled());
  fireEvent.click(screen.getByRole("radio", { name: "上方" }));
  fireEvent.click(screen.getByRole("radio", { name: "中" }));
  await waitFor(() => expect(finishWrite).toBeTypeOf("function"));
  expect(window.matlensDesktopState?.saving).toBe(true);
  expect(writes).toBe(1);
  finishWrite!();
  await waitFor(() => expect(saved).toEqual({ ...DEFAULT_UI, panel_position: "top", tile_size: "medium" }));
  await waitFor(() => expect(window.matlensDesktopState?.saving).toBe(false));
  expect(window.matlensDesktopState?.dirty).toBe(false);
});

it("排序與角色操作不打開看圖，鍵盤看圖可換圖且不改原角色", async () => {
  const { container } = render(<App />);
  await upload();
  fireEvent.change(screen.getByLabelText("first.jpg 的角色"), { target: { value: "設備標籤" } });
  const items = container.querySelectorAll(".thumbnail-item");
  fireEvent.dragStart(items[0]);
  fireEvent.drop(items[1], { dataTransfer: { files: [] } });
  fireEvent.dragEnd(items[0]);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByLabelText("first.jpg 的角色")).toHaveValue("設備標籤");
  await new Promise(resolve => setTimeout(resolve, 0));
  fireEvent.click(screen.getByRole("button", { name: "放大 second.jpg" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.keyDown(within(dialog).getByRole("region", { name: "可縮放圖片預覽" }), { key: "ArrowRight" });
  expect(within(dialog).getByRole("heading")).toHaveTextContent("設備標籤");
  fireEvent.click(within(dialog).getByRole("button", { name: "關閉放大圖片" }));
  expect(screen.getByLabelText("first.jpg 的角色")).toHaveValue("設備標籤");
});

it("讀取設定失敗可明確恢復預設，尚未讀取成功前不自動覆蓋", async () => {
  const original = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) === "/api/settings/ui-preferences" && !init?.method) {
      return { ok: false, json: async () => ({ detail: "介面設定損壞" }) } as Response;
    }
    return original(input, init);
  }));
  render(<App />);
  await settings();
  expect(await screen.findByText("介面設定損壞")).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "原版三欄" })).toBeDisabled();
  expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "恢復預設版面" }));
  await waitFor(() => expect(screen.getByRole("radio", { name: "原版三欄" })).toBeEnabled());
});

it("原版三欄不套用新版上方收合配置，切回新版仍還原原本選擇", async () => {
  saved = { ...DEFAULT_UI, layout: "classic", panel_position: "top", panel_collapsed: true };
  const { container } = render(<App />);
  await screen.findByRole("radio", { name: "底座" });
  await waitFor(() => expect(container.querySelector(".workspace")).toHaveClass("layout-classic", "panel-right"));
  expect(screen.getByLabelText("樓層")).toBeVisible();
  await settings();
  fireEvent.click(screen.getByRole("radio", { name: "照片圖塊（新版）" }));
  workspace();
  expect(container.querySelector(".workspace")).toHaveClass("panel-top");
  expect(screen.getByRole("button", { name: "展開案件資料" })).toBeInTheDocument();
});
