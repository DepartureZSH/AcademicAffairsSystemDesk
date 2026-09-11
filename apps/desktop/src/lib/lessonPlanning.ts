import type { EntityRecord } from './sidecar';

export type PreferredTime = { time_slot_id: string; week_bits: string; penalty: number };
export type LessonConfig = { preferred_times: PreferredTime[]; room_mode: 'default' | 'custom'; room_ids: string[] };
export type LessonDraft = { key: string; id?: string; label: string; enabled: boolean; duration_slots: number; week_bits: string; day_bits: string; planning_config: LessonConfig };
export const priorities = [{ value: 0, label: '最高优先' }, { value: 10, label: '普通优先' }, { value: 30, label: '较低优先' }, { value: 60, label: '兜底可排' }, { value: -1, label: '绝对不排' }];
export function draftLesson(item: Partial<EntityRecord>, weeks: string, days: string, index = 0): LessonDraft {
  const config = typeof item.planning_config === 'string' ? JSON.parse(item.planning_config) : item.planning_config || {};
  return { key: crypto.randomUUID(), ...(item.id ? { id: item.id } : {}), label: String(item.label || `第${index + 1}课次`), enabled: item.enabled !== 0,
    duration_slots: Number(item.duration_slots ?? 1), week_bits: String(item.week_bits || weeks), day_bits: String(item.day_bits || days),
    planning_config: { preferred_times: config.preferred_times || [], room_mode: config.room_mode || 'default', room_ids: config.room_ids || [] } };
}
export function cloneLessons(items: LessonDraft[]): LessonDraft[] { return JSON.parse(JSON.stringify(items)); }
export function serializeLesson(item: LessonDraft): Record<string, unknown> { const { key, ...record } = item; return record; }
export function fitsLesson(slot: EntityRecord, slots: EntityRecord[], duration: number): boolean {
  if (!Number.isInteger(duration) || duration < 1) return false;
  const day = slots.filter(item => item.weekday === slot.weekday).sort((a, b) => Number(a.period_index) - Number(b.period_index));
  const start = day.findIndex(item => item.id === slot.id), window = day.slice(start, start + duration);
  return window.length === duration && window.every((item, i) => !i || Number(item.period_index) === Number(window[i - 1].period_index) + 1 && Number(item.start_slot) === Number(window[i - 1].start_slot) + Number(window[i - 1].length_slots));
}
