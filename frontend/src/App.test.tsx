import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const references = {
  buildings: ["二門診"],
  materials: ["底座"],
  issues: ["錯誤設備"],
  photo_roles: ["前", "中", "後", "完成", "樓層", "位置", "設備標籤", "其他"],
  custom_materials: [],
  custom_issues: [],
};

const currentMonth = `${new Date().getMonth() + 1}月`;

const storageTree = {
  root: "C:\\MatLens照片",
  target_month: currentMonth,
  month_exists: true,
  months: [{ name: currentMonth, subfolders: ["底座", "探頭"] }],
};

describe("照片拖放", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const payload = init?.method === "DELETE"
        ? { type: "material", value: "消防泵" }
        : url.endsWith("reference-values/material")
        ? { type: "material", value: "消防泵" }
        : url.endsWith("reference-values/issue")
          ? { type: "issue", value: "壓力不足" }
          : url.includes("reference-values")
            ? references
            : url.includes("settings/storage/tree")
              ? storageTree
              : url.includes("settings/storage")
              ? { path: "C:\\MatLens照片" }
              : { items: [], total: 0, page: 1, page_size: 20, pages: 1 };
      return { ok: true, json: async () => payload } as Response;
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("已有一張照片時仍可拖入第二張", async () => {
    render(<App />);
    const section = screen.getByRole("region", { name: "本次照片" });
    const first = new File(["first"], "first.jpg", { type: "image/jpeg" });
    const second = new File(["second"], "second.jpg", { type: "image/jpeg" });

    fireEvent.drop(screen.getByRole("button", { name: /拉入 3～5 張照片/ }), {
      dataTransfer: { files: [first] },
    });
    expect(await screen.findByText("first.jpg")).toBeInTheDocument();

    fireEvent.drop(section, { dataTransfer: { files: [second] } });

    await waitFor(() => expect(screen.getByText("second.jpg")).toBeInTheDocument());
    expect(screen.getByText("2 張")).toBeInTheDocument();
    expect(window.matlensDesktopState?.dirty).toBe(true);
  });

  it("四張照片依前中後完成自動排列", async () => {
    const { container } = render(<App />);
    const files = ["a", "b", "c", "d"].map(
      (name) => new File([name], `${name}.jpg`, { type: "image/jpeg" }),
    );

    fireEvent.drop(screen.getByRole("button", { name: /拉入 3～5 張照片/ }), {
      dataTransfer: { files },
    });

    await screen.findByText("d.jpg");
    expect(
      [...container.querySelectorAll(".thumbnail-copy strong")].map((node) => node.textContent),
    ).toEqual(["前", "中", "後", "完成"]);
    expect(screen.getByRole("combobox", { name: "這張照片是" }).querySelectorAll("option")[2])
      .toHaveTextContent("後");
  });

  it("案件清單可重新掃描目前資料夾並使用分頁", async () => {
    let rescanned = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      let payload: object;
      if (url.includes("reference-values")) payload = references;
      else if (url.includes("settings/storage/tree")) payload = storageTree;
      else if (url.includes("settings/storage")) payload = { path: "C:\\MatLens照片" };
      else if (url.includes("cases/rescan")) {
        rescanned = true;
        payload = {
          registered: 21,
          unchanged: 18,
          relinked: 1,
          imported: 63,
          removed: 2,
          unresolved: 0,
          ambiguous: 0,
          skipped: 0,
        };
      } else {
        payload = {
          items: [{
            id: "case-1",
            work_date: "2026-09-22",
            building: "二門診",
            floor: "3F",
            address_code: rescanned ? "UPDATED" : "OLD",
            material: "底座",
            issues: ["錯誤設備"],
            location: "",
            notes: "",
            folder_path: rescanned ? "新路徑" : "舊路徑",
            photo_count: 3,
            is_complete: true,
            missing_roles: [],
          }],
          total: 21,
          page: url.includes("page=2") ? 2 : 1,
          page_size: 20,
          pages: 2,
        };
      }
      return { ok: true, json: async () => payload } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await screen.findByText("共 21 筆，第 1／2 頁");
    fireEvent.click(screen.getByRole("button", { name: "下一頁" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("page=2")));

    fireEvent.click(screen.getByRole("button", { name: "掃描目前資料夾" }));
    await screen.findByText("掃描完成，已重新連結 1 筆案件、新增 63 筆案件、清除 2 筆失效紀錄。");
    await screen.findByText("UPDATED");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/cases/rescan?path=C%3A%5CMatLens%E7%85%A7%E7%89%87"),
      { method: "POST" },
    );
  });

  it("自由路徑案件掃描使用目前選擇的子目錄", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const payload = url.includes("reference-values")
        ? references
        : url.includes("settings/storage/tree")
          ? storageTree
          : url.includes("settings/storage/scan")
            ? { root: "C:\\現場照片", subfolders: ["底座"] }
            : url.includes("cases/rescan")
              ? { registered: 0, unchanged: 0, relinked: 0, imported: 69, removed: 0, unresolved: 0, ambiguous: 0, skipped: 0 }
              : url.includes("settings/storage")
                ? { path: "C:\\MatLens照片" }
                : { items: [], total: 0, page: 1, page_size: 20, pages: 1 };
      return { ok: true, json: async () => payload } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(screen.getByRole("tab", { name: "自由路徑" }));
    fireEvent.change(screen.getByLabelText("掃描路徑"), { target: { value: "C:\\現場照片" } });
    fireEvent.click(screen.getByRole("button", { name: "掃描" }));
    await screen.findByRole("radio", { name: "底座" });
    fireEvent.click(screen.getByRole("button", { name: "掃描目前資料夾" }));

    await screen.findByText("掃描完成，已新增 69 筆案件。");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/cases/rescan?path=C%3A%5C%E7%8F%BE%E5%A0%B4%E7%85%A7%E7%89%87%5C%E5%BA%95%E5%BA%A7"),
      { method: "POST" },
    );
  });

  it("桌面版辨識未儲存欄位，並阻止拖放圖片導致頁面離開", async () => {
    render(<App />);
    expect(window.matlensDesktopState?.dirty).toBe(false);
    fireEvent.change(screen.getByPlaceholderText("例如 3F、B2"), { target: { value: "3F" } });
    expect(window.matlensDesktopState?.dirty).toBe(true);
    const dropped = new Event("drop", { bubbles: true, cancelable: true });
    document.dispatchEvent(dropped);
    expect(dropped.defaultPrevented).toBe(true);
  });

  it("可新增並立即選用自訂材料", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "新增材料選項" }));
    fireEvent.change(screen.getByLabelText("自訂材料名稱"), {
      target: { value: "消防泵" },
    });
    fireEvent.click(screen.getByRole("button", { name: "加入材料" }));

    const customMaterial = await screen.findByRole("button", { name: "消防泵" });
    expect(customMaterial).toHaveAttribute("aria-pressed", "true");
  });

  it("可刪除自訂材料但不顯示內建材料的刪除鈕", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "新增材料選項" }));
    fireEvent.change(screen.getByLabelText("自訂材料名稱"), {
      target: { value: "消防泵" },
    });
    fireEvent.click(screen.getByRole("button", { name: "加入材料" }));

    const deleteButton = await screen.findByRole("button", { name: "刪除材料選項 消防泵" });
    expect(screen.queryByRole("button", { name: "刪除材料選項 底座" })).not.toBeInTheDocument();
    fireEvent.click(deleteButton);

    await waitFor(() => expect(screen.queryByRole("button", { name: "消防泵" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "底座" })).toHaveAttribute("aria-pressed", "true");
  });

  it("依日期預選月份並列出掃描到的子目錄", async () => {
    render(<App />);

    await waitFor(() => (
      expect(screen.getByRole("combobox", { name: "月份資料夾" })).toHaveValue(currentMonth)
    ));
    expect(screen.getByRole("combobox", { name: "儲存子目錄" })).toHaveValue("底座");
    expect(screen.getAllByText(new RegExp(`${currentMonth}\\\\底座`))).toHaveLength(2);
  });

  it("月份不存在時可批次建立常用與自訂子目錄", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const requestedMonth = url.includes("2026-10-05") ? "10月" : currentMonth;
      const isCreated = fetchMock.mock.calls.some(([, options]) => options?.method === "POST");
      const payload = url.includes("reference-values")
        ? references
        : url.includes("settings/storage/tree")
          ? {
              root: "C:\\MatLens照片",
              target_month: requestedMonth,
              month_exists: requestedMonth !== "10月" || isCreated,
              months: requestedMonth === "10月" && !isCreated
                ? storageTree.months
                : [...storageTree.months, { name: "10月", subfolders: ["底座", "探頭", "模組"] }],
            }
          : url.endsWith("settings/storage/folders")
            ? { root: "C:\\MatLens照片", month: { name: "10月", subfolders: ["底座", "探頭", "模組"] } }
            : url.includes("settings/storage")
              ? { path: "C:\\MatLens照片" }
              : { items: [], total: 0, page: 1, page_size: 20, pages: 1 };
      return { ok: true, json: async () => payload } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.change(screen.getByLabelText("維修日期"), { target: { value: "2026-10-05" } });
    expect(await screen.findByText(/找不到「10月」資料夾/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("自訂子目錄名稱"), { target: { value: "模組" } });
    fireEvent.click(screen.getByRole("button", { name: "建立 10月與子目錄" }));

    await waitFor(() => expect(screen.getByRole("combobox", { name: "儲存子目錄" })).toHaveValue("模組"));
    const createCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("settings/storage/folders"));
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      month: "10月",
      subfolders: ["底座", "探頭", "模組"],
    });
  });
});
