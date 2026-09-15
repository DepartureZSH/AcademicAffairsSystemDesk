import { invoke } from "@tauri-apps/api/core";

export interface AuthUser {
  id: string;
  email: string;
}

export interface AuthStatus {
  configured: boolean;
  authenticated: boolean;
  offline: boolean;
  user: AuthUser | null;
  message: string | null;
}

export interface LicenseStatus {
  mode: "real" | "mock" | "disabled";
  active: boolean;
  needsActivation: boolean;
  expiresAt: number | null;
  deviceId: string | null;
  deviceLimit: number;
  message: string | null;
}

export interface GateStatus {
  auth: AuthStatus;
  license: LicenseStatus;
  canStartSidecar: boolean;
}

export interface PurchaseLaunchResult {
  mode: "mock" | "real";
  opened: boolean;
  message: string;
}

export const accessGate = {
  status: () => invoke<GateStatus>("access_gate_status"),
  signIn: (email: string, password: string) =>
    invoke<GateStatus>("auth_sign_in", { email, password }),
  signUp: (email: string, password: string) =>
    invoke<AuthStatus>("auth_sign_up", { email, password }),
  requestPasswordReset: (email: string) =>
    invoke<string>("auth_request_password_reset", { email }),
  completePasswordReset: (recoveryLink: string, newPassword: string) =>
    invoke<string>("auth_complete_password_reset", { recoveryLink, newPassword }),
  signOut: () => invoke<GateStatus>("auth_sign_out"),
  openPurchasePage: () => invoke<PurchaseLaunchResult>("open_purchase_page"),
};
