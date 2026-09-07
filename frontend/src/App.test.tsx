import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const references = {
  buildings: ["二門診"],
  materials: ["底座"],
  issues: ["錯誤設備"],
  photo_roles: ["前", "中", "完成", "樓層", "位置", "設備標籤", "其他"],
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
              : { items: [], total: 0 };
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
              : { items: [], total: 0 };
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
