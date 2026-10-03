export type ReferenceValues = {
  buildings: string[];
  materials: string[];
  issues: string[];
  photo_roles: string[];
  custom_materials: string[];
  custom_issues: string[];
};

export type PhotoDraft = {
  id: string;
  file: File;
  url: string;
  role: string;
};

export type SavedPhoto = {
  id: string;
  role: string;
  stored_name: string;
  original_name: string;
  content_url: string;
};

export type CaseRecord = {
  id: string;
  work_date: string;
  building: string;
  floor: string;
  address_code: string;
  material: string;
  issues: string[];
  location: string;
  notes: string;
  folder_path: string;
  photo_count: number;
  is_complete: boolean;
  missing_roles: string[];
  photos?: SavedPhoto[];
};

export type StorageMonth = {
  name: string;
  subfolders: string[];
};

export type StorageTree = {
  root: string;
  target_month: string;
  month_exists: boolean;
  months: StorageMonth[];
};

export type FreeScanResult = {
  root: string;
  subfolders: string[];
};

export type StorageMode = "month" | "free";

export type CustomOptionKind = "material" | "issue";

export type OverviewPhoto = {
  name: string;
  role: string;
  url: string;
  thumb_url: string;
};

export type OverviewCase = {
  id: string;
  title: string;
  work_date: string;
  material: string;
  building: string;
  photos: OverviewPhoto[];
};

export type OverviewData = {
  source: "db" | "disk";
  total: number;
  filenames: string;
  cases: OverviewCase[];
};
