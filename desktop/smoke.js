// Synthetic photos only: used by the isolated --self-test desktop mode.
(async () => {
  window.matlensSmokeStep = 'start';
  const wait = async (check, label) => {
    window.matlensSmokeStep = label;
    for (let i = 0; i < 100; i++) {
      if (await check()) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(`Timed out: ${label}`);
  };
  const change = (selector, value) => {
    const input = document.querySelector(selector);
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const ui = async (layout, position = 'right', size = 'large') => {
    document.querySelector('#tab-settings').click();
    await wait(() => !document.querySelector('input[name=workspace-layout]').disabled, 'UI settings loaded');
    document.querySelector(`input[name=workspace-layout][value=${layout}]`).click();
    if (layout === 'tiles') {
      document.querySelector(`input[name=case-panel-position][value=${position}]`).click();
      document.querySelector(`input[name=photo-tile-size][value=${size}]`).click();
    }
    await wait(async () => {
      const saved = await (await fetch('/api/settings/ui-preferences')).json();
      return saved.layout === layout && (layout !== 'tiles' || (saved.panel_position === position && saved.tile_size === size)) && !window.matlensDesktopState.saving;
    }, 'UI settings saved');
    document.querySelector('#tab-workspace').click();
  };
  const transferFor = (color, name) => {
    window.matlensSmokeStep = `synthetic image: ${name}`;
    const canvas = document.createElement('canvas');
    canvas.width = 800;
    canvas.height = 1600;
    const context = canvas.getContext('2d');
    context.fillStyle = color;
    context.fillRect(0, 0, canvas.width, canvas.height);
    const data = atob(canvas.toDataURL('image/png').split(',')[1]);
    const blob = new Blob([Uint8Array.from(data, char => char.charCodeAt(0))], { type: 'image/png' });
    const transfer = new DataTransfer();
    transfer.items.add(new File([blob], name, { type: 'image/png' }));
    return transfer;
  };
  try {
    await wait(() => document.querySelector('.photo-rail'), 'React render');
    await wait(() => document.querySelector('input[name="storage-subfolder"][value="底座"]'), 'storage scan');
    document.querySelector('input[name="storage-subfolder"][value="底座"]').click();
    await wait(() => document.querySelector('.storage-save-status')?.textContent === '已儲存', 'save selected folder');
    document.querySelector('.free-date-toggle input').click();
    await wait(() => !document.querySelector('.free-date-toggle input').checked && !window.matlensDesktopState.saving, 'save date setting');
    const transfer = transferFor('red', '貼上消防測試.png');
    const paste = () => document.querySelector('.photo-rail').dispatchEvent(new ClipboardEvent('paste', {
      bubbles: true, cancelable: true, clipboardData: transfer,
    }));
    paste();
    await wait(() => document.querySelector('.paste-confirmation'), 'paste confirmation');
    if (document.querySelectorAll('.thumbnail-item').length) throw new Error('Paste added before confirmation');
    document.querySelector('.paste-actions button').click();
    await wait(() => !document.querySelector('.paste-confirmation'), 'cancel paste');
    if (window.matlensDesktopState.dirty) throw new Error('Cancelled paste changed draft');
    paste();
    await wait(() => document.querySelector('.paste-confirmation'), 'second paste confirmation');
    document.querySelector('.paste-actions .primary').click();
    await wait(() => document.querySelectorAll('.thumbnail-item').length === 1, 'confirm paste');
    for (const [index, color] of ['green', 'blue'].entries()) {
      document.querySelector('.photo-rail').dispatchEvent(new DragEvent('drop', {
        bubbles: true, cancelable: true, dataTransfer: transferFor(color,
          index === 0 ? `${'longmaintenancephotoname'.repeat(9)}.png` : '消防測試3.png'),
      }));
      await wait(() => document.querySelectorAll('.thumbnail-item').length === index + 2,
                 'sequential drop');
    }
    if (!document.querySelector('.workspace.layout-tiles')) throw new Error('Missing default tile workspace');
    document.querySelector('.thumbnail-button').click();
    await wait(() => document.querySelector('.photo-lightbox .image-stage img')?.naturalWidth === 800, 'lightbox preview');
    const stage = document.querySelector('.interactive-preview');
    const preview = stage.querySelector('img');
    const bounds = stage.getBoundingClientRect();
    if (getComputedStyle(preview).objectFit !== 'contain' || preview.getBoundingClientRect().height > bounds.height + 1) {
      throw new Error('Portrait image is cropped by intrinsic grid sizing');
    }
    document.querySelector('button[aria-label="放大圖片"]').click();
    await wait(() => document.querySelector('output').textContent === '125%', 'zoom button');
    // Synthetic PointerEvents cannot acquire native OS pointer capture.
    stage.setPointerCapture = () => {};
    stage.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 1, button: 0, clientX: 200, clientY: 150 }));
    stage.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, pointerId: 1, clientX: 200, clientY: 170 }));
    stage.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 1 }));
    await wait(() => preview.style.transform.includes('20px'), 'preview pan');
    stage.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: -100, clientX: bounds.left + bounds.width / 2, clientY: bounds.top + bounds.height / 2 }));
    await wait(() => parseInt(document.querySelector('output').textContent) > 125, 'wheel zoom');
    stage.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    await wait(() => preview.style.transform === 'translate(0px, 0px) scale(1)', 'fit image');
    document.querySelector('.lightbox-next').click();
    await wait(() => document.querySelector('.photo-lightbox header p')?.textContent.startsWith('2／'), 'next photo');
    if (document.documentElement.scrollWidth > innerWidth + 1) throw new Error('Long filename overflows lightbox');
    document.querySelector('.lightbox-close').click();
    await wait(() => !document.querySelector('.photo-lightbox'), 'close lightbox');
    await ui('classic');
    await wait(() => document.querySelector('.preview-panel .image-stage img')?.naturalWidth === 800, 'classic preview');
    if (document.querySelectorAll('.thumbnail-item').length !== 3) throw new Error('Layout switch lost photos');
    await ui('tiles', 'top', 'medium');
    if (!window.matlensDesktopState.dirty) throw new Error('Missing unsaved state');
    change('input[placeholder="例如 3F、B2"]', '3F');
    change('input[placeholder="例如 M3-07"]', 'DESKTOP-QA');
    await wait(() => document.querySelector('.path-preview').textContent.includes('DESKTOP-QA'), 'edit');
    document.querySelector('button[form="case-form"]').click();
    await wait(() => document.querySelector('.message.success')?.textContent.includes('已安全儲存'), 'save');
    await wait(() => !window.matlensDesktopState.dirty && !window.matlensDesktopState.saving, 'clean state');
    await wait(() => document.querySelector('.row-actions button'), 'case list');
    document.querySelector('.row-actions button').click();
    await wait(() => document.querySelectorAll('.saved-photo-grid img').length === 3, 'case detail');
    await wait(() => [...document.querySelectorAll('.saved-photo-grid img')].every(img => img.naturalWidth === 800), 'saved photos');
    document.querySelector('.case-modal > header button').click();
    document.querySelector('#tab-settings').click();
    [...document.querySelectorAll('button')].find(button => button.textContent === '恢復預設版面').click();
    await wait(async () => {
      const saved = await (await fetch('/api/settings/ui-preferences')).json();
      return saved.layout === 'tiles' && saved.panel_position === 'right' && saved.tile_size === 'large' && !saved.panel_collapsed && !window.matlensDesktopState.saving;
    }, 'reset layout saved');
    const defaults = await (await fetch('/api/settings/ui-preferences')).json();
    if (defaults.layout !== 'tiles' || defaults.panel_position !== 'right' || defaults.tile_size !== 'large' || defaults.panel_collapsed) throw new Error('Wrong reset scope/defaults');
    document.querySelector('#tab-workspace').click();
    await ui('tiles', 'top', 'medium');
    document.querySelector('.collapse-editor').click();
    await wait(() => document.querySelector('#case-editor-fields').hidden && !window.matlensDesktopState.saving, 'collapse saved');
    let update_panel = false;
    if (window.pywebview?.api.update_status) {
      await wait(() => document.querySelector('.update-section > button'), 'update panel');
      document.querySelector('.update-section > button').click();
      await wait(() => document.querySelector('select[aria-label="更新頻道"]'), 'update channel');
      update_panel = document.querySelector('select[aria-label="更新頻道"]').value === 'stable';
      if (!window.pywebview.api.open_update_logs || ![...document.querySelectorAll('button')]
        .some(button => button.textContent === '開啟更新紀錄')) throw new Error('Missing update log access');
    }
    const database = await (await fetch('/api/settings/database')).json();
    await wait(() => document.querySelector('.case-list-section .database-location')?.textContent.includes(database.path), 'active database path');
    if (![...document.querySelectorAll('button')].some(button => button.textContent === '開啟資料庫位置')) throw new Error('Missing database location button');
    const selection = await (await fetch('/api/settings/storage-selection')).json();
    if (selection.subfolder !== '底座' || selection.with_date !== false) throw new Error('Storage settings not persisted');
    if (!document.querySelector('.destination-badge')?.textContent.includes('目前儲存資料夾：底座')) throw new Error('Wrong destination badge');
    return { ok: true, photos: 3, address: 'DESKTOP-QA', dirty: window.matlensDesktopState.dirty, portrait_fit: true, zoom_pan: true, update_panel, database_location: true, clipboard_confirmation: true, storage_selection: true, tile_workspace: true, lightbox: true, long_filenames: true, classic_switch: true, ui_reset: true, panel_collapse: true };
  } catch (error) {
    return { ok: false, error: String(error), text: document.body.innerText };
  }
})()
