import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import PhotoPreview from "./PhotoPreview";

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: 400, height: 300, left: 0, top: 0, right: 400, bottom: 300,
    x: 0, y: 0, toJSON: () => ({}),
  });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function preview() {
  const result = render(<PhotoPreview src="portrait.png" alt="直向照片" />);
  const img = screen.getByAltText("直向照片");
  Object.defineProperties(img, {
    naturalWidth: { value: 800 }, naturalHeight: { value: 1600 },
  });
  fireEvent.load(img);
  return { ...result, img };
}

it("直向照片預設完整顯示，縮放後可一鍵還原", () => {
  const { img } = preview();
  expect(screen.getByLabelText("預覽縮放比例")).toHaveTextContent("100%");
  expect(img).toHaveStyle({ objectFit: "contain", position: "absolute" });
  fireEvent.click(screen.getByRole("button", { name: "放大圖片" }));
  expect(screen.getByLabelText("預覽縮放比例")).toHaveTextContent("125%");
  fireEvent.click(screen.getByRole("button", { name: "顯示完整圖片" }));
  expect(img.style.transform).toBe("translate(0px, 0px) scale(1)");
});

it("滾輪及鍵盤可縮放，放大後可移動，且不會移到圖片外", () => {
  const { img } = preview();
  const stage = screen.getByRole("region", { name: "可縮放圖片預覽" });
  fireEvent.wheel(stage, { deltaY: -400, clientX: 200, clientY: 150 });
  expect(img.style.transform).not.toContain("scale(1)");
  fireEvent.keyDown(stage, { key: "ArrowDown" });
  expect(img.style.transform).not.toContain("translate(0px, 0px)");
  fireEvent.keyDown(stage, { key: "Home" });
  expect(img.style.transform).toBe("translate(0px, 0px) scale(1)");
  for (let index = 0; index < 30; index++) fireEvent.keyDown(stage, { key: "+" });
  expect(screen.getByLabelText("預覽縮放比例")).toHaveTextContent("800%");
  expect(screen.getByRole("button", { name: "放大圖片" })).toBeDisabled();
});

it("拖曳移動照片，切換照片時恢復完整顯示", () => {
  const { img, rerender } = preview();
  const stage = screen.getByRole("region", { name: "可縮放圖片預覽" });
  fireEvent.keyDown(stage, { key: "+" });
  fireEvent.pointerDown(stage, { button: 0, pointerId: 1, clientX: 200, clientY: 150 });
  fireEvent.pointerMove(stage, { pointerId: 1, clientX: 200, clientY: 170 });
  fireEvent.pointerUp(stage, { pointerId: 1 });
  expect(img.style.transform).toBe("translate(0px, 20px) scale(1.25)");
  rerender(<PhotoPreview key="second" src="landscape.png" alt="橫向照片" />);
  expect(screen.getByAltText("橫向照片").style.transform).toBe("translate(0px, 0px) scale(1)");
});
