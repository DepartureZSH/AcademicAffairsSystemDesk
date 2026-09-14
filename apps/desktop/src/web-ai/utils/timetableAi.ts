// @ts-nocheck -- upstream source
export type TimetableAiOptions = {
  name: string;
  planning_mode: 'independent' | 'reuse';
  regular: boolean;
  fixed: boolean;
  sheet: string;
  cell_roles?: Record<string, 'course' | 'custom' | 'detail' | 'header' | 'axis'>;
};
export type TimetableSheetCell = { address: string; row: number; column: number; value: string; merge?: { anchor: string; rowspan: number; colspan: number } | null };
export type TimetableSheet = { name: string; rows: number; columns: number; cells?: TimetableSheetCell[] };
export type TimetableZoning = {
  suitable: boolean; reason: string; regular: boolean; fixed: boolean; layout: string;
  show_time_axis: boolean; column_header_row: number;
  columns: Array<{ source_column: number; kind: 'weekday' | 'custom'; weekday: number }>;
  cells: Array<{ source: string; role: string; [key: string]: unknown }>;
};
export type TimetableAiResult = {
  default_template_id: string;
  draft: {
    name: string;
    periods: Array<Record<string, unknown>>;
    display_config: Record<string, any>;
    zones: Array<{ source: string; role: string; reason: string }>;
    reason: string;
  };
};
