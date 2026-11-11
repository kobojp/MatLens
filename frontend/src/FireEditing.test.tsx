import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App";
import { FALLBACK_REFERENCES } from "./utils";
import { DEFAULT_UI } from "./useUIPreferences";
import type { UIPreferences } from "./useUIPreferences";

let includeMaterial = true;
let customDetails: string[] = [];
let caseData: Record<string, unknown>;
let uiPrefs: UIPreferences;
beforeEach(() => {
  includeMaterial = true; customDetails = [];
  uiPrefs = { ...DEFAULT_UI };
  caseData = { id: "saved", work_date: "2026-11-10", building: "二門診", floor: "1F", address_code: "M3-01",
    material: "底座", issues: ["火警", "底座故障"], location: "", notes: "原備註", photo_count: 1,
    is_complete: false, missing_roles: ["中"], folder_path: "底座/原資料夾", original_path: "C:\\舊目錄\\底座\\原資料夾",
    storage_root: "C:\\舊目錄", name_with_sequence: false, edit_token: "a".repeat(64), naming: { include_date: false, include_material: true, separator: "-" },
    photos: [{ id: "photo", role: "前", original_name: "source.jpg", stored_name: "前.jpg", content_url: "/api/photos/photo/content" }] };
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); let data: unknown = {};
    if (url === "/api/settings/fire-naming") {
      if (init?.method === "POST") includeMaterial = JSON.parse(String(init.body)).include_material;
      data = { include_material: includeMaterial };
    } else if (url === "/api/reference-values/fire-detail") {
      const value = JSON.parse(String(init?.body)).value;
      customDetails = init?.method === "DELETE" ? customDetails.filter(item => item !== value) : [...customDetails, value];
      data = { value };
    } else if (url === "/api/reference-values") data = { ...FALLBACK_REFERENCES, fire_details: ["無回應", ...customDetails], custom_fire_details: customDetails };
    else if (url.includes("ui-preferences")) data = uiPrefs;
    else if (url.includes("storage-selection")) data = { path: "C:\\新目錄", subfolder: "底座", with_date: false };
    else if (url.includes("storage/scan")) data = { root: "C:\\新目錄", subfolders: ["底座"] };
    else if (url.endsWith("/edit-preview")) data = { old_path: caseData.original_path, new_path: "C:\\舊目錄\\底座\\更正名稱", rename: true };
    else if (url === "/api/cases/saved/save" && init?.method === "POST") {
      const change = JSON.parse(String((init.body as FormData).get("change")));
      const retained = caseData.photos as Array<{ id: string; role: string }>;
      const files = (init.body as FormData).getAll("photos") as File[];
      const savedPhotos = change.photos.map((item: { photo_id?: string; upload_index?: number; role: string }) => item.photo_id
        ? ({ ...retained.find(photo => photo.id === item.photo_id), role: item.role })
        : ({ id: `new-${item.upload_index}`, role: item.role, original_name: files[item.upload_index!].name,
             stored_name: `${item.role}.jpg`, content_url: `/api/photos/new-${item.upload_index}/content` }));
      caseData = { ...caseData, ...change, photos: savedPhotos, edit_token: "b".repeat(64), original_path: "C:\\舊目錄\\底座\\更正名稱" };
      data = caseData;
    }
    else if (url.endsWith("/edit")) data = caseData;
    else if (url.startsWith("/api/cases?")) data = { items: [caseData], total: 1, pages: 1 };
    return { ok: true, json: async () => data } as Response;
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function confirmEdit() {
  const dialog = await screen.findByRole("dialog", { name: "確認儲存案件更正" });
  expect(within(dialog).getByText("C:\\舊目錄\\底座\\更正名稱")).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "確認儲存" }));
}

it("可在火警細項新增，保持火警且不加入一般問題，命名開關重開仍還原", async () => {
  const app = render(<App />);
  await screen.findByRole("radio", { name: "底座" });
  fireEvent.change(screen.getByLabelText("樓層"), { target: { value: "1F" } });
  fireEvent.change(screen.getByLabelText("定址碼"), { target: { value: "M3-01" } });
  fireEvent.click(screen.getByRole("button", { name: "火警" }));
  fireEvent.click(screen.getByRole("button", { name: "新增火警細項選項" }));
  fireEvent.change(screen.getByLabelText("自訂火警細項名稱"), { target: { value: "底座故障" } });
  fireEvent.click(screen.getByRole("button", { name: "加入火警細項" }));
  expect(await screen.findByRole("button", { name: "火警細項 底座故障" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "火警" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.queryByRole("button", { name: "底座故障" })).toBeNull();
  fireEvent.click(screen.getByLabelText("火警資料夾名稱包含材料"));
  await waitFor(() => expect(includeMaterial).toBe(false));
  expect(screen.getAllByText(/二門診1F M3-01 火警 底座故障/).length).toBeGreaterThan(0);
  app.unmount(); render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "火警" }));
  await waitFor(() => expect(screen.getByLabelText("火警資料夾名稱包含材料")).not.toBeChecked());
});

it.each(["classic", "right", "top"])("%s 配置編輯載入既有案件，以主工作區更新同一 id 並保留背景草稿", async mode => {
  uiPrefs = { ...DEFAULT_UI, layout: mode === "classic" ? "classic" : "tiles", panel_position: mode === "top" ? "top" : "right" };
  render(<App />);
  fireEvent.change(screen.getByLabelText("備註"), { target: { value: "新增案件的背景草稿" } });
  fireEvent.click(await screen.findByRole("button", { name: "編輯案件 M3-01" }));
  await screen.findByRole("button", { name: "取消編輯" });
  await waitFor(() => expect(screen.getByLabelText("定址碼")).toHaveValue("M3-01"));
  expect(screen.queryByRole("dialog", { name: "編輯既有案件" })).toBeNull();
  expect(screen.getByLabelText("定址碼")).toHaveValue("M3-01");
  expect(screen.getAllByRole("img")[0]).toHaveAttribute("src", expect.stringContaining("/api/photos/photo/content"));
  fireEvent.change(screen.getByLabelText("定址碼"), { target: { value: "M3-02" } });
  fireEvent.click(screen.getByRole("button", { name: "儲存變更" }));
  await confirmEdit();
  await screen.findByText(/案件更正已儲存/);
  expect(screen.getByLabelText("定址碼")).toHaveValue("M3-02");
  await waitFor(() => expect(window.matlensDesktopState?.dirty).toBe(true));
  expect(window.confirm).not.toHaveBeenCalled();
  const updates = vi.mocked(fetch).mock.calls.filter(([url, init]) => String(url).endsWith("/save") && init?.method === "POST");
  expect(updates).toHaveLength(1);
  expect(String(updates[0][0])).toBe("/api/cases/saved/save");
  expect(JSON.parse(String((updates[0][1]?.body as FormData).get("change"))).address_code).toBe("M3-02");
  expect(vi.mocked(fetch).mock.calls.filter(([url, init]) => String(url) === "/api/cases" && init?.method === "POST")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "取消編輯" }));
  expect(screen.getByLabelText("備註")).toHaveValue("新增案件的背景草稿");
});

it("火警命名保存失敗可重試，不顯示假成功", async () => {
  const original = globalThis.fetch;
  let fail = true;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("fire-naming") && init?.method === "POST" && fail) {
      return { ok: false, json: async () => ({ detail: "磁碟寫入失敗" }) } as Response;
    }
    return original(input, init);
  }));
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "火警" }));
  await waitFor(() => expect(screen.getByLabelText("火警資料夾名稱包含材料")).toBeEnabled());
  fireEvent.click(screen.getByLabelText("火警資料夾名稱包含材料"));
  expect(await screen.findByText("儲存失敗：磁碟寫入失敗")).toBeInTheDocument();
  expect(includeMaterial).toBe(true);
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "重試火警命名設定" }));
  await waitFor(() => expect(includeMaterial).toBe(false));
  await screen.findByText("火警命名設定已儲存");
});

it("新增細項請求中取消並切換一般問題，晚到的結果不改案件選擇", async () => {
  const original = globalThis.fetch;
  let finish: (() => void) | undefined;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("reference-values/fire-detail") && init?.method === "POST") {
      await new Promise<void>(resolve => { finish = resolve; });
    }
    return original(input, init);
  }));
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "火警" }));
  fireEvent.click(screen.getByRole("button", { name: "新增火警細項選項" }));
  fireEvent.change(screen.getByLabelText("自訂火警細項名稱"), { target: { value: "晚到細項" } });
  fireEvent.click(screen.getByRole("button", { name: "加入火警細項" }));
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  fireEvent.click(screen.getByRole("button", { name: "故障" }));
  finish!();
  await screen.findByText("火警細項選項已新增。");
  expect(screen.getByRole("button", { name: "故障" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.queryByRole("button", { name: "火警細項 晚到細項" })).toBeNull();
});

it("刪除自訂細項只清除細項，保留火警", async () => {
  customDetails = ["底座故障"];
  render(<App />);
  await screen.findByRole("radio", { name: "底座" });
  fireEvent.click(screen.getByRole("button", { name: "火警" }));
  fireEvent.click(screen.getByRole("button", { name: "火警細項 底座故障" }));
  fireEvent.click(screen.getByRole("button", { name: "刪除火警細項選項 底座故障" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "火警細項 底座故障" })).toBeNull());
  expect(screen.getByRole("button", { name: "火警" })).toHaveAttribute("aria-pressed", "true");
  expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("已儲存案件不受影響"));
});

it("刪除同名的一般問題，不清除獨立火警細項的選取", async () => {
  customDetails = ["底座故障"];
  const original = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) === "/api/reference-values") {
      const response = await original(input, init);
      return { ok: true, json: async () => ({ ...await response.json(),
        issues: [...FALLBACK_REFERENCES.issues, "底座故障"], custom_issues: ["底座故障"] }) } as Response;
    }
    return original(input, init);
  }));
  render(<App />);
  await screen.findByRole("button", { name: "刪除問題選項 底座故障" });
  fireEvent.click(screen.getByRole("button", { name: "火警" }));
  fireEvent.click(screen.getByRole("button", { name: "火警細項 底座故障" }));
  fireEvent.click(screen.getByRole("button", { name: "刪除問題選項 底座故障" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "刪除問題選項 底座故障" })).toBeNull());
  expect(screen.getByRole("button", { name: "火警細項 底座故障" })).toHaveAttribute("aria-pressed", "true");
});

it("取消置中確認窗不送出更新，保留更正內容並還原焦點", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "編輯案件 M3-01" }));
  await screen.findByRole("button", { name: "取消編輯" });
  await waitFor(() => expect(screen.getByLabelText("定址碼")).toHaveValue("M3-01"));
  expect(screen.queryByRole("dialog", { name: "編輯既有案件" })).toBeNull();
  await screen.findByLabelText("定址碼");
  fireEvent.change(screen.getByLabelText("定址碼"), { target: { value: "M3-02" } });
  const save = screen.getByRole("button", { name: "儲存變更" });
  save.focus(); fireEvent.click(save);
  const dialog = await screen.findByRole("dialog", { name: "確認儲存案件更正" });
  expect(within(dialog).getByText("C:\\舊目錄\\底座\\原資料夾")).toBeInTheDocument();
  expect(document.body.style.overflow).toBe("hidden");
  expect(within(dialog).getByRole("button", { name: "取消" })).toHaveFocus();
  expect(screen.getByRole("region", { name: "編輯模式", hidden: true }).closest("main")).toHaveAttribute("inert");
  expect(window.matlensDesktopState?.saving).toBe(true);
  fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
  await waitFor(() => expect(save).toHaveFocus());
  expect(document.body.style.overflow).not.toBe("hidden");
  expect(screen.getByLabelText("定址碼")).toHaveValue("M3-02");
  await waitFor(() => expect(screen.getByRole("button", { name: "取消編輯" })).toBeEnabled());
  expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith("/save") && init?.method === "POST")).toBe(false);
  vi.mocked(window.confirm).mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "取消編輯" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "取消編輯" })).toBeNull());
});

it("編輯儲存衝突保留更正內容，重新載入才還原", async () => {
  const original = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/save") && init?.method === "POST") return { ok: false, json: async () => ({ detail: "案件已變更，請重新載入" }) } as Response;
    return original(input, init);
  }));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "編輯案件 M3-01" }));
  await screen.findByRole("button", { name: "取消編輯" });
  await waitFor(() => expect(screen.getByLabelText("定址碼")).toHaveValue("M3-01"));
  expect(screen.queryByRole("dialog", { name: "編輯既有案件" })).toBeNull();
  await screen.findByLabelText("定址碼");
  fireEvent.change(screen.getByLabelText("備註"), { target: { value: "更正備註" } });
  fireEvent.click(screen.getByRole("button", { name: "儲存變更" }));
  await confirmEdit();
  await screen.findByText("案件已變更，請重新載入");
  expect(screen.getByLabelText("備註")).toHaveValue("更正備註");
  fireEvent.click(screen.getByRole("button", { name: "重新載入案件" }));
  await waitFor(() => expect(screen.getByLabelText("備註")).toHaveValue("原備註"));
});

it("既有照片直接進入主圖塊，可放大、調整角色並追加照片，只上傳新增檔案", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "編輯案件 M3-01" }));
  await screen.findByRole("button", { name: "放大 source.jpg" });
  fireEvent.click(screen.getByRole("button", { name: "放大 source.jpg" }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "關閉放大圖片" }));
  fireEvent.change(screen.getByLabelText("source.jpg 的角色"), { target: { value: "完成" } });
  fireEvent.drop(screen.getByRole("region", { name: "本次照片" }), { dataTransfer: { files: [new File(["new"], "new.jpg", { type: "image/jpeg" })] } });
  expect(screen.getByLabelText("source.jpg 的角色")).toHaveValue("完成");
  fireEvent.click(screen.getByRole("button", { name: "將 new.jpg 往前移" }));
  fireEvent.click(screen.getByRole("button", { name: "儲存變更" }));
  await confirmEdit();
  await screen.findByText(/案件更正已儲存/);
  const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url) === "/api/cases/saved/save")!;
  const form = call[1]!.body as FormData;
  expect((form.getAll("photos") as File[]).map(file => file.name)).toEqual(["new.jpg"]);
  expect(JSON.parse(String(form.get("change"))).photos).toEqual([
    { upload_index: 0, role: "中" }, { photo_id: "photo", role: "完成" },
  ]);
  expect(screen.getByRole("button", { name: "取消編輯" })).toBeEnabled();
  expect(window.matlensDesktopState?.dirty).toBe(false);
});

it("取消編輯還原原新增草稿與照片，既有照片不是新增上傳檔", async () => {
  const revoke = vi.spyOn(URL, "revokeObjectURL");
  render(<App />);
  fireEvent.change(screen.getByLabelText("備註"), { target: { value: "原草稿" } });
  fireEvent.drop(screen.getByRole("region", { name: "本次照片" }), { dataTransfer: { files: [new File(["draft"], "draft.jpg", { type: "image/jpeg" })] } });
  fireEvent.click(await screen.findByRole("button", { name: "編輯案件 M3-01" }));
  await screen.findByRole("button", { name: "移除 source.jpg" });
  fireEvent.click(screen.getByRole("button", { name: "移除 source.jpg" }));
  fireEvent.click(screen.getByRole("button", { name: "取消編輯" }));
  expect(screen.getByLabelText("備註")).toHaveValue("原草稿");
  expect(screen.getByRole("button", { name: "放大 draft.jpg" })).toBeInTheDocument();
  expect(revoke).not.toHaveBeenCalled();
});

it("確認視窗以 Esc 取消後草稿仍可接續，重複確認只送出一次", async () => {
  const original = globalThis.fetch;
  let finish: (() => void) | undefined;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith("/save")) await new Promise<void>(resolve => { finish = resolve; });
    return original(input, init);
  }));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "編輯案件 M3-01" }));
  await screen.findByRole("button", { name: "放大 source.jpg" });
  fireEvent.change(screen.getByLabelText("定址碼"), { target: { value: "M3-02" } });
  fireEvent.click(screen.getByRole("button", { name: "儲存變更" }));
  fireEvent.keyDown(await screen.findByRole("dialog", { name: "確認儲存案件更正" }), { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(screen.getByLabelText("定址碼")).toHaveValue("M3-02");
  expect(screen.getByRole("button", { name: "放大 source.jpg" })).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/save"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "儲存變更" }));
  const dialog = await screen.findByRole("dialog", { name: "確認儲存案件更正" });
  const confirm = within(dialog).getByRole("button", { name: "確認儲存" });
  fireEvent.click(confirm); fireEvent.click(confirm);
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/save"))).toHaveLength(1);
  expect(window.matlensDesktopState?.saving).toBe(true);
  finish!();
  await screen.findByText(/案件更正已儲存/);
});
