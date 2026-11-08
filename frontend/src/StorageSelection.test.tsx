import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App";

const path = "C:\\現場照片";
let saved: { path: string; subfolder: string; with_date: boolean };
let folders: string[];
let failSave: boolean;

beforeEach(() => {
  saved = { path, subfolder: "底座", with_date: false };
  folders = ["三分考克", "底座", "磁力門扣"];
  failSave = false;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    let data: object = { items: [], total: 0, page: 1, pages: 1 };
    if (url === "/api/settings/ui-preferences") data = {
      layout: "classic", panel_position: "right", tile_size: "large", panel_collapsed: false,
    };
    else if (url === "/api/settings/storage-selection") {
      if (init?.method === "POST") {
        if (failSave) return { ok: false, json: async () => ({ detail: "設定寫入失敗" }) } as Response;
        saved = JSON.parse(String(init.body));
      }
      data = { ...saved };
    } else if (url.includes("storage/scan")) data = { root: path, subfolders: folders };
    else if (url === "/api/settings/storage") data = { path };
    else if (url.includes("reference-values")) data = {
      buildings: ["二門診"], materials: ["底座", "探頭"], issues: ["錯誤設備"],
      photo_roles: ["前", "中", "後"], custom_materials: [], custom_issues: [],
    };
    else if (url.includes("database")) data = { path: "C:\\MatLens\\matlens.db" };
    return { ok: true, json: async () => data } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("桌面橋接尚未準備好時仍可載入介面與儲存設定", async () => {
  vi.stubGlobal("pywebview", { api: {} });
  render(<App />);
  expect(await screen.findByRole("radio", { name: "底座" })).toBeChecked();
});

it("移除月份模式，還原非第一項子資料夾及日期設定而不覆寫", async () => {
  render(<App />);
  expect(await screen.findByRole("radio", { name: "底座" })).toBeChecked();
  expect(screen.queryByRole("tab", { name: "月份模式" })).not.toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: /日期前綴/ })).not.toBeChecked();
  expect(screen.getByText("目前儲存資料夾：底座")).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
});

it("切換資料夾會保存，重新掃描與重掛載仍保留，同時與材料分開", async () => {
  const app = render(<App />);
  fireEvent.click(await screen.findByRole("radio", { name: "磁力門扣" }));
  await waitFor(() => expect(saved.subfolder).toBe("磁力門扣"));
  fireEvent.click(screen.getByRole("button", { name: "探頭" }));
  expect(screen.getByText("目前儲存資料夾：磁力門扣")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "掃描" }));
  await waitFor(() => expect(screen.getByRole("radio", { name: "磁力門扣" })).toBeChecked());
  app.unmount();
  render(<App />);
  expect(await screen.findByRole("radio", { name: "磁力門扣" })).toBeChecked();
});

it("失效選擇不默默換成第一項，輸入未掃描路徑時不沿用舊標示", async () => {
  saved.subfolder = "不存在";
  render(<App />);
  expect(await screen.findByRole("radio", { name: "三分考克" })).not.toBeChecked();
  expect(screen.getByText(/請重新選擇子資料夾/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("radio", { name: "底座" }));
  expect(screen.getByText("目前儲存資料夾：底座")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("掃描路徑"), { target: { value: "C:\\其他位置" } });
  expect(screen.queryByText("目前儲存資料夾：底座")).not.toBeInTheDocument();
});

it("保存失敗不能顯示已儲存，日期前綴也會持久化", async () => {
  render(<App />);
  await screen.findByRole("radio", { name: "底座" });
  fireEvent.click(screen.getByRole("checkbox", { name: /日期前綴/ }));
  await waitFor(() => expect(saved.with_date).toBe(true));
  failSave = true;
  fireEvent.click(screen.getByRole("radio", { name: "磁力門扣" }));
  expect(await screen.findByText(/儲存失敗/)).toBeInTheDocument();
  expect(saved.subfolder).toBe("底座");
});

it("快速切換按順序寫入最後的選擇，儲存期間阻止桌面更新或關閉", async () => {
  const originalFetch = globalThis.fetch;
  let release: (() => void) | undefined;
  let writes = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) === "/api/settings/storage-selection" && init?.method === "POST") {
      if (++writes === 1) await new Promise<void>((resolve) => { release = resolve; });
    }
    return originalFetch(input, init);
  }));
  render(<App />);
  fireEvent.click(await screen.findByRole("radio", { name: "三分考克" }));
  fireEvent.click(screen.getByRole("radio", { name: "磁力門扣" }));
  await waitFor(() => expect(release).toBeTypeOf("function"));
  expect(writes).toBe(1);
  expect(window.matlensDesktopState?.saving).toBe(true);
  release!();
  await waitFor(() => expect(saved.subfolder).toBe("磁力門扣"));
  await waitFor(() => expect(window.matlensDesktopState?.saving).toBe(false));
  expect(window.matlensDesktopState?.dirty).toBe(false);
});
