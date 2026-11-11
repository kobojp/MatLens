import { useEffect, useRef } from "react";

export type EditPreview = {
  old_path: string; new_path: string; rename: boolean;
  photos_changed: boolean; added: number; removed: number;
  requires_managed_confirmation: boolean;
};

export default function EditConfirmation({ plan, onChoose, returnFocus }: {
  plan: EditPreview; onChoose: (confirmed: boolean) => void; returnFocus: HTMLElement | null;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancel.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      requestAnimationFrame(() => {
        if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
      });
    };
  }, [returnFocus]);
  return <div className="modal-backdrop edit-confirm-backdrop">
    <div ref={panel} className="edit-confirmation" role="dialog" aria-modal="true"
      aria-labelledby="edit-confirm-title" aria-describedby="edit-confirm-description"
      onKeyDown={event => {
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onChoose(false); }
        if (event.key === "Tab") {
          const buttons = panel.current?.querySelectorAll<HTMLButtonElement>("button");
          if (!buttons?.length) return;
          const first = buttons[0], last = buttons[buttons.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      }}>
      <header className="edit-confirm-header">
        <span className="edit-confirm-icon" aria-hidden="true">↻</span>
        <div><h2 id="edit-confirm-title">確認儲存案件更正</h2>
          <p id="edit-confirm-description">請核對下列內容，確認後將更新同一筆案件。</p></div>
      </header>
      <div className="edit-confirm-body">
        <div className="edit-confirm-paths">
          {[["原資料夾", plan.old_path], [plan.rename ? "變更後資料夾" : "儲存資料夾（位置不變）", plan.new_path]].map(([label, path], index) =>
            <section key={label} className={`edit-confirm-path ${index ? "is-target" : ""}`} aria-label={label}>
              <span>{label}</span><strong>{path.split(/[\\/]/).filter(Boolean).pop()}</strong><code>{path}</code>
            </section>)}
        </div>
        {!plan.rename && <p className="edit-confirm-hint">資料夾位置不變，僅儲存本次更正內容。</p>}
        {plan.photos_changed && <section className="edit-confirm-photos" aria-label="照片變動">
          <strong>照片變動</strong><p>新增 {plan.added} 張、移除 {plan.removed} 張</p>
          <p>角色與順序依畫面保存；變更前的原案照片會保留備份。</p>
        </section>}
        {plan.requires_managed_confirmation && <p className="edit-confirm-warning">
          確認儲存即表示：這是整理後的案件資料夾，並非原始來源照片目錄。
        </p>}
      </div>
      <footer className="edit-confirm-footer">
        <button ref={cancel} type="button" className="button secondary" onClick={() => onChoose(false)}>取消</button>
        <button type="button" className="button primary" onClick={() => onChoose(true)}>確認儲存</button>
      </footer>
    </div>
  </div>;
}
