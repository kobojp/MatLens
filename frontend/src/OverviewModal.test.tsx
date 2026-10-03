import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OverviewModal from "./OverviewModal";

const overview = {
  source: "db",
  total: 2,
  filenames: "二門診3F M3-07 錯誤設備\n01_前.jpg\n02_中.jpg\n\n三門診2F A1-01 火警-無回應\n01_前.jpg",
  cases: [
    {
      id: "a",
      title: "二門診3F M3-07 錯誤設備",
      work_date: "2026-09-21",
      material: "底座",
      building: "二門診",
      photos: [
        { name: "01_前.jpg", role: "前", url: "/p/1/content", thumb_url: "/p/1/thumbnail" },
        { name: "02_中.jpg", role: "中", url: "/p/2/content", thumb_url: "/p/2/thumbnail" },
      ],
    },
    {
      id: "b",
      title: "三門診2F A1-01 火警-無回應",
      work_date: "2026-09-22",
      material: "底座",
      building: "三門診",
      photos: [{ name: "01_前.jpg", role: "前", url: "/p/3/content", thumb_url: "/p/3/thumbnail" }],
    },
  ],
};

function renderModal(view: "gallery" | "names" = "gallery", scanPath = "C:\\照片") {
  return render(
    <OverviewModal
      buildings={["二門診", "三門診"]}
      materials={["底座", "探頭"]}
      defaultMaterial="底座"
      scanPath={scanPath}
      initialView={view}
      onClose={() => undefined}
    />,
  );
}

describe("照片總覽", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let autoScanEnabled: boolean;

  beforeEach(() => {
    autoScanEnabled = true;
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const payload = url.includes("overview-auto-scan")
        ? { enabled: autoScanEnabled }
        : url.includes("/api/cases/rescan")
          ? { imported: 1, relinked: 0 }
          : url.includes("/api/overview/export")
            ? { path: "C:\\exports\\x.html", size_bytes: 2097152, total: 2 }
            : overview;
      void init;
      return { ok: true, json: async () => payload } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("顯示材料總數、案件標題與每張照片的檔名", async () => {
    renderModal();

    expect(await screen.findByRole("heading", { name: "底座共 2 筆" })).toBeInTheDocument();
    expect(screen.getByText("二門診3F M3-07 錯誤設備")).toBeInTheDocument();
    expect(screen.getAllByText("01_前.jpg")).toHaveLength(2);
    expect(screen.getByText("02_中.jpg")).toBeInTheDocument();
    const requested = fetchMock.mock.calls.map(([url]) => String(url));
    expect(requested.some((url) => url.includes("/api/overview?source=db&material=%E5%BA%95%E5%BA%A7"))).toBe(true);
  });

  it("開啟時自動掃描只匯入不刪除（prune=false）", async () => {
    renderModal();
    await screen.findByRole("heading", { name: "底座共 2 筆" });

    const rescan = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/cases/rescan"));
    expect(String(rescan?.[0])).toContain("prune=false");
    expect(await screen.findByText("自動掃描已更新 1 筆案件。")).toBeInTheDocument();
  });

  it("關閉自動掃描後會儲存設定，且不再掃描", async () => {
    autoScanEnabled = false;
    renderModal();
    await screen.findByRole("heading", { name: "底座共 2 筆" });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/cases/rescan"))).toBe(false);

    fireEvent.click(screen.getByRole("checkbox", { name: /自動掃描/ }));
    const saved = fetchMock.mock.calls.find(
      ([url, init]) => String(url).includes("overview-auto-scan") && (init as RequestInit | undefined)?.method === "POST",
    );
    expect(JSON.parse(String((saved?.[1] as RequestInit).body))).toEqual({ enabled: true });
  });

  it("點縮圖可放大並切換上一張／下一張", async () => {
    renderModal();
    fireEvent.click(await screen.findByRole("button", { name: "放大 二門診3F M3-07 錯誤設備 01_前.jpg" }));

    const dialog = screen.getByRole("dialog", { name: "放大檢視" });
    expect(dialog.querySelector("img")).toHaveAttribute("src", "/p/1/content");
    expect(screen.getByRole("button", { name: "上一張" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "下一張" }));
    expect(dialog.querySelector("img")).toHaveAttribute("src", "/p/2/content");
    fireEvent.click(screen.getByRole("button", { name: "關閉放大檢視" }));
    expect(screen.queryByRole("dialog", { name: "放大檢視" })).not.toBeInTheDocument();
  });

  it("檔名清單依案件分組，可一鍵複製", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderModal("names");

    const box = (await screen.findByLabelText("檔名清單內容")) as HTMLTextAreaElement;
    expect(box.value).toBe(overview.filenames);
    fireEvent.click(screen.getByRole("button", { name: "全部複製" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(overview.filenames));
    expect(await screen.findByRole("button", { name: "已複製" })).toBeInTheDocument();
  });

  it("可輸出輕量版與獨立版網頁", async () => {
    renderModal();
    await screen.findByRole("heading", { name: "底座共 2 筆" });
    fireEvent.click(screen.getByRole("button", { name: "另存網頁（輕量）" }));
    expect(await screen.findByText(/已輸出 2 筆（2.0 MB）：C:\\exports\\x\.html/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "另存網頁（獨立）" }));

    await waitFor(() => {
      const modes = fetchMock.mock.calls
        .filter(([url]) => String(url).includes("/api/overview/export"))
        .map(([, init]) => JSON.parse(String((init as RequestInit).body)).mode);
      expect(modes).toEqual(["light", "standalone"]);
    });
  });
});
