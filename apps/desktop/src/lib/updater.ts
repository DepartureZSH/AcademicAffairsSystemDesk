import { Channel, invoke } from "@tauri-apps/api/core";

export interface DownloadProgress { downloaded: number; total: number | null }

export interface UpdateStatus {
  mode: "mock" | "real";
  available: boolean;
  currentVersion: string;
  version: string | null;
  notes: string | null;
  message: string;
}

export const updater = {
  check: () => invoke<UpdateStatus>("check_for_update"),
  download: (onProgress: (value: DownloadProgress) => void) => {
    const progress = new Channel<DownloadProgress>();
    progress.onmessage = onProgress;
    return invoke<void>("download_checked_update", { progress });
  },
  install: () => invoke<void>("install_checked_update"),
};
