<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { formatLocalError, localApi, type EntityRecord } from "../lib/sidecar";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();

const revision = ref(props.revision);
const activeTab = ref<"plans" | "tasks">("plans");
const editingId = ref<string | null>(null);
const busy = ref(false);
const errorMessage = ref("");
const plans = ref<EntityRecord[]>([]);
const tasks = ref<EntityRecord[]>([]);
const lessons = ref<EntityRecord[]>([]);
const terms = ref<EntityRecord[]>([]);
const homerooms = ref<EntityRecord[]>([]);
const subjects = ref<EntityRecord[]>([]);
const teachers = ref<EntityRecord[]>([]);
const rooms = ref<EntityRecord[]>([]);
const roomTypes = ref<EntityRecord[]>([]);
const selectedHomeroomId = ref("");
const selectedSubjectId = ref("");
const classSearch = ref("");
const editorOpen = ref(false);

const planForm = reactive({ term_id: "", homeroom_id: "", subject_id: "", weekly_slots: 5, duration_slots: 1, allow_double_period: 0, priority: 0, week_bits: "11111111111111111111", day_bits: "11111" });
const taskForm = reactive({ term_id: "", course_plan_id: "", homeroom_id: "", subject_id: "", primary_teacher_id: "", weekly_slots: 5, duration_slots: 1, required_room_type: "", fixed_room_id: "", status: "active", week_bits: "11111111111111111111", day_bits: "11111" });

watch(() => props.revision, (value) => { revision.value = value; });
watch(activeTab, () => { editingId.value = null; });

const activeRecords = computed(() => activeTab.value === "plans" ? plans.value : tasks.value);
const filteredHomerooms = computed(() => {
  const keyword = classSearch.value.trim().toLocaleLowerCase("zh-CN");
  return keyword ? homerooms.value.filter((item) => String(item.name).toLocaleLowerCase("zh-CN").includes(keyword)) : homerooms.value;
});
const selectedHomeroom = computed(() => homerooms.value.find((item) => item.id === selectedHomeroomId.value) ?? null);
const selectedSubject = computed(() => subjects.value.find((item) => item.id === selectedSubjectId.value) ?? null);
const selectedSubjectTasks = computed(() => tasks.value.filter((item) => item.homeroom_id === selectedHomeroomId.value && item.subject_id === selectedSubjectId.value));
const selectedTask = computed(() => selectedSubjectTasks.value.find((item) => item.id === editingId.value) ?? null);

function homeroomStatus(id: string) {
  const classTasks = tasks.value.filter((item) => item.homeroom_id === id && item.status !== "inactive");
  const configured = new Set(classTasks.map((item) => String(item.subject_id))).size;
  const total = Math.max(1, subjects.value.length);
  const progress = Math.round((configured / total) * 100);
  return { configured, lessons: classTasks.reduce((sum, item) => sum + lessonCount(item.id), 0), progress, complete: configured >= subjects.value.length && subjects.value.length > 0 };
}

function subjectTasks(subjectId: string) {
  return tasks.value.filter((item) => item.homeroom_id === selectedHomeroomId.value && item.subject_id === subjectId);
}

function selectHomeroom(id: string) {
  selectedHomeroomId.value = id;
  selectedSubjectId.value = "";
  editorOpen.value = false;
}

function openSubject(id: string) {
  selectedSubjectId.value = id;
  activeTab.value = "tasks";
  const existing = subjectTasks(id)[0];
  if (existing) edit(existing);
  else {
    editingId.value = null;
    Object.assign(taskForm, { term_id: terms.value[0]?.id ?? "", course_plan_id: "", homeroom_id: selectedHomeroomId.value, subject_id: id, primary_teacher_id: "", weekly_slots: 5, duration_slots: Number(subjects.value.find((item) => item.id === id)?.default_duration_slots ?? 1), required_room_type: "", fixed_room_id: "", status: "active", week_bits: "11111111111111111111", day_bits: "11111" });
  }
  editorOpen.value = true;
}

function newTeacherTask() {
  if (!selectedSubjectId.value) return;
  editingId.value = null;
  Object.assign(taskForm, { term_id: terms.value[0]?.id ?? "", course_plan_id: "", homeroom_id: selectedHomeroomId.value, subject_id: selectedSubjectId.value, primary_teacher_id: "", weekly_slots: Number(selectedSubjectTasks.value[0]?.weekly_slots ?? 5), duration_slots: Number(selectedSubjectTasks.value[0]?.duration_slots ?? selectedSubject.value?.default_duration_slots ?? 1), required_room_type: "", fixed_room_id: "", status: "active", week_bits: "11111111111111111111", day_bits: "11111" });
}

function label(items: EntityRecord[], id: unknown) {
  return items.find((item) => item.id === id)?.name ?? "未指定";
}

function lessonCount(taskId: string) {
  return lessons.value.filter((item) => item.teaching_task_id === taskId).length;
}

async function loadAll() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const results = await Promise.all([
      localApi.listEntities("course_plan"), localApi.listEntities("teaching_task"),
      localApi.listEntities("task_lesson"), localApi.listEntities("term"),
      localApi.listEntities("homeroom"), localApi.listEntities("subject"),
      localApi.listEntities("teacher"), localApi.listEntities("room"),
      localApi.listEntities("room_type"),
    ]);
    [plans.value, tasks.value, lessons.value, terms.value, homerooms.value, subjects.value, teachers.value, rooms.value, roomTypes.value] = results.map((result) => result.items);
    if (!selectedHomeroomId.value && homerooms.value.length) selectedHomeroomId.value = homerooms.value[0].id;
    revision.value = Math.max(...results.map((result) => result.revision));
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

function clean(data: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(data).filter(([, value]) => value !== ""));
}

async function savePlan() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const data = clean({ ...planForm });
    if (editingId.value) data.id = editingId.value;
    const result = await localApi.saveEntity("course_plan", data, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    editingId.value = null;
    Object.assign(planForm, { term_id: "", homeroom_id: "", subject_id: "", weekly_slots: 5, duration_slots: 1, allow_double_period: 0, priority: 0, week_bits: "11111111111111111111", day_bits: "11111" });
    await loadAll();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function saveTask() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const data = clean({ ...taskForm });
    if (editingId.value) data.id = editingId.value;
    const result = await localApi.saveTeachingTask(data, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    const savedSubjectId = String(taskForm.subject_id);
    editingId.value = null;
    Object.assign(taskForm, { term_id: "", course_plan_id: "", homeroom_id: "", subject_id: "", primary_teacher_id: "", weekly_slots: 5, duration_slots: 1, required_room_type: "", fixed_room_id: "", status: "active", week_bits: "11111111111111111111", day_bits: "11111" });
    await loadAll();
    if (savedSubjectId) openSubject(savedSubjectId);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

function applyPlan() {
  const plan = plans.value.find((item) => item.id === taskForm.course_plan_id);
  if (!plan) return;
  taskForm.term_id = String(plan.term_id ?? "");
  taskForm.homeroom_id = String(plan.homeroom_id);
  taskForm.subject_id = String(plan.subject_id);
  taskForm.weekly_slots = Number(plan.weekly_slots);
  taskForm.duration_slots = Number(plan.duration_slots);
  taskForm.week_bits = String(plan.week_bits);
  taskForm.day_bits = String(plan.day_bits);
}

function edit(item: EntityRecord) {
  editingId.value = item.id;
  const target = activeTab.value === "plans" ? planForm : taskForm;
  for (const key of Object.keys(target)) {
    (target as Record<string, unknown>)[key] = item[key] ?? (target as Record<string, unknown>)[key];
  }
}

function cancelEdit() {
  editingId.value = null;
  if (activeTab.value === "plans") Object.assign(planForm, { term_id: "", homeroom_id: "", subject_id: "", weekly_slots: 5, duration_slots: 1, allow_double_period: 0, priority: 0, week_bits: "11111111111111111111", day_bits: "11111" });
  else Object.assign(taskForm, { term_id: "", course_plan_id: "", homeroom_id: "", subject_id: "", primary_teacher_id: "", weekly_slots: 5, duration_slots: 1, required_room_type: "", fixed_room_id: "", status: "active", week_bits: "11111111111111111111", day_bits: "11111" });
}

function closeEditor() {
  cancelEdit();
  editorOpen.value = false;
}

async function remove(item: EntityRecord) {
  const type = activeTab.value === "plans" ? "course_plan" : "teaching_task";
  if (!window.confirm(`确定删除这条${activeTab.value === "plans" ? "课程计划" : "教学任务"}吗？`)) return;
  busy.value = true;
  try {
    const result = await localApi.deleteEntity(type, item.id, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    await loadAll();
    if (activeTab.value === "tasks" && selectedSubjectId.value) openSubject(selectedSubjectId.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

onMounted(loadAll);
</script>

<template>
  <section class="module-view planning-panel planning-guided-page">
    <section class="official-class-flow">
      <header><div><span class="official-flow-badge">官方建议流程</span><h3>先完整配置一个示范班级</h3><p>请逐科完成课次、教师和教室。全部通过检查后，再配置其他班级。</p></div><div class="class-flow-progress"><strong>{{ selectedHomeroom ? homeroomStatus(selectedHomeroom.id).progress : 0 }}%</strong><span>配置完整度</span></div></header>
      <div class="official-flow-steps"><div class="active"><span>1</span><div><strong>完整示范班级</strong><small>逐科配置全部信息</small></div></div><div><span>2</span><div><strong>复制同类班级</strong><small>继承课次设置</small></div></div><div><span>3</span><div><strong>补充差异信息</strong><small>教师、教室及差异项</small></div></div></div>
    </section>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <div class="planning-class-workbench">
      <aside class="planning-class-panel"><div class="table-title"><div><h3>行政班</h3><span>先选择要配置的班级</span></div></div><label class="planning-class-search"><input v-model="classSearch" type="search" placeholder="搜索行政班" /></label><div class="class-list">
        <button v-for="homeroom in filteredHomerooms" :key="homeroom.id" class="class-list-item" :class="{ active: selectedHomeroomId === homeroom.id, complete: homeroomStatus(homeroom.id).complete, attention: !homeroomStatus(homeroom.id).complete }" @click="selectHomeroom(homeroom.id)"><div class="class-list-item-heading"><strong>{{ homeroom.name }}</strong><em>{{ homeroomStatus(homeroom.id).lessons }} 课次</em></div><span>{{ homeroomStatus(homeroom.id).configured }} / {{ subjects.length }} 门科目已配置</span><div class="class-card-progress"><progress :value="homeroomStatus(homeroom.id).progress" max="100"></progress><span>{{ homeroomStatus(homeroom.id).progress }}%</span></div><div class="class-card-footer"><span>{{ homeroomStatus(homeroom.id).complete ? '配置完整' : '待完善' }}</span><b>›</b></div></button>
        <p v-if="!filteredHomerooms.length" class="class-list-empty">没有匹配的行政班</p>
      </div></aside>

      <article class="subject-plan-panel"><div class="table-title"><div><h3>{{ selectedHomeroom?.name || '科目' }}</h3><span>选择要配置的科目</span></div></div><div class="subject-plan-list">
        <button v-for="subject in subjects" :key="subject.id" class="subject-plan-row" :class="{ configured: subjectTasks(subject.id).length, active: selectedSubjectId === subject.id }" @click="openSubject(subject.id)"><div><strong>{{ subject.name }}</strong><span>{{ subjectTasks(subject.id).length ? subjectTasks(subject.id).map((task) => label(teachers, task.primary_teacher_id)).join('、') : '未指定教师' }}</span></div><em>{{ subjectTasks(subject.id).reduce((sum, task) => sum + lessonCount(task.id), 0) }} 课次</em><small>{{ subjectTasks(subject.id).length ? '已配置' : '待完善' }}</small></button>
        <p v-if="!subjects.length" class="class-list-empty">请先在学校数据中添加科目</p>
      </div></article>

      <aside class="plan-detail-panel"><div v-if="selectedSubject" class="task-editor-heading"><div><h3>{{ selectedSubject.name }}</h3><span>{{ selectedHomeroom?.name }}</span></div><button class="secondary-button" @click="newTeacherTask">＋ 新增授课老师</button></div><p v-else class="preview-empty">从中间选择一个科目开始配置</p>
        <template v-if="selectedSubject"><div class="task-switcher"><button v-for="task in selectedSubjectTasks" :key="task.id" class="task-switcher-item" :class="{ active: editingId === task.id }" @click="edit(task)"><strong>{{ label(teachers, task.primary_teacher_id) }}</strong><span>{{ lessonCount(task.id) }} 个课次</span></button></div>
        <form class="detail-form" @submit.prevent="saveTask"><label>教师<select v-model="taskForm.primary_teacher_id"><option value="">未指定教师</option><option v-for="item in teachers" :key="item.id" :value="item.id">{{ item.name }}{{ item.department ? ` · ${item.department}` : '' }}</option></select></label><div class="inline-fields"><label>每周课时<input v-model.number="taskForm.weekly_slots" type="number" min="0" required /></label><label>连续课时<input v-model.number="taskForm.duration_slots" type="number" min="1" required /></label></div><label>教室类型<select v-model="taskForm.required_room_type"><option value="">不限定教室类型</option><option v-for="item in roomTypes" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>默认教室<select v-model="taskForm.fixed_room_id"><option value="">不指定固定教室</option><option v-for="item in rooms" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><div class="lesson-summary-card"><div><strong>课次</strong><span>{{ taskForm.weekly_slots }} 个课次 · 保存后自动生成</span></div></div><button class="primary-button plan-save-button" :disabled="busy">{{ editingId ? '保存授课任务' : '新增授课任务' }}</button><button v-if="editingId && selectedTask" type="button" class="danger-button" @click="remove(selectedTask)">删除任务</button></form></template>
      </aside>
    </div>
  </section>
</template>
