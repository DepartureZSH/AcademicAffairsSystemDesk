<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { formatLocalError, localApi, type EntityRecord } from "../lib/sidecar";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();

const revision = ref(props.revision);
const activeTab = ref<"constraints" | "availability">("constraints");
const editingId = ref<string | null>(null);
const busy = ref(false);
const errorMessage = ref("");
const constraints = ref<EntityRecord[]>([]);
const availability = ref<EntityRecord[]>([]);
const schedules = ref<EntityRecord[]>([]);
const slots = ref<EntityRecord[]>([]);
const teachers = ref<EntityRecord[]>([]);
const homerooms = ref<EntityRecord[]>([]);
const rooms = ref<EntityRecord[]>([]);
const lessons = ref<EntityRecord[]>([]);

const constraintForm = reactive({ type: "max_daily_lessons", name: "每日最大课时", severity: "soft", enabled: 1, weight: 100, parameters: '{"max":6}' });
const availabilityForm = reactive({ entity_type: "teacher", entity_id: "", bell_schedule_id: "", time_slot_id: "", week_bits: "11111111111111111111", day_bits: "11111", required: 0, penalty: 100, reason: "" });

watch(() => props.revision, (value) => { revision.value = value; });
watch(activeTab, () => { editingId.value = null; });

const entityOptions = computed(() => {
  if (availabilityForm.entity_type === "teacher") return teachers.value;
  if (availabilityForm.entity_type === "homeroom") return homerooms.value;
  if (availabilityForm.entity_type === "room") return rooms.value;
  return lessons.value.map((item) => ({ ...item, name: item.label || `课次 ${Number(item.lesson_index) + 1}` }));
});
const visibleSlots = computed(() => slots.value.filter((item) => !availabilityForm.bell_schedule_id || item.bell_schedule_id === availabilityForm.bell_schedule_id));
const activeRecords = computed(() => activeTab.value === "constraints" ? constraints.value : availability.value);

function label(items: EntityRecord[], id: unknown) {
  return items.find((item) => item.id === id)?.name ?? "未知记录";
}

function availabilityEntityName(item: EntityRecord) {
  if (item.entity_type === "teacher") return label(teachers.value, item.entity_id);
  if (item.entity_type === "homeroom") return label(homerooms.value, item.entity_id);
  if (item.entity_type === "room") return label(rooms.value, item.entity_id);
  return lessons.value.find((lesson) => lesson.id === item.entity_id)?.label ?? "课次";
}

async function loadAll() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const results = await Promise.all([
      localApi.listEntities("constraint"), localApi.listEntities("availability_rule"),
      localApi.listEntities("bell_schedule"), localApi.listEntities("time_slot"),
      localApi.listEntities("teacher"), localApi.listEntities("homeroom"),
      localApi.listEntities("room"), localApi.listEntities("task_lesson"),
    ]);
    [constraints.value, availability.value, schedules.value, slots.value, teachers.value, homerooms.value, rooms.value, lessons.value] = results.map((result) => result.items);
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

async function saveActive() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const type = activeTab.value === "constraints" ? "constraint" : "availability_rule";
    const source = activeTab.value === "constraints" ? constraintForm : availabilityForm;
    const data = clean({ ...source });
    if (editingId.value) data.id = editingId.value;
    const result = await localApi.saveEntity(type, data, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    editingId.value = null;
    resetForm();
    await loadAll();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

function resetForm() {
  if (activeTab.value === "constraints") Object.assign(constraintForm, { type: "max_daily_lessons", name: "每日最大课时", severity: "soft", enabled: 1, weight: 100, parameters: '{"max":6}' });
  else Object.assign(availabilityForm, { entity_type: "teacher", entity_id: "", bell_schedule_id: "", time_slot_id: "", week_bits: "11111111111111111111", day_bits: "11111", required: 0, penalty: 100, reason: "" });
}

function applyTemplate() {
  const templates: Record<string, [string, string]> = {
    max_daily_lessons: ["每日最大课时", '{"max":6}'],
    same_day_spacing: ["同科课次分散", '{"minimumGap":1}'],
    consecutive_limit: ["连续授课限制", '{"maxConsecutive":3}'],
    preferred_periods: ["优先时段", '{"periods":[0,1,2]}'],
  };
  const selected = templates[constraintForm.type];
  if (selected) [constraintForm.name, constraintForm.parameters] = selected;
}

function edit(item: EntityRecord) {
  editingId.value = item.id;
  const target = activeTab.value === "constraints" ? constraintForm : availabilityForm;
  for (const key of Object.keys(target)) {
    (target as Record<string, unknown>)[key] = item[key] ?? (target as Record<string, unknown>)[key];
  }
}

async function remove(item: EntityRecord) {
  const type = activeTab.value === "constraints" ? "constraint" : "availability_rule";
  if (!window.confirm("确定删除这条约束配置吗？")) return;
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
    <div class="module-heading"><div><p class="eyebrow">CONSTRAINTS</p><h2>约束配置</h2><p>资源冲突始终作为硬约束；这里配置偏好、上限和可用时段。</p></div><span>Revision {{ revision }}</span></div>
    <div class="invariant-banner"><strong>内置硬约束</strong><span>教师、班级、教室同一时段不可冲突；停用任务不参与排课；固定教室必须满足任务要求。</span></div>
    <div class="data-tabs"><button :class="{ active: activeTab === 'constraints' }" @click="activeTab = 'constraints'">规则约束 <small>{{ constraints.length }}</small></button><button :class="{ active: activeTab === 'availability' }" @click="activeTab = 'availability'">可用时段 <small>{{ availability.length }}</small></button></div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <div class="directory-layout planning-layout">
      <article class="panel data-panel">
        <p class="eyebrow">{{ editingId ? "EDIT" : "NEW" }}</p><h3>{{ activeTab === "constraints" ? "规则约束" : "可用时段" }}</h3>
        <form v-if="activeTab === 'constraints'" class="compact-form" @submit.prevent="saveActive">
          <select v-model="constraintForm.type" @change="applyTemplate"><option value="max_daily_lessons">每日最大课时</option><option value="same_day_spacing">同科课次分散</option><option value="consecutive_limit">连续授课限制</option><option value="preferred_periods">优先时段</option><option v-if="constraintForm.type === 'custom'" value="custom" disabled>旧版未编译自定义类型</option></select>
          <input v-model="constraintForm.name" placeholder="约束名称" required />
          <div class="inline-fields"><select v-model="constraintForm.severity"><option value="hard">硬约束</option><option value="soft">软约束</option></select><label>权重<input v-model.number="constraintForm.weight" type="number" min="0" /></label></div>
          <label>参数（JSON 对象）<textarea v-model="constraintForm.parameters" spellcheck="false"></textarea></label>
          <label class="check-label"><input v-model="constraintForm.enabled" type="checkbox" :true-value="1" :false-value="0" />启用</label>
          <p class="form-copy">这里列出的四类规则均进入本地求解或候选校验；不接受会被静默忽略的任意自定义类型。</p>
          <button class="primary-button" :disabled="busy">{{ editingId ? "更新约束" : "保存约束" }}</button>
        </form>
        <form v-else class="compact-form" @submit.prevent="saveActive">
          <select v-model="availabilityForm.entity_type" @change="availabilityForm.entity_id = ''"><option value="teacher">教师</option><option value="homeroom">班级</option><option value="room">教室</option><option value="lesson">课次</option></select>
          <select v-model="availabilityForm.entity_id" required><option value="" disabled>选择对象</option><option v-for="item in entityOptions" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <select v-model="availabilityForm.bell_schedule_id"><option value="">所有作息表</option><option v-for="item in schedules" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <select v-model="availabilityForm.time_slot_id"><option value="">所有课节</option><option v-for="item in visibleSlots" :key="item.id" :value="item.id">周{{ item.weekday }} · {{ item.label }}</option></select>
          <div class="inline-fields"><select v-model.number="availabilityForm.required"><option :value="1">必须可用</option><option :value="0">不可用/尽量避开</option></select><label>违约代价<input v-model.number="availabilityForm.penalty" type="number" min="0" /></label></div>
          <input v-model="availabilityForm.reason" placeholder="原因或备注" />
          <button class="primary-button" :disabled="busy">{{ editingId ? "更新时段规则" : "保存时段规则" }}</button>
        </form>
      </article>

      <article class="panel data-panel records-panel">
        <div class="panel-heading"><div><p class="eyebrow">LOCAL RULES</p><h3>{{ activeTab === "constraints" ? "规则约束" : "可用时段" }}列表</h3></div><span>{{ activeRecords.length }} 条</span></div>
        <p v-if="activeRecords.length === 0" class="empty-copy">还没有自定义配置，排课仍会执行内置资源冲突硬约束。</p>
        <div v-else class="data-list tall-list"><div v-for="item in activeRecords" :key="item.id" class="data-row"><span v-if="activeTab === 'constraints'"><strong>{{ item.name }}</strong><small>{{ item.severity === "hard" ? "硬约束" : "软约束" }} · 权重 {{ item.weight }} · {{ item.enabled ? "启用" : "停用" }}</small></span><span v-else><strong>{{ availabilityEntityName(item) }}</strong><small>{{ item.required ? "必须可用" : "不可用/避开" }} · 代价 {{ item.penalty }} · {{ item.reason || "无备注" }}</small></span><div class="row-actions"><button @click="edit(item)">编辑</button><button class="danger-action" @click="remove(item)">删除</button></div></div></div>
      </article>
    </div>
  </section>
</template>
