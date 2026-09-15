// @ts-nocheck -- upstream source
type Data = Record<string, unknown>;
export type ChangeItem = {
  id: string; target: string; operation: string; status: string;
  before_data?: Data | null; after_data?: Data | null;
  display_data?: Data; identity?: Data; source_ref?: Data; error_message?: string | null;
};
type Column = { key: string; label: string };
export const changeTargets: Record<string, string> = {
  teacher: "教师", homeroom: "班级", subject: "科目", room: "教室", room_type: "教室类型",
  term: "学期", timetable_template: "课表模板", course_plan: "课程计划", task: "授课任务",
  lesson: "课次", constraint: "约束", run: "排课运行",
};
export const changeOperations: Record<string, string> = {
  create: "新增", update: "修改", delete: "删除", skip: "跳过", run: "发起排课",
};
const fields: Record<string, string> = {
  name: "名称", department: "教师分组", student_count: "人数", group_name: "分组",
  head_teacher_id: "班主任", default_room_id: "默认教室", description: "说明", category: "类别",
  default_duration_slots: "默认课长", code: "编码", capacity: "容量", type: "类型", type_id: "教室类型",
  room_type_name: "教室类型", unavailable_period_ids: "不可用时段", unavailable_slots: "不可用时间",
  unavailable_rules: "不可用规则", homeroom_id: "班级", subject_id: "科目", primary_teacher_id: "任课教师",
  teacher_id: "教师", fixed_room_id: "固定教室", room_ids: "可用教室", required_room_type: "所需教室类型",
  weekly_slots: "每周课次", duration_slots: "每次课长", lessons: "课次安排",
  week_bits: "教学周", day_bits: "上课日", allow_double_period: "允许连堂", priority: "优先级",
  preferred_period_ids: "优先时段", preferred_slots: "优先时间", course_plan_id: "课程计划",
  week_count: "学期周数", day_count: "每周天数", slot_duration_minutes: "时间槽（分钟）",
  template_kind: "模板类型", application_scope: "适用对象", is_default: "默认模板",
  period_source_template_id: "时段来源模板", periods_locked: "锁定时段", publish_as_preset: "发布模板",
  preset_scope: "保存范围", display_config: "展示设置", periods: "课次时段",
  distribution_type: "规则类型", required: "必须满足", penalty: "违反扣分", parameters: "规则条件",
  groups: "作用分组", structured_payload: "约束设置", human_summary: "规则说明",
  label: "名称", enabled: "启用", weekday: "星期", start_slot: "开始时间槽", end_slot: "结束时间槽",
  start_time: "开始时间", end_time: "结束时间", period_index: "节次", period_id: "时段",
  room_id: "教室", room_options: "教室选项", time_preferences: "时间偏好", teacher_name: "教师",
  homeroom_name: "班级", subject_name: "科目", room_name: "教室", tags: "标签",
  export_template_id: "导出模板", timetable_template_id: "课表模板", template_id: "模板",
  selected_homeroom_ids: "指定班级", homeroom_ids: "班级", teacher_ids: "教师", subject_ids: "科目",
  max_count: "最大数量", min_count: "最小数量", count: "数量", days: "日期", weeks: "周次",
  title: "标题", content: "内容", text: "文字", color: "颜色", font_size: "字号", align: "对齐",
  lesson_id: "课次", lesson_ids: "课次", task_id: "授课任务", task_ids: "授课任务",
  enabled_weekdays: "上课日", time_mode: "时间模式", show_time_axis: "显示时间轴",
  start_time_minutes: "开始时间", end_time_minutes: "结束时间", active: "安排课次",
  cell_mode: "单元格用途", custom_content: "自定义内容", colspan: "跨列数",
  course_cell_layout: "课程单元格布局", course_cell_top_field: "首行信息", course_cell_bottom_field: "次行信息",
};
const coreFields: Record<string, string[]> = {
  teacher: ["name", "department"], homeroom: ["name", "student_count", "group_name", "head_teacher_id", "default_room_id"],
  subject: ["name", "default_duration_slots"], room: ["name", "type_id", "capacity"], room_type: ["name", "description"],
  term: ["name", "week_count", "day_count"],
  timetable_template: ["name", "template_kind", "day_count", "slot_duration_minutes", "application_scope", "is_default"],
  course_plan: ["homeroom_id", "subject_id", "planning_teacher", "planning_room", "planning_lesson", "planning_lesson_room"],
  task: ["homeroom_id", "subject_id", "primary_teacher_id", "fixed_room_id", "weekly_slots", "duration_slots"],
  lesson: ["label", "duration_slots", "enabled"], constraint: ["name", "distribution_type", "required", "penalty"],
  run: ["name"],
};
const metadata = new Set(["id", "organization_id", "project_id", "term_id", "created_at", "updated_at", "created_by", "_agent_preallocated"]);
const relations: Record<string, string> = {
  head_teacher_id: "teacher", primary_teacher_id: "teacher", teacher_id: "teacher", teacher_ids: "teacher",
  homeroom_id: "homeroom", homeroom_ids: "homeroom", selected_homeroom_ids: "homeroom",
  subject_id: "subject", subject_ids: "subject", default_room_id: "room", fixed_room_id: "room", room_id: "room", room_ids: "room",
  type_id: "room_type", period_source_template_id: "timetable_template", export_template_id: "timetable_template",
  timetable_template_id: "timetable_template", template_id: "timetable_template", course_plan_id: "course_plan",
  period_id: "period", preferred_period_ids: "period", unavailable_period_ids: "period",
  lesson_id: "lesson", lesson_ids: "lesson", task_id: "task", task_ids: "task",
};
const enums: Record<string, Record<string, string>> = {
  template_kind: { normal: "普通模板", special: "特殊模板" },
  application_scope: { all: "全部", ...changeTargets, student: "学生" },
  preset_scope: { project: "本项目", organization: "本机构", marketplace: "模板广场" },
  category: { academic: "学科课程", activity: "活动课程" },
  align: { left: "左对齐", center: "居中", right: "右对齐" },
  time_mode: { fixed: "固定时段", variable: "弹性时间" },
  cell_mode: { scheduled: "安排课次", custom: "自定义内容", disabled: "不安排" },
  course_cell_layout: { two_line: "上下两行", single_line: "单行", split_rows: "分行" },
  course_cell_top_field: { subject: "科目", teacher: "教师", room: "教室", homeroom: "班级" },
  course_cell_bottom_field: { subject: "科目", teacher: "教师", room: "教室", homeroom: "班级" },
};
const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
function record(value: unknown): Data { return value && typeof value === "object" && !Array.isArray(value) ? value as Data : {}; }
function equal(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (left == null || right == null || typeof left !== "object" || typeof right !== "object") return false;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((v, i) => equal(v, right[i]));
  }
  const a = record(left), b = record(right);
  return Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(key => key in b && equal(a[key], b[key]));
}

export function buildAgentChangeTables(items: ChangeItem[], catalogs: Record<string, Data[]> = {},
  formatters: { duration?: (value: unknown) => string; constraintType?: (value: unknown) => string } = {}, contextItems: ChangeItem[] = items) {
  // Keep before/after lookups separate so renamed linked records do not rewrite the old value.
  const lookups = { before: new Map<string, Data>(), after: new Map<string, Data>() };
  for (const [target, rows] of Object.entries(catalogs)) for (const row of rows) {
    if (row.id) for (const lookup of Object.values(lookups)) lookup.set(`${target}:${row.id}`, row);
  }
  for (const item of contextItems) {
    const before = item.before_data, after = item.after_data;
    if (before?.id) lookups.before.set(`${item.target}:${before.id}`, before);
    if (after?.id) lookups.after.set(`${item.target}:${after.id}`, after);
    else if (before?.id) lookups.after.set(`${item.target}:${before.id}`, before);
  }
  // Resolve the complete action, not just the current audit page or filter.
  function planningValue(plan: Data, key: string, side: "before" | "after") {
    const tasks = new Map<string, Data>();
    for (const task of catalogs.task || []) tasks.set(String(task.id), task);
    for (const item of contextItems.filter(item => item.target === "task")) {
      const data = side === "before" ? item.before_data : item.after_data;
      const id = String(data?.id || item.before_data?.id || item.id);
      if (data) tasks.set(id, data);
      else tasks.delete(id);
    }
    const related = [...tasks.values()].filter(task =>
      task.course_plan_id && plan.id ? task.course_plan_id === plan.id
        : Boolean(plan.homeroom_id && plan.subject_id && task.homeroom_id === plan.homeroom_id && task.subject_id === plan.subject_id));
    const roomIds = (data: Data): unknown[] => Array.isArray(data.room_ids) ? data.room_ids
      : Array.isArray(data.room_options) ? data.room_options.map(option => record(option).room_id).filter(Boolean) : [];
    const defaultRoom = (task: Data) => {
      if (task.required_room_type === "__no_room__") return "不使用教室";
      const ids = roomIds(task);
      if (ids.length) return ids.map(id => format(id, "room_id", side)).join("、");
      return task.fixed_room_id ? format(task.fixed_room_id, "room_id", side) : "未分配教室";
    };
    if (!related.length) return plan.weekly_slots === 0 ? "不安排" : "未生成授课任务";
    return related.flatMap(task => {
      const initialLessons = Array.isArray(task.lessons) ? task.lessons.map(record)
        : (catalogs.lesson || []).filter(lesson => lesson.teaching_task_id === task.id);
      const lessonMap = new Map(initialLessons.map((lesson, index) => [String(lesson.id || `index:${index}`), lesson]));
      for (const item of contextItems.filter(item => item.target === "lesson")) {
        const data = side === "before" ? item.before_data : item.after_data;
        const owner = data || item.before_data || item.after_data || {};
        if ((owner.teaching_task_id || owner.task_id) !== task.id) continue;
        const id = String(owner.id || item.id);
        if (data) lessonMap.set(id, data);
        else lessonMap.delete(id);
      }
      const lessons = [...lessonMap.values()];
      return (lessons.length ? lessons : [{}]).map(lesson => {
        if (key === "planning_teacher") return task.primary_teacher_id ? format(task.primary_teacher_id, "teacher_id", side) : "未指定教师";
        if (key === "planning_room") return defaultRoom(task);
        if (key === "planning_lesson") return String(lesson.label || lesson.name || "未生成课次");
        const ids = roomIds(lesson);
        return !lessons.length ? "未生成课次" : ids.length ? ids.map(id => format(id, "room_id", side)).join("、") : `默认（${defaultRoom(task)}）`;
      });
    }).join("\n");
  }
  function format(value: unknown, key: string, side: "before" | "after", depth = 0): string {
    if (value == null || value === "") return "未设置";
    if (typeof value === "boolean") return value ? "是" : "否";
    if (Array.isArray(value)) return value.length ? value.map((part, index) =>
      `${typeof part === "object" && part ? `第 ${index + 1} 项：\n` : ""}${format(part, key, side, depth + 1)}`).join("\n") : "无";
    if (typeof value === "object") {
      return Object.entries(record(value)).filter(([field]) => !metadata.has(field))
        .map(([field, part]) => `${fields[field] || field}：${format(part, field, side, depth + 1)}`).join("\n") || "无";
    }
    if (relations[key]) {
      const row = lookups[side].get(`${relations[key]}:${value}`);
      if (row) {
        if (relations[key] === "course_plan" && depth < 4) return `${format(row.homeroom_id, "homeroom_id", side, depth + 1)} · ${format(row.subject_id, "subject_id", side, depth + 1)}`;
        return String(row.name || row.label || row.title || `已选择${changeTargets[relations[key]] || "时段"}`);
      }
      return `名称待加载（${changeTargets[relations[key]] || "时段"}）`;
    }
    if (["duration_slots", "default_duration_slots"].includes(key)) return formatters.duration?.(value) || `${Number(value) * 5} 分钟`;
    if (["start_time_minutes", "end_time_minutes"].includes(key)) return `${String(Math.floor(Number(value) / 60)).padStart(2, "0")}:${String(Number(value) % 60).padStart(2, "0")}`;
    if (key === "distribution_type" && formatters.constraintType) return formatters.constraintType(value);
    if ((key === "week_bits" || key === "day_bits") && /^[01]+$/.test(String(value))) {
      const indices = Array.from(String(value)).flatMap((bit, index) => bit === "1" ? [key === "day_bits" ? weekdays[index] || `第 ${index + 1} 天` : `第 ${index + 1} 周`] : []);
      return indices.join("、") || "无";
    }
    if (key === "weekday") return weekdays[Number(value) - 1] || String(value);
    return enums[key]?.[String(value)] || String(value);
  }
  const groups = new Map<string, ChangeItem[]>();
  for (const item of items) {
    if (!groups.has(item.target)) groups.set(item.target, []);
    groups.get(item.target)!.push(item);
  }
  return Array.from(groups, ([target, group]) => {
    const keys = [...(coreFields[target] || ["name"])];
    for (const item of group) for (const key of new Set([...Object.keys(item.before_data || {}), ...Object.keys(item.after_data || {})])) {
      if (!metadata.has(key) && !keys.includes(key)) keys.push(key);
    }
    const planningLabels: Record<string, string> = { planning_teacher: "教师", planning_room: "默认教室", planning_lesson: "课次名", planning_lesson_room: "课次教室" };
    const columns: Column[] = keys.map(key => ({ key, label: planningLabels[key] || (key === "name" ? changeTargets[target] || "名称" : fields[key] || key) }));
    const rows = group.map(item => {
      const before = item.before_data || {}, after = item.after_data || {};
      const data = item.operation === "delete" ? before : item.after_data || before;
      const cells = columns.map(column => {
        const key = column.key;
        if (target === "course_plan" && key in planningLabels) {
          const oldValue = planningValue(before, key, "before");
          const newValue = planningValue(data, key, item.operation === "delete" ? "before" : "after");
          return { key, before: oldValue, after: newValue, changed: item.operation === "update" && oldValue !== newValue, expanded: needsDetails(oldValue) || needsDetails(newValue) };
        }
        const changed = item.operation === "update" && !equal(before[key], after[key]);
        const current = data[key] ?? (key === "name" ? item.display_data?.name || item.identity?.name : undefined);
        let display = format(current, key, item.operation === "delete" ? "before" : "after");
        if (target === "task" && current == null && key === "weekly_slots" && Array.isArray(data.lessons)) {
          display = String(data.lessons.length);
        }
        if (target === "task" && current == null && key === "duration_slots") {
          const subject = lookups[item.operation === "delete" ? "before" : "after"].get(`subject:${data.subject_id}`);
          display = subject?.default_duration_slots != null
            ? `沿用科目：${format(subject.default_duration_slots, "duration_slots", "after")}`
            : "沿用科目默认课长";
          if (Array.isArray(data.lessons) && data.lessons.some(lesson => lesson.duration_slots != null)) display = "按课次设置";
        }
        const previousDisplay = format(before[key], key, "before");
        return { key, changed, before: previousDisplay,
          after: display,
          expanded: needsDetails(display) || needsDetails(previousDisplay) || typeof current === "object" && current !== null || typeof before[key] === "object" && before[key] !== null };
      });
      const source = item.source_ref || {};
      return { id: item.id, operation: item.operation, operationLabel: changeOperations[item.operation] || "其他操作", cells,
        status: ({ pending: "待执行", executed: "已执行", skipped: "已跳过", failed: "执行失败", rejected: "已拒绝" } as Record<string, string>)[item.status] || "待核对",
        error: item.error_message || "",
        source: [source.filename, source.sheet, source.row ? `第 ${source.row} 行` : ""].filter(Boolean).join(" · ") || "AI 对话" };
    });
    return { target, title: changeTargets[target] || "其他数据", columns, rows };
  });
}

function needsDetails(value: string): boolean {
  return value.length > 80 || value.split("\n").length > 3;
}
