import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import EditConfirmation from "./EditConfirmation";

afterEach(() => { cleanup(); document.body.style.overflow = ""; });
const plan = { old_path: "C:\\照片\\原資料夾", new_path: "C:\\照片\\新資料夾", rename: true,
  photos_changed: true, added: 1, removed: 2, requires_managed_confirmation: true };

it("分區呈現完整路徑、照片摘要及來源確認，焦點從取消開始並限制在視窗內", () => {
  const onChoose = vi.fn();
  render(<EditConfirmation plan={plan} onChoose={onChoose} returnFocus={null} />);
  const dialog = screen.getByRole("dialog", { name: "確認儲存案件更正" });
  expect(screen.getByText(plan.old_path)).toBeInTheDocument();
  expect(screen.getByText(plan.new_path)).toBeInTheDocument();
  expect(screen.getByText(/新增 1 張、移除 2 張/)).toBeInTheDocument();
  expect(screen.getByText(/並非原始來源照片目錄/)).toBeInTheDocument();
  const cancel = screen.getByRole("button", { name: "取消" });
  const confirm = screen.getByRole("button", { name: "確認儲存" });
  expect(cancel).toHaveFocus();
  fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true });
  expect(confirm).toHaveFocus();
  fireEvent.keyDown(confirm, { key: "Tab" });
  expect(cancel).toHaveFocus();
  fireEvent.click(dialog.parentElement!);
  expect(onChoose).not.toHaveBeenCalled();
  fireEvent.keyDown(cancel, { key: "Escape" });
  expect(onChoose).toHaveBeenCalledExactlyOnceWith(false);
});

it("只在確認按鈕明確操作時同意儲存，純更名不顯示照片變動", () => {
  const onChoose = vi.fn();
  render(<EditConfirmation plan={{ ...plan, photos_changed: false, requires_managed_confirmation: false }} onChoose={onChoose} returnFocus={null} />);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Enter" });
  expect(onChoose).not.toHaveBeenCalled();
  expect(screen.queryByText(/新增 1 張/)).toBeNull();
  expect(screen.queryByText(/並非原始來源照片目錄/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "確認儲存" }));
  expect(onChoose).toHaveBeenCalledExactlyOnceWith(true);
});

it("不更名時顯示原位置不變，卸載時還原原本的捲動設定", () => {
  document.body.style.overflow = "auto";
  const app = render(<EditConfirmation plan={{ ...plan, rename: false }} onChoose={vi.fn()} returnFocus={null} />);
  expect(screen.getByText(/資料夾位置不變/)).toBeInTheDocument();
  app.unmount();
  expect(document.body.style.overflow).toBe("auto");
});
