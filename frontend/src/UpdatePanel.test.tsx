import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import UpdatePanel, { type UpdateState } from "./UpdatePanel";

const available: UpdateState = { current: "0.3.0", version: "0.4.0", channel: "stable", phase: "available",
  progress: 0, message: "有新版本可下載。", notes: "更新說明", installable: true };

beforeEach(() => {
  window.matlensDesktopState = { dirty: false, saving: false };
  window.pywebview = { api: {
    update_state: vi.fn(async () => undefined),
    update_status: vi.fn(async () => available),
    check_update: vi.fn(async () => available),
    download_update: vi.fn(async () => ({ ...available, phase: "ready", message: "驗證完成" })),
    install_update: vi.fn(async () => ({ ok: true })),
  } };
  vi.stubGlobal("confirm", vi.fn(() => true));
});
afterEach(() => { cleanup(); delete window.pywebview; delete window.matlensDesktopState; vi.unstubAllGlobals(); });

it("預設只檢查正式版，不自動下载安裝，並可手動切換測試版", async () => {
  render(<UpdatePanel />);
  fireEvent.click(await screen.findByRole("button", { name: /關於與更新/ }));
  expect(window.pywebview!.api.check_update).toHaveBeenCalledWith("stable");
  expect(window.pywebview!.api.download_update).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("更新頻道"), { target: { value: "preview" } });
  fireEvent.click(screen.getByRole("button", { name: "檢查更新" }));
  expect(window.pywebview!.api.check_update).toHaveBeenCalledWith("preview");
});

it("下載後有未儲存照片時不可安裝；清除後才可確認重啟", async () => {
  render(<UpdatePanel />);
  fireEvent.click(await screen.findByRole("button", { name: /關於與更新/ }));
  fireEvent.click(screen.getByRole("button", { name: "下載更新" }));
  const install = await screen.findByRole("button", { name: "安裝並重新啟動" });
  window.matlensDesktopState!.dirty = true;
  fireEvent.click(install);
  expect(await screen.findByRole("alert")).toHaveTextContent("請先儲存");
  expect(window.pywebview!.api.install_update).not.toHaveBeenCalled();
  window.matlensDesktopState!.dirty = false;
  fireEvent.click(install);
  await waitFor(() => expect(window.pywebview!.api.install_update).toHaveBeenCalledWith(false, false));
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
});

it("使用者取消更新時不關閉程式", async () => {
  vi.stubGlobal("confirm", vi.fn(() => false));
  window.pywebview!.api.update_status = vi.fn(async () => ({ ...available, phase: "ready" }));
  render(<UpdatePanel />);
  fireEvent.click(await screen.findByRole("button", { name: /關於與更新/ }));
  fireEvent.click(screen.getByRole("button", { name: "安裝並重新啟動" }));
  expect(window.pywebview!.api.install_update).not.toHaveBeenCalled();
});

it("桌面拒絕安裝時解除操作鎖定並顯示錯誤", async () => {
  const onInstalling = vi.fn();
  window.pywebview!.api.update_status = vi.fn(async () => ({ ...available, phase: "ready" }));
  window.pywebview!.api.install_update = vi.fn(async () => ({ error: "請先儲存案件" }));
  render(<UpdatePanel onInstalling={onInstalling} />);
  fireEvent.click(await screen.findByRole("button", { name: /關於與更新/ }));
  fireEvent.click(screen.getByRole("button", { name: "安裝並重新啟動" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("請先儲存案件");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(onInstalling).toHaveBeenLastCalledWith(false);
});

it("可攜版不允許下載安裝，離線錯誤仍可重新檢查", async () => {
  window.pywebview!.api.update_status = vi.fn(async () => ({ ...available, installable: false }));
  window.pywebview!.api.check_update = vi.fn(async () => { throw new Error("offline"); });
  render(<UpdatePanel />);
  fireEvent.click(await screen.findByRole("button", { name: /關於與更新/ }));
  expect(screen.getByRole("button", { name: "下載更新" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "檢查更新" }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "檢查更新" })).toBeEnabled();
});
