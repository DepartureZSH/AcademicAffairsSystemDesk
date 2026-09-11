<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { formatLocalError, localApi, type EntityRecord } from "../lib/sidecar";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();

const revision = ref(props.revision);
const years = ref<EntityRecord[]>([]);
const terms = ref<EntityRecord[]>([]);
const schedules = ref<EntityRecord[]>([]);
const slots = ref<EntityRecord[]>([]);
const assignments = ref<EntityRecord[]>([]);
const teachers = ref<EntityRecord[]>([]);
const homerooms = ref<EntityRecord[]>([]);
const subjects = ref<EntityRecord[]>([]);
const rooms = ref<EntityRecord[]>([]);
const roomTypes = ref<EntityRecord[]>([]);
const busy = ref(false);
const errorMessage = ref("");
const selectedScheduleId = ref("");
const openWeekday = ref(1);
const slotEditorOpen = ref(false);

const yearForm = ref({ name: "", start_date: "", end_date: "" });
const termForm = ref({ academic_year_id: "", name: "", start_date: "", end_date: "", week_count: 20, day_count: 5 });
const scheduleForm = ref({ term_id: "", name: "", day_count: 5, slot_duration_minutes: 40, is_default: 1 });
const slotForm = ref({ bell_schedule_id: "", weekday: 1, period_index: 0, label: "第1节", start_time: "08:00", end_time: "08:40" });
const assignmentForm = ref({ entity_type: "homeroom", entity_id: "", bell_schedule_id: "" });
const editing = reactive<Record<string, string | null>>({ academic_year: null, term: null, bell_schedule: null, time_slot: null });

watch(() => props.revision, (value) => { revision.value = value; });

const assignmentOptions = computed(() => {
  if (assignmentForm.value.entity_type === "homeroom") return homerooms.value;
  if (assignmentForm.value.entity_type === "teacher") return teachers.value;
  if (assignmentForm.value.entity_type === "subject") return subjects.value;
  if (assignmentForm.value.entity_type === "room") return rooms.value;
  if (assignmentForm.value.entity_type === "room_type") return roomTypes.value;
  return [];
});
const selectedSchedule = computed(() => schedules.value.find((item) => item.id === selectedScheduleId.value) ?? null);
const weekdayLabels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

function periodsForWeekday(day: number) {
  return slots.value.filter((item) => item.bell_schedule_id === selectedScheduleId.value && Number(item.weekday) === day).sort((left, right) => Number(left.period_index) - Number(right.period_index));
}

function selectSchedule(id: string) {
  const item = schedules.value.find((value) => value.id === id);
  if (!item) return;
  selectedScheduleId.value = id;
  editSchedule(item);
  slotForm.value.bell_schedule_id = id;
  slotEditorOpen.value = false;
}

function newSchedule() {
  editing.bell_schedule = null;
  selectedScheduleId.value = "";
  scheduleForm.value = { term_id: terms.value[0]?.id ?? "", name: "新课表模板", day_count: 5, slot_duration_minutes: 40, is_default: schedules.value.length ? 0 : 1 };
}

function addSlotForDay(day: number) {
  const periods = periodsForWeekday(day);
  const last = periods.at(-1);
  const start = last ? Number(last.end_time_minutes) : 8 * 60;
  openWeekday.value = day;
  editing.time_slot = null;
  slotEditorOpen.value = true;
  slotForm.value = { bell_schedule_id: selectedScheduleId.value, weekday: day, period_index: periods.length, label: `第${periods.length + 1}节`, start_time: clock(start), end_time: clock(start + Number(selectedSchedule.value?.slot_duration_minutes ?? 40)) };
}

function cancelSlotEdit() {
  editing.time_slot = null;
  slotEditorOpen.value = false;
}

function minutes(value: string) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

function clock(value: unknown) {
  const total = Number(value);
  const hour = Math.floor(total / 60).toString().padStart(2, "0");
  const minute = (total % 60).toString().padStart(2, "0");
  return `${hour}:${minute}`;
}

async function loadAll() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const results = await Promise.all([
      localApi.listEntities("academic_year"),
      localApi.listEntities("term"),
      localApi.listEntities("bell_schedule"),
      localApi.listEntities("time_slot"),
      localApi.listEntities("timetable_template_assignment"),
      localApi.listEntities("teacher"),
      localApi.listEntities("homeroom"),
      localApi.listEntities("subject"),
      localApi.listEntities("room"),
      localApi.listEntities("room_type"),
    ]);
    const [yearResult, termResult, scheduleResult, slotResult, assignmentResult, teacherResult, homeroomResult, subjectResult, roomResult, roomTypeResult] = results;
    years.value = yearResult.items;
    terms.value = termResult.items;
    schedules.value = scheduleResult.items;
    slots.value = slotResult.items;
    assignments.value = assignmentResult.items;
    teachers.value = teacherResult.items;
    homerooms.value = homeroomResult.items;
    subjects.value = subjectResult.items;
    rooms.value = roomResult.items;
    roomTypes.value = roomTypeResult.items;
    if (!editing.term && terms.value.length) editTerm(terms.value[0]);
    if (!selectedScheduleId.value && schedules.value.length) selectSchedule(schedules.value.find((item) => Number(item.is_default))?.id ?? schedules.value[0].id);
    revision.value = Math.max(...results.map((result) => result.revision));
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function save(entityType: string, data: Record<string, unknown>): Promise<boolean> {
  busy.value = true;
  errorMessage.value = "";
  try {
    const clean = Object.fromEntries(Object.entries(data).filter(([, value]) => value !== ""));
    const result = await localApi.saveEntity(entityType, clean, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    await loadAll();
    return true;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
    return false;
  } finally {
    busy.value = false;
  }
}

async function remove(entityType: string, item: EntityRecord) {
  if (!window.confirm(`确定删除“${String(item.name ?? item.label ?? item.id)}”吗？相关数据可能同时被删除。`)) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const result = await localApi.deleteEntity(entityType, item.id, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    if (entityType === "bell_schedule" && item.id === selectedScheduleId.value) selectedScheduleId.value = "";
    if (entityType === "time_slot" && item.id === editing.time_slot) slotEditorOpen.value = false;
    await loadAll();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function createYear() {
  if (await save("academic_year", { ...yearForm.value, ...(editing.academic_year ? { id: editing.academic_year } : {}) })) {
    yearForm.value = { name: "", start_date: "", end_date: "" };
    editing.academic_year = null;
  }
}

async function createTerm() {
  const savedName = termForm.value.name;
  if (await save("term", { ...termForm.value, active: 1, ...(editing.term ? { id: editing.term } : {}) })) {
    const saved = terms.value.find((item) => item.name === savedName);
    if (saved) editTerm(saved);
  }
}

async function createSchedule() {
  const savedName = scheduleForm.value.name;
  if (await save("bell_schedule", { ...scheduleForm.value, display_config: "{}", ...(editing.bell_schedule ? { id: editing.bell_schedule } : {}) })) {
    const saved = schedules.value.find((item) => item.name === savedName);
    if (saved) selectSchedule(saved.id);
  }
}

async function createSlot() {
  if (await save("time_slot", {
    bell_schedule_id: slotForm.value.bell_schedule_id,
    weekday: slotForm.value.weekday,
    period_index: slotForm.value.period_index,
    label: slotForm.value.label,
    start_slot: slotForm.value.period_index,
    length_slots: 1,
    start_time_minutes: minutes(slotForm.value.start_time),
    end_time_minutes: minutes(slotForm.value.end_time),
    active: 1,
    display_config: "{}",
    ...(editing.time_slot ? { id: editing.time_slot } : {}),
  })) {
    editing.time_slot = null;
    slotEditorOpen.value = false;
    slotForm.value.period_index += 1;
    slotForm.value.label = `第${slotForm.value.period_index + 1}节`;
  }
}

async function saveAssignment() {
  const entityType = assignmentForm.value.entity_type;
  const entityId = entityType === "all" ? null : assignmentForm.value.entity_id;
  const existing = assignments.value.find((item) => item.entity_type === entityType && String(item.entity_id ?? "") === String(entityId ?? ""));
  if (await save("timetable_template_assignment", {
    ...(existing ? { id: existing.id } : {}),
    entity_type: entityType,
    entity_id: entityId,
    bell_schedule_id: assignmentForm.value.bell_schedule_id,
  })) {
    assignmentForm.value.entity_id = "";
  }
}

function assignmentEntityName(item: EntityRecord) {
  if (item.entity_type === "all") return "全部未单独分配的课程";
  const collections: Record<string, EntityRecord[]> = { homeroom: homerooms.value, teacher: teachers.value, subject: subjects.value, room: rooms.value, room_type: roomTypes.value };
  return String(collections[String(item.entity_type)]?.find((value) => value.id === item.entity_id)?.name ?? "未知对象");
}

function scheduleName(id: unknown) {
  return String(schedules.value.find((item) => item.id === id)?.name ?? "未知作息表");
}

function editYear(item: EntityRecord) {
  yearForm.value = { name: String(item.name), start_date: String(item.start_date ?? ""), end_date: String(item.end_date ?? "") };
  editing.academic_year = item.id;
}

function editTerm(item: EntityRecord) {
  termForm.value = { academic_year_id: String(item.academic_year_id ?? ""), name: String(item.name), start_date: String(item.start_date ?? ""), end_date: String(item.end_date ?? ""), week_count: Number(item.week_count), day_count: Number(item.day_count) };
  editing.term = item.id;
}

function editSchedule(item: EntityRecord) {
  scheduleForm.value = { term_id: String(item.term_id ?? ""), name: String(item.name), day_count: Number(item.day_count), slot_duration_minutes: Number(item.slot_duration_minutes), is_default: Number(item.is_default) };
  editing.bell_schedule = item.id;
  selectedScheduleId.value = item.id;
}

function editSlot(item: EntityRecord) {
  slotForm.value = { bell_schedule_id: String(item.bell_schedule_id), weekday: Number(item.weekday), period_index: Number(item.period_index), label: String(item.label), start_time: clock(item.start_time_minutes), end_time: clock(item.end_time_minutes) };
  editing.time_slot = item.id;
  slotEditorOpen.value = true;
  openWeekday.value = Number(item.weekday);
}

onMounted(loadAll);
</script>

<template>
  <section class="module-view master-data-panel">
    <header class="section-heading timetable-section-heading"><div><h2 title="设置学期范围、课次规划和候选课表导出样式">课表设置</h2></div><div class="master-summary"><label class="term-summary-editor"><span>学期周数</span><input v-model.number="termForm.week_count" type="number" min="1" max="60" /><em>周</em></label><span>每周 7 天</span><span>模板 {{ schedules.length }}</span><span>节次 {{ slots.length }}</span></div></header>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <div class="timetable-settings-layout">
      <div class="template-editor settings-card">
        <div class="settings-editor-header"><div><h3 title="课次规划会用于课程计划、排课运行和课表导出">周课程表模板</h3></div><div class="template-actions"><button class="secondary-button" @click="newSchedule">新建</button><button v-if="selectedSchedule" class="secondary-button danger-button" :disabled="busy" @click="remove('bell_schedule', selectedSchedule)">删除当前模板</button><button class="primary-button" :disabled="busy" @click="createSchedule">保存</button></div></div>
        <div v-if="schedules.length" class="template-project-list"><div class="template-project-list-heading"><strong>本项目模板</strong><span>{{ schedules.length }} 个模板</span></div><div class="project-template-stack"><button v-for="item in schedules" :key="item.id" class="project-template-card" :class="{ active: selectedScheduleId === item.id, 'is-default': item.is_default }" @click="selectSchedule(item.id)"><span class="project-template-marker">{{ item.is_default ? '默' : '模' }}</span><span class="project-template-copy"><strong>{{ item.name }}</strong><small>{{ item.is_default ? '项目默认模板' : '普通模板' }}</small></span><span>{{ selectedScheduleId === item.id ? '当前编辑' : '打开编辑' }}</span></button></div></div>
        <div v-if="!schedules.length && !editing.bell_schedule" class="template-empty-state"><strong>暂无课表模板</strong><button class="primary-button" @click="newSchedule">新建第一个模板</button></div>
        <form v-if="editing.bell_schedule || !schedules.length || scheduleForm.name" class="template-form" @submit.prevent="createSchedule"><label>模板名称<input v-model="scheduleForm.name" placeholder="默认周课程表" required /></label><div class="template-form-options"><label class="check-label"><input v-model="scheduleForm.is_default" type="checkbox" :true-value="1" :false-value="0" />设为默认模板</label></div></form>

        <div v-if="selectedSchedule" class="weekday-visibility-strip" aria-label="选择周课程表显示的星期"><button v-for="(label, index) in weekdayLabels" :key="label" :class="{ active: periodsForWeekday(index + 1).length }" @click="openWeekday = index + 1">{{ label }}</button></div>
        <div v-if="selectedSchedule" class="weekday-drawers"><section v-for="(label, index) in weekdayLabels" :key="label" class="weekday-drawer" :class="{ open: openWeekday === index + 1 }"><button class="weekday-drawer-header" @click="openWeekday = openWeekday === index + 1 ? 0 : index + 1"><span>{{ label }}</span><small>{{ periodsForWeekday(index + 1).length }} 节</small><strong>{{ openWeekday === index + 1 ? '收起' : '展开' }}</strong></button><div v-if="openWeekday === index + 1" class="weekday-drawer-body"><div class="weekday-period-list"><div v-for="period in periodsForWeekday(index + 1)" :key="period.id" class="weekday-period-row"><strong>{{ period.label }}</strong><span>{{ clock(period.start_time_minutes) }}</span><span>{{ clock(period.end_time_minutes) }}</span><button class="secondary-button" @click="editSlot(period)">编辑</button><button class="danger-button" @click="remove('time_slot', period)">删除</button></div></div><button class="secondary-button" @click="addSlotForDay(index + 1)">新增{{ label }}节次</button></div></section></div>

        <form v-if="selectedSchedule && slotEditorOpen" class="period-inline-editor" @submit.prevent="createSlot"><strong>{{ editing.time_slot ? '编辑课次' : '新增课次' }}</strong><input v-model="slotForm.label" placeholder="课次名称" required /><input v-model="slotForm.start_time" type="time" required /><input v-model="slotForm.end_time" type="time" required /><button class="primary-button" :disabled="busy">保存课次</button><button type="button" class="secondary-button" @click="cancelSlotEdit">取消</button></form>
      </div>

      <aside class="timetable-side-settings">
        <article class="settings-card"><div class="settings-editor-header"><div><h3>学期设置</h3><p>设置当前项目使用的学期和周数。</p></div></div><form class="detail-form" @submit.prevent="createTerm"><label>学期名称<input v-model="termForm.name" placeholder="第一学期" required /></label><label>学期周数<input v-model.number="termForm.week_count" type="number" min="1" max="60" /></label><button class="primary-button" :disabled="busy">保存学期设置</button></form><div class="compact-record-list"><button v-for="item in terms" :key="item.id" @click="editTerm(item)"><strong>{{ item.name }}</strong><span>{{ item.week_count }} 周</span></button></div></article>
        <details class="settings-card advanced-details"><summary>模板分配</summary><form class="detail-form" @submit.prevent="saveAssignment"><label>分配对象<select v-model="assignmentForm.entity_type" @change="assignmentForm.entity_id = ''"><option value="homeroom">班级</option><option value="teacher">教师</option><option value="subject">科目</option><option value="room">教室</option><option value="room_type">教室类型</option><option value="all">全部</option></select></label><label v-if="assignmentForm.entity_type !== 'all'">具体对象<select v-model="assignmentForm.entity_id" required><option value="" disabled>选择对象</option><option v-for="item in assignmentOptions" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>课表模板<select v-model="assignmentForm.bell_schedule_id" required><option value="" disabled>选择模板</option><option v-for="item in schedules" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><button class="primary-button">保存分配</button></form><div class="compact-record-list"><div v-for="item in assignments" :key="item.id"><span>{{ assignmentEntityName(item) }} · {{ scheduleName(item.bell_schedule_id) }}</span><button class="danger-button" @click="remove('timetable_template_assignment', item)">删除</button></div></div></details>
      </aside>
    </div>
  </section>
</template>
