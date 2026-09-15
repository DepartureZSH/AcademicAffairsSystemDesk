export interface RunCardState {
  run: {status: string} | null;
  active: boolean; optimizing: boolean; busy: boolean; progress: number; candidateId: string;
  display: {tone: string; label: string; algorithm: string; description: string; stage: string; hasSolution: boolean};
  steps: Array<{label: string; state: string}>;
  input: {generated: boolean; classText: number | string; roomText: number | string; constraintText: number | string};
  result: {title: string; detail: string};
  validation: {tone: string; title: string; detail: string; summary: null | {
    total_cost: number; missing_time: number; missing_room: number; hard_violations: number;
    soft_violations?: number; time_penalty: number; room_penalty: number; soft_penalty: number;
  }; qualityItems: unknown[]};
  qualityGroups: Array<{key: string; label: string; total: number; items: Array<{title: string; detail: string; penalty: number}>}>;
  issueGroups: Array<{key: string; tone: string; label: string; items: Array<{
    category: string; title: string; detail: string; severity: string;
    diagnostic?: {class_id: string; reason_groups: Array<{code: string; title: string; detail: string}>};
  }>} >;
}
