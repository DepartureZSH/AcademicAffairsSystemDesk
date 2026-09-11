// Extracted from STT/apps/web-admin/src/composables/useAppController.ts.
import { computed, nextTick, ref } from 'vue';
import type { Cell as ExcelCell } from 'exceljs';
import { fitWorksheetToPrintedPage } from './excelPrintLayout';
import { compareNaturalClassNames, compareNaturalRoomNames } from './naturalClassNameSort';
import { localApi, sidecarRequest, formatLocalError } from '../lib/sidecar';

export function useTimetableEditor(onRevision: (revision: number) => void) {
const organizationId = ref("local");
const projectId = ref("local");
type TimetableEntry = {
    entry_id?: string;
    lesson_id?: string;
    task_lesson_id?: string | null;
    source_xml_class_id?: string | null;
    lesson_label?: string | null;
    lesson_index?: number | string | null;
    homeroom_id?: string | null;
    homeroom_name?: string | null;
    subject_name?: string | null;
    primary_teacher_id?: string | null;
    teaching_task_id?: string | null;
    subject_id?: string | null;
    teacher_name?: string | null;
    weekday: number | string;
    week_bits?: string;
    start_slot: number | string;
    length_slots?: number | string;
    start_time?: string;
    end_time?: string;
    time_range?: string;
    duration_minutes?: number;
    duration_label?: string;
    active_weeks?: number[];
    week_label?: string;
    room_id?: string | null;
    room_name?: string | null;
    room_options?: Array<{ room_id?: string; room_name?: string; is_primary?: boolean }>;
    time_preferences?: Array<Record<string, unknown>>;
  };

type TimetableWeekday = {
    weekday: number | string;
    label: string;
  };

type TimetableView = {
    solution_id: string;
    project_id: string;
    weekdays: TimetableWeekday[];
    week_count: number;
    week_options: Array<{ week: number; label: string }>;
    start_slots: Array<number | string>;
    slot_rows: Array<{
      start_slot: number | string;
      label?: string;
      start_time: string;
      time_range?: string;
      weekday_start_slots?: Record<string, number | string>;
    }>;
    cells: Record<string, Record<string, TimetableEntry[]>>;
    buffer_entries?: TimetableEntry[];
  };

type TimetableResultViewMode = "all" | "homeroom" | "teacher" | "room" | "student";

type CourseCellExportLayout = "single_line" | "two_line" | "split_rows";

type CourseCellExportField = "subject" | "teacher" | "room" | "time" | "homeroom";

type PeriodCellMode = "scheduled" | "custom" | "disabled";

type PeriodCellExportStyle = "default" | "custom";

type TimetableTemplateLayoutKind = "weekly" | "all_classes_grid";

type AllClassesTemplateVariant = "homeroom_rows" | "period_rows_grouped";

type SpecialTimetableTemplatePreset = {
    key: string;
    name: string;
    description: string;
    layoutKind: "all_classes_grid";
    applicationScope: "all";
    variant: AllClassesTemplateVariant;
    displayConfig: Record<string, unknown>;
  };

type TemplateMarketplaceItem = {
    key: string;
    sourceType: "weekly" | "special";
    sourceId: string;
    name: string;
    description: string;
    organizationName: string;
    isOwned: boolean;
    layoutKind: TimetableTemplateLayoutKind;
    timeMode: "fixed" | "variable";
    displayConfig: Record<string, unknown>;
    periods: Array<Record<string, unknown>>;
  };

type CandidateExcelColorMode = "monochrome" | "color";

type CandidateExcelPageOrientation = "landscape" | "portrait";

type CandidateExportSheet = {
    name: string;
    ownerName: string;
    columnCount: number;
    html: string;
  };

type SchoolData = {
    active_term?: Record<string, unknown>;
    weekly_timetable_templates: Array<Record<string, unknown>>;
    weekly_timetable_periods: Array<Record<string, unknown>>;
    default_weekly_timetable_template?: Record<string, unknown> | null;
    timetable_template_assignments: Array<Record<string, unknown>>;
    teachers: Array<Record<string, unknown>>;
    rooms: Array<Record<string, unknown>>;
    room_types: Array<Record<string, unknown>>;
    subjects: Array<Record<string, unknown>>;
    homerooms: Array<Record<string, unknown>>;
  };

type SectionKey =
    | "console"
    | "billing"
    | "agent"
    | "profile"
    | "organization_join"
    | "organization_registration"
    | "organization_detail"
    | "timetable"
    | "school"
    | "rooms"
    | "planning"
    | "constraints"
    | "runs";

type PeriodDraft = {
    id?: string;
    weekday: number;
    period_index: number;
    label: string;
    start_time: string;
    end_time: string;
    active: boolean;
    align: "left" | "center";
    colspan: number;
    cell_mode?: PeriodCellMode;
    custom_content?: string;
    sample_subject?: string;
    sample_teacher?: string;
    sample_room?: string;
    sample_homeroom?: string;
    export_style?: PeriodCellExportStyle;
    export_layout?: CourseCellExportLayout;
    export_top_field?: CourseCellExportField;
    export_bottom_field?: CourseCellExportField;
  };

type PreviewAlign = "left" | "center" | "right";

type PreviewBlankCellDraft = {
    label: string;
    align: PreviewAlign;
    colspan: number;
    rowspan: number;
    active: boolean;
    coveredBy?: string;
  };

type PreviewBlankRowDraft = {
    id: string;
    label: string;
    align: PreviewAlign;
    colspan: number;
    order_index: number;
    cells: Record<string, PreviewBlankCellDraft>;
  };

type PreviewBlankColumnDraft = {
    id: string;
    label: string;
    align: PreviewAlign;
    colspan: number;
    order_index: number;
    cells: Record<string, PreviewBlankCellDraft>;
  };

type PreviewHeaderBinding =
    | "template_name"
    | "school_name"
    | "project_name"
    | "owner_name"
    | "custom";

type PreviewHeaderCellDraft = PreviewBlankCellDraft & {
    binding: PreviewHeaderBinding;
  };

type PreviewHeaderRowDraft = {
    id: string;
    order_index: number;
    cells: Record<string, PreviewHeaderCellDraft>;
  };

type PreviewSelection =
    | { kind: "period"; periodIndex: number; dayIndex: number }
    | { kind: "header-cell"; rowId: string; columnKey: string }
    | { kind: "blank-row"; id: string }
    | { kind: "blank-row-cell"; rowId: string; columnKey: string }
    | { kind: "blank-column"; id: string }
    | { kind: "blank-column-cell"; columnId: string; rowKey: string };

const activeSection = ref<SectionKey>("timetable");

const organizations = ref<Array<Record<string, string>>>([]);

const projects = ref<Array<Record<string, string>>>([]);

const schoolData = ref<SchoolData>({
    active_term: { name: "默认学期", week_count: 14, day_count: 7 },
    weekly_timetable_templates: [],
    weekly_timetable_periods: [],
    default_weekly_timetable_template: null,
    timetable_template_assignments: [],
    teachers: [],
    rooms: [],
    room_types: [],
    subjects: [],
    homerooms: [],
  });

const timetable = ref<TimetableView | null>(null);

const candidateExcelPageOrientation = ref<CandidateExcelPageOrientation>("landscape");

let candidateExportCapture: { fileName: string; sheets: CandidateExportSheet[] } | null = null;

const termForm = ref({ name: "默认学期", week_count: 14, day_count: 7 });

const selectedTemplateId = ref("");

const timetableTemplateForm = ref({
    id: "",
    name: "默认周课程表",
    day_count: 7,
    slot_duration_minutes: 5,
    is_default: true,
  });

const timetableTemplateDescription = ref("");

const weeklyPeriodDrafts = ref<PeriodDraft[]>([]);

const loading = ref(false);

const error = ref("");

const roomUnavailableRuleForm = ref({
    week_bits: "",
    day_bits: "",
    period_index: 1,
  });

const coursePreferredRuleForm = ref({
    week_bits: "",
    day_bits: "",
    period_index: 1,
    penalty: 0,
    forbidden: false,
  });

const previewBlankRows = ref<PreviewBlankRowDraft[]>([]);

const previewBlankColumns = ref<PreviewBlankColumnDraft[]>([]);

const previewHeaderRows = ref<PreviewHeaderRowDraft[]>([]);

const selectedPreviewCell = ref<PreviewSelection | null>(null);

const enabledWeekdays = ref<number[]>([1, 2, 3, 4, 5]);

const timetableTimeMode = ref<"fixed" | "variable">("fixed");

const showTimetableTimeAxis = ref(true);

const publishTimetablePreset = ref(false);

const timetableTemplateKind = ref<"normal" | "special">("normal");

const timetableTemplateApplicationScope = ref("all");

const timetableTemplatePeriodSourceId = ref("");

const timetableTemplatePeriodsLocked = ref(false);

const showTimetableTimePresetPicker = ref(false);

const showNewTimetableTemplateConfirm = ref(false);

const newTemplateConfirmStep = ref<"planning" | "marketplace" | "details">("planning");

const templateCreatePlanningMode = ref<"independent" | "reuse">("independent");

const templateMarketplaceSearch = ref("");

const templateMarketplaceFilters = ref({ owned: "all", regular: "all", fixed: "all" });

const selectedTemplateMarketplaceKey = ref("");

const previewTemplateMarketplaceKey = ref("");

const creatingNewTimetableTemplate = ref(false);

const timetableTemplateDraftActive = ref(false);

const hasTimetableTemplateEditor = computed(() =>
    schoolData.value.weekly_timetable_templates.length > 0 || timetableTemplateDraftActive.value,
  );

const timetablePresetLibrary = ref<{
    weekly_timetable_presets: Array<Record<string, unknown>>;
    weekly_timetable_preset_periods: Array<Record<string, unknown>>;
  }>({
    weekly_timetable_presets: [],
    weekly_timetable_preset_periods: [],
  });

const timetablePresetLibraryLoading = ref(false);

const periodTimeErrors = ref<Record<string, string>>({});

const periodTimeDrafts = ref<Record<string, { start_time: string; end_time: string }>>({});

const courseCellExportLayout = ref<CourseCellExportLayout>("two_line");

const courseCellExportTopField = ref<CourseCellExportField>("subject");

const courseCellExportBottomField = ref<CourseCellExportField>("teacher");

const timetableTemplateLayoutKind = ref<TimetableTemplateLayoutKind>("weekly");

const allClassesTemplateVariant = ref<AllClassesTemplateVariant>("homeroom_rows");

const weekdayOptions = [
    { index: 0, label: "周一" },
    { index: 1, label: "周二" },
    { index: 2, label: "周三" },
    { index: 3, label: "周四" },
    { index: 4, label: "周五" },
    { index: 5, label: "周六" },
    { index: 6, label: "周日" },
  ];

const fixedWeeklyDayCount = 7;

const selectedOrganization = computed(() =>
    organizations.value.find((organization) => String(organization.id) === organizationId.value),
  );

const selectedProject = computed(() =>
    projects.value.find((project) => String(project.id) === projectId.value),
  );

const currentProjectName = computed(() => String(selectedProject.value?.name || "尚未选择项目"));

const schoolDataSummary = computed(() => ({
    templates: schoolData.value.weekly_timetable_templates.length,
    periods: schoolData.value.weekly_timetable_periods.length,
    teachers: schoolData.value.teachers.length,
    rooms: schoolData.value.rooms.length,
    roomTypes: schoolData.value.room_types.length,
    subjects: schoolData.value.subjects.length,
    homerooms: schoolData.value.homerooms.length,
  }));

const termDayCount = computed(() => fixedWeeklyDayCount);

function previewDraftId(prefix: string) {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

function templateDisplayConfig(template: Record<string, unknown> | null | undefined) {
    return (template?.display_config || {}) as {
      enabled_weekdays?: number[];
      description?: string;
      blank_rows?: Array<Partial<PreviewBlankRowDraft>>;
      blank_columns?: Array<Partial<PreviewBlankColumnDraft>>;
      header_rows?: Array<Partial<PreviewHeaderRowDraft>>;
      time_mode?: "fixed" | "variable";
      show_time_axis?: boolean;
      is_public_preset?: boolean;
      course_cell_layout?: CourseCellExportLayout;
      course_cell_top_field?: CourseCellExportField;
      course_cell_bottom_field?: CourseCellExportField;
      layout_kind?: TimetableTemplateLayoutKind;
      applicable_views?: TimetableResultViewMode[];
      all_classes_variant?: AllClassesTemplateVariant;
    };
  }

function normalizeTimetableTemplateLayoutKind(value: unknown): TimetableTemplateLayoutKind {
    return value === "all_classes_grid" ? "all_classes_grid" : "weekly";
  }

function normalizeAllClassesTemplateVariant(value: unknown): AllClassesTemplateVariant {
    return value === "period_rows_grouped" ? "period_rows_grouped" : "homeroom_rows";
  }

function periodDraftTimesAreFixed(drafts: PeriodDraft[]) {
    const timeByPeriod = new Map<number, string>();
    for (const period of drafts) {
      const periodIndex = Number(period.period_index);
      const timeKey = `${period.start_time}-${period.end_time}`;
      const current = timeByPeriod.get(periodIndex);
      if (current && current !== timeKey) {
        return false;
      }
      timeByPeriod.set(periodIndex, timeKey);
    }
    return true;
  }

function normalizeEnabledWeekdays(days: unknown) {
    const values = Array.isArray(days)
      ? days.map((day) => Number(day)).filter((day) => day >= 1 && day <= fixedWeeklyDayCount)
      : [1, 2, 3, 4, 5];
    const normalized = Array.from(new Set(values)).sort((left, right) => left - right);
    return normalized.length ? normalized : [1, 2, 3, 4, 5];
  }

function normalizePreviewBlankCells(
    cells: Record<string, Partial<PreviewBlankCellDraft>> | undefined,
  ): Record<string, PreviewBlankCellDraft> {
    return Object.fromEntries(
      Object.entries(cells || {}).map(([key, cell]) => [
        key,
        {
          label: String(cell.label || ""),
          align: cell.align === "left" ? "left" : "center",
          colspan: Math.max(Number(cell.colspan || 1), 1),
          rowspan: Math.max(Number(cell.rowspan || 1), 1),
          active: cell.active !== false,
          coveredBy: cell.coveredBy ? String(cell.coveredBy) : undefined,
        },
      ]),
    );
  }

function normalizePreviewBlankRows(rows: Array<Partial<PreviewBlankRowDraft>> | undefined): PreviewBlankRowDraft[] {
    return (rows || []).map((row, index) => {
      const cells = normalizePreviewBlankCells(
        (row as { cells?: Record<string, Partial<PreviewBlankCellDraft>> }).cells,
      );
      const label = String(row.label || ``);
      // 空白行 ${index + 1}
      if (!Object.keys(cells).length && row.label) {
        cells["weekday-0"] = {
          label,
          align: (row.align === "left" ? "left" : "center") as PreviewAlign,
          colspan: Math.max(Number(row.colspan || fixedWeeklyDayCount), 1),
          rowspan: 1,
          active: true,
        };
      }
      return {
        id: String(row.id || previewDraftId("blank-row")),
        label,
        align: (row.align === "left" ? "left" : "center") as PreviewAlign,
        colspan: Math.max(Number(row.colspan || fixedWeeklyDayCount), 1),
        order_index: Number((row as { order_index?: number }).order_index ?? 100 + index),
        cells,
      };
    });
  }

function normalizePreviewBlankColumns(columns: Array<Partial<PreviewBlankColumnDraft>> | undefined): PreviewBlankColumnDraft[] {
    return (columns || []).map((column, index) => ({
      id: String(column.id || previewDraftId("blank-column")),
      label: String(column.label || ``),
      // 空白列 ${index + 1}
      align: (column.align === "left" ? "left" : "center") as PreviewAlign,
      colspan: Math.max(Number(column.colspan || 1), 1),
      order_index: Number((column as { order_index?: number }).order_index ?? fixedWeeklyDayCount + index),
      cells: normalizePreviewBlankCells(
        (column as { cells?: Record<string, Partial<PreviewBlankCellDraft>> }).cells,
      ),
    }));
  }

function previewHeaderColumnKey(index: number) {
    return `header-${index}`;
  }

function normalizePreviewHeaderBinding(value: unknown): PreviewHeaderBinding {
    const normalizedValue = String(value);
    if (normalizedValue === "term_name") {
      return "project_name";
    }
    return ["template_name", "school_name", "project_name", "owner_name", "custom"].includes(normalizedValue)
      ? normalizedValue as PreviewHeaderBinding
      : "custom";
  }

function headerCellDefault(binding: PreviewHeaderBinding = "custom"): PreviewHeaderCellDraft {
    return {
      ...blankCellDefault(),
      binding,
    };
  }

function createDefaultPreviewHeaderRows(): PreviewHeaderRowDraft[] {
    return [{
      id: "template-title-header",
      order_index: 0,
      cells: {
        [previewHeaderColumnKey(0)]: {
          ...headerCellDefault("template_name"),
          colspan: fixedWeeklyDayCount + 1,
        },
      },
    }];
  }

function normalizePreviewHeaderRows(rows: Array<Partial<PreviewHeaderRowDraft>> | undefined): PreviewHeaderRowDraft[] {
    if (rows === undefined) {
      return createDefaultPreviewHeaderRows();
    }
    return rows.map((row, index) => {
      const sourceCells = (row as { cells?: Record<string, Partial<PreviewHeaderCellDraft>> }).cells || {};
      const cells = Object.fromEntries(
        Object.entries(sourceCells).map(([key, cell]) => [
          key,
          {
            label: String(cell.label || ""),
            binding: normalizePreviewHeaderBinding(cell.binding),
            align: (cell.align === "left" ? "left" : "center") as PreviewAlign,
            colspan: Math.max(Number(cell.colspan || 1), 1),
            rowspan: Math.max(Number(cell.rowspan || 1), 1),
            active: cell.active !== false,
            coveredBy: cell.coveredBy ? String(cell.coveredBy) : undefined,
          },
        ]),
      ) as Record<string, PreviewHeaderCellDraft>;
      return {
        id: String(row.id || previewDraftId("header-row")),
        order_index: Number((row as { order_index?: number }).order_index ?? index),
        cells,
      };
    }).sort((left, right) => left.order_index - right.order_index || left.id.localeCompare(right.id));
  }

function syncTimetableTemplateForms() {
    timetableTemplateDraftActive.value = false;
    periodTimeDrafts.value = {};
    periodTimeErrors.value = {};
    const template =
      selectedTimetableTemplate.value ||
      schoolData.value.default_weekly_timetable_template ||
      schoolData.value.weekly_timetable_templates[0];
    if (!template) {
      timetableTemplateForm.value = {
        id: "",
        name: "默认周课程表",
        day_count: fixedWeeklyDayCount,
        slot_duration_minutes: 5,
        is_default: true,
      };
      timetableTemplateDescription.value = "";
      selectedTemplateId.value = "";
      weeklyPeriodDrafts.value = generateDefaultPeriodDrafts();
      enabledWeekdays.value = [1, 2, 3, 4, 5];
      previewBlankRows.value = [];
      previewBlankColumns.value = [];
      previewHeaderRows.value = createDefaultPreviewHeaderRows();
      timetableTimeMode.value = "fixed";
      showTimetableTimeAxis.value = true;
      publishTimetablePreset.value = false;
      timetableTemplateKind.value = "normal";
      timetableTemplateApplicationScope.value = "all";
      timetableTemplatePeriodSourceId.value = "";
      timetableTemplatePeriodsLocked.value = false;
      courseCellExportLayout.value = "two_line";
      courseCellExportTopField.value = "subject";
      courseCellExportBottomField.value = "teacher";
      timetableTemplateLayoutKind.value = "weekly";
      allClassesTemplateVariant.value = "homeroom_rows";
      return;
    }

    selectedTemplateId.value = String(template.id || "");
    timetableTemplateForm.value = {
      id: String(template.id || ""),
      name: String(template.name || "默认周课程表"),
      day_count: fixedWeeklyDayCount,
      slot_duration_minutes: Number(template.slot_duration_minutes || 5),
      is_default: Boolean(template.is_default),
    };
    timetableTemplateDescription.value = String(templateDisplayConfig(template).description || "");
    timetableTemplateKind.value = template.template_kind === "special" ? "special" : "normal";
    timetableTemplateApplicationScope.value = String(template.application_scope || "all");
    timetableTemplatePeriodSourceId.value = String(template.period_source_template_id || "");
    timetableTemplatePeriodsLocked.value = Boolean(template.periods_locked);
    const periodTemplateId = String(template.period_source_template_id || template.id || "");
    const periods = schoolData.value.weekly_timetable_periods
      .filter((period) => String(period.template_id || "") === periodTemplateId)
      .sort((left, right) => {
        const weekdayDiff = Number(left.weekday || 0) - Number(right.weekday || 0);
        return weekdayDiff || Number(left.period_index || 0) - Number(right.period_index || 0);
      });
    weeklyPeriodDrafts.value = periods.length
      ? normalizeSevenDayPeriodDrafts(periods.map((period) => ({
          id: String(period.id || ""),
          weekday: Number(period.weekday || 1),
          period_index: Number(period.period_index || 1),
          label: periodDraftLabel(period),
          start_time: minutesToClock(period.start_time_minutes),
          end_time: minutesToClock(period.end_time_minutes),
          active: period.active !== false,
          align: periodDisplayConfig(period).align === "left" ? "left" : "center",
          colspan: Math.max(Number(periodDisplayConfig(period).colspan || 1), 1),
          ...periodDraftDisplayFields(period),
        })))
      : generateDefaultPeriodDrafts();
    const displayConfig = templateDisplayConfig(template);
    enabledWeekdays.value = normalizeEnabledWeekdays(displayConfig.enabled_weekdays);
    previewBlankRows.value = normalizePreviewBlankRows(displayConfig.blank_rows);
    previewBlankColumns.value = normalizePreviewBlankColumns(displayConfig.blank_columns);
    previewHeaderRows.value = normalizePreviewHeaderRows(displayConfig.header_rows);
    timetableTimeMode.value = displayConfig.time_mode
      ? (displayConfig.time_mode === "variable" ? "variable" : "fixed")
      : (periodDraftTimesAreFixed(weeklyPeriodDrafts.value) ? "fixed" : "variable");
    showTimetableTimeAxis.value = displayConfig.show_time_axis !== false;
    publishTimetablePreset.value = displayConfig.is_public_preset === true;
    courseCellExportLayout.value = ["single_line", "split_rows"].includes(String(displayConfig.course_cell_layout))
      ? displayConfig.course_cell_layout as CourseCellExportLayout
      : "two_line";
    courseCellExportTopField.value = displayConfig.course_cell_top_field || "subject";
    courseCellExportBottomField.value = displayConfig.course_cell_bottom_field || "teacher";
    timetableTemplateLayoutKind.value = normalizeTimetableTemplateLayoutKind(displayConfig.layout_kind);
    allClassesTemplateVariant.value = normalizeAllClassesTemplateVariant(displayConfig.all_classes_variant);
  }

function applySavedTimetablePreset(template: Record<string, unknown>) {
    const templateId = String(template.id || "");
    const periods = timetablePresetLibrary.value.weekly_timetable_preset_periods
      .filter((period) => String(period.template_id || "") === templateId)
      .sort((left, right) => {
        const weekdayDiff = Number(left.weekday || 0) - Number(right.weekday || 0);
        return weekdayDiff || Number(left.period_index || 0) - Number(right.period_index || 0);
      });
    if (!periods.length) {
      error.value = "这个预设没有可复用的课程时段";
      return;
    }
    if (creatingNewTimetableTemplate.value) {
      resetNewTimetableTemplateDraft();
    }
    weeklyPeriodDrafts.value = normalizeSevenDayPeriodDrafts(periods.map((period) => ({
      weekday: Number(period.weekday || 1),
      period_index: Number(period.period_index || 1),
      label: periodDraftLabel(period),
      start_time: minutesToClock(period.start_time_minutes),
      end_time: minutesToClock(period.end_time_minutes),
      active: period.active !== false,
      align: periodDisplayConfig(period).align === "left" ? "left" : "center",
      colspan: Math.max(Number(periodDisplayConfig(period).colspan || 1), 1),
      ...periodDraftDisplayFields(period),
    })));
    const displayConfig = templateDisplayConfig(template);
    enabledWeekdays.value = normalizeEnabledWeekdays(displayConfig.enabled_weekdays);
    previewBlankRows.value = normalizePreviewBlankRows(displayConfig.blank_rows);
    previewBlankColumns.value = normalizePreviewBlankColumns(displayConfig.blank_columns);
    previewHeaderRows.value = normalizePreviewHeaderRows(displayConfig.header_rows);
    timetableTimeMode.value = displayConfig.time_mode === "variable" ? "variable" : "fixed";
    showTimetableTimeAxis.value = displayConfig.show_time_axis !== false;
    courseCellExportLayout.value = ["single_line", "split_rows"].includes(String(displayConfig.course_cell_layout))
      ? displayConfig.course_cell_layout as CourseCellExportLayout
      : "two_line";
    courseCellExportTopField.value = displayConfig.course_cell_top_field || "subject";
    courseCellExportBottomField.value = displayConfig.course_cell_bottom_field || "teacher";
    timetableTemplateLayoutKind.value = normalizeTimetableTemplateLayoutKind(displayConfig.layout_kind);
    allClassesTemplateVariant.value = normalizeAllClassesTemplateVariant(displayConfig.all_classes_variant);
    periodTimeDrafts.value = {};
    periodTimeErrors.value = {};
    selectedPreviewCell.value = null;
    showTimetableTimePresetPicker.value = false;
    timetableTemplateDraftActive.value = true;
    creatingNewTimetableTemplate.value = false;
  }

function generateDefaultPeriodDrafts() {
    const starts = ["08:00", "08:50", "10:00", "10:50", "14:00", "14:50", "16:00", "16:50"];
    return Array.from({ length: fixedWeeklyDayCount }, (_, dayIndex) =>
      starts.map((start, index) => {
        const startMinutes = clockToMinutes(start);
        return {
          weekday: dayIndex + 1,
          period_index: index + 1,
          label: defaultCellLabel(dayIndex + 1, index + 1),
          start_time: start,
          end_time: minutesToClock(startMinutes + 40),
          active: dayIndex < 5,
          align: "center" as const,
          colspan: 1,
        };
      }),
    ).flat();
  }

function normalizeSevenDayPeriodDrafts(drafts: PeriodDraft[]) {
    const sanitized = drafts
      .filter((period) => Number(period.weekday) >= 1 && Number(period.weekday) <= fixedWeeklyDayCount)
      .map((period) => ({
        ...period,
        weekday: Number(period.weekday),
        period_index: Number(period.period_index),
        colspan: Math.min(
          Math.max(Number(period.colspan || 1), 1),
          fixedWeeklyDayCount - Number(period.weekday) + 1,
        ),
      }));
    if (!sanitized.length) {
      return generateDefaultPeriodDrafts();
    }

    const rowIndexes = Array.from(
      new Set(sanitized.map((period) => Number(period.period_index || 0)).filter(Boolean)),
    ).sort((left, right) => left - right);

    for (const periodIndex of rowIndexes) {
      const sibling = sanitized.find((period) => Number(period.period_index) === periodIndex);
      for (let weekday = 1; weekday <= fixedWeeklyDayCount; weekday += 1) {
        const exists = sanitized.some(
          (period) => Number(period.period_index) === periodIndex && Number(period.weekday) === weekday,
        );
        if (!exists) {
          sanitized.push({
            weekday,
            period_index: periodIndex,
            label: defaultCellLabel(weekday, periodIndex),
            start_time: sibling?.start_time || "08:00",
            end_time: sibling?.end_time || "08:40",
            active: false,
            align: "center",
            colspan: 1,
          });
        }
      }
    }

    return sanitized.sort((left, right) => left.period_index - right.period_index || left.weekday - right.weekday);
  }

function periodDisplayConfig(period: Record<string, unknown>) {
    return (period.display_config || {}) as {
      align?: string;
      colspan?: number;
      cell_mode?: PeriodCellMode;
      custom_content?: string;
      sample_subject?: string;
      sample_teacher?: string;
      sample_room?: string;
      sample_homeroom?: string;
      export_style?: PeriodCellExportStyle;
      export_layout?: CourseCellExportLayout;
      export_top_field?: CourseCellExportField;
      export_bottom_field?: CourseCellExportField;
    };
  }

function normalizePeriodCellMode(value: unknown, active = true): PeriodCellMode {
    if (value === "scheduled" || value === "custom" || value === "disabled") {
      return value;
    }
    return active ? "scheduled" : "disabled";
  }

function normalizeCourseCellExportLayout(value: unknown, fallback: CourseCellExportLayout = "two_line") {
    return value === "single_line" || value === "two_line" || value === "split_rows" ? value : fallback;
  }

function normalizeCourseCellExportField(value: unknown, fallback: CourseCellExportField) {
    return value === "subject" || value === "teacher" || value === "room" || value === "time" || value === "homeroom"
      ? value
      : fallback;
  }

function periodDraftDisplayFields(period: Record<string, unknown>) {
    const display = periodDisplayConfig(period);
    const mode = normalizePeriodCellMode(display.cell_mode, period.active !== false);
    return {
      cell_mode: mode,
      custom_content: String(display.custom_content || ""),
      sample_subject: String(display.sample_subject || ""),
      sample_teacher: String(display.sample_teacher || ""),
      sample_room: String(display.sample_room || ""),
      sample_homeroom: String(display.sample_homeroom || ""),
      export_style: display.export_style === "custom" ? "custom" as const : "default" as const,
      export_layout: normalizeCourseCellExportLayout(display.export_layout),
      export_top_field: normalizeCourseCellExportField(display.export_top_field, "subject"),
      export_bottom_field: normalizeCourseCellExportField(display.export_bottom_field, "teacher"),
    };
  }

function defaultCellLabel(weekday: number, periodIndex: number) {
    const day = weekdayOptions[weekday - 1]?.label || `周${weekday}`;
    return `${day}第${periodIndex}节`;
  }

function escapeHtml(value: unknown) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

function blankCellDefault(): PreviewBlankCellDraft {
    return { label: "", align: "center", colspan: 1, rowspan: 1, active: true };
  }

function selectNumberValue(event: Event | { target: { value: unknown } }) {
    return Number((event.target as HTMLSelectElement).value || 1);
  }

function blankRowCellRootId(rowId: string, columnKey: string) {
    return `blank-row:${rowId}:${columnKey}`;
  }

function blankColumnCellRootId(columnId: string, rowKey: string) {
    return `blank-column:${columnId}:${rowKey}`;
  }

function sanitizeFileName(value: string) {
    return value
      .trim()
      .replace(/[\\/:*?"<>|]/g, "-")
      .replace(/\s+/g, "-")
      .slice(0, 80) || "周课程表模板";
  }

function periodDraftLabel(period: Record<string, unknown>) {
    const weekday = Number(period.weekday || 1);
    const periodIndex = Number(period.period_index || 1);
    return defaultCellLabel(weekday, periodIndex);
  }

function selectTimetableTemplate(templateId: string) {
    selectedTemplateId.value = templateId;
    syncTimetableTemplateForms();
  }

function periodsForWeekday(weekday: number) {
    return weeklyPeriodDrafts.value
      .filter((period) => Number(period.weekday) === Number(weekday))
      .sort((left, right) => Number(left.period_index) - Number(right.period_index));
  }

function isTemplateWeekdayEnabled(weekday: number) {
    return enabledWeekdays.value.includes(weekday);
  }

function setTemplateWeekdayEnabled(weekday: number, active: boolean) {
    if (active) {
      enabledWeekdays.value = Array.from(new Set([...enabledWeekdays.value, weekday])).sort((left, right) => left - right);
      periodsForWeekday(weekday).forEach((period) => {
        period.active = period.cell_mode ? period.cell_mode === "scheduled" : true;
      });
      roomUnavailableRuleForm.value.day_bits = sanitizeDayBitsForEnabledWeekdays(roomUnavailableRuleForm.value.day_bits);
      coursePreferredRuleForm.value.day_bits = sanitizeDayBitsForEnabledWeekdays(coursePreferredRuleForm.value.day_bits);
      return;
    }
    if (enabledWeekdays.value.length <= 1 && enabledWeekdays.value.includes(weekday)) {
      return;
    }
    enabledWeekdays.value = enabledWeekdays.value.filter((day) => day !== weekday);
    periodsForWeekday(weekday).forEach((period) => {
      period.active = false;
    });
    roomUnavailableRuleForm.value.day_bits = sanitizeDayBitsForEnabledWeekdays(roomUnavailableRuleForm.value.day_bits);
    coursePreferredRuleForm.value.day_bits = sanitizeDayBitsForEnabledWeekdays(coursePreferredRuleForm.value.day_bits);
  }

function relabelWeekdayPeriods(weekday: number) {
    periodsForWeekday(weekday).forEach((period, index) => {
      period.period_index = index + 1;
      period.label = defaultCellLabel(weekday, index + 1);
    });
  }

function relabelAllPeriods() {
    for (let weekday = 1; weekday <= fixedWeeklyDayCount; weekday += 1) {
      relabelWeekdayPeriods(weekday);
    }
  }

function applyFixedTimetableTimes() {
    const periodIndexes = Array.from(
      new Set(weeklyPeriodDrafts.value.map((period) => Number(period.period_index)).filter(Boolean)),
    );
    for (const periodIndex of periodIndexes) {
      const matching = weeklyPeriodDrafts.value
        .filter((period) => Number(period.period_index) === periodIndex)
        .sort((left, right) => Number(left.weekday) - Number(right.weekday));
      const source = matching.find((period) => Number(period.weekday) === 1) || matching[0];
      if (!source) continue;
      matching.forEach((period) => {
        period.start_time = source.start_time;
        period.end_time = source.end_time;
      });
    }
  }

function setTimetableTimeMode(mode: "fixed" | "variable") {
    timetableTimeMode.value = mode;
    if (mode === "fixed") {
      applyFixedTimetableTimes();
    }
    periodTimeDrafts.value = {};
    periodTimeErrors.value = {};
    showTimetableTimePresetPicker.value = false;
  }

function periodTimeKey(period: PeriodDraft) {
    return `${Number(period.weekday)}-${Number(period.period_index)}`;
  }

function periodTimeError(period: PeriodDraft | null) {
    return period ? periodTimeErrors.value[periodTimeKey(period)] || "" : "";
  }

function ensurePeriodTimeDraft(period: PeriodDraft) {
    const key = periodTimeKey(period);
    if (!periodTimeDrafts.value[key]) {
      periodTimeDrafts.value[key] = {
        start_time: period.start_time,
        end_time: period.end_time,
      };
    }
    return periodTimeDrafts.value[key];
  }

function periodTimeDraftValue(period: PeriodDraft | null, field: "start_time" | "end_time") {
    return period ? ensurePeriodTimeDraft(period)[field] : "";
  }

function clearPeriodTimeError(period: PeriodDraft) {
    const nextErrors = { ...periodTimeErrors.value };
    delete nextErrors[periodTimeKey(period)];
    periodTimeErrors.value = nextErrors;
  }

function neighboringActivePeriods(period: PeriodDraft) {
    const siblings = periodsForWeekday(Number(period.weekday))
      .filter((candidate) => candidate !== period && candidate.active !== false)
      .sort((left, right) => Number(left.period_index) - Number(right.period_index));
    const previousPeriods = siblings.filter(
      (candidate) => Number(candidate.period_index) < Number(period.period_index),
    );
    return {
      previous: previousPeriods[previousPeriods.length - 1] || null,
      next: siblings.find((candidate) => Number(candidate.period_index) > Number(period.period_index)) || null,
    };
  }

function previousPeriodEndTime(period: PeriodDraft) {
    return neighboringActivePeriods(period).previous?.end_time || "";
  }

function nextPeriodStartTime(period: PeriodDraft) {
    return neighboringActivePeriods(period).next?.start_time || "";
  }

function beginPeriodTimeEdit(period: PeriodDraft) {
    const key = periodTimeKey(period);
    if (!periodTimeErrors.value[key]) {
      periodTimeDrafts.value[key] = {
        start_time: period.start_time,
        end_time: period.end_time,
      };
    } else {
      ensurePeriodTimeDraft(period);
    }
    clearPeriodTimeError(period);
  }

function validatePeriodTimeRange(period: PeriodDraft, startTime: string, endTime: string) {
    const weekday = weekdayOptions[Number(period.weekday) - 1]?.label || `星期 ${period.weekday}`;
    const startMinutes = clockToMinutes(startTime);
    const endMinutes = clockToMinutes(endTime);
    if (!startTime || !endTime || endMinutes <= startMinutes) {
      return `${weekday}的结束时间必须晚于开始时间。`;
    }
    const { previous, next } = neighboringActivePeriods(period);
    if (previous && startMinutes < clockToMinutes(previous.end_time)) {
      return `${weekday}当前课程开始时间不能早于上一课程结束时间 ${previous.end_time}。`;
    }
    if (next && endMinutes > clockToMinutes(next.start_time)) {
      return `${weekday}当前课程结束时间不能晚于下一课程开始时间 ${next.start_time}。`;
    }
    return "";
  }

function updatePeriodTimeDraft(
    period: PeriodDraft | null,
    field: "start_time" | "end_time",
    event: Event,
  ) {
    if (!period) return;
    const input = event.target as HTMLInputElement;
    ensurePeriodTimeDraft(period)[field] = input.value;
    clearPeriodTimeError(period);
  }

function commitPeriodTimeDraft(period: PeriodDraft | null) {
    if (!period) return true;
    const key = periodTimeKey(period);
    const draft = ensurePeriodTimeDraft(period);
    const targets = timetableTimeMode.value === "fixed"
      ? weeklyPeriodDrafts.value.filter(
          (candidate) => Number(candidate.period_index) === Number(period.period_index),
        )
      : [period];
    let message = "";
    for (const target of targets) {
      message = validatePeriodTimeRange(target, draft.start_time, draft.end_time);
      if (message) break;
    }
    if (message) {
      periodTimeErrors.value = { ...periodTimeErrors.value, [key]: message };
      return false;
    }
    targets.forEach((target) => {
      target.start_time = draft.start_time;
      target.end_time = draft.end_time;
      periodTimeDrafts.value[periodTimeKey(target)] = {
        start_time: draft.start_time,
        end_time: draft.end_time,
      };
    });
    const nextErrors = { ...periodTimeErrors.value };
    targets.forEach((target) => delete nextErrors[periodTimeKey(target)]);
    periodTimeErrors.value = nextErrors;
    return true;
  }

function commitPeriodTimeOnEnter(period: PeriodDraft | null, event: KeyboardEvent) {
    const input = event.currentTarget as HTMLInputElement;
    input.blur();
  }

function validateAllPeriodTimes() {
    for (const weekday of enabledWeekdays.value) {
      const periods = periodsForWeekday(weekday).filter((period) => period.active !== false);
      for (const period of periods) {
        const draft = periodTimeDrafts.value[periodTimeKey(period)];
        if (
          draft &&
          (draft.start_time !== period.start_time || draft.end_time !== period.end_time) &&
          !commitPeriodTimeDraft(period)
        ) {
          return periodTimeError(period);
        }
      }
    }
    const nextErrors: Record<string, string> = {};
    for (const weekday of enabledWeekdays.value) {
      const periods = periodsForWeekday(weekday).filter((period) => period.active !== false);
      for (const period of periods) {
        const message = validatePeriodTimeRange(period, period.start_time, period.end_time);
        if (message) {
          nextErrors[periodTimeKey(period)] = message;
        }
      }
    }
    periodTimeErrors.value = nextErrors;
    return Object.values(nextErrors)[0] || "";
  }

const timetablePreviewDays = computed(() => weekdayOptions);

const enabledTimetablePreviewDays = computed(() =>
    weekdayOptions.filter((day) => enabledWeekdays.value.includes(day.index + 1)),
  );

const timetablePreviewColumns = computed(() => {
    const weekdayColumns = enabledTimetablePreviewDays.value.map((day) => ({
      kind: "weekday" as const,
      id: `weekday-${day.index}`,
      sort: day.index,
      day,
    }));
    const blankColumns = previewBlankColumns.value.map((column, index) => ({
      kind: "blank" as const,
      id: column.id,
      sort: Number.isFinite(column.order_index) ? column.order_index : fixedWeeklyDayCount + index,
      column,
    }));
    return [...weekdayColumns, ...blankColumns].sort((left, right) => {
      const diff = left.sort - right.sort;
      if (diff !== 0) return diff;
      if (left.kind === right.kind) return left.id.localeCompare(right.id);
      return left.kind === "blank" ? -1 : 1;
    });
  });

const previewBodyColumnCount = computed(
    () =>
      enabledTimetablePreviewDays.value.length +
      previewBlankColumns.value.reduce((total, column) => total + Math.max(Number(column.colspan || 1), 1), 0),
  );

const previewHeaderColumnCount = computed(
    () => Math.max(
      timetableTemplateLayoutKind.value === "all_classes_grid"
        ? (allClassesTemplateVariant.value === "period_rows_grouped"
            ? fullTablePreviewColumnCount.value
            : irregularPreviewColumnCount.value + 1)
        : previewBodyColumnCount.value + (showTimetableTimeAxis.value ? 1 : 0),
      1,
    ),
  );

const canDeleteCurrentRow = computed(
    () => selectedPreviewCell.value?.kind === "period" || selectedPreviewCell.value?.kind === "blank-row",
  );

const timetablePreviewRows = computed(() => {
    const buildRow = (
      rowIndex: number,
      startTime: string,
      periods: PeriodDraft[],
      fixedPeriodIndex?: number,
      timeline?: {
        allPeriods: PeriodDraft[];
        intervals: Array<{ start: string; end: string }>;
        terminalTime?: string;
      },
    ) => {
      const renderedCells: Array<
        | { kind: "period"; period: PeriodDraft | null; dayIndex: number; colspan: number; rowspan: number }
        | { kind: "blank"; column: PreviewBlankColumnDraft; rowKey: string; colspan: number; rowspan: number }
      > = [];
      const rowKey = `period-${rowIndex}`;
      for (let index = 0; index < timetablePreviewColumns.value.length; index += 1) {
        const column = timetablePreviewColumns.value[index];
        if (column.kind === "blank") {
          const blankCell = previewBlankColumnCell(column.column, rowKey);
          if (blankCell.coveredBy) {
            continue;
          }
          const colspan = Math.min(
            Math.max(Number(blankCell.colspan || column.column.colspan || 1), 1),
            maxBlankColumnCellColspan(column.column.id),
          );
          renderedCells.push({
            kind: "blank",
            column: column.column,
            rowKey,
            colspan,
            rowspan: Math.max(Number(blankCell.rowspan || 1), 1),
          });
          index += colspan - 1;
          continue;
        }
        const period =
          periods.find(
            (item) =>
              Number(item.weekday) === column.day.index + 1,
          ) || null;
        const isCoveredByEarlierPeriod = Boolean(
          timeline &&
          !period &&
          timeline.allPeriods.some(
            (item) =>
              Number(item.weekday) === column.day.index + 1 &&
              clockToMinutes(item.start_time) < clockToMinutes(startTime) &&
              clockToMinutes(item.end_time) > clockToMinutes(startTime),
          ),
        );
        if (isCoveredByEarlierPeriod) {
          continue;
        }
        let maxSpan = 1;
        for (let cursor = index + 1; cursor < timetablePreviewColumns.value.length; cursor += 1) {
          const nextColumn = timetablePreviewColumns.value[cursor];
          if (nextColumn.kind !== "weekday" || nextColumn.day.index !== column.day.index + maxSpan) {
            break;
          }
          maxSpan += 1;
        }
        // Variable-time rows must retain one cell per weekday so missing periods
        // remain visible as blank placeholders instead of being swallowed by colspan.
        const requestedSpan =
          period && timetableTimeMode.value === "fixed"
            ? Math.max(Number(period.colspan || 1), 1)
            : 1;
        const colspan = Math.min(requestedSpan, maxSpan);
        const rowspan = timeline && period
          ? Math.max(
            timeline.intervals.filter(
              (interval) =>
                clockToMinutes(interval.start) >= clockToMinutes(period.start_time) &&
                clockToMinutes(interval.end) <= clockToMinutes(period.end_time),
            ).length,
            1,
          )
          : 1;
        renderedCells.push({ kind: "period", period, dayIndex: column.day.index, colspan, rowspan });
        index += colspan - 1;
      }
      return {
        id: timeline
          ? `time-${startTime}`
          : timetableTimeMode.value === "fixed"
          ? `fixed-${fixedPeriodIndex || rowIndex}`
          : `time-${startTime}`,
        rowKey,
        periodIndex: fixedPeriodIndex || periods[0]?.period_index || rowIndex,
        sort: rowIndex,
        timeLabel: startTime || "--:--",
        terminalTimeLabel: timeline?.terminalTime || "",
        renderedCells,
      };
    };

    const timelinePeriods = weeklyPeriodDrafts.value.filter(
      (period) =>
        enabledWeekdays.value.includes(Number(period.weekday)) &&
        period.start_time &&
        period.end_time,
    );
    const timelinePoints = Array.from(
      new Set(timelinePeriods.flatMap((period) => [period.start_time, period.end_time])),
    ).sort((left, right) => clockToMinutes(left) - clockToMinutes(right));
    const visibleIntervals = timelinePoints
      .slice(0, -1)
      .map((start, index) => ({ start, end: timelinePoints[index + 1] }))
      .filter((interval) =>
        timelinePeriods.some(
          (period) =>
            clockToMinutes(period.start_time) < clockToMinutes(interval.end) &&
            clockToMinutes(period.end_time) > clockToMinutes(interval.start),
        ),
      );
    return visibleIntervals.map((interval, rowIndex) => {
      const startTime = interval.start;
      const periods = timelinePeriods.filter((period) => period.start_time === startTime);
      const nextInterval = visibleIntervals[rowIndex + 1];
      const endsBeforeGap = !nextInterval || nextInterval.start !== interval.end;
      return buildRow(
        rowIndex + 1,
        startTime,
        periods,
        timetableTimeMode.value === "fixed"
          ? Number(periods[0]?.period_index || 0) || undefined
          : undefined,
        {
          allPeriods: timelinePeriods,
          intervals: visibleIntervals,
          terminalTime: endsBeforeGap ? interval.end : "",
        },
      );
    });
  });

const timetablePreviewRowFlow = computed(() => {
    const periodRows = timetablePreviewRows.value.map((row) => ({
      kind: "period" as const,
      id: row.id,
      sort: Number(row.sort),
      row,
    }));
    const blankRows = previewBlankRows.value.map((row, index) => ({
      kind: "blank" as const,
      id: row.id,
      sort: Number.isFinite(row.order_index) ? row.order_index : 100 + index,
      row,
    }));
    return [...periodRows, ...blankRows].sort((left, right) => {
      const diff = left.sort - right.sort;
      if (diff !== 0) return diff;
      if (left.kind === right.kind) return left.id.localeCompare(right.id);
      return left.kind === "blank" ? -1 : 1;
    });
  });

function fullTableHomeroom(id: string, name: string) {
    const normalizedName = String(name || "未命名班级").trim();
    const match = normalizedName.match(/^(.*?年级)\s*([一二三四五六七八九十\d]+)\s*班$/);
    return {
      id,
      name: normalizedName,
      gradeLabel: match?.[1] || "其他班级",
      classLabel: match?.[2] || normalizedName,
    };
  }

function fullTableGradeGroups<T extends { gradeLabel: string }>(homerooms: T[]) {
    const groups: Array<{ label: string; homerooms: T[] }> = [];
    for (const homeroom of homerooms) {
      let group = groups.find((item) => item.label === homeroom.gradeLabel);
      if (!group) {
        group = { label: homeroom.gradeLabel, homerooms: [] };
        groups.push(group);
      }
      group.homerooms.push(homeroom);
    }
    return groups;
  }

function fullTableDaySegment(startTime: string) {
    const minutes = clockToMinutes(startTime || "00:00");
    if (minutes < 12 * 60) return "上午";
    if (minutes < 14 * 60) return "中午";
    return "下午";
  }

const irregularPreviewDayGroups = computed(() =>
    enabledTimetablePreviewDays.value.map((day) => ({
      weekday: day.index + 1,
      label: day.label,
      periods: periodsForWeekday(day.index + 1).filter((period) => period.active),
    })).filter((group) => group.periods.length),
  );

const irregularPreviewHomerooms = computed(() => {
    const rows = schoolData.value.homerooms.map((homeroom) => ({
      id: String(homeroom.id || recordName(homeroom)),
      name: recordName(homeroom, "未命名班级"),
    }));
    return rows.length ? rows : [{ id: "sample-homeroom", name: "示例班级" }];
  });

const irregularPreviewColumnCount = computed(() =>
    irregularPreviewDayGroups.value.reduce((total, group) => total + group.periods.length, 0),
  );

const fullTablePreviewHomerooms = computed(() =>
    irregularPreviewHomerooms.value.map((homeroom) => fullTableHomeroom(homeroom.id, homeroom.name)),
  );

const fullTablePreviewDayGroups = computed(() => {
    const gradeGroups = fullTableGradeGroups(fullTablePreviewHomerooms.value);
    return enabledTimetablePreviewDays.value.map((day) => ({
      weekday: day.index + 1,
      label: day.label,
      gradeGroups,
      homerooms: fullTablePreviewHomerooms.value,
    }));
  });

const fullTablePreviewPeriods = computed(() => {
    const periodsByIndex = new Map<number, PeriodDraft>();
    for (const period of weeklyPeriodDrafts.value) {
      if (!period.active || periodsByIndex.has(Number(period.period_index))) continue;
      periodsByIndex.set(Number(period.period_index), period);
    }
    const periods = Array.from(periodsByIndex.values())
      .sort((left, right) => Number(left.period_index) - Number(right.period_index))
      .map((period) => ({
        ...period,
        segment: fullTableDaySegment(period.start_time),
        segmentStart: false,
        segmentRowspan: 0,
      }));
    for (let index = 0; index < periods.length; index += 1) {
      if (index > 0 && periods[index - 1].segment === periods[index].segment) continue;
      let end = index + 1;
      while (end < periods.length && periods[end].segment === periods[index].segment) end += 1;
      periods[index].segmentStart = true;
      periods[index].segmentRowspan = (end - index) * 2;
    }
    return periods;
  });

const fullTablePreviewColumnCount = computed(() =>
    3 + fullTablePreviewDayGroups.value.reduce((total, group) => total + group.homerooms.length, 0),
  );

const selectedPreviewPeriod = computed(() => {
    const selection = selectedPreviewCell.value;
    if (!selection || selection.kind !== "period") {
      return null;
    }
    return weeklyPeriodDrafts.value.find(
      (period) =>
        Number(period.period_index) === selection.periodIndex &&
        Number(period.weekday) === selection.dayIndex + 1,
    ) || null;
  });

function previewPeriodMode(period: PeriodDraft | null | undefined): PeriodCellMode {
    return period ? normalizePeriodCellMode(period.cell_mode, period.active) : "disabled";
  }

function ensurePeriodDraftDisplayDefaults(period: PeriodDraft) {
    period.cell_mode = previewPeriodMode(period);
    period.custom_content ??= "";
    period.sample_subject ??= "数学";
    period.sample_teacher ??= "张三";
    period.sample_room ??= "一号教室";
    period.sample_homeroom ??= "一年级1班";
    period.export_style = period.export_style === "custom" ? "custom" : "default";
    period.export_layout = normalizeCourseCellExportLayout(period.export_layout, courseCellExportLayout.value);
    period.export_top_field = normalizeCourseCellExportField(period.export_top_field, courseCellExportTopField.value);
    period.export_bottom_field = normalizeCourseCellExportField(period.export_bottom_field, courseCellExportBottomField.value);
  }

function setPreviewPeriodMode(period: PeriodDraft, mode: PeriodCellMode) {
    ensurePeriodDraftDisplayDefaults(period);
    period.cell_mode = mode;
    period.active = mode === "scheduled";
    if (mode === "disabled") {
      period.custom_content = "";
    }
  }

function previewPeriodExportStyle(period: PeriodDraft | null | undefined): PeriodCellExportStyle {
    return period?.export_style === "custom" ? "custom" : "default";
  }

function setPreviewPeriodExportStyle(period: PeriodDraft, style: PeriodCellExportStyle) {
    ensurePeriodDraftDisplayDefaults(period);
    period.export_style = style;
  }

const selectedPreviewHeaderCell = computed(() => {
    const selection = selectedPreviewCell.value;
    if (!selection || selection.kind !== "header-cell") {
      return null;
    }
    const row = previewHeaderRows.value.find((item) => item.id === selection.rowId);
    if (!row) {
      return null;
    }
    if (!row.cells[selection.columnKey]) {
      row.cells[selection.columnKey] = headerCellDefault();
    }
    return {
      row,
      columnKey: selection.columnKey,
      cell: row.cells[selection.columnKey],
    };
  });

function previewHeaderBindingValue(
    binding: PreviewHeaderBinding,
    customLabel = "",
    templateName?: string,
    ownerName = "归属主体名称",
  ) {
    const values: Record<Exclude<PreviewHeaderBinding, "custom">, string> = {
      template_name: String(templateName ?? timetableTemplateForm.value.name ?? "周课程表模板"),
      school_name: String(selectedOrganization.value?.name || ""),
      project_name: currentProjectName.value,
      owner_name: ownerName,
    };
    return binding === "custom" ? customLabel : values[binding];
  }

function previewHeaderCellText(cell: PreviewHeaderCellDraft, templateName?: string, ownerName?: string) {
    return previewHeaderBindingValue(cell.binding, cell.label, templateName, ownerName);
  }

function headerRowRenderedCells(
    rows: PreviewHeaderRowDraft[],
    row: PreviewHeaderRowDraft,
    columnCount: number,
    templateName?: string,
    ownerName?: string,
  ) {
    const rendered: Array<{
      columnKey: string;
      cell: PreviewHeaderCellDraft;
      label: string;
      colspan: number;
      rowspan: number;
    }> = [];
    for (let index = 0; index < columnCount; index += 1) {
      const columnKey = previewHeaderColumnKey(index);
      const cell = row.cells[columnKey] || headerCellDefault();
      if (cell.coveredBy) {
        continue;
      }
      const colspan = Math.min(Math.max(Number(cell.colspan || 1), 1), columnCount - index);
      const rowIndex = rows.findIndex((item) => item.id === row.id);
      const rowspan = Math.min(
        Math.max(Number(cell.rowspan || 1), 1),
        Math.max(rows.length - Math.max(rowIndex, 0), 1),
      );
      rendered.push({
        columnKey,
        cell,
        label: previewHeaderCellText(cell, templateName, ownerName),
        colspan,
        rowspan,
      });
      index += colspan - 1;
    }
    return rendered;
  }

function previewHeaderRowRenderedCells(row: PreviewHeaderRowDraft) {
    return headerRowRenderedCells(previewHeaderRows.value, row, previewHeaderColumnCount.value);
  }

function selectPreviewHeaderCell(row: PreviewHeaderRowDraft, columnKey: string) {
    if (!row.cells[columnKey]) {
      row.cells[columnKey] = headerCellDefault();
    }
    selectedPreviewCell.value = { kind: "header-cell", rowId: row.id, columnKey };
  }

function isPreviewHeaderCellSelected(row: PreviewHeaderRowDraft, columnKey: string) {
    return selectedPreviewCell.value?.kind === "header-cell"
      && selectedPreviewCell.value.rowId === row.id
      && selectedPreviewCell.value.columnKey === columnKey;
  }

function headerCellRootId(rowId: string, columnKey: string) {
    return `header:${rowId}:${columnKey}`;
  }

function clearPreviewHeaderCellMerge(rootId: string) {
    for (const row of previewHeaderRows.value) {
      for (const [columnKey, cell] of Object.entries(row.cells)) {
        if (cell.coveredBy === rootId) {
          delete cell.coveredBy;
        }
        if (headerCellRootId(row.id, columnKey) === rootId) {
          cell.colspan = 1;
          cell.rowspan = 1;
        }
      }
    }
  }

function addPreviewHeaderRow() {
    const row: PreviewHeaderRowDraft = {
      id: previewDraftId("header-row"),
      order_index: previewHeaderRows.value.length,
      cells: {
        [previewHeaderColumnKey(0)]: {
          ...headerCellDefault("custom"),
          colspan: previewHeaderColumnCount.value,
        },
      },
    };
    previewHeaderRows.value.push(row);
    selectPreviewHeaderCell(row, previewHeaderColumnKey(0));
  }

function canMovePreviewHeaderRow(rowId: string, direction: -1 | 1) {
    const index = previewHeaderRows.value.findIndex((row) => row.id === rowId);
    const nextIndex = index + direction;
    return index >= 0 && nextIndex >= 0 && nextIndex < previewHeaderRows.value.length;
  }

function movePreviewHeaderRow(rowId: string, direction: -1 | 1) {
    const index = previewHeaderRows.value.findIndex((row) => row.id === rowId);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= previewHeaderRows.value.length) {
      return;
    }
    const nextRows = [...previewHeaderRows.value];
    [nextRows[index], nextRows[nextIndex]] = [nextRows[nextIndex], nextRows[index]];
    nextRows.forEach((row, rowIndex) => {
      row.order_index = rowIndex;
    });
    previewHeaderRows.value = nextRows;
  }

function deletePreviewHeaderRow(rowId: string) {
    const row = previewHeaderRows.value.find((item) => item.id === rowId);
    if (!row) return;
    const rootIds = new Set<string>();
    for (const [columnKey, cell] of Object.entries(row.cells)) {
      rootIds.add(cell.coveredBy || headerCellRootId(row.id, columnKey));
    }
    rootIds.forEach(clearPreviewHeaderCellMerge);
    previewHeaderRows.value = previewHeaderRows.value
      .filter((item) => item.id !== rowId)
      .map((item, index) => ({ ...item, order_index: index }));
    selectedPreviewCell.value = null;
  }

const selectedPreviewHeaderCellMaxColspan = computed(() => {
    const selection = selectedPreviewHeaderCell.value;
    if (!selection) return 1;
    const index = Number(selection.columnKey.replace("header-", ""));
    return Number.isFinite(index) ? Math.max(previewHeaderColumnCount.value - index, 1) : 1;
  });

const selectedPreviewHeaderCellMaxRowspan = computed(() => {
    const selection = selectedPreviewHeaderCell.value;
    if (!selection) return 1;
    const index = previewHeaderRows.value.findIndex((row) => row.id === selection.row.id);
    return index < 0 ? 1 : Math.max(previewHeaderRows.value.length - index, 1);
  });

function applySelectedHeaderCellMerge(rowspan: number, colspan: number) {
    const selection = selectedPreviewHeaderCell.value;
    if (!selection) return;
    const startRowIndex = previewHeaderRows.value.findIndex((row) => row.id === selection.row.id);
    const startColumnIndex = Number(selection.columnKey.replace("header-", ""));
    if (startRowIndex < 0 || !Number.isFinite(startColumnIndex)) return;
    const safeRowspan = Math.max(Math.min(rowspan, selectedPreviewHeaderCellMaxRowspan.value), 1);
    const safeColspan = Math.max(Math.min(colspan, selectedPreviewHeaderCellMaxColspan.value), 1);
    const rootId = headerCellRootId(selection.row.id, selection.columnKey);
    const rootCell = selection.cell;
    const targets: Array<{ cell: PreviewHeaderCellDraft; isRoot: boolean }> = [];
    for (let rowOffset = 0; rowOffset < safeRowspan; rowOffset += 1) {
      const row = previewHeaderRows.value[startRowIndex + rowOffset];
      if (!row) return;
      for (let colOffset = 0; colOffset < safeColspan; colOffset += 1) {
        const columnKey = previewHeaderColumnKey(startColumnIndex + colOffset);
        if (!row.cells[columnKey]) {
          row.cells[columnKey] = headerCellDefault();
        }
        const cell = row.cells[columnKey];
        const isRoot = row.id === selection.row.id && columnKey === selection.columnKey;
        if (!isRoot && (cell.coveredBy || Number(cell.colspan || 1) > 1 || Number(cell.rowspan || 1) > 1)) {
          error.value = "合并区域里已有合并单元格，请先拆分后再合并。";
          return;
        }
        targets.push({ cell, isRoot });
      }
    }
    if (!previewHeaderCellText(rootCell).trim()) {
      const source = targets.find((target) => previewHeaderCellText(target.cell).trim());
      if (source) {
        rootCell.binding = source.cell.binding;
        rootCell.label = source.cell.label;
      }
    }
    clearPreviewHeaderCellMerge(rootId);
    rootCell.rowspan = safeRowspan;
    rootCell.colspan = safeColspan;
    for (const target of targets) {
      if (!target.isRoot) {
        resetCoveredCell(target.cell, rootId);
        target.cell.binding = "custom";
      }
    }
  }

function splitSelectedHeaderCell() {
    const selection = selectedPreviewHeaderCell.value;
    if (!selection) return;
    clearPreviewHeaderCellMerge(headerCellRootId(selection.row.id, selection.columnKey));
  }

const selectedPreviewBlankRow = computed(() => {
    const selection = selectedPreviewCell.value;
    if (!selection || selection.kind !== "blank-row") {
      return null;
    }
    return previewBlankRows.value.find((row) => row.id === selection.id) || null;
  });

const selectedPreviewBlankRowCell = computed(() => {
    const selection = selectedPreviewCell.value;
    if (!selection || selection.kind !== "blank-row-cell") {
      return null;
    }
    const row = previewBlankRows.value.find((item) => item.id === selection.rowId);
    if (!row) {
      return null;
    }
    if (!row.cells[selection.columnKey]) {
      row.cells[selection.columnKey] = blankCellDefault();
    }
    return {
      row,
      columnKey: selection.columnKey,
      cell: row.cells[selection.columnKey],
    };
  });

const selectedPreviewBlankColumn = computed(() => {
    const selection = selectedPreviewCell.value;
    if (!selection || selection.kind !== "blank-column") {
      return null;
    }
    return previewBlankColumns.value.find((column) => column.id === selection.id) || null;
  });

const selectedPreviewBlankColumnCell = computed(() => {
    const selection = selectedPreviewCell.value;
    if (!selection || selection.kind !== "blank-column-cell") {
      return null;
    }
    const column = previewBlankColumns.value.find((item) => item.id === selection.columnId);
    if (!column) {
      return null;
    }
    if (!column.cells[selection.rowKey]) {
      column.cells[selection.rowKey] = blankCellDefault();
    }
    return {
      column,
      rowKey: selection.rowKey,
      cell: column.cells[selection.rowKey],
    };
  });

function previewBlankColumnIndex(columnId: string) {
    return timetablePreviewColumns.value.findIndex((column) => column.kind === "blank" && column.id === columnId);
  }

function canMovePreviewBlankColumn(columnId: string, direction: -1 | 1) {
    const index = previewBlankColumnIndex(columnId);
    if (index < 0) {
      return false;
    }
    const nextIndex = index + direction;
    return nextIndex >= 0 && nextIndex < timetablePreviewColumns.value.length;
  }

function movePreviewBlankColumn(columnId: string, direction: -1 | 1) {
    const index = previewBlankColumnIndex(columnId);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= timetablePreviewColumns.value.length) {
      return;
    }
    const moving = previewBlankColumns.value.find((column) => column.id === columnId);
    const target = timetablePreviewColumns.value[nextIndex];
    if (!moving || !target) {
      return;
    }
    const boundary = timetablePreviewColumns.value[nextIndex + direction];
    moving.order_index = boundary
      ? (target.sort + boundary.sort) / 2
      : target.sort + direction;
  }

function previewBlankRowIndex(rowId: string) {
    return timetablePreviewRowFlow.value.findIndex((row) => row.kind === "blank" && row.id === rowId);
  }

function canMovePreviewBlankRow(rowId: string, direction: -1 | 1) {
    const index = previewBlankRowIndex(rowId);
    if (index < 0) {
      return false;
    }
    const nextIndex = index + direction;
    return nextIndex >= 0 && nextIndex < timetablePreviewRowFlow.value.length;
  }

function movePreviewBlankRow(rowId: string, direction: -1 | 1) {
    const index = previewBlankRowIndex(rowId);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= timetablePreviewRowFlow.value.length) {
      return;
    }
    const moving = previewBlankRows.value.find((row) => row.id === rowId);
    const target = timetablePreviewRowFlow.value[nextIndex];
    if (!moving || !target) {
      return;
    }
    const boundary = timetablePreviewRowFlow.value[nextIndex + direction];
    moving.order_index = boundary
      ? (target.sort + boundary.sort) / 2
      : target.sort + direction;
  }

const selectedPeriodMergeSpanCount = computed(() => {
    const selection = selectedPreviewCell.value;
    if (!selection || selection.kind !== "period") {
      return 1;
    }
    const startIndex = timetablePreviewColumns.value.findIndex(
      (column) => column.kind === "weekday" && column.day.index === selection.dayIndex,
    );
    if (startIndex < 0) {
      return 1;
    }
    let count = 1;
    for (let index = startIndex + 1; index < timetablePreviewColumns.value.length; index += 1) {
      const column = timetablePreviewColumns.value[index];
      if (column.kind !== "weekday" || column.day.index !== selection.dayIndex + count) {
        break;
      }
      count += 1;
    }
    return count;
  });

function selectPreviewCell(periodIndex: number, dayIndex: number, period: PeriodDraft | null) {
    if (!period) {
      return;
    }
    ensurePeriodDraftDisplayDefaults(period);
    selectedPreviewCell.value = { kind: "period", periodIndex, dayIndex };
  }

function isPreviewCellSelected(periodIndex: number, dayIndex: number) {
    return (
      selectedPreviewCell.value?.kind === "period" &&
      selectedPreviewCell.value?.periodIndex === periodIndex &&
      selectedPreviewCell.value?.dayIndex === dayIndex
    );
  }

function selectPreviewBlankRow(row: PreviewBlankRowDraft) {
    selectedPreviewCell.value = { kind: "blank-row", id: row.id };
  }

function previewColumnKey(column: typeof timetablePreviewColumns.value[number]) {
    return column.kind === "weekday" ? `weekday-${column.day.index}` : `blank-${column.column.id}`;
  }

function previewBlankRowCell(row: PreviewBlankRowDraft, columnKey: string) {
    return row.cells[columnKey] || blankCellDefault();
  }

function blankRowRenderedCells(row: PreviewBlankRowDraft) {
    const rendered: Array<{ columnKey: string; label: string; align: PreviewAlign; colspan: number; rowspan: number; active: boolean }> = [];
    for (let index = 0; index < timetablePreviewColumns.value.length; index += 1) {
      const column = timetablePreviewColumns.value[index];
      const columnKey = previewColumnKey(column);
      const cell = previewBlankRowCell(row, columnKey);
      if (cell.coveredBy) {
        continue;
      }
      const colspan = Math.min(
        Math.max(Number(cell.colspan || 1), 1),
        timetablePreviewColumns.value.length - index,
      );
      rendered.push({
        columnKey,
        label: cell.label,
        align: cell.align,
        colspan,
        rowspan: Math.min(
          Math.max(Number(cell.rowspan || 1), 1),
          maxBlankRowCellRowspan(row.id, columnKey),
        ),
        active: cell.active !== false,
      });
      index += colspan - 1;
    }
    return rendered;
  }

function selectPreviewBlankRowCell(row: PreviewBlankRowDraft, columnKey: string) {
    if (!row.cells[columnKey]) {
      row.cells[columnKey] = blankCellDefault();
    }
    selectedPreviewCell.value = { kind: "blank-row-cell", rowId: row.id, columnKey };
  }

function selectPreviewBlankColumn(column: PreviewBlankColumnDraft) {
    selectedPreviewCell.value = { kind: "blank-column", id: column.id };
  }

function selectPreviewBlankColumnCell(column: PreviewBlankColumnDraft, rowKey: string) {
    if (!column.cells[rowKey]) {
      column.cells[rowKey] = blankCellDefault();
    }
    selectedPreviewCell.value = { kind: "blank-column-cell", columnId: column.id, rowKey };
  }

function isPreviewBlankRowSelected(row: PreviewBlankRowDraft) {
    return selectedPreviewCell.value?.kind === "blank-row" && selectedPreviewCell.value.id === row.id;
  }

function isPreviewBlankRowCellSelected(row: PreviewBlankRowDraft, columnKey: string) {
    return (
      selectedPreviewCell.value?.kind === "blank-row-cell" &&
      selectedPreviewCell.value.rowId === row.id &&
      selectedPreviewCell.value.columnKey === columnKey
    );
  }

function isPreviewBlankColumnSelected(column: PreviewBlankColumnDraft) {
    return selectedPreviewCell.value?.kind === "blank-column" && selectedPreviewCell.value.id === column.id;
  }

function isPreviewBlankColumnCellSelected(column: PreviewBlankColumnDraft, rowKey: string) {
    return (
      selectedPreviewCell.value?.kind === "blank-column-cell" &&
      selectedPreviewCell.value.columnId === column.id &&
      selectedPreviewCell.value.rowKey === rowKey
    );
  }

function previewBlankColumnCell(column: PreviewBlankColumnDraft, rowKey: string) {
    return column.cells[rowKey] || blankCellDefault();
  }

function columnIndexByKey(columnKey: string) {
    return timetablePreviewColumns.value.findIndex((column) => previewColumnKey(column) === columnKey);
  }

function ensureBlankRowCell(row: PreviewBlankRowDraft, columnKey: string) {
    if (!row.cells[columnKey]) {
      row.cells[columnKey] = blankCellDefault();
    }
    return row.cells[columnKey];
  }

function ensureBlankColumnCell(column: PreviewBlankColumnDraft, rowKey: string) {
    if (!column.cells[rowKey]) {
      column.cells[rowKey] = blankCellDefault();
    }
    return column.cells[rowKey];
  }

function maxBlankRowCellRowspan(rowId: string, columnKey: string) {
    const startIndex = timetablePreviewRowFlow.value.findIndex((row) => row.kind === "blank" && row.id === rowId);
    if (startIndex < 0) return 1;
    const columnIndex = columnIndexByKey(columnKey);
    const column = timetablePreviewColumns.value[columnIndex];
    if (column?.kind === "blank") {
      return Math.max(timetablePreviewRowFlow.value.length - startIndex, 1);
    }
    let count = 0;
    for (let index = startIndex; index < timetablePreviewRowFlow.value.length; index += 1) {
      if (timetablePreviewRowFlow.value[index].kind !== "blank") break;
      count += 1;
    }
    return Math.max(count, 1);
  }

function maxBlankColumnCellColspan(columnId: string) {
    const startIndex = timetablePreviewColumns.value.findIndex((column) => column.kind === "blank" && column.id === columnId);
    if (startIndex < 0) return 1;
    let count = 0;
    for (let index = startIndex; index < timetablePreviewColumns.value.length; index += 1) {
      if (timetablePreviewColumns.value[index].kind !== "blank") break;
      count += 1;
    }
    return Math.max(count, 1);
  }

function maxBlankColumnCellRowspan(columnId: string, rowKey: string) {
    const startIndex = timetablePreviewRowFlow.value.findIndex(
      (row) => row.kind === "period" && row.row.rowKey === rowKey,
    );
    const columnExists = timetablePreviewColumns.value.some(
      (column) => column.kind === "blank" && column.id === columnId,
    );
    if (startIndex < 0 || !columnExists) return 1;
    return Math.max(timetablePreviewRowFlow.value.length - startIndex, 1);
  }

const selectedPreviewBlankRowCellMaxColspan = computed(() => {
    const selection = selectedPreviewBlankRowCell.value;
    if (!selection) return 1;
    const index = columnIndexByKey(selection.columnKey);
    return index < 0 ? 1 : Math.max(timetablePreviewColumns.value.length - index, 1);
  });

const selectedPreviewBlankRowCellMaxRowspan = computed(() => {
    const selection = selectedPreviewBlankRowCell.value;
    return selection ? maxBlankRowCellRowspan(selection.row.id, selection.columnKey) : 1;
  });

const selectedPreviewBlankColumnCellMaxColspan = computed(() => {
    const selection = selectedPreviewBlankColumnCell.value;
    return selection ? maxBlankColumnCellColspan(selection.column.id) : 1;
  });

const selectedPreviewBlankColumnCellMaxRowspan = computed(() => {
    const selection = selectedPreviewBlankColumnCell.value;
    return selection ? maxBlankColumnCellRowspan(selection.column.id, selection.rowKey) : 1;
  });

function clearBlankCellMerge(rootId: string) {
    for (const row of previewBlankRows.value) {
      for (const cell of Object.values(row.cells)) {
        if (cell.coveredBy === rootId) {
          delete cell.coveredBy;
        }
      }
    }
    for (const column of previewBlankColumns.value) {
      for (const cell of Object.values(column.cells)) {
        if (cell.coveredBy === rootId) {
          delete cell.coveredBy;
        }
      }
    }
  }

function chooseMergeLabel(candidates: Array<{ label: string; source: string }>) {
    const withContent = candidates.filter((candidate) => candidate.label.trim());
    if (withContent.length <= 1) {
      return withContent[0]?.label || "";
    }
    const message = [
      "多个待合并单元格都有内容，请输入要保留的编号：",
      ...withContent.map((candidate, index) => `${index + 1}. ${candidate.source}: ${candidate.label}`),
    ].join("\n");
    const answer = window.prompt(message, "1");
    if (answer === null) {
      return null;
    }
    const index = Math.max(Math.min(Number(answer || 1), withContent.length), 1) - 1;
    return withContent[index]?.label || "";
  }

function resetCoveredCell(cell: PreviewBlankCellDraft, rootId: string) {
    cell.label = "";
    cell.colspan = 1;
    cell.rowspan = 1;
    cell.active = true;
    cell.coveredBy = rootId;
  }

function splitBlankCell(cell: PreviewBlankCellDraft, rootId: string) {
    clearBlankCellMerge(rootId);
    cell.colspan = 1;
    cell.rowspan = 1;
    delete cell.coveredBy;
  }

function applySelectedBlankRowCellMerge(rowspan: number, colspan: number) {
    const selection = selectedPreviewBlankRowCell.value;
    if (!selection) return;
    const rootId = blankRowCellRootId(selection.row.id, selection.columnKey);
    const rootCell = ensureBlankRowCell(selection.row, selection.columnKey);
    const safeRowspan = Math.max(Math.min(rowspan, selectedPreviewBlankRowCellMaxRowspan.value), 1);
    const safeColspan = Math.max(Math.min(colspan, selectedPreviewBlankRowCellMaxColspan.value), 1);
    const startColumnIndex = columnIndexByKey(selection.columnKey);
    const startRowIndex = timetablePreviewRowFlow.value.findIndex((row) => row.kind === "blank" && row.id === selection.row.id);
    if (startColumnIndex < 0 || startRowIndex < 0) return;
    const targets: Array<{ cell: PreviewBlankCellDraft; source: string; isRoot: boolean }> = [];
    for (let rowOffset = 0; rowOffset < safeRowspan; rowOffset += 1) {
      const flowRow = timetablePreviewRowFlow.value[startRowIndex + rowOffset];
      if (!flowRow) return;
      for (let colOffset = 0; colOffset < safeColspan; colOffset += 1) {
        const column = timetablePreviewColumns.value[startColumnIndex + colOffset];
        if (!column) return;
        const columnKey = previewColumnKey(column);
        if (flowRow.kind === "period" && column.kind !== "blank") {
          error.value = "跨课程行纵向合并时，合并区域只能包含自定义列。";
          return;
        }
        let cell: PreviewBlankCellDraft;
        if (flowRow.kind === "period") {
          if (column.kind !== "blank") return;
          cell = ensureBlankColumnCell(column.column, flowRow.row.rowKey);
        } else {
          cell = ensureBlankRowCell(flowRow.row, columnKey);
        }
        const isRoot = flowRow.kind === "blank"
          && flowRow.row.id === selection.row.id
          && columnKey === selection.columnKey;
        if (!isRoot && (cell.coveredBy || Number(cell.colspan || 1) > 1 || Number(cell.rowspan || 1) > 1)) {
          error.value = "合并区域里已有合并单元格，请先拆分后再合并。";
          return;
        }
        const rowLabel = flowRow.kind === "period"
          ? flowRow.row.timeLabel
          : flowRow.row.label || "自定义行";
        targets.push({
          cell,
          source: `${rowLabel} ${column.kind === "weekday" ? column.day.label : column.column.label}`,
          isRoot,
        });
      }
    }
    const keepLabel = chooseMergeLabel(targets.map((target) => ({ label: target.cell.label, source: target.source })));
    if (keepLabel === null) return;
    clearBlankCellMerge(rootId);
    rootCell.label = keepLabel;
    rootCell.rowspan = safeRowspan;
    rootCell.colspan = safeColspan;
    for (const target of targets) {
      if (!target.isRoot) {
        resetCoveredCell(target.cell, rootId);
      }
    }
  }

function applySelectedBlankColumnCellMerge(rowspan: number, colspan: number) {
    const selection = selectedPreviewBlankColumnCell.value;
    if (!selection) return;
    const rootId = blankColumnCellRootId(selection.column.id, selection.rowKey);
    const rootCell = ensureBlankColumnCell(selection.column, selection.rowKey);
    const safeRowspan = Math.max(Math.min(rowspan, selectedPreviewBlankColumnCellMaxRowspan.value), 1);
    const safeColspan = Math.max(Math.min(colspan, selectedPreviewBlankColumnCellMaxColspan.value), 1);
    const startColumnIndex = timetablePreviewColumns.value.findIndex(
      (column) => column.kind === "blank" && column.id === selection.column.id,
    );
    const startRowIndex = timetablePreviewRowFlow.value.findIndex(
      (row) => row.kind === "period" && row.row.rowKey === selection.rowKey,
    );
    if (startColumnIndex < 0 || startRowIndex < 0) return;
    const targets: Array<{ cell: PreviewBlankCellDraft; source: string; isRoot: boolean }> = [];
    for (let rowOffset = 0; rowOffset < safeRowspan; rowOffset += 1) {
      const flowRow = timetablePreviewRowFlow.value[startRowIndex + rowOffset];
      if (!flowRow) return;
      for (let colOffset = 0; colOffset < safeColspan; colOffset += 1) {
        const column = timetablePreviewColumns.value[startColumnIndex + colOffset];
        if (!column || column.kind !== "blank") {
          error.value = "空白列单元格只能和相邻空白列合并，不能合并到课程列。";
          return;
        }
        const columnKey = previewColumnKey(column);
        const cell = flowRow.kind === "period"
          ? ensureBlankColumnCell(column.column, flowRow.row.rowKey)
          : ensureBlankRowCell(flowRow.row, columnKey);
        const isRoot = flowRow.kind === "period"
          && column.column.id === selection.column.id
          && flowRow.row.rowKey === selection.rowKey;
        if (!isRoot && (cell.coveredBy || Number(cell.colspan || 1) > 1 || Number(cell.rowspan || 1) > 1)) {
          error.value = "合并区域里已有合并单元格，请先拆分后再合并。";
          return;
        }
        const rowLabel = flowRow.kind === "period"
          ? flowRow.row.timeLabel
          : flowRow.row.label || "自定义行";
        targets.push({ cell, source: `${rowLabel} ${column.column.label || ""}`, isRoot });
      }
    }
    const keepLabel = chooseMergeLabel(targets.map((target) => ({ label: target.cell.label, source: target.source })));
    if (keepLabel === null) return;
    clearBlankCellMerge(rootId);
    rootCell.label = keepLabel;
    rootCell.rowspan = safeRowspan;
    rootCell.colspan = safeColspan;
    for (const target of targets) {
      if (!target.isRoot) {
        resetCoveredCell(target.cell, rootId);
      }
    }
  }

function splitSelectedBlankRowCell() {
    const selection = selectedPreviewBlankRowCell.value;
    if (!selection) return;
    splitBlankCell(selection.cell, blankRowCellRootId(selection.row.id, selection.columnKey));
  }

function splitSelectedBlankColumnCell() {
    const selection = selectedPreviewBlankColumnCell.value;
    if (!selection) return;
    splitBlankCell(selection.cell, blankColumnCellRootId(selection.column.id, selection.rowKey));
  }

function excelSpanAttrs(cell: { colspan?: number; rowspan?: number }) {
    return `${Number(cell.colspan || 1) > 1 ? ` colspan="${Number(cell.colspan || 1)}"` : ""}${Number(cell.rowspan || 1) > 1 ? ` rowspan="${Number(cell.rowspan || 1)}"` : ""}`;
  }

function excelCellStyle(
    align: PreviewAlign = "center",
    role: "title" | "header" | "time" | "body" | "empty" | "inactive" = "body",
    colorMode: CandidateExcelColorMode = "color",
  ) {
    const colorRoleStyle = {
      title: "background:#2F7D6D;color:#FFFFFF;font-size:16pt;font-weight:700;",
      header: "background:#E8F3EE;color:#21342F;font-size:11pt;font-weight:700;",
      time: "background:#F4F7F4;color:#40534C;font-size:10pt;font-weight:700;",
      body: "background:#FFFFFF;color:#24342F;font-size:10pt;",
      empty: "background:#E7EAE8;color:#8B948F;font-size:10pt;",
      inactive: "background:#ECEEEC;color:#9AA19D;font-size:10pt;",
    }[role];
    const monochromeRoleStyle = {
      title: "color:#111111;font-size:16pt;font-weight:700;",
      header: "color:#111111;font-size:11pt;font-weight:700;",
      time: "color:#111111;font-size:10pt;font-weight:700;",
      body: "color:#111111;font-size:10pt;",
      empty: "color:#333333;font-size:10pt;",
      inactive: "color:#666666;font-size:10pt;",
    }[role];
    const roleStyle = colorMode === "monochrome" ? monochromeRoleStyle : colorRoleStyle;
    return `border:1px solid #AAB8B1;padding:6px 8px;text-align:${align};vertical-align:middle;white-space:normal;mso-number-format:'\\@';${roleStyle}`;
  }

function excelHeaderRows(
    rows: PreviewHeaderRowDraft[],
    columnCount: number,
    templateName: string,
    ownerName = "归属主体名称",
    colorMode: CandidateExcelColorMode = "color",
  ) {
    return rows.map((row, rowIndex) => {
      const cells = headerRowRenderedCells(rows, row, columnCount, templateName, ownerName).map((cell) => {
        const role = rowIndex === 0 && cell.colspan >= columnCount ? "title" : "header";
        return `<th${excelSpanAttrs(cell)} style="${excelCellStyle(cell.cell.align, role, colorMode)}">${escapeHtml(cell.label)}</th>`;
      });
      return `<tr style="height:${rowIndex === 0 ? 32 : 26}pt">${cells.join("")}</tr>`;
    }).join("");
  }

function downloadExcelHtml(tableRows: string, fileName: string) {
    const html = `<table>${tableRows}</table>`;
    const document = new DOMParser().parseFromString(html, "text/html");
    const columnCount = Math.max(
      1,
      ...Array.from(document.querySelectorAll("tr")).map((row) =>
        Array.from(row.querySelectorAll(":scope > th, :scope > td")).reduce(
          (total, cell) => total + Math.max(Number(cell.getAttribute("colspan") || 1), 1),
          0,
        ),
      ),
    );
    const sheet = {
      name: sanitizeExcelSheetName(fileName),
      ownerName: fileName,
      columnCount,
      html,
    };
    if (candidateExportCapture) {
      candidateExportCapture.fileName = fileName;
      candidateExportCapture.sheets = [sheet];
      return;
    }
    void downloadExcelSpreadsheetXml([sheet], fileName).catch((cause) => {
      error.value = cause instanceof Error ? `Excel 导出失败：${cause.message}` : "Excel 导出失败，请稍后重试";
    });
  }

function sanitizeExcelSheetName(value: string) {
    const cleaned = String(value || "")
      .replace(/[\\/:?*[\]]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 31);
    return cleaned || "Sheet";
  }

async function downloadExcelSpreadsheetXml(
    sheets: Array<{ name: string; columnCount: number; html: string }>,
    fileName: string,
  ) {
    const ExcelJS = await import("exceljs");
    const workbook = new ExcelJS.Workbook();
    workbook.creator = "时奕智能教务系统";
    workbook.created = new Date();
    const orientation = candidateExcelPageOrientation.value === "landscape" ? "landscape" : "portrait";
    for (const sheet of sheets) {
      const worksheet = workbook.addWorksheet(sheet.name, {
        views: [{ showGridLines: false }],
      });
      worksheet.columns = Array.from({ length: sheet.columnCount }, () => ({ width: 13 }));
      const document = new DOMParser().parseFromString(sheet.html, "text/html");
      const rows = Array.from(document.querySelectorAll("tr"));
      const occupiedUntil: number[] = [];
      const occupiedCells = new Set<string>();
      const regions: Array<{
        startRow: number;
        endRow: number;
        startColumn: number;
        endColumn: number;
        cell: ExcelCell;
      }> = [];
      rows.forEach((row, rowIndex) => {
        const excelRow = rowIndex + 1;
        worksheet.getRow(excelRow).height = spreadsheetRowHeight(row);
        let nextColumn = 1;
        const cells = Array.from(row.querySelectorAll(":scope > th, :scope > td"));
        cells.forEach((cell) => {
          while ((occupiedUntil[nextColumn] || -1) >= rowIndex) {
            nextColumn += 1;
          }
          const column = nextColumn;
          const colspan = Math.max(Number(cell.getAttribute("colspan") || 1), 1);
          const rowspan = Math.max(Number(cell.getAttribute("rowspan") || 1), 1);
          const endRow = excelRow + rowspan - 1;
          const endColumn = column + colspan - 1;
          const excelCell = worksheet.getCell(excelRow, column);
          excelCell.value = spreadsheetCellText(cell);
          Object.assign(excelCell, spreadsheetExcelJsStyle(cell.getAttribute("style") || ""));
          if (rowspan > 1 || colspan > 1) {
            worksheet.mergeCells(excelRow, column, endRow, endColumn);
          }
          for (let offset = 0; offset < colspan; offset += 1) {
            occupiedUntil[column + offset] = Math.max(
              occupiedUntil[column + offset] || -1,
              rowIndex + rowspan - 1,
            );
          }
          for (let mergedRow = excelRow; mergedRow <= endRow; mergedRow += 1) {
            for (let mergedColumn = column; mergedColumn <= endColumn; mergedColumn += 1) {
              occupiedCells.add(`${mergedRow}:${mergedColumn}`);
            }
          }
          regions.push({ startRow: excelRow, endRow, startColumn: column, endColumn, cell: excelCell });
          nextColumn = column + colspan;
        });
      });
      for (const region of regions) {
        const hasTopNeighbor = Array.from(
          { length: region.endColumn - region.startColumn + 1 },
          (_, index) => occupiedCells.has(`${region.startRow - 1}:${region.startColumn + index}`),
        ).every(Boolean);
        const hasLeftNeighbor = Array.from(
          { length: region.endRow - region.startRow + 1 },
          (_, index) => occupiedCells.has(`${region.startRow + index}:${region.startColumn - 1}`),
        ).every(Boolean);
        region.cell.border = spreadsheetExcelJsBorder(!hasTopNeighbor, !hasLeftNeighbor);
      }
      fitWorksheetToPrintedPage(worksheet, orientation);
    }
    const workbookBuffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([workbookBuffer], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${sanitizeFileName(fileName)}.xlsx`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  }

function spreadsheetCellText(cell: Element) {
    const clone = cell.cloneNode(true) as Element;
    clone.querySelectorAll("br").forEach((breakElement) => {
      breakElement.replaceWith("\n");
    });
    return (clone.textContent || "").replace(/\u00a0/g, " ").trim();
  }

function spreadsheetRowHeight(row: Element) {
    const style = row.getAttribute("style") || "";
    const heightMatch = style.match(/height:\s*([\d.]+)(px|pt)/i);
    if (heightMatch) {
      const value = Number(heightMatch[1]);
      const unit = heightMatch[2].toLowerCase();
      return unit === "pt" ? value : value * 0.75;
    }
    return 28.5;
  }

function spreadsheetStyleCss(styleText: string) {
    const css: Record<string, string> = {};
    styleText.split(";").forEach((declaration) => {
      const separator = declaration.indexOf(":");
      if (separator < 0) return;
      css[declaration.slice(0, separator).trim().toLowerCase()] = declaration.slice(separator + 1).trim();
    });
    return css;
  }

function spreadsheetArgb(value: string, fallback: string) {
    let hex = String(value || fallback).trim().replace(/^#/, "");
    if (/^[0-9a-f]{3}$/i.test(hex)) hex = hex.split("").map((character) => `${character}${character}`).join("");
    if (/^[0-9a-f]{6}$/i.test(hex)) return `FF${hex.toUpperCase()}`;
    if (/^[0-9a-f]{8}$/i.test(hex)) return hex.toUpperCase();
    return `FF${fallback.replace(/^#/, "").toUpperCase()}`;
  }

function spreadsheetExcelJsStyle(styleText: string): Record<string, unknown> {
    const css = spreadsheetStyleCss(styleText);
    const horizontal = css["text-align"] === "left" ? "left" : css["text-align"] === "right" ? "right" : "center";
    const vertical = css["vertical-align"] === "top" ? "top" : css["vertical-align"] === "bottom" ? "bottom" : "middle";
    const fontSize = Number.parseFloat(css["font-size"] || "10") || 10;
    const bold = Number.parseInt(css["font-weight"] || "400", 10) >= 600 || css["font-weight"] === "bold";
    const background = css.background || css["background-color"];
    return {
      font: {
        name: "Microsoft YaHei",
        size: fontSize,
        bold,
        color: { argb: spreadsheetArgb(css.color || "#24342F", "#24342F") },
      },
      alignment: { horizontal, vertical, wrapText: true },
      ...(background ? {
        fill: {
          type: "pattern",
          pattern: "solid",
          fgColor: { argb: spreadsheetArgb(background, "#FFFFFF") },
        },
      } : {}),
      ...(/mso-number-format/i.test(styleText) ? { numFmt: "@" } : {}),
    };
  }

function spreadsheetExcelJsBorder(includeTop: boolean, includeLeft: boolean) {
    const borderSide = () => ({ style: "thin" as const, color: { argb: "FFAAB8B1" } });
    return {
      ...(includeTop ? { top: borderSide() } : {}),
      ...(includeLeft ? { left: borderSide() } : {}),
      right: borderSide(),
      bottom: borderSide(),
    };
  }

function exportTimetableTemplateExcel() {
    relabelAllPeriods();
    const title = timetableTemplateForm.value.name || "周课程表模板";
    if (timetableTemplateLayoutKind.value === "all_classes_grid") {
      if (allClassesTemplateVariant.value === "period_rows_grouped") {
        const columnCount = Math.max(fullTablePreviewColumnCount.value, 4);
        const customHeaderRows = excelHeaderRows(previewHeaderRows.value, columnCount, title);
        const weekdayHeaders = fullTablePreviewDayGroups.value.map((group) =>
          `<th colspan="${Math.max(group.homerooms.length, 1)}" style="${excelCellStyle("center", "header")}">${escapeHtml(group.label)}</th>`,
        );
        const gradeHeaders = fullTablePreviewDayGroups.value.flatMap((group) =>
          group.gradeGroups.map((grade) =>
            `<th colspan="${Math.max(grade.homerooms.length, 1)}" style="${excelCellStyle("center", "header")}">${escapeHtml(grade.label)}</th>`,
          ),
        );
        const homeroomHeaders = fullTablePreviewDayGroups.value.flatMap((group) =>
          group.homerooms.map((homeroom) =>
            `<th style="${excelCellStyle("center", "header")}">${escapeHtml(homeroom.classLabel)}</th>`,
          ),
        );
        const headings = `<tr><th rowspan="3" style="${excelCellStyle("center", "header")}">时段</th><th rowspan="3" style="${excelCellStyle("center", "header")}">时间</th><th rowspan="3" style="${excelCellStyle("center", "header")}">节次</th>${weekdayHeaders.join("")}</tr><tr>${gradeHeaders.join("")}</tr><tr>${homeroomHeaders.join("")}</tr>`;
        const bodyRows: string[] = [];
        fullTablePreviewPeriods.value.forEach((period, index) => {
          const isSegmentStart = index === 0 || fullTablePreviewPeriods.value[index - 1]?.segment !== period.segment;
          let segmentLength = 0;
          if (isSegmentStart) {
            for (let cursor = index; cursor < fullTablePreviewPeriods.value.length && fullTablePreviewPeriods.value[cursor]?.segment === period.segment; cursor += 1) {
              segmentLength += 1;
            }
          }
          const leadingCells = [
            isSegmentStart ? `<th rowspan="${segmentLength * 2}" style="${excelCellStyle("center", "time")}">${escapeHtml(period.segment)}</th>` : "",
            `<th rowspan="2" style="${excelCellStyle("center", "time")}">${escapeHtml(`${period.start_time}-${period.end_time}`)}</th>`,
            `<th rowspan="2" style="${excelCellStyle("center", "time")}">${escapeHtml(period.label || `第${period.period_index}节`)}</th>`,
          ].join("");
          const cellCount = fullTablePreviewDayGroups.value.reduce((total, group) => total + group.homerooms.length, 0);
          const subjectCells = Array.from({ length: cellCount }, () =>
            `<td style="${excelCellStyle("center", "empty")}"></td>`,
          ).join("");
          const teacherCells = Array.from({ length: cellCount }, () =>
            `<td style="${excelCellStyle("center", "empty")}"></td>`,
          ).join("");
          bodyRows.push(`<tr>${leadingCells}${subjectCells}</tr>`, `<tr>${teacherCells}</tr>`);
        });
        downloadExcelHtml(`${customHeaderRows}${headings}${bodyRows.join("")}`, title);
        return;
      }
      const columnCount = Math.max(irregularPreviewColumnCount.value + 1, 2);
      const customHeaderRows = excelHeaderRows(previewHeaderRows.value, columnCount, title);
      const dayHeaders = irregularPreviewDayGroups.value.map((group) =>
        `<th colspan="${group.periods.length}" style="${excelCellStyle("center", "header")}">${escapeHtml(group.label)}</th>`,
      );
      const periodHeaders = irregularPreviewDayGroups.value.flatMap((group) =>
        group.periods.map((period) =>
          `<th style="${excelCellStyle("center", "header")}">${escapeHtml(`第${period.period_index}节`)}</th>`,
        ),
      );
      const bodyRows = irregularPreviewHomerooms.value.map((homeroom) => {
        const cells = Array.from({ length: irregularPreviewColumnCount.value }, () =>
          `<td style="${excelCellStyle("center", "empty")}"></td>`,
        );
        return `<tr><td style="${excelCellStyle("left", "time")}">${escapeHtml(homeroom.name)}</td>${cells.join("")}</tr>`;
      });
      const headings = `<tr><th rowspan="2" style="${excelCellStyle("center", "header")}">班级</th>${dayHeaders.join("")}</tr><tr>${periodHeaders.join("")}</tr>`;
      downloadExcelHtml(`${customHeaderRows}${headings}${bodyRows.join("")}`, title);
      return;
    }
    const columnCount = Math.max(previewBodyColumnCount.value, 1);
    const customHeaderRows = excelHeaderRows(previewHeaderRows.value, columnCount, title);
    const headerCells = timetablePreviewColumns.value.map((column) => {
      if (column.kind === "weekday") {
        return `<th style="${excelCellStyle("center", "header")}">${escapeHtml(column.day.label)}</th>`;
      }
      return `<th colspan="${Math.max(Number(column.column.colspan || 1), 1)}" style="${excelCellStyle(column.column.align, "header")}">${escapeHtml(column.column.label || "")}</th>`;
    });
    const weekdayHeaderRow = `<tr style="height:28pt">${headerCells.join("")}</tr>`;
    const bodyRows = timetablePreviewRowFlow.value.map((flowRow) => {
      if (flowRow.kind === "blank") {
        const cells = blankRowRenderedCells(flowRow.row).map((cell) =>
          `<td${excelSpanAttrs(cell)} style="${excelCellStyle(cell.align, cell.active ? "body" : "inactive")}">${escapeHtml(cell.label)}</td>`,
        );
        return `<tr>${cells.join("")}</tr>`;
      }
      const cells = flowRow.row.renderedCells.map((cell) => {
        if (cell.kind === "blank") {
          const blankCell = previewBlankColumnCell(cell.column, cell.rowKey);
          return `<td${excelSpanAttrs(cell)} style="${excelCellStyle(blankCell.align, blankCell.active ? "body" : "inactive")}">${escapeHtml(blankCell.label)}</td>`;
        }
        const cellMode = previewPeriodMode(cell.period);
        const content = cell.period ? courseCellTemplatePreviewLines(cell.period).join("\n") : "";
        const role = cellMode === "disabled" ? "inactive" : content ? "body" : "empty";
        return `<td${excelSpanAttrs(cell)} style="${excelCellStyle(cell.period?.align || "center", role)}">${escapeHtml(content).replace(/\n/g, "<br>")}</td>`;
      });
      return `<tr>${cells.join("")}</tr>`;
    });
    downloadExcelHtml(`${customHeaderRows}${weekdayHeaderRow}${bodyRows.join("")}`, title);
  }

function addPreviewRow() {
    const nextIndex = Math.max(0, ...weeklyPeriodDrafts.value.map((period) => Number(period.period_index || 0))) + 1;
    const previous = weeklyPeriodDrafts.value.find((period) => Number(period.period_index) === nextIndex - 1);
    const startMinutes = previous ? clockToMinutes(previous.end_time) + 10 : 8 * 60 + (nextIndex - 1) * 50;
    for (const day of timetablePreviewDays.value) {
      weeklyPeriodDrafts.value.push({
        weekday: day.index + 1,
        period_index: nextIndex,
        label: defaultCellLabel(day.index + 1, nextIndex),
        start_time: minutesToClock(startMinutes),
        end_time: minutesToClock(startMinutes + 40),
        active: true,
        align: "center",
        colspan: 1,
      });
    }
  }

function addPreviewBlankRow() {
    const nextOrder = Math.max(0, ...timetablePreviewRowFlow.value.map((row) => Number(row.sort || 0))) + 1;
    const row = {
      id: previewDraftId("blank-row"),
      label: "",
      align: "center" as const,
      colspan: previewBodyColumnCount.value,
      order_index: nextOrder,
      cells: {},
    };
    previewBlankRows.value.push(row);
    selectPreviewBlankRow(row);
  }

function addPreviewBlankColumn() {
    const column = {
      id: previewDraftId("blank-column"),
      label: "",
      align: "center" as const,
      colspan: 1,
      order_index: Math.max(
        fixedWeeklyDayCount,
        ...previewBlankColumns.value.map((item) => Number(item.order_index || fixedWeeklyDayCount)),
      ) + 1,
      cells: {},
    };
    previewBlankColumns.value.push(column);
    selectPreviewBlankColumn(column);
  }

function deletePreviewRow(periodIndex: number) {
    const confirmed = window.confirm(`删除第 ${periodIndex} 节整行？这一行在周一到周日的节次都会被删除。`);
    if (!confirmed) {
      return;
    }
    weeklyPeriodDrafts.value = weeklyPeriodDrafts.value.filter(
      (period) => Number(period.period_index) !== Number(periodIndex),
    );
    if (selectedPreviewCell.value?.kind === "period" && selectedPreviewCell.value.periodIndex === periodIndex) {
      selectedPreviewCell.value = null;
    }
    relabelAllPeriods();
    periodTimeDrafts.value = {};
    periodTimeErrors.value = {};
  }

function deleteSelectedPreviewRow() {
    if (!selectedPreviewCell.value) {
      return;
    }
    if (selectedPreviewCell.value.kind === "period") {
      deletePreviewRow(selectedPreviewCell.value.periodIndex);
    } else if (selectedPreviewCell.value.kind === "blank-row") {
      deletePreviewBlankRow(selectedPreviewCell.value.id);
    }
  }

function deletePreviewBlankRow(rowId: string) {
    const confirmed = window.confirm("删除这个空白行？");
    if (!confirmed) {
      return;
    }
    previewBlankRows.value = previewBlankRows.value.filter((row) => row.id !== rowId);
    if (
      (selectedPreviewCell.value?.kind === "blank-row" && selectedPreviewCell.value.id === rowId)
      || (selectedPreviewCell.value?.kind === "blank-row-cell" && selectedPreviewCell.value.rowId === rowId)
    ) {
      selectedPreviewCell.value = null;
    }
  }

function deletePreviewBlankColumn(columnId: string) {
    const confirmed = window.confirm("删除这个空白列？");
    if (!confirmed) {
      return;
    }
    previewBlankColumns.value = previewBlankColumns.value.filter((column) => column.id !== columnId);
    if (selectedPreviewCell.value?.kind === "blank-column" && selectedPreviewCell.value.id === columnId) {
      selectedPreviewCell.value = null;
    }
  }

const selectedTimetableTemplate = computed(() => {
    return (
      schoolData.value.weekly_timetable_templates.find(
        (template) => String(template.id || "") === selectedTemplateId.value,
      ) ||
      schoolData.value.default_weekly_timetable_template ||
      schoolData.value.weekly_timetable_templates[0] ||
      null
    );
  });

function minutesToClock(value: unknown) {
    const minutes = Number(value || 0);
    const hours = Math.floor(minutes / 60);
    const minute = minutes % 60;
    return `${String(hours).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  }

function clockToMinutes(value: string) {
    const [hours, minutes] = value.split(":").map((part) => Number(part || 0));
    return Math.min(Math.max(hours * 60 + minutes, 0), 1440);
  }

function bitsFromNumbers(values: number[], length: number) {
    const set = new Set(values.filter((value) => value >= 1 && value <= length));
    return Array.from({ length }, (_, index) => (set.has(index + 1) ? "1" : "0")).join("");
  }

function periodDraftPayload(period: PeriodDraft) {
    const weekday = Number(period.weekday);
    const periodIndex = Number(period.period_index);
    const cellMode = previewPeriodMode(period);
    return {
      id: period.id || null,
      weekday,
      period_index: periodIndex,
      label: defaultCellLabel(weekday, periodIndex),
      start_time_minutes: clockToMinutes(period.start_time),
      end_time_minutes: clockToMinutes(period.end_time),
      active: cellMode === "scheduled",
      display_config: {
        align: period.align,
        colspan: Math.max(Number(period.colspan || 1), 1),
        cell_mode: cellMode,
        custom_content: cellMode === "custom" ? String(period.custom_content || "").trim() : "",
        sample_subject: String(period.sample_subject || "").trim(),
        sample_teacher: String(period.sample_teacher || "").trim(),
        sample_room: String(period.sample_room || "").trim(),
        sample_homeroom: String(period.sample_homeroom || "").trim(),
        export_style: previewPeriodExportStyle(period),
        export_layout: normalizeCourseCellExportLayout(period.export_layout, courseCellExportLayout.value),
        export_top_field: normalizeCourseCellExportField(period.export_top_field, courseCellExportTopField.value),
        export_bottom_field: normalizeCourseCellExportField(period.export_bottom_field, courseCellExportBottomField.value),
      },
    };
  }

function normalizeBits(bits: unknown, length: number, fallback = "1") {
    const raw = String(bits || "");
    const normalized = Array.from({ length }, (_, index) => (raw[index] === "1" ? "1" : "0")).join("");
    return normalized.includes("1") ? normalized : fallback.repeat(length);
  }

function enabledDayNumbers() {
    return normalizeEnabledWeekdays(enabledWeekdays.value).filter((day) => day <= termDayCount.value);
  }

function sanitizeDayBitsForEnabledWeekdays(bits: unknown, fallbackToEnabled = true) {
    const enabledDays = enabledDayNumbers();
    const enabledSet = new Set(enabledDays);
    const normalized = normalizeBits(bits, termDayCount.value, "0")
      .split("")
      .map((value, index) => (value === "1" && enabledSet.has(index + 1) ? "1" : "0"))
      .join("");
    if (!normalized.includes("1") && fallbackToEnabled) {
      return bitsFromNumbers(enabledDays, termDayCount.value);
    }
    return normalized;
  }

function resetNewTimetableTemplateDraft() {
    selectedTemplateId.value = "";
    timetableTemplateForm.value = {
      id: "",
      name: "新周课程表模板",
      day_count: fixedWeeklyDayCount,
      slot_duration_minutes: 5,
      is_default: false,
    };
    timetableTemplateDescription.value = "";
    weeklyPeriodDrafts.value = generateDefaultPeriodDrafts();
    periodTimeDrafts.value = {};
    periodTimeErrors.value = {};
    enabledWeekdays.value = [1, 2, 3, 4, 5];
    previewBlankRows.value = [];
    previewBlankColumns.value = [];
    previewHeaderRows.value = createDefaultPreviewHeaderRows();
    selectedPreviewCell.value = null;
    timetableTimeMode.value = "fixed";
    showTimetableTimeAxis.value = true;
    publishTimetablePreset.value = false;
    timetableTemplateKind.value = "normal";
    timetableTemplateApplicationScope.value = "all";
    timetableTemplatePeriodSourceId.value = "";
    timetableTemplatePeriodsLocked.value = false;
    courseCellExportLayout.value = "two_line";
    courseCellExportTopField.value = "subject";
    courseCellExportBottomField.value = "teacher";
    timetableTemplateLayoutKind.value = "weekly";
    allClassesTemplateVariant.value = "homeroom_rows";
  }

function timetableTemplateHasCompletePeriods(template: Record<string, unknown>) {
    const templateId = String(template.id || "");
    const config = templateDisplayConfig(template);
    const requiredDays = normalizeEnabledWeekdays(config.enabled_weekdays);
    const periods = schoolData.value.weekly_timetable_periods.filter(
      (period) => String(period.template_id || "") === templateId && period.active !== false,
    );
    return Boolean(templateId) && requiredDays.every((weekday) =>
      periods.some((period) =>
        Number(period.weekday) === weekday
        && Number(period.period_index || 0) > 0
        && Number(period.end_time_minutes || 0) > Number(period.start_time_minutes || 0),
      ),
    );
  }

const baseWeeklyTemplateForIrregular = computed(() =>
    schoolData.value.weekly_timetable_templates.find((template) =>
      normalizeTimetableTemplateLayoutKind(templateDisplayConfig(template).layout_kind) === "weekly"
      && timetableTemplateHasCompletePeriods(template),
    ) || null,
  );

const specialTimetableTemplatePresets = ref<SpecialTimetableTemplatePreset[]>([]);

const specialTimetableTemplatePresetsLoading = ref(false);

const defaultTemplateTimeMode = computed<"fixed" | "variable">(() => {
    const template = schoolData.value.default_weekly_timetable_template;
    return templateDisplayConfig(template || {}).time_mode === "variable" ? "variable" : "fixed";
  });

const templateMarketplaceItems = computed<TemplateMarketplaceItem[]>(() => {
    const weeklyItems = timetablePresetLibrary.value.weekly_timetable_presets.map((template) => {
      const config = templateDisplayConfig(template);
      const sourceId = String(template.id || "");
      return {
        key: `weekly:${sourceId}`,
        sourceType: "weekly" as const,
        sourceId,
        name: String(template.name || "未命名模板"),
        description: String(config.description || "适用于常规周课程表，可在创建后继续调整。"),
        organizationName: String(template.organization_name || "本机构"),
        isOwned: Boolean(template.is_owned),
        layoutKind: normalizeTimetableTemplateLayoutKind(config.layout_kind),
        timeMode: config.time_mode === "variable" ? "variable" as const : "fixed" as const,
        displayConfig: { ...config },
        periods: timetablePresetLibrary.value.weekly_timetable_preset_periods.filter(
          (period) => String(period.template_id || "") === sourceId,
        ),
      };
    });
    const builtinPeriods = generateDefaultPeriodDrafts().filter((period) => period.weekday <= 5 && period.period_index <= 6);
    const builtinDisplayConfig = (timeMode: "fixed" | "variable") => ({
      enabled_weekdays: [1, 2, 3, 4, 5],
      time_mode: timeMode,
      show_time_axis: true,
      course_cell_layout: "two_line",
      course_cell_top_field: "subject",
      course_cell_bottom_field: "teacher",
      layout_kind: "weekly",
    });
    const variableShiftPatterns = [
      [0, 0, 0, 0, 0, 0],
      [10, 0, 10, 0, 10, 0],
      [0, 10, 0, 10, 0, 10],
      [10, 10, 0, 0, 10, 10],
      [0, 10, 10, 0, 0, 10],
    ];
    const platformItems: TemplateMarketplaceItem[] = [
      {
        key: "builtin:fixed",
        sourceType: "weekly",
        sourceId: "builtin:fixed",
        name: "标准固定时段周课表",
        description: "横轴为星期、纵轴为时间，每天使用同一组课次时间。",
        organizationName: "内置模板",
        isOwned: false,
        layoutKind: "weekly",
        timeMode: "fixed",
        displayConfig: builtinDisplayConfig("fixed"),
        periods: builtinPeriods,
      },
      {
        key: "builtin:variable",
        sourceType: "weekly",
        sourceId: "builtin:variable",
        name: "弹性时段周课表",
        description: "横轴为星期、纵轴为时间，允许每天使用不同课次时间。",
        organizationName: "内置模板",
        isOwned: false,
        layoutKind: "weekly",
        timeMode: "variable",
        displayConfig: builtinDisplayConfig("variable"),
        periods: builtinPeriods.map((period) => {
          const shift = variableShiftPatterns[period.weekday - 1]?.[(period.period_index - 1) % 6] || 0;
          return {
            ...period,
            start_time: minutesToClock(clockToMinutes(period.start_time) + shift),
            end_time: minutesToClock(clockToMinutes(period.end_time) + shift),
          };
        }),
      },
    ];
    const defaultTemplateId = String(schoolData.value.default_weekly_timetable_template?.id || "");
    const specialPeriods = schoolData.value.weekly_timetable_periods.filter(
      (period) => String(period.template_id || "") === defaultTemplateId,
    );
    const specialItems = specialTimetableTemplatePresets.value.map((preset) => ({
      key: `special:${preset.key}`,
      sourceType: "special" as const,
      sourceId: preset.key,
      name: preset.name,
      description: preset.description,
      organizationName: "内置模板",
      isOwned: false,
      layoutKind: preset.layoutKind,
      timeMode: defaultTemplateTimeMode.value,
      displayConfig: {
        ...preset.displayConfig,
        layout_kind: preset.layoutKind,
        all_classes_variant: preset.variant,
      },
      periods: specialPeriods.length ? specialPeriods : builtinPeriods,
    }));
    return [...platformItems, ...weeklyItems, ...specialItems];
  });

const filteredTemplateMarketplaceItems = computed(() => {
    const query = templateMarketplaceSearch.value.trim().toLowerCase();
    const filters = templateMarketplaceFilters.value;
    return templateMarketplaceItems.value.filter((item) => {
      if (templateCreatePlanningMode.value === "reuse" && item.timeMode !== defaultTemplateTimeMode.value) return false;
      if (filters.owned === "yes" && !item.isOwned) return false;
      if (filters.owned === "no" && item.isOwned) return false;
      if (filters.regular === "yes" && item.layoutKind !== "weekly") return false;
      if (filters.regular === "no" && item.layoutKind === "weekly") return false;
      if (filters.fixed === "yes" && item.timeMode !== "fixed") return false;
      if (filters.fixed === "no" && item.timeMode !== "variable") return false;
      return !query || `${item.name} ${item.description} ${item.organizationName}`.toLowerCase().includes(query);
    });
  });

const selectedTemplateMarketplaceItem = computed(() =>
    templateMarketplaceItems.value.find((item) => item.key === selectedTemplateMarketplaceKey.value) || null,
  );

const previewTemplateMarketplaceItem = computed(() =>
    templateMarketplaceItems.value.find((item) => item.key === previewTemplateMarketplaceKey.value) || null,
  );

const newTemplateConfirmTitle = computed(() => {
    if (newTemplateConfirmStep.value === "marketplace") return "模板库";
    if (newTemplateConfirmStep.value === "details") return "填写模板信息";
    return "选择课次规划方式";
  });

const newTemplateConfirmDescription = computed(() => {
    if (newTemplateConfirmStep.value === "marketplace") return "搜索并筛选适合当前课次规划方式的模板。";
    if (newTemplateConfirmStep.value === "details") return "模板会在确认后自动保存，并立即进入现有编辑器。";
    return "规划方式决定新模板的课次时间独立维护，还是持续跟随项目默认模板。";
  });

function createIrregularAllClassesTemplate(
    presetKey: string,
  ) {
    const baseTemplate = baseWeeklyTemplateForIrregular.value;
    const baseId = String(baseTemplate?.id || "");
    const periods = baseId
      ? schoolData.value.weekly_timetable_periods
          .filter((period) => String(period.template_id || "") === baseId)
          .sort((left, right) => Number(left.weekday || 0) - Number(right.weekday || 0)
            || Number(left.period_index || 0) - Number(right.period_index || 0))
      : [];
    const config = templateDisplayConfig(baseTemplate);
    const preset = specialTimetableTemplatePresets.value.find((item) => item.key === presetKey);
    if (!preset) {
      error.value = "该特殊模板预设已停用或不存在，请返回后重新选择";
      return;
    }
    selectedTemplateId.value = "";
    timetableTemplateForm.value = {
      id: "",
      name: preset.name,
      day_count: fixedWeeklyDayCount,
      slot_duration_minutes: Number(baseTemplate?.slot_duration_minutes || 5),
      is_default: false,
    };
    weeklyPeriodDrafts.value = periods.length
      ? normalizeSevenDayPeriodDrafts(periods.map((period) => ({
          weekday: Number(period.weekday || 1),
          period_index: Number(period.period_index || 1),
          label: periodDraftLabel(period),
          start_time: minutesToClock(period.start_time_minutes),
          end_time: minutesToClock(period.end_time_minutes),
          active: period.active !== false,
          align: periodDisplayConfig(period).align === "left" ? "left" : "center",
          colspan: Math.max(Number(periodDisplayConfig(period).colspan || 1), 1),
          ...periodDraftDisplayFields(period),
        })))
      : generateDefaultPeriodDrafts();
    enabledWeekdays.value = normalizeEnabledWeekdays(config.enabled_weekdays || [1, 2, 3, 4, 5]);
    previewBlankRows.value = [];
    previewBlankColumns.value = [];
    previewHeaderRows.value = createDefaultPreviewHeaderRows();
    selectedPreviewCell.value = null;
    timetableTimeMode.value = config.time_mode === "variable" ? "variable" : "fixed";
    showTimetableTimeAxis.value = preset.displayConfig.show_time_axis !== false;
    publishTimetablePreset.value = false;
    const presetCellLayout = String(preset.displayConfig.course_cell_layout || "single_line");
    const presetTopField = String(preset.displayConfig.course_cell_top_field || "subject");
    const presetBottomField = String(preset.displayConfig.course_cell_bottom_field || "teacher");
    courseCellExportLayout.value = ["single_line", "two_line", "split_rows"].includes(presetCellLayout)
      ? presetCellLayout as CourseCellExportLayout
      : "single_line";
    courseCellExportTopField.value = ["subject", "teacher", "room", "time", "homeroom"].includes(presetTopField)
      ? presetTopField as CourseCellExportField
      : "subject";
    courseCellExportBottomField.value = ["subject", "teacher", "room", "time", "homeroom"].includes(presetBottomField)
      ? presetBottomField as CourseCellExportField
      : "teacher";
    timetableTemplateLayoutKind.value = preset.layoutKind;
    allClassesTemplateVariant.value = preset.variant;
    timetableTemplateKind.value = "special";
    timetableTemplateApplicationScope.value = preset.applicationScope;
    timetableTemplatePeriodSourceId.value = baseId;
    timetableTemplatePeriodsLocked.value = Boolean(baseId);
    timetableTemplateDraftActive.value = true;
    newTemplateConfirmStep.value = "planning";
    showNewTimetableTemplateConfirm.value = false;
  }

function createNewTimetableTemplate() {
    newTemplateConfirmStep.value = "planning";
    templateCreatePlanningMode.value = "independent";
    selectedTemplateMarketplaceKey.value = "";
    previewTemplateMarketplaceKey.value = "";
    templateMarketplaceSearch.value = "";
    templateMarketplaceFilters.value = { owned: "all", regular: "all", fixed: "all" };
    showNewTimetableTemplateConfirm.value = true;
  }

function cancelNewTimetableTemplate() {
    newTemplateConfirmStep.value = "planning";
    previewTemplateMarketplaceKey.value = "";
    showNewTimetableTemplateConfirm.value = false;
  }

async function chooseTemplatePlanningMode(mode: "independent" | "reuse") {
    if (mode === "reuse" && !schoolData.value.default_weekly_timetable_template?.id) {
      error.value = "当前项目还没有默认模板，暂时不能复用默认安排";
      return;
    }
    templateCreatePlanningMode.value = mode;
    newTemplateConfirmStep.value = "marketplace";
    await loadTemplateMarketplace();
    const compatible = filteredTemplateMarketplaceItems.value[0];
    selectedTemplateMarketplaceKey.value = compatible?.key || "";
  }

function backNewTemplateStep() {
    if (newTemplateConfirmStep.value === "details") {
      newTemplateConfirmStep.value = "marketplace";
      return;
    }
    newTemplateConfirmStep.value = "planning";
  }

function selectTemplateMarketplaceItem(key: string) {
    selectedTemplateMarketplaceKey.value = key;
  }

function openTemplateMarketplacePreview(key: string) {
    previewTemplateMarketplaceKey.value = key;
  }

function closeTemplateMarketplacePreview() {
    previewTemplateMarketplaceKey.value = "";
  }

function continueTemplateMarketplace() {
    const item = selectedTemplateMarketplaceItem.value;
    if (!item) {
      error.value = "请先选择一个模板";
      return;
    }
    timetableTemplateForm.value.name = `${item.name} 副本`;
    timetableTemplateDescription.value = "";
    newTemplateConfirmStep.value = "details";
  }

async function confirmNewTemplateFromMarketplace() {
    const item = selectedTemplateMarketplaceItem.value;
    if (!item) {
      error.value = "请选择一个模板";
      return;
    }
    if (!timetableTemplateForm.value.name.trim()) {
      error.value = "模板名称不能为空";
      return;
    }
    const defaultTemplate = schoolData.value.default_weekly_timetable_template;
    const nextName = timetableTemplateForm.value.name.trim();
    if (item.sourceType === "special") {
      createIrregularAllClassesTemplate(item.sourceId);
      if (!timetableTemplateDraftActive.value) return;
      showNewTimetableTemplateConfirm.value = true;
    } else if (item.sourceId.startsWith("builtin:")) {
      resetNewTimetableTemplateDraft();
      setTimetableTimeMode(item.timeMode);
      timetableTemplateDraftActive.value = true;
    } else {
      const source = timetablePresetLibrary.value.weekly_timetable_presets.find(
        (template) => String(template.id || "") === item.sourceId,
      );
      if (!source) {
        error.value = "所选模板已不可用，请返回模板库重新选择";
        return;
      }
      resetNewTimetableTemplateDraft();
      creatingNewTimetableTemplate.value = true;
      applySavedTimetablePreset(source);
    }
    timetableTemplateForm.value.name = nextName;
    timetableTemplateDescription.value = "";
    if (templateCreatePlanningMode.value === "reuse" && defaultTemplate?.id) {
      timetableTemplatePeriodSourceId.value = String(defaultTemplate.id);
      timetableTemplatePeriodsLocked.value = true;
      syncDraftPeriodsFromTemplate(String(defaultTemplate.id));
    } else {
      timetableTemplatePeriodSourceId.value = "";
      timetableTemplatePeriodsLocked.value = false;
    }
    showNewTimetableTemplateConfirm.value = false;
    creatingNewTimetableTemplate.value = false;
    if (await persistTimetableTemplate("project")) {
      timetableTemplateDraftActive.value = false;
    }
  }

function syncDraftPeriodsFromTemplate(templateId: string) {
    const periods = schoolData.value.weekly_timetable_periods
      .filter((period) => String(period.template_id || "") === templateId)
      .sort((left, right) => Number(left.weekday || 0) - Number(right.weekday || 0)
        || Number(left.period_index || 0) - Number(right.period_index || 0));
    if (!periods.length) return;
    weeklyPeriodDrafts.value = normalizeSevenDayPeriodDrafts(periods.map((period) => ({
      weekday: Number(period.weekday || 1),
      period_index: Number(period.period_index || 1),
      label: periodDraftLabel(period),
      start_time: minutesToClock(period.start_time_minutes),
      end_time: minutesToClock(period.end_time_minutes),
      active: period.active !== false,
      align: periodDisplayConfig(period).align === "left" ? "left" : "center",
      colspan: Math.max(Number(periodDisplayConfig(period).colspan || 1), 1),
      ...periodDraftDisplayFields(period),
    })));
  }

function compactId(value?: string | null) {
    if (!value) {
      return "-";
    }
    return value.length > 18 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value;
  }

function timetableEntryRoomLabel(entry: TimetableEntry) {
    return String(entry.room_name || "").trim() || (entry.room_id ? `教室 ${compactId(entry.room_id)}` : "");
  }

function courseCellFieldLabel(field: CourseCellExportField) {
    const labels: Record<CourseCellExportField, string> = {
      subject: "课程名",
      teacher: "教师名",
      room: "教室",
      time: "时间",
      homeroom: "班级",
    };
    return labels[field];
  }

function courseCellFieldValue(field: CourseCellExportField, entry?: TimetableEntry) {
    if (!entry) {
      const sample: Record<CourseCellExportField, string> = {
        subject: "数学",
        teacher: "张三",
        room: "一号教室",
        time: "08:20-09:00",
        homeroom: "一年级1班",
      };
      return sample[field];
    }
    const values: Record<CourseCellExportField, string> = {
      subject: String(entry.lesson_label || entry.subject_name || "").trim(),
      teacher: String(entry.teacher_name || "").trim(),
      room: timetableEntryRoomLabel(entry),
      time: String(entry.time_range || `${entry.start_time || ""}${entry.end_time ? `-${entry.end_time}` : ""}`).trim(),
      homeroom: String(entry.homeroom_name || "").trim(),
    };
    return values[field];
  }

const courseCellSampleLines = computed(() => {
    const lines = [
      `${courseCellFieldLabel(courseCellExportTopField.value)}：${courseCellFieldValue(courseCellExportTopField.value)}`,
    ];
    if (courseCellExportLayout.value !== "single_line") {
      lines.push(`${courseCellFieldLabel(courseCellExportBottomField.value)}：${courseCellFieldValue(courseCellExportBottomField.value)}`);
    }
    return lines;
  });

function courseCellTemplatePreviewValue(field: CourseCellExportField, period: PeriodDraft) {
    if (field === "time") {
      return `${period.start_time}-${period.end_time}`;
    }
    const sampleValues: Partial<Record<CourseCellExportField, string>> = {
      subject: String(period.sample_subject || "").trim(),
      teacher: String(period.sample_teacher || "").trim(),
      room: String(period.sample_room || "").trim(),
      homeroom: String(period.sample_homeroom || "").trim(),
    };
    if (sampleValues[field]) {
      return sampleValues[field] as string;
    }
    return courseCellFieldValue(field);
  }

function courseCellTemplatePreviewLines(period: PeriodDraft) {
    const mode = previewPeriodMode(period);
    if (mode === "disabled") {
      return [];
    }
    if (mode === "custom") {
      return [String(period.custom_content || "").trim()].filter(Boolean);
    }
    const useCustomExport = previewPeriodExportStyle(period) === "custom";
    const layout = useCustomExport
      ? normalizeCourseCellExportLayout(period.export_layout, courseCellExportLayout.value)
      : courseCellExportLayout.value;
    const topField = useCustomExport
      ? normalizeCourseCellExportField(period.export_top_field, courseCellExportTopField.value)
      : courseCellExportTopField.value;
    const bottomField = useCustomExport
      ? normalizeCourseCellExportField(period.export_bottom_field, courseCellExportBottomField.value)
      : courseCellExportBottomField.value;
    const lines = [
      courseCellTemplatePreviewValue(topField, period),
    ];
    if (layout !== "single_line") {
      lines.push(courseCellTemplatePreviewValue(bottomField, period));
    }
    return lines;
  }

function courseCellTemplatePreviewLayout(period: PeriodDraft): CourseCellExportLayout {
    if (previewPeriodMode(period) !== "scheduled") {
      return "single_line";
    }
    if (previewPeriodExportStyle(period) !== "custom") {
      return courseCellExportLayout.value;
    }
    return normalizeCourseCellExportLayout(period.export_layout, courseCellExportLayout.value);
  }

function recordName(record: Record<string, unknown>, fallback = "-") {
    return String(record.name || record.homeroom_name || record.subject_name || fallback);
  }
// Local persistence boundary. The editor above is mechanically reused from the web app.
activeSection.value = "timetable";
const localNotice = ref("");
async function loadSchoolData() {
  loading.value = true;
  error.value = "";
  try {
    const result = await sidecarRequest<{ schoolData: SchoolData; project: Record<string, unknown>; revision: number }>({method: "GET", path: "/v1/timetable/settings"});
    schoolData.value = result.schoolData;
    projects.value = [{id: String(result.project.id), name: String(result.project.name)}];
    projectId.value = String(result.project.id);
    termForm.value = {name: String(result.schoolData.active_term?.name || "默认学期"), week_count: Number(result.schoolData.active_term?.week_count || 20), day_count: 7};
    localRevision = result.revision;
    onRevision(result.revision);
    syncTimetableTemplateForms();
  } catch(cause) { error.value = formatLocalError(cause); }
  finally { loading.value = false; }
}
let localRevision = 0;
let termSave: Promise<boolean> | null = null;
async function updateActiveTerm() {
  if (termSave) return termSave;
  if (schoolData.value.active_term?.id && Number(schoolData.value.active_term.week_count) === Number(termForm.value.week_count)) return true;
  termSave = saveTerm();
  try { return await termSave; } finally { termSave = null; }
}
async function saveTerm() {
  try {
    const term = schoolData.value.active_term;
    const result = await localApi.saveEntity("term", {...termForm.value, ...(term?.id ? {id: term.id} : {}), active: 1}, localRevision);
    localRevision = result.revision;
    schoolData.value.active_term = result.item;
    onRevision(result.revision);
    localNotice.value = "学期周数已保存到本机";
    return true;
  } catch(cause) { error.value = formatLocalError(cause); return false; }
}
async function persistTimetableTemplate(_scope: "project" | "organization" | "marketplace" = "project") {
  if (loading.value) return false;
  if (!timetableTemplateForm.value.name.trim()) { error.value = "模板名称不能为空"; return false; }
  const invalid = timetableTemplatePeriodsLocked.value ? "" : validateAllPeriodTimes();
  if (invalid) { error.value = invalid; return false; }
  if (!timetableTemplatePeriodsLocked.value) relabelAllPeriods();
  loading.value = true;
  error.value = "";
  localNotice.value = "";
  try {
    if (!await updateActiveTerm()) return false;
    const template = {
      ...timetableTemplateForm.value,
      term_id: schoolData.value.active_term?.id || null,
      template_kind: timetableTemplateKind.value,
      period_source_template_id: timetableTemplatePeriodSourceId.value || null,
      periods_locked: timetableTemplatePeriodsLocked.value,
      display_config: {
        title: timetableTemplateForm.value.name.trim(), enabled_weekdays: enabledWeekdays.value,
        time_mode: timetableTimeMode.value, show_time_axis: showTimetableTimeAxis.value,
        course_cell_layout: courseCellExportLayout.value, course_cell_top_field: courseCellExportTopField.value,
        course_cell_bottom_field: courseCellExportBottomField.value, layout_kind: timetableTemplateLayoutKind.value,
        all_classes_variant: allClassesTemplateVariant.value, blank_rows: previewBlankRows.value,
        blank_columns: previewBlankColumns.value, header_rows: previewHeaderRows.value,
      },
    };
    const result = await sidecarRequest<{templateId: string; revision: number}>({method:"PUT", path:"/v1/timetable/templates", body:{expected_revision:localRevision, data:{template, periods:weeklyPeriodDrafts.value.map(periodDraftPayload)}}});
    selectedTemplateId.value = result.templateId;
    localRevision = result.revision;
    onRevision(result.revision);
    await loadSchoolData();
    localNotice.value = "课表模板已保存到本机";
    return true;
  } catch(cause) { error.value = formatLocalError(cause); return false; }
  finally { loading.value = false; }
}
async function saveTimetableTemplate() { return persistTimetableTemplate("project"); }
async function deleteTimetableTemplate() {
  if (loading.value) return;
  if (!selectedTemplateId.value || !window.confirm("确定删除当前模板？被其他数据引用的模板不能删除。")) return;
  loading.value = true;
  try {
    if (!await updateActiveTerm()) return;
    await sidecarRequest({method:"DELETE",path:`/v1/timetable/templates/${encodeURIComponent(selectedTemplateId.value)}?expected_revision=${localRevision}`});
    selectedTemplateId.value = "";
    await loadSchoolData();
  } catch(cause) { error.value = formatLocalError(cause); }
  finally { loading.value = false; }
}
async function loadTemplateMarketplace() {
  timetablePresetLibrary.value = {
    weekly_timetable_presets: schoolData.value.weekly_timetable_templates.map(t => ({...t, is_owned: true, organization_name:"本机模板"})),
    weekly_timetable_preset_periods: schoolData.value.weekly_timetable_periods,
  };
  specialTimetableTemplatePresets.value = [
    {key:"local:class-rows", name:"全校班级总课表", description:"按班级分行展示全校课表。", layoutKind:"all_classes_grid", applicationScope:"all", variant:"homeroom_rows", displayConfig:{}},
    {key:"local:period-rows", name:"全校分时段总课表", description:"按时段和年级展示全校课表。", layoutKind:"all_classes_grid", applicationScope:"all", variant:"period_rows_grouped", displayConfig:{}},
  ];
}

return { activeSection, addPreviewBlankColumn, addPreviewBlankRow, addPreviewHeaderRow, addPreviewRow, applySelectedBlankColumnCellMerge, applySelectedBlankRowCellMerge, applySelectedHeaderCellMerge, blankRowRenderedCells, canDeleteCurrentRow, canMovePreviewBlankColumn, canMovePreviewBlankRow, canMovePreviewHeaderRow, cancelNewTimetableTemplate, courseCellExportBottomField, courseCellExportLayout, courseCellExportTopField, courseCellSampleLines, courseCellTemplatePreviewLayout, courseCellTemplatePreviewLines, createNewTimetableTemplate, deletePreviewBlankColumn, deletePreviewBlankRow, deletePreviewHeaderRow, deleteSelectedPreviewRow, deleteTimetableTemplate, exportTimetableTemplateExcel, isPreviewBlankColumnCellSelected, isPreviewBlankColumnSelected, isPreviewBlankRowCellSelected, isPreviewBlankRowSelected, isPreviewCellSelected, isPreviewHeaderCellSelected, isTemplateWeekdayEnabled, allClassesTemplateVariant, fullTablePreviewColumnCount, fullTablePreviewDayGroups, fullTablePreviewPeriods, hasTimetableTemplateEditor, irregularPreviewColumnCount, irregularPreviewDayGroups, irregularPreviewHomerooms, loading, movePreviewBlankColumn, movePreviewBlankRow, movePreviewHeaderRow, newTemplateConfirmDescription, newTemplateConfirmStep, newTemplateConfirmTitle, previewBlankColumnCell, previewBodyColumnCount, previewHeaderCellText, previewHeaderRowRenderedCells, previewHeaderRows, previewPeriodMode, saveTimetableTemplate, schoolData, schoolDataSummary, selectNumberValue, selectPreviewBlankColumn, selectPreviewBlankColumnCell, selectPreviewBlankRow, selectPreviewBlankRowCell, selectPreviewCell, selectPreviewHeaderCell, selectTimetableTemplate, selectedPreviewBlankColumn, selectedPreviewBlankColumnCell, selectedPreviewBlankColumnCellMaxColspan, selectedPreviewBlankColumnCellMaxRowspan, selectedPreviewBlankRow, selectedPreviewBlankRowCell, selectedPreviewBlankRowCellMaxColspan, selectedPreviewBlankRowCellMaxRowspan, selectedPreviewCell, selectedPreviewHeaderCell, selectedPreviewHeaderCellMaxColspan, selectedPreviewHeaderCellMaxRowspan, selectedPreviewPeriod, selectedTemplateId, setTemplateWeekdayEnabled, showNewTimetableTemplateConfirm, showTimetableTimeAxis, splitSelectedBlankColumnCell, splitSelectedBlankRowCell, splitSelectedHeaderCell, specialTimetableTemplatePresetsLoading, templateDisplayConfig, termForm, timetable, timetablePresetLibraryLoading, timetablePreviewColumns, timetablePreviewDays, timetablePreviewRowFlow, timetableTemplateForm, timetableTemplateKind, timetableTemplateLayoutKind, templateCreatePlanningMode, templateMarketplaceSearch, templateMarketplaceFilters, filteredTemplateMarketplaceItems, selectedTemplateMarketplaceKey, previewTemplateMarketplaceItem, chooseTemplatePlanningMode, backNewTemplateStep, selectTemplateMarketplaceItem, openTemplateMarketplacePreview, closeTemplateMarketplacePreview, continueTemplateMarketplace, confirmNewTemplateFromMarketplace, beginPeriodTimeEdit, commitPeriodTimeDraft, commitPeriodTimeOnEnter, nextPeriodStartTime, periodTimeDraftValue, periodTimeError, previousPeriodEndTime, previewPeriodExportStyle, selectedPeriodMergeSpanCount, setPreviewPeriodExportStyle, setPreviewPeriodMode, updatePeriodTimeDraft, updateActiveTerm, syncTimetableTemplateForms, error, periodDraftPayload, validateAllPeriodTimes, persistTimetableTemplate, loadSchoolData, periodTimeDrafts, periodTimeErrors, timetableTemplatePeriodSourceId, timetableTemplatePeriodsLocked, previewBlankRows, previewBlankColumns, localNotice };
}
