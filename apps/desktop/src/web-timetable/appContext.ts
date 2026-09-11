import type { InjectionKey } from 'vue';
import type { useTimetableEditor } from './useTimetableEditor';
export const APP_CONTEXT_KEY: InjectionKey<ReturnType<typeof useTimetableEditor>> = Symbol.for('stt.desktop.local-timetable-editor');
