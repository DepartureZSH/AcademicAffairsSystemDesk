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

export interface EntityRecord {
  id: string;
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
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

export function formatLocalError(error: unknown): string {
  const raw = String(error);
  try {
    const parsed = JSON.parse(raw) as { error?: { message?: string; correlationId?: string } };
    const message = parsed.error?.message;
    const correlationId = parsed.error?.correlationId;
    if (message) return correlationId ? `${message}（追踪号 ${correlationId}）` : message;
  } catch {
    // Tauri command errors that are not local API envelopes are already safe display strings.
  }
  return raw;
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
  listEntities: <T extends EntityRecord = EntityRecord>(entityType: string) =>
    sidecarRequest<{ items: T[]; revision: number }>({
      method: "GET",
      path: `/v1/data/${encodeURIComponent(entityType)}`,
    }),
  saveEntity: <T extends EntityRecord = EntityRecord>(
    entityType: string,
    data: Record<string, unknown>,
    expectedRevision: number,
  ) =>
    sidecarRequest<{ item: T; revision: number }>({
      method: "PUT",
      path: `/v1/data/${encodeURIComponent(entityType)}`,
      body: { data, expected_revision: expectedRevision },
    }),
  deleteEntity: (entityType: string, entityId: string, expectedRevision: number) =>
    sidecarRequest<{ deletedId: string; revision: number }>({
      method: "DELETE",
      path: `/v1/data/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}?expected_revision=${expectedRevision}`,
    }),
};
