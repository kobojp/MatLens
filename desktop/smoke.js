// Synthetic photos only: used by the isolated --self-test desktop mode.
(async () => {
  const wait = async (check, label) => {
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
  const drop = async (color, name) => {
    const canvas = document.createElement('canvas');
    canvas.width = 800;
    canvas.height = 1600;
    const context = canvas.getContext('2d');
    context.fillStyle = color;
    context.fillRect(0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    const transfer = new DataTransfer();
    transfer.items.add(new File([blob], name, { type: 'image/png' }));
    document.querySelector('.photo-rail').dispatchEvent(new DragEvent('drop', {
      bubbles: true, cancelable: true, dataTransfer: transfer,
    }));
  };
  try {
    await wait(() => document.querySelector('.photo-rail'), 'React render');
    for (const [index, color] of ['red', 'green', 'blue'].entries()) {
      await drop(color, `消防測試${index + 1}.png`);
      await wait(() => document.querySelectorAll('.thumbnail-item').length === index + 1,
                 'sequential drop');
    }
    await wait(() => document.querySelector('.image-stage img')?.naturalWidth === 800, 'preview');
    await wait(() => document.querySelector('select[aria-label="月份資料夾"]')?.value, 'storage scan');
    if (!document.querySelector('select[aria-label="儲存子目錄"]')?.value) {
      document.querySelector('.folder-custom-row button').click();
      await wait(() => document.querySelector('select[aria-label="儲存子目錄"]')?.value, 'create storage folders');
    }
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
    let update_panel = false;
    if (window.pywebview?.api.update_status) {
      await wait(() => document.querySelector('.update-section > button'), 'update panel');
      document.querySelector('.update-section > button').click();
      await wait(() => document.querySelector('select[aria-label="更新頻道"]'), 'update channel');
      update_panel = document.querySelector('select[aria-label="更新頻道"]').value === 'stable';
    }
    return { ok: true, photos: 3, address: 'DESKTOP-QA', dirty: window.matlensDesktopState.dirty, portrait_fit: true, zoom_pan: true, update_panel };
  } catch (error) {
    return { ok: false, error: String(error), text: document.body.innerText };
  }
})()
