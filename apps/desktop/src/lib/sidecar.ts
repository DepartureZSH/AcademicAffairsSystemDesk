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

export interface SchedulingRound extends Record<string, unknown> {
  id: string;
  session_id: string;
  status: string;
  candidate_id: string | null;
  total_score: number | null;
  error_message: string | null;
  events?: Array<Record<string, unknown>>;
}

export interface SchedulingCandidate extends Record<string, unknown> {
  id: string;
  round_id: string;
  session_id: string;
  parent_candidate_id: string | null;
  total_score: number;
  entry_count: number;
  created_at: string;
}

export interface TimetableEntry extends EntityRecord {
  candidate_id: string;
  task_lesson_id: string;
  weekday: number;
  start_slot: number;
  duration_slots: number;
  week_bits: string;
  teacher_name: string | null;
  homeroom_name: string | null;
  subject_name: string | null;
  room_name: string | null;
}

export interface ManualMovePreview {
  valid: boolean;
  conflicts: Array<Record<string, unknown>>;
  score: Record<string, number> | null;
  preview: Record<string, unknown> | null;
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
  saveTeachingTask: (
    data: Record<string, unknown>,
    expectedRevision: number,
  ) =>
    sidecarRequest<{ task: EntityRecord; lessons: EntityRecord[]; revision: number }>({
      method: "PUT",
      path: "/v1/planning/tasks",
      body: { data, expected_revision: expectedRevision },
    }),
  runSchedulingRound: (options: {
    timeBudgetSeconds: number;
    randomSeed: number;
    sessionId?: string;
    parentCandidateId?: string;
    name?: string;
  }) =>
    sidecarRequest<{ round: SchedulingRound; revision: number }>({
      method: "POST",
      path: "/v1/scheduling/rounds",
      body: {
        time_budget_seconds: options.timeBudgetSeconds,
        random_seed: options.randomSeed,
        session_id: options.sessionId,
        parent_candidate_id: options.parentCandidateId,
        name: options.name,
      },
    }),
  listSchedulingRounds: (sessionId?: string) =>
    sidecarRequest<{ items: SchedulingRound[]; revision: number }>({
      method: "GET",
      path: `/v1/scheduling/rounds${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`,
    }),
  listSchedulingCandidates: () =>
    sidecarRequest<{ items: SchedulingCandidate[]; revision: number }>({
      method: "GET",
      path: "/v1/scheduling/candidates",
    }),
  getTimetable: (candidateId: string, entityType?: string, entityId?: string) => {
    const query = entityType && entityId
      ? `?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`
      : "";
    return sidecarRequest<{
      candidate: SchedulingCandidate;
      items: TimetableEntry[];
      snapshotRevision: number;
      currentRevision: number;
      basedOnOldData: boolean;
      revision: number;
    }>({ method: "GET", path: `/v1/timetables/${encodeURIComponent(candidateId)}${query}` });
  },
  validateManualMove: (data: Record<string, unknown>) =>
    sidecarRequest<ManualMovePreview>({
      method: "POST",
      path: "/v1/timetables/validate-move",
      body: data,
    }),
  applyManualMove: (data: Record<string, unknown>) =>
    sidecarRequest<{ round: SchedulingRound; revision: number }>({
      method: "POST",
      path: "/v1/timetables/manual-fork",
      body: data,
    }),
  exportCandidate: (data: Record<string, unknown>) =>
    sidecarRequest<{ export: Record<string, unknown>; revision: number }>({
      method: "POST",
      path: "/v1/exports",
      body: data,
    }),
  listExports: () =>
    sidecarRequest<{ items: Array<Record<string, unknown>>; revision: number }>({
      method: "GET",
      path: "/v1/exports",
    }),
};
