import type { CustomOptionKind } from "./types";

type Props = {
  kind: CustomOptionKind;
  /** 「材料」「問題」：用於按鈕與輸入框的 accessible name */
  noun: string;
  legend: string;
  single?: boolean;
  items: string[];
  customItems: string[];
  isActive: (item: string) => boolean;
  onSelect: (item: string) => void;
  deletingOption: string;
  editing: boolean;
  editorValue: string;
  saving: boolean;
  onStartAdd: () => void;
  onEditorChange: (value: string) => void;
  onAdd: () => void;
  onCancel: () => void;
  onDelete: (item: string) => void;
};

export default function OptionField(props: Props) {
  const { kind, noun } = props;
  return (
    <fieldset>
      <legend className="option-legend">
        <span>{props.legend}</span>
        <button type="button" aria-label={`新增${noun}選項`} onClick={props.onStartAdd}>＋ 新增</button>
      </legend>
      <div className={props.single ? "choices single-choice" : "choices"}>
        {props.items.map((item) => {
          const isCustom = props.customItems.includes(item);
          const active = props.isActive(item);
          return (
            <span key={item} className={`choice-option ${active ? "active" : ""}`}>
              <button type="button" className="choice-value" aria-pressed={active} onClick={() => props.onSelect(item)}>{item}</button>
              {isCustom && (
                <button
                  type="button"
                  className="choice-delete"
                  aria-label={`刪除${noun}選項 ${item}`}
                  disabled={props.deletingOption === `${kind}:${item}`}
                  onClick={() => props.onDelete(item)}
                >×</button>
              )}
            </span>
          );
        })}
      </div>
      {props.editing && (
        <div className="custom-option-editor">
          <input
            aria-label={`自訂${noun}名稱`}
            autoFocus
            maxLength={40}
            value={props.editorValue}
            onChange={(event) => props.onEditorChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                props.onAdd();
              }
            }}
            placeholder={`輸入${noun}名稱`}
          />
          <button type="button" className="confirm" disabled={props.saving} onClick={props.onAdd}>加入{noun}</button>
          <button type="button" onClick={props.onCancel}>取消</button>
        </div>
      )}
    </fieldset>
  );
}
