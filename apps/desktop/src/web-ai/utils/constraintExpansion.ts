// @ts-nocheck -- upstream source
export type ExpansionSource = {
  name: string; scenario_type: string; template_id?: string | null; required: boolean; penalty: number | null;
  groups: string[][]; parameters?: Record<string, unknown>;
};
export type ExpansionPayload = { source: ExpansionSource; mode: string; instruction: string; include_source: boolean; selected_ids: string[] };

export function distributionScenario(type: string) {
  if (type.startsWith("ParallelLimit(")) return `common:${type}`;
  return `itc2019:${type}`;
}

export function resolveConstraintLesson(value: string, lessons: Record<string, any>[], tasks: Record<string, any>[]) {
  let lesson = lessons.find(row => String(row.id) === value || String(row.xml_class_id || "") === value);
  const legacy = value.match(/^(.*)-L(\d+)$/);
  if (!lesson && legacy) {
    const matches = lessons.filter(row => String(row.teaching_task_id) === legacy[1] && Number(row.lesson_index) === Number(legacy[2]));
    if (matches.length === 1) lesson = matches[0];
  }
  const taskId = lesson?.teaching_task_id || legacy?.[1];
  return { lesson, task: tasks.find(row => String(row.id) === String(taskId)), ordinal: Number(lesson?.lesson_index || legacy?.[2] || 0) };
}
