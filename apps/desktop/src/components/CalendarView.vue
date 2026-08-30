<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { formatLocalError, localApi, type EntityRecord } from "../lib/sidecar";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();

const revision = ref(props.revision);
const years = ref<EntityRecord[]>([]);
const terms = ref<EntityRecord[]>([]);
const schedules = ref<EntityRecord[]>([]);
const slots = ref<EntityRecord[]>([]);
const busy = ref(false);
const errorMessage = ref("");

const yearForm = ref({ name: "", start_date: "", end_date: "" });
const termForm = ref({ academic_year_id: "", name: "", start_date: "", end_date: "", week_count: 20, day_count: 5 });
const scheduleForm = ref({ term_id: "", name: "", day_count: 5, slot_duration_minutes: 40, is_default: 1 });
const slotForm = ref({ bell_schedule_id: "", weekday: 1, period_index: 0, label: "第1节", start_time: "08:00", end_time: "08:40" });
const editing = reactive<Record<string, string | null>>({ academic_year: null, term: null, bell_schedule: null, time_slot: null });

watch(() => props.revision, (value) => { revision.value = value; });

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
    const [yearResult, termResult, scheduleResult, slotResult] = await Promise.all([
      localApi.listEntities("academic_year"),
      localApi.listEntities("term"),
      localApi.listEntities("bell_schedule"),
      localApi.listEntities("time_slot"),
    ]);
    years.value = yearResult.items;
    terms.value = termResult.items;
    schedules.value = scheduleResult.items;
    slots.value = slotResult.items;
    revision.value = Math.max(yearResult.revision, termResult.revision, scheduleResult.revision, slotResult.revision);
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
  if (await save("term", { ...termForm.value, active: 1, ...(editing.term ? { id: editing.term } : {}) })) {
    termForm.value = { academic_year_id: "", name: "", start_date: "", end_date: "", week_count: 20, day_count: 5 };
    editing.term = null;
  }
}

async function createSchedule() {
  if (await save("bell_schedule", { ...scheduleForm.value, display_config: "{}", ...(editing.bell_schedule ? { id: editing.bell_schedule } : {}) })) {
    scheduleForm.value = { term_id: "", name: "", day_count: 5, slot_duration_minutes: 40, is_default: 1 };
    editing.bell_schedule = null;
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
    slotForm.value.period_index += 1;
    slotForm.value.label = `第${slotForm.value.period_index + 1}节`;
  }
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
}

function editSlot(item: EntityRecord) {
  slotForm.value = { bell_schedule_id: String(item.bell_schedule_id), weekday: Number(item.weekday), period_index: Number(item.period_index), label: String(item.label), start_time: clock(item.start_time_minutes), end_time: clock(item.end_time_minutes) };
  editing.time_slot = item.id;
}

onMounted(loadAll);
</script>

<template>
  <section class="module-view">
    <div class="module-heading">
      <div><p class="eyebrow">ACADEMIC CALENDAR</p><h2>学期与作息</h2><p>依次建立学年、学期、作息表和每日课节。</p></div>
      <span>Revision {{ revision }}</span>
    </div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <div class="module-grid">
      <article class="panel data-panel">
        <h3>学年</h3>
        <form class="compact-form" @submit.prevent="createYear">
          <input v-model="yearForm.name" placeholder="如：2026-2027学年" required />
          <input v-model="yearForm.start_date" type="date" />
          <input v-model="yearForm.end_date" type="date" />
          <button class="primary-button" :disabled="busy">{{ editing.academic_year ? "更新学年" : "新增学年" }}</button>
        </form>
        <div class="data-list"><div v-for="item in years" :key="item.id" class="data-row"><span><strong>{{ item.name }}</strong><small>{{ item.start_date || "未设日期" }} 至 {{ item.end_date || "未设日期" }}</small></span><div class="row-actions"><button @click="editYear(item)">编辑</button><button class="danger-action" @click="remove('academic_year', item)">删除</button></div></div></div>
      </article>

      <article class="panel data-panel">
        <h3>学期</h3>
        <form class="compact-form" @submit.prevent="createTerm">
          <select v-model="termForm.academic_year_id"><option value="">不关联学年</option><option v-for="item in years" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <input v-model="termForm.name" placeholder="如：第一学期" required />
          <div class="inline-fields"><input v-model="termForm.start_date" type="date" /><input v-model="termForm.end_date" type="date" /></div>
          <div class="inline-fields"><label>周数<input v-model.number="termForm.week_count" type="number" min="1" max="60" /></label><label>上课日<input v-model.number="termForm.day_count" type="number" min="1" max="7" /></label></div>
          <button class="primary-button" :disabled="busy">{{ editing.term ? "更新学期" : "新增学期" }}</button>
        </form>
        <div class="data-list"><div v-for="item in terms" :key="item.id" class="data-row"><span><strong>{{ item.name }}</strong><small>{{ item.week_count }} 周 · 每周 {{ item.day_count }} 天</small></span><div class="row-actions"><button @click="editTerm(item)">编辑</button><button class="danger-action" @click="remove('term', item)">删除</button></div></div></div>
      </article>

      <article class="panel data-panel">
        <h3>作息表</h3>
        <form class="compact-form" @submit.prevent="createSchedule">
          <select v-model="scheduleForm.term_id"><option value="">不关联学期</option><option v-for="item in terms" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <input v-model="scheduleForm.name" placeholder="如：常规作息" required />
          <div class="inline-fields"><label>上课日<input v-model.number="scheduleForm.day_count" type="number" min="1" max="7" /></label><label>基础分钟<input v-model.number="scheduleForm.slot_duration_minutes" type="number" min="5" max="240" /></label></div>
          <button class="primary-button" :disabled="busy">{{ editing.bell_schedule ? "更新作息表" : "新增作息表" }}</button>
        </form>
        <div class="data-list"><div v-for="item in schedules" :key="item.id" class="data-row"><span><strong>{{ item.name }}</strong><small>{{ item.day_count }} 天 · {{ item.slot_duration_minutes }} 分钟</small></span><div class="row-actions"><button @click="editSchedule(item)">编辑</button><button class="danger-action" @click="remove('bell_schedule', item)">删除</button></div></div></div>
      </article>

      <article class="panel data-panel">
        <h3>课节</h3>
        <form class="compact-form" @submit.prevent="createSlot">
          <select v-model="slotForm.bell_schedule_id" required><option value="" disabled>选择作息表</option><option v-for="item in schedules" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <div class="inline-fields"><label>星期<input v-model.number="slotForm.weekday" type="number" min="1" max="7" /></label><label>序号<input v-model.number="slotForm.period_index" type="number" min="0" /></label></div>
          <input v-model="slotForm.label" placeholder="课节名称" required />
          <div class="inline-fields"><input v-model="slotForm.start_time" type="time" required /><input v-model="slotForm.end_time" type="time" required /></div>
          <button class="primary-button" :disabled="busy">{{ editing.time_slot ? "更新课节" : "新增课节" }}</button>
        </form>
        <div class="data-list tall-list"><div v-for="item in slots" :key="item.id" class="data-row"><span><strong>周{{ item.weekday }} · {{ item.label }}</strong><small>{{ clock(item.start_time_minutes) }}–{{ clock(item.end_time_minutes) }}</small></span><div class="row-actions"><button @click="editSlot(item)">编辑</button><button class="danger-action" @click="remove('time_slot', item)">删除</button></div></div></div>
      </article>
    </div>
  </section>
</template>
