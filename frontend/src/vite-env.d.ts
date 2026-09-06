/// <reference types="vite/client" />

interface Window {
  matlensDesktopState?: { dirty: boolean; saving: boolean };
  pywebview?: { api: { update_state(sequence: number, dirty: boolean, saving: boolean): Promise<void> } };
}
