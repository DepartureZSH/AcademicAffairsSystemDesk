<script setup lang="ts">
import { computed } from "vue";

type MarketplaceItem = {
  name: string;
  organizationName: string;
  layoutKind: "weekly" | "all_classes_grid";
  displayConfig: Record<string, unknown>;
  periods: Array<Record<string, unknown>>;
};

type PreviewCell = {
  label: string;
  align: "left" | "center" | "right";
  colspan: number;
  rowspan: number;
  active: boolean;
  coveredBy?: string;
  binding?: string;
};

type PreviewColumn =
  | { kind: "weekday"; key: string; sort: number; weekday: number; label: string }
  | { kind: "blank"; key: string; sort: number; id: string; label: string; colspan: number; cells: Record<string, PreviewCell> };

type PreviewPeriod = {
  weekday: number;
  periodIndex: number;
  label: string;
  startTime: string;
  endTime: string;
  active: boolean;
  align: "left" | "center";
  colspan: number;
  cellMode: "scheduled" | "custom" | "disabled";
  customContent: string;
  sampleSubject: string;
  sampleTeacher: string;
  sampleRoom: string;
  sampleHomeroom: string;
  exportStyle: "default" | "custom";
  exportLayout: "single_line" | "two_line" | "split_rows";
  exportTopField: string;
  exportBottomField: string;
};

const props = defineProps<{ item: MarketplaceItem }>();
const weekdayLabels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

const config = computed(() => props.item.displayConfig || {});

function numberValue(value: unknown, fallback = 1) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function clockFromMinutes(value: unknown) {
  const minutes = numberValue(value, 0);
  const hour = Math.floor(minutes / 60);
  const minute = minutes % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function normalizeCell(source: unknown): PreviewCell {
  const cell = source && typeof source === "object" ? source as Record<string, unknown> : {};
  return {
    label: String(cell.label || ""),
    align: cell.align === "left" ? "left" : cell.align === "right" ? "right" : "center",
    colspan: Math.max(numberValue(cell.colspan), 1),
    rowspan: Math.max(numberValue(cell.rowspan), 1),
    active: cell.active !== false,
    coveredBy: cell.coveredBy ? String(cell.coveredBy) : undefined,
    binding: cell.binding ? String(cell.binding) : undefined,
  };
}

function normalizeCells(source: unknown) {
  if (!source || typeof source !== "object") return {} as Record<string, PreviewCell>;
  return Object.fromEntries(
    Object.entries(source as Record<string, unknown>).map(([key, value]) => [key, normalizeCell(value)]),
  );
}

const enabledWeekdays = computed(() => {
  const source = Array.isArray(config.value.enabled_weekdays) ? config.value.enabled_weekdays : [1, 2, 3, 4, 5];
  const days = Array.from(new Set(source.map(Number).filter((day) => day >= 1 && day <= 7))).sort((a, b) => a - b);
  return days.length ? days : [1, 2, 3, 4, 5];
});

const periods = computed<PreviewPeriod[]>(() => props.item.periods.map((source) => {
  const display = source.display_config && typeof source.display_config === "object"
    ? source.display_config as Record<string, unknown>
    : source;
  const cellMode: PreviewPeriod["cellMode"] = display.cell_mode === "custom" || display.cell_mode === "disabled" || display.cell_mode === "scheduled"
    ? display.cell_mode
    : source.active === false ? "disabled" : "scheduled";
  const exportLayout: PreviewPeriod["exportLayout"] = display.export_layout === "single_line" || display.export_layout === "split_rows"
    ? display.export_layout
    : "two_line";
  const exportStyle: PreviewPeriod["exportStyle"] = display.export_style === "custom" ? "custom" : "default";
  return {
    weekday: numberValue(source.weekday),
    periodIndex: numberValue(source.period_index),
    label: String(source.label || `第${numberValue(source.period_index)}节`),
    startTime: String(source.start_time || "") || clockFromMinutes(source.start_time_minutes),
    endTime: String(source.end_time || "") || clockFromMinutes(source.end_time_minutes),
    active: source.active !== false,
    align: display.align === "left" ? "left" as const : "center" as const,
    colspan: Math.max(numberValue(display.colspan), 1),
    cellMode,
    customContent: String(display.custom_content || ""),
    sampleSubject: String(display.sample_subject || "示例课程"),
    sampleTeacher: String(display.sample_teacher || "示例教师"),
    sampleRoom: String(display.sample_room || "示例教室"),
    sampleHomeroom: String(display.sample_homeroom || "示例班级"),
    exportStyle,
    exportLayout,
    exportTopField: String(display.export_top_field || "subject"),
    exportBottomField: String(display.export_bottom_field || "teacher"),
  };
}).filter((period) => enabledWeekdays.value.includes(period.weekday)));

const blankColumns = computed(() => {
  const rows = Array.isArray(config.value.blank_columns) ? config.value.blank_columns : [];
  return rows.map((source, index) => {
    const column = source && typeof source === "object" ? source as Record<string, unknown> : {};
    const id = String(column.id || `blank-column-${index + 1}`);
    return {
      kind: "blank" as const,
      key: `blank-${id}`,
      id,
      label: String(column.label || ""),
      sort: numberValue(column.order_index, 7 + index),
      colspan: Math.max(numberValue(column.colspan), 1),
      cells: normalizeCells(column.cells),
    };
  });
});

const columns = computed<PreviewColumn[]>(() => [
  ...enabledWeekdays.value.map((weekday) => ({
    kind: "weekday" as const,
    key: `weekday-${weekday - 1}`,
    sort: weekday - 1,
    weekday,
    label: weekdayLabels[weekday - 1],
  })),
  ...blankColumns.value,
].sort((left, right) => left.sort - right.sort || left.key.localeCompare(right.key)));

const showTimeAxis = computed(() => config.value.show_time_axis !== false);
const bodyColumnCount = computed(() => columns.value.reduce(
  (total, column) => total + (column.kind === "blank" ? column.colspan : 1),
  0,
));

const headerRows = computed(() => {
  const sourceRows = config.value.header_rows;
  if (sourceRows === undefined) {
    return [{
      id: "default-title",
      orderIndex: 0,
      cells: {
        "header-0": {
          ...normalizeCell({ binding: "template_name" }),
          colspan: Math.max(headerColumnCount.value, 1),
        },
      },
    }];
  }
  return (Array.isArray(sourceRows) ? sourceRows : []).map((source, index) => {
    const row = source && typeof source === "object" ? source as Record<string, unknown> : {};
    return {
      id: String(row.id || `header-row-${index + 1}`),
      orderIndex: numberValue(row.order_index, index),
      cells: normalizeCells(row.cells),
    };
  }).sort((left, right) => left.orderIndex - right.orderIndex || left.id.localeCompare(right.id));
});

function headerLabel(cell: PreviewCell) {
  const values: Record<string, string> = {
    template_name: props.item.name,
    school_name: props.item.organizationName,
    project_name: "示例项目",
    owner_name: props.item.organizationName,
  };
  return cell.binding && cell.binding !== "custom" ? values[cell.binding] || cell.label : cell.label;
}

function renderedHeaderCells(row: typeof headerRows.value[number]) {
  const rendered: Array<{ key: string; cell: PreviewCell; label: string; colspan: number; rowspan: number }> = [];
  for (let index = 0; index < headerColumnCount.value; index += 1) {
    const key = `header-${index}`;
    const cell = row.cells[key] || normalizeCell({});
    if (cell.coveredBy) continue;
    const colspan = Math.min(cell.colspan, headerColumnCount.value - index);
    const rowIndex = headerRows.value.findIndex((entry) => entry.id === row.id);
    rendered.push({
      key,
      cell,
      label: headerLabel(cell),
      colspan,
      rowspan: Math.min(cell.rowspan, Math.max(headerRows.value.length - rowIndex, 1)),
    });
    index += colspan - 1;
  }
  return rendered;
}

const periodIndexes = computed(() => Array.from(new Set(periods.value.map((period) => period.periodIndex))).sort((a, b) => a - b));
const weeklyRows = computed(() => {
  const variableTimeMode = config.value.time_mode === "variable";
  const periodRows = variableTimeMode
    ? Array.from(new Set(periods.value.map((period) => `${period.startTime}|${period.endTime}`)))
        .sort((left, right) => left.localeCompare(right))
        .map((timeRange, index) => {
          const [startTime, endTime] = timeRange.split("|");
          const matchingPeriods = periods.value.filter(
            (period) => period.startTime === startTime && period.endTime === endTime,
          );
          return {
            kind: "period" as const,
            id: `time-${startTime}-${endTime}`,
            rowKey: `period-${index + 1}`,
            sort: index + 1,
            periodIndex: matchingPeriods[0]?.periodIndex || index + 1,
            periods: matchingPeriods,
          };
        })
    : periodIndexes.value.map((periodIndex, index) => ({
        kind: "period" as const,
        id: `period-${periodIndex}`,
        rowKey: `period-${index + 1}`,
        sort: periodIndex,
        periodIndex,
        periods: periods.value.filter((period) => period.periodIndex === periodIndex),
      }));
  const sourceRows = Array.isArray(config.value.blank_rows) ? config.value.blank_rows : [];
  const customRows = sourceRows.map((source, index) => {
    const row = source && typeof source === "object" ? source as Record<string, unknown> : {};
    return {
      kind: "blank" as const,
      id: String(row.id || `blank-row-${index + 1}`),
      sort: numberValue(row.order_index, 100 + index),
      label: String(row.label || ""),
      cells: normalizeCells(row.cells),
    };
  });
  return [...periodRows, ...customRows].sort((left, right) => left.sort - right.sort || left.id.localeCompare(right.id));
});

function weeklyPeriodCells(row: Extract<typeof weeklyRows.value[number], { kind: "period" }>) {
  const rendered: Array<{
    key: string;
    kind: "period" | "blank";
    period?: PreviewPeriod;
    cell?: PreviewCell;
    colspan: number;
    rowspan: number;
  }> = [];
  for (let index = 0; index < columns.value.length; index += 1) {
    const column = columns.value[index];
    if (column.kind === "blank") {
      const cell = column.cells[row.rowKey] || normalizeCell({ label: column.label });
      if (cell.coveredBy) continue;
      rendered.push({ key: `${row.id}-${column.id}`, kind: "blank", cell, colspan: cell.colspan, rowspan: cell.rowspan });
      index += Math.max(cell.colspan - 1, 0);
      continue;
    }
    const period = row.periods.find((entry) => entry.weekday === column.weekday);
    const colspan = Math.min(period?.colspan || 1, columns.value.length - index);
    rendered.push({ key: `${row.id}-${column.weekday}`, kind: "period", period, colspan, rowspan: 1 });
    index += colspan - 1;
  }
  return rendered;
}

function renderedBlankRowCells(row: Extract<typeof weeklyRows.value[number], { kind: "blank" }>) {
  const rendered: Array<{ key: string; cell: PreviewCell; colspan: number; rowspan: number }> = [];
  for (let index = 0; index < columns.value.length; index += 1) {
    const column = columns.value[index];
    const cell = row.cells[column.key] || normalizeCell(index === 0 && row.label ? { label: row.label } : {});
    if (cell.coveredBy) continue;
    const colspan = Math.min(cell.colspan, columns.value.length - index);
    rendered.push({ key: column.key, cell, colspan, rowspan: cell.rowspan });
    index += colspan - 1;
  }
  return rendered;
}

const cellLayout = computed(() => ["single_line", "split_rows"].includes(String(config.value.course_cell_layout))
  ? String(config.value.course_cell_layout)
  : "two_line");
const topField = computed(() => String(config.value.course_cell_top_field || "subject"));
const bottomField = computed(() => String(config.value.course_cell_bottom_field || "teacher"));

function courseField(field: string, period: PreviewPeriod) {
  const values: Record<string, string> = {
    subject: period.sampleSubject,
    teacher: period.sampleTeacher,
    room: period.sampleRoom,
    time: `${period.startTime}-${period.endTime}`,
    homeroom: period.sampleHomeroom,
  };
  return values[field] || values.subject;
}

function courseLines(period: PreviewPeriod) {
  if (period.cellMode === "disabled") return [];
  if (period.cellMode === "custom") return period.customContent ? [period.customContent] : [];
  const layout = period.exportStyle === "custom" ? period.exportLayout : cellLayout.value;
  const firstField = period.exportStyle === "custom" ? period.exportTopField : topField.value;
  const secondField = period.exportStyle === "custom" ? period.exportBottomField : bottomField.value;
  const lines = [courseField(firstField, period)];
  if (layout !== "single_line") lines.push(courseField(secondField, period));
  return lines;
}

const specialVariant = computed(() => config.value.all_classes_variant === "period_rows_grouped"
  ? "period_rows_grouped"
  : "homeroom_rows");
const sampleHomerooms = [
  { id: "7-1", grade: "七年级", label: "1", name: "七年级1班" },
  { id: "7-2", grade: "七年级", label: "2", name: "七年级2班" },
  { id: "8-1", grade: "八年级", label: "1", name: "八年级1班" },
  { id: "8-2", grade: "八年级", label: "2", name: "八年级2班" },
];
const specialDayGroups = computed(() => enabledWeekdays.value.map((weekday) => ({
  weekday,
  label: weekdayLabels[weekday - 1],
  periods: periodIndexes.value,
})));
const specialHomeroomColumnCount = computed(() => 1 + specialDayGroups.value.length * periodIndexes.value.length);
const fullSchoolColumnCount = computed(() => 3 + specialDayGroups.value.length * sampleHomerooms.length);
const headerColumnCount = computed(() => props.item.layoutKind === "weekly"
  ? bodyColumnCount.value + (showTimeAxis.value ? 1 : 0)
  : specialVariant.value === "period_rows_grouped"
    ? fullSchoolColumnCount.value
    : specialHomeroomColumnCount.value);

function periodTime(periodIndex: number) {
  const period = periods.value.find((entry) => entry.periodIndex === periodIndex);
  return period ? `${period.startTime}-${period.endTime}` : "--:--";
}

function daySegment(periodIndex: number) {
  const period = periods.value.find((entry) => entry.periodIndex === periodIndex);
  return period && Number(period.startTime.slice(0, 2)) < 12 ? "上午" : "下午";
}

function segmentRowspan(periodIndex: number) {
  const segment = daySegment(periodIndex);
  return periodIndexes.value.filter((index) => daySegment(index) === segment).length * 2;
}

function isSegmentStart(periodIndex: number) {
  return periodIndexes.value.find((index) => daySegment(index) === daySegment(periodIndex)) === periodIndex;
}
</script>

<template>
  <div class="template-marketplace-preview-canvas">
    <table v-if="item.layoutKind === 'weekly'" class="weekly-preview-table marketplace-weekly-preview">
      <thead>
        <tr v-for="row in headerRows" :key="row.id" class="preview-custom-header-row">
          <th
            v-for="cell in renderedHeaderCells(row)"
            :key="`${row.id}-${cell.key}`"
            :colspan="cell.colspan"
            :rowspan="cell.rowspan"
            class="preview-custom-heading"
            :class="{ left: cell.cell.align === 'left', inactive: !cell.cell.active }"
          >{{ cell.label }}</th>
        </tr>
        <tr>
          <th v-if="showTimeAxis" class="preview-time-heading">时间</th>
          <th
            v-for="column in columns"
            :key="column.key"
            :colspan="column.kind === 'blank' ? column.colspan : 1"
            :class="{ 'blank-column-heading': column.kind === 'blank' }"
          >{{ column.label }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in weeklyRows" :key="row.id">
          <tr v-if="row.kind === 'period'" class="timeline-interval-row">
            <th v-if="showTimeAxis" class="period-row-heading preview-time-axis">
              <span>{{ row.periods[0]?.startTime || '--:--' }}</span>
              <span class="time-axis-end">{{ row.periods[0]?.endTime || '' }}</span>
            </th>
            <td
              v-for="cell in weeklyPeriodCells(row)"
              :key="cell.key"
              :colspan="cell.colspan"
              :rowspan="cell.rowspan"
              :class="{
                'period-time-block': cell.kind === 'period' && cell.period,
                'empty-time-slot': cell.kind === 'period' && !cell.period,
                'blank-column-cell': cell.kind === 'blank',
                inactive: cell.kind === 'period' ? cell.period?.cellMode === 'disabled' : cell.cell?.active === false,
                'custom-content-cell': cell.kind === 'period' && cell.period?.cellMode === 'custom',
                left: cell.kind === 'period' ? cell.period?.align === 'left' : cell.cell?.align === 'left',
              }"
            >
              <div v-if="cell.kind === 'period' && cell.period" class="template-course-cell-preview" :class="{ split: (cell.period.exportStyle === 'custom' ? cell.period.exportLayout : cellLayout) === 'split_rows' }">
                <div v-for="(line, index) in courseLines(cell.period)" :key="index" class="template-course-cell-line">{{ line }}</div>
              </div>
              <template v-else-if="cell.kind === 'blank'">{{ cell.cell?.label }}</template>
              <span v-else class="time-slot-placeholder"></span>
            </td>
          </tr>
          <tr v-else class="blank-preview-row">
            <td v-if="showTimeAxis" class="preview-time-axis blank-row-time"><span>{{ row.label }}</span></td>
            <td
              v-for="cell in renderedBlankRowCells(row)"
              :key="cell.key"
              :colspan="cell.colspan"
              :rowspan="cell.rowspan"
              class="blank-row-cell"
              :class="{ left: cell.cell.align === 'left', inactive: !cell.cell.active }"
            >{{ cell.cell.label }}</td>
          </tr>
        </template>
      </tbody>
    </table>

    <table v-else-if="specialVariant === 'homeroom_rows'" class="weekly-preview-table irregular-template-preview-table">
      <thead>
        <tr v-for="row in headerRows" :key="row.id" class="preview-custom-header-row">
          <th v-for="cell in renderedHeaderCells(row)" :key="`${row.id}-${cell.key}`" :colspan="cell.colspan" :rowspan="cell.rowspan" class="preview-custom-heading" :class="{ left: cell.cell.align === 'left' }">{{ cell.label }}</th>
        </tr>
        <tr><th rowspan="2" class="irregular-class-heading">班级</th><th v-for="group in specialDayGroups" :key="group.weekday" :colspan="group.periods.length">{{ group.label }}</th></tr>
        <tr><template v-for="group in specialDayGroups" :key="`periods-${group.weekday}`"><th v-for="periodIndex in group.periods" :key="`${group.weekday}-${periodIndex}`">第{{ periodIndex }}节</th></template></tr>
      </thead>
      <tbody>
        <tr v-for="homeroom in sampleHomerooms" :key="homeroom.id"><th class="irregular-homeroom-heading">{{ homeroom.name }}</th><td v-for="index in specialDayGroups.length * periodIndexes.length" :key="index" class="irregular-subject-cell">{{ index % 4 === 1 ? '示例课程' : '' }}</td></tr>
      </tbody>
    </table>

    <table v-else class="weekly-preview-table full-school-template-table">
      <thead>
        <tr v-for="row in headerRows" :key="row.id" class="preview-custom-header-row">
          <th v-for="cell in renderedHeaderCells(row)" :key="`${row.id}-${cell.key}`" :colspan="cell.colspan" :rowspan="cell.rowspan" class="preview-custom-heading" :class="{ left: cell.cell.align === 'left' }">{{ cell.label }}</th>
        </tr>
        <tr><th rowspan="3">时段</th><th rowspan="3">时间</th><th rowspan="3">节次</th><th v-for="group in specialDayGroups" :key="group.weekday" :colspan="sampleHomerooms.length">{{ group.label }}</th></tr>
        <tr><template v-for="group in specialDayGroups" :key="`grades-${group.weekday}`"><th v-for="grade in ['七年级', '八年级']" :key="`${group.weekday}-${grade}`" colspan="2">{{ grade }}</th></template></tr>
        <tr><template v-for="group in specialDayGroups" :key="`classes-${group.weekday}`"><th v-for="homeroom in sampleHomerooms" :key="`${group.weekday}-${homeroom.id}`">{{ homeroom.label }}</th></template></tr>
      </thead>
      <tbody>
        <template v-for="periodIndex in periodIndexes" :key="periodIndex">
          <tr>
            <th v-if="isSegmentStart(periodIndex)" :rowspan="segmentRowspan(periodIndex)" class="full-school-segment-cell">{{ daySegment(periodIndex) }}</th>
            <th rowspan="2" class="full-school-time-cell">{{ periodTime(periodIndex) }}</th>
            <th rowspan="2" class="full-school-period-cell">第{{ periodIndex }}节</th>
            <template v-for="group in specialDayGroups" :key="`subjects-${periodIndex}-${group.weekday}`"><td v-for="homeroom in sampleHomerooms" :key="`${group.weekday}-${homeroom.id}`" class="full-school-course-cell subject-line">示例课程</td></template>
          </tr>
          <tr><template v-for="group in specialDayGroups" :key="`teachers-${periodIndex}-${group.weekday}`"><td v-for="homeroom in sampleHomerooms" :key="`${group.weekday}-${homeroom.id}`" class="full-school-course-cell teacher-line">示例教师</td></template></tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
