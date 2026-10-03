import type { CaseRecord } from "./types";

type Props = {
  cases: CaseRecord[];
  buildings: string[];
  materials: string[];
  query: string;
  caseBuilding: string;
  caseMaterial: string;
  casePage: number;
  casePages: number;
  caseTotal: number;
  scanning: boolean;
  onQueryChange: (value: string) => void;
  onBuildingChange: (value: string) => void;
  onMaterialChange: (value: string) => void;
  onPageChange: (updater: (page: number) => number) => void;
  onRescan: () => void;
  onOpenOverview: (view: "gallery" | "names") => void;
  onView: (id: string) => void;
  onOpenFolder: (id: string) => void;
};

export default function CaseListSection(props: Props) {
  const { cases, buildings, materials, query, caseBuilding, caseMaterial, casePage, casePages, caseTotal, scanning } = props;
  return (
    <section className="case-list-section">
      <div className="list-header">
        <div><span className="eyebrow">ARCHIVE</span><h2>案件清單</h2><p>依棟別、定址碼、材料或問題快速尋找</p></div>
        <div className="list-filters">
          <button type="button" className="rescan-cases" onClick={props.onRescan} disabled={scanning}>
            {scanning ? "掃描中…" : "掃描目前資料夾"}
          </button>
          <button type="button" className="overview-open" onClick={() => props.onOpenOverview("gallery")}>
            照片總覽
          </button>
          <button type="button" className="overview-open" onClick={() => props.onOpenOverview("names")}>
            檔名清單
          </button>
          <input type="search" value={query} onChange={(event) => props.onQueryChange(event.target.value)} placeholder="搜尋定址碼或問題…" aria-label="搜尋案件" />
          <select value={caseBuilding} onChange={(event) => props.onBuildingChange(event.target.value)} aria-label="依棟別篩選"><option value="">全部棟別</option>{buildings.map((item) => <option key={item}>{item}</option>)}</select>
          <select value={caseMaterial} onChange={(event) => props.onMaterialChange(event.target.value)} aria-label="依材料篩選"><option value="">全部材料</option>{materials.map((item) => <option key={item}>{item}</option>)}</select>
        </div>
      </div>
      <div className="case-table-wrap">
        <table className="case-table">
          <thead><tr><th>日期</th><th>位置</th><th>定址碼</th><th>材料／問題</th><th>照片</th><th>狀態</th><th><span className="sr-only">操作</span></th></tr></thead>
          <tbody>
            {!cases.length ? (
              <tr><td colSpan={7} className="empty-row">尚無案件。儲存第一筆後會顯示在這裡。</td></tr>
            ) : cases.map((item) => (
              <tr key={item.id}>
                <td>{item.work_date}</td><td><strong>{item.building}</strong> {item.floor}</td><td><code>{item.address_code}</code></td>
                <td><strong>{item.material}</strong><span className="issue-summary">{item.issues.join("／")}</span></td><td>{item.photo_count} 張</td>
                <td><span className={`status ${item.is_complete ? "complete" : "incomplete"}`}>{item.is_complete ? "完整" : `缺 ${item.missing_roles.join("、")}`}</span></td>
                <td className="row-actions"><button type="button" onClick={() => props.onView(item.id)}>檢視</button><button type="button" onClick={() => props.onOpenFolder(item.id)}>開啟資料夾</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <nav className="case-pagination" aria-label="案件清單分頁">
        <span>共 {caseTotal} 筆，第 {casePage}／{casePages} 頁</span>
        <div>
          <button type="button" disabled={casePage <= 1} onClick={() => props.onPageChange((page) => page - 1)}>上一頁</button>
          <button type="button" disabled={casePage >= casePages} onClick={() => props.onPageChange((page) => page + 1)}>下一頁</button>
        </div>
      </nav>
    </section>
  );
}
