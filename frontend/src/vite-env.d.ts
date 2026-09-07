/// <reference types="vite/client" />

interface Window {
  matlensDesktopState?: { dirty: boolean; saving: boolean };
  pywebview?: { api: {
    update_state(sequence: number, dirty: boolean, saving: boolean): Promise<void>;
    update_status(): Promise<import("./UpdatePanel").UpdateState>;
    check_update(channel: string): Promise<import("./UpdatePanel").UpdateState | { error: string }>;
    download_update(): Promise<import("./UpdatePanel").UpdateState | { error: string }>;
    install_update(dirty: boolean, saving: boolean): Promise<{ ok: boolean } | { error: string }>;
  } };
}
