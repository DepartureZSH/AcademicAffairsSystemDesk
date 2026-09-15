import { invoke, isTauri } from '@tauri-apps/api/core';

export interface AiConnectionStatus {
  baseUrl: string;
  model: string;
  hasApiKey: boolean;
}
export const aiAvailable = () => isTauri();
export const aiConnection = {
  status: () => invoke<AiConnectionStatus>('ai_connection_status'),
  save: (input: { baseUrl: string; model: string; apiKey: string | null }) =>
    invoke<AiConnectionStatus>('ai_save_connection', { input }),
  clear: () => invoke<void>('ai_clear_connection'),
  test: (confirmed: boolean) => invoke<void>('ai_test_connection', { confirmed }),
};
