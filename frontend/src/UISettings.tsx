import type useUIPreferences from "./useUIPreferences";

export default function UISettings({ preferences }: { preferences: ReturnType<typeof useUIPreferences> }) {
  const { value, ready, loading, error, status, failed, update, reset } = preferences;
  return <section className="ui-settings" aria-labelledby="ui-settings-title">
    <header><h2 id="ui-settings-title">介面配置</h2><p>變更立即預覽並保存，重新開啟後沿用。</p></header>
    {error && <div role="alert" className="preferences-error">{error}
      <button type="button" disabled={loading || preferences.saving} onClick={() => void preferences.reload()}>重新讀取介面設定</button>
    </div>}
    <fieldset disabled={!ready}><legend>工作區樣式</legend>
      <div className="layout-options">{([
        ["classic", "原版三欄", "左側縮圖、中央預覽、右側案件資料；保留原配色。"],
        ["tiles", "照片圖塊（新版）", "大型照片圖塊、點圖放大，採藍白配色。"],
      ] as const).map(([layout, title, description]) => <label key={layout} className={`layout-option ${value.layout === layout ? "active" : ""}`}>
        <span><input type="radio" name="workspace-layout" aria-label={title} value={layout} checked={value.layout === layout}
          onChange={() => update({ layout })} />{title}</span>
        <small>{description}</small>
        <div aria-hidden="true" className={`layout-sketch sketch-${layout} position-${value.panel_position}`}><i /><i /><i /><i /></div>
      </label>)}</div>
    </fieldset>
    <fieldset disabled={!ready || value.layout === "classic"}><legend>案件資料位置</legend>
      <div className="setting-choices">{([["right", "右側"], ["top", "上方"]] as const).map(([position, title]) =>
        <label key={position}><input type="radio" name="case-panel-position" value={position}
          checked={value.panel_position === position} onChange={() => update({ panel_position: position })} />{title}</label>)}</div>
      <p>上方模式可收合資料區，為照片保留更多空間。</p>
    </fieldset>
    <fieldset disabled={!ready || value.layout === "classic"}><legend>照片圖塊尺寸</legend>
      <div className="setting-choices">{([["medium", "中"], ["large", "大"]] as const).map(([size, title]) =>
        <label key={size}><input type="radio" name="photo-tile-size" value={size}
          checked={value.tile_size === size} onChange={() => update({ tile_size: size })} />{title}</label>)}</div>
    </fieldset>
    <footer><div><button className="button secondary" type="button" disabled={loading} onClick={reset}>恢復預設版面</button>
      <p>恢復新版圖塊、右側資料、大圖塊及資料展開。照片、案件內容與儲存位置會保留。</p></div>
      <p className={failed ? "preferences-error" : "preferences-status"} role={failed ? "alert" : "status"}>{status}</p>
      {failed && <button className="button secondary" type="button" onClick={preferences.retry}>重試儲存介面設定</button>}
    </footer>
  </section>;
}
