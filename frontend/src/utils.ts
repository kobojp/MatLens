import type { PhotoDraft, ReferenceValues } from "./types";

export const FALLBACK_REFERENCES: ReferenceValues = {
  buildings: ["二門診", "三門診", "思源", "致德", "身障", "長青", "立體", "臨床"],
  materials: ["底座", "探頭", "模組", "磁力門扣"],
  issues: ["錯誤設備", "無回應", "火警", "漏水", "自檢異常", "鏽蝕", "故障"],
  photo_roles: ["前", "中", "後", "完成", "樓層", "位置", "設備標籤", "其他"],
  custom_materials: [],
  custom_issues: [],
};

export function localDate(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export const DEFAULT_ROLE_ORDER = ["前", "中", "後"];

export function moveItem<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

// 依「預設角色順序」從第一個開始分配；照片比角色多時沿用最後一個角色
export function initialRoles(count: number, order: string[] = DEFAULT_ROLE_ORDER): string[] {
  const roles = order.length ? order : DEFAULT_ROLE_ORDER;
  return Array.from({ length: count }, (_, index) => roles[Math.min(index, roles.length - 1)]);
}

export function safeName(value: string): string {
  return value.replace(/[<>:"/\\|?*\x00-\x1f]/g, "-").replace(/\s+/g, " ").trim();
}

export function roleFileNames(photos: PhotoDraft[], withSequence: boolean): string[] {
  const totals = new Map<string, number>();
  const seen = new Map<string, number>();
  photos.forEach((photo) => totals.set(photo.role, (totals.get(photo.role) ?? 0) + 1));
  return photos.map((photo, index) => {
    const current = (seen.get(photo.role) ?? 0) + 1;
    seen.set(photo.role, current);
    // 同角色多張：前-1、前-2、前-3；只有一張就只有角色名
    const suffix = totals.get(photo.role)! > 1 ? `-${current}` : "";
    const extension = photo.file.name.split(".").pop()?.toLowerCase() || "jpg";
    const prefix = withSequence ? `${String(index + 1).padStart(2, "0")}_` : "";
    return `${prefix}${photo.role}${suffix}.${extension}`;
  });
}

export function errorText(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "操作失敗，請稍後再試。";
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return "案件資料格式不正確。";
}
