import type { CaseRecord } from "./types";

type Props = {
  selectedCase: CaseRecord;
  onClose: () => void;
};

export default function CaseModal({ selectedCase, onClose }: Props) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <section className="case-modal" role="dialog" aria-modal="true" aria-labelledby="case-title">
        <header><div><span className="eyebrow">案件照片</span><h2 id="case-title">{selectedCase.building} {selectedCase.floor} · {selectedCase.address_code}</h2><p>{selectedCase.work_date}　{selectedCase.material}　{selectedCase.issues.join("／")}</p></div><button type="button" aria-label="關閉案件" onClick={onClose}>×</button></header>
        <div className="saved-photo-grid">
          {selectedCase.photos?.map((photo) => <figure key={photo.id}><img src={photo.content_url} alt={`${photo.role} ${photo.original_name}`} /><figcaption><strong>{photo.role}</strong><span>{photo.stored_name}</span></figcaption></figure>)}
        </div>
      </section>
    </div>
  );
}
