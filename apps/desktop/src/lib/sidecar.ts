import { invoke } from "@tauri-apps/api/core";

export interface RuntimeStatus {
  running: boolean;
  port: number | null;
  pid: number | null;
  protocolVersion: string | null;
  workspacePath: string | null;
}

export interface HealthStatus {
  status: string;
  protocolVersion: string;
  schemaVersion: number;
  serviceModes: Record<string, "real" | "mock" | "disabled">;
  projectOpen: boolean;
}

export interface ProjectInfo {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

interface SidecarRequest {
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  body?: unknown;
}

export async function startSidecar(workspacePath?: string): Promise<RuntimeStatus> {
  return invoke<RuntimeStatus>("start_sidecar", { workspacePath: workspacePath ?? null });
}

export async function stopSidecar(): Promise<void> {
  await invoke("stop_sidecar");
}

export async function runtimeStatus(): Promise<RuntimeStatus> {
  return invoke<RuntimeStatus>("runtime_status");
}

export async function sidecarRequest<T>(request: SidecarRequest): Promise<T> {
  return invoke<T>("sidecar_request", { request });
}

export const localApi = {
  health: () => sidecarRequest<HealthStatus>({ method: "GET", path: "/v1/health" }),
  listProjects: () =>
    sidecarRequest<{ projects: Array<Record<string, unknown>> }>({
      method: "GET",
      path: "/v1/projects",
    }),
  createProject: (name: string) =>
    sidecarRequest<{ project: ProjectInfo; revision: number }>({
      method: "POST",
      path: "/v1/projects",
      body: { name },
    }),
  openProject: (projectId: string) =>
    sidecarRequest<{ project: ProjectInfo; revision: number }>({
      method: "POST",
      path: `/v1/projects/${encodeURIComponent(projectId)}/open`,
    }),
};
