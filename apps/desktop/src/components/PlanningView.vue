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

const planForm = reactive({ term_id: "", homeroom_id: "", subject_id: "", weekly_slots: 5, duration_slots: 1, allow_double_period: 0, priority: 0, week_bits: "11111111111111111111", day_bits: "11111" });
const taskForm = reactive({ term_id: "", course_plan_id: "", homeroom_id: "", subject_id: "", primary_teacher_id: "", weekly_slots: 5, duration_slots: 1, required_room_type: "", fixed_room_id: "", status: "active", week_bits: "11111111111111111111", day_bits: "11111" });

watch(() => props.revision, (value) => { revision.value = value; });
watch(activeTab, () => { editingId.value = null; });

const activeRecords = computed(() => activeTab.value === "plans" ? plans.value : tasks.value);

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
    editingId.value = null;
    Object.assign(taskForm, { term_id: "", course_plan_id: "", homeroom_id: "", subject_id: "", primary_teacher_id: "", weekly_slots: 5, duration_slots: 1, required_room_type: "", fixed_room_id: "", status: "active", week_bits: "11111111111111111111", day_bits: "11111" });
    await loadAll();
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

async function remove(item: EntityRecord) {
  const type = activeTab.value === "plans" ? "course_plan" : "teaching_task";
  if (!window.confirm(`确定删除这条${activeTab.value === "plans" ? "课程计划" : "教学任务"}吗？`)) return;
  busy.value = true;
  try {
    const result = await localApi.deleteEntity(type, item.id, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    await loadAll();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

onMounted(loadAll);
</script>

<template>
  <section class="module-view">
    <div class="module-heading"><div><p class="eyebrow">COURSE PLANNING</p><h2>课程计划与教学任务</h2><p>先定义班级周课时，再分配教师、教室并自动展开排课课次。</p></div><span>Revision {{ revision }}</span></div>
    <div class="data-tabs"><button :class="{ active: activeTab === 'plans' }" @click="activeTab = 'plans'">课程计划 <small>{{ plans.length }}</small></button><button :class="{ active: activeTab === 'tasks' }" @click="activeTab = 'tasks'">教学任务 <small>{{ tasks.length }}</small></button></div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <div class="directory-layout planning-layout">
      <article class="panel data-panel">
        <p class="eyebrow">{{ editingId ? "EDIT" : "NEW" }}</p><h3>{{ activeTab === "plans" ? "课程计划" : "教学任务" }}</h3>
        <form v-if="activeTab === 'plans'" class="compact-form" @submit.prevent="savePlan">
          <select v-model="planForm.term_id"><option value="">不限定学期</option><option v-for="item in terms" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <select v-model="planForm.homeroom_id" required><option value="" disabled>选择班级</option><option v-for="item in homerooms" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <select v-model="planForm.subject_id" required><option value="" disabled>选择科目</option><option v-for="item in subjects" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <div class="inline-fields"><label>每周课时<input v-model.number="planForm.weekly_slots" type="number" min="0" required /></label><label>连续课时<input v-model.number="planForm.duration_slots" type="number" min="1" required /></label></div>
          <div class="inline-fields"><label>优先级<input v-model.number="planForm.priority" type="number" /></label><label class="check-label"><input v-model="planForm.allow_double_period" type="checkbox" :true-value="1" :false-value="0" />允许连堂</label></div>
          <button class="primary-button" :disabled="busy">{{ editingId ? "更新计划" : "保存计划" }}</button><button v-if="editingId" type="button" class="secondary-button" @click="cancelEdit">取消编辑</button>
        </form>
        <form v-else class="compact-form" @submit.prevent="saveTask">
          <select v-model="taskForm.course_plan_id" @change="applyPlan"><option value="">不关联计划/手工填写</option><option v-for="item in plans" :key="item.id" :value="item.id">{{ label(homerooms, item.homeroom_id) }} · {{ label(subjects, item.subject_id) }}</option></select>
          <div class="inline-fields"><select v-model="taskForm.homeroom_id" required><option value="" disabled>选择班级</option><option v-for="item in homerooms" :key="item.id" :value="item.id">{{ item.name }}</option></select><select v-model="taskForm.subject_id" required><option value="" disabled>选择科目</option><option v-for="item in subjects" :key="item.id" :value="item.id">{{ item.name }}</option></select></div>
          <select v-model="taskForm.primary_teacher_id"><option value="">未分配教师</option><option v-for="item in teachers" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <div class="inline-fields"><label>每周课时<input v-model.number="taskForm.weekly_slots" type="number" min="0" required /></label><label>连续课时<input v-model.number="taskForm.duration_slots" type="number" min="1" required /></label></div>
          <div class="inline-fields"><select v-model="taskForm.required_room_type"><option value="">不限定教室类型</option><option v-for="item in roomTypes" :key="item.id" :value="item.id">{{ item.name }}</option></select><select v-model="taskForm.fixed_room_id"><option value="">不指定固定教室</option><option v-for="item in rooms" :key="item.id" :value="item.id">{{ item.name }}</option></select></div>
          <button class="primary-button" :disabled="busy">{{ editingId ? "更新任务并重建课次" : "保存任务并生成课次" }}</button><button v-if="editingId" type="button" class="secondary-button" @click="cancelEdit">取消编辑</button>
        </form>
      </article>

      <article class="panel data-panel records-panel">
        <div class="panel-heading"><div><p class="eyebrow">LOCAL RECORDS</p><h3>{{ activeTab === "plans" ? "课程计划" : "教学任务" }}列表</h3></div><span>{{ activeRecords.length }} 条</span></div>
        <p v-if="activeRecords.length === 0" class="empty-copy">当前项目还没有记录。请先在基础资料中准备班级和科目。</p>
        <div v-else class="data-list tall-list"><div v-for="item in activeRecords" :key="item.id" class="data-row"><span><strong>{{ label(homerooms, item.homeroom_id) }} · {{ label(subjects, item.subject_id) }}</strong><small v-if="activeTab === 'plans'">每周 {{ item.weekly_slots }} 课时 · 连续 {{ item.duration_slots }} · 优先级 {{ item.priority }}</small><small v-else>{{ label(teachers, item.primary_teacher_id) }} · {{ lessonCount(item.id) }} 个课次 · 每周 {{ item.weekly_slots }} 课时</small></span><div class="row-actions"><button @click="edit(item)">编辑</button><button class="danger-action" @click="remove(item)">删除</button></div></div></div>
      </article>
    </div>
  </section>
</template>
