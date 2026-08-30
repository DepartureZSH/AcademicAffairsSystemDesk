import { invoke } from "@tauri-apps/api/core";

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
  install: () => invoke<void>("install_checked_update"),
};
