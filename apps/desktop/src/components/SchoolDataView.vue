<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { formatLocalError, localApi, type EntityRecord } from "../lib/sidecar";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();

const kinds = [
  { key: "grade", label: "年级" },
  { key: "teacher", label: "教师" },
  { key: "room_type", label: "教室类型" },
  { key: "room", label: "教室" },
  { key: "homeroom", label: "班级" },
  { key: "subject", label: "科目" },
] as const;

const activeType = ref<(typeof kinds)[number]["key"]>("teacher");
const editingId = ref<string | null>(null);
const revision = ref(props.revision);
const records = reactive<Record<string, EntityRecord[]>>({});
const terms = ref<EntityRecord[]>([]);
const busy = ref(false);
const errorMessage = ref("");

const forms = reactive({
  grade: { name: "", code: "", sort_order: 0 },
  teacher: { name: "", employee_no: "", department: "", status: "active" },
  room_type: { name: "", code: "", description: "" },
  room: { name: "", room_no: "", room_type_id: "", capacity: 0, status: "active" },
  homeroom: { name: "", grade_id: "", term_id: "", head_teacher_id: "", default_room_id: "", group_name: "", student_count: 0, status: "active" },
  subject: { name: "", code: "", category: "general", default_duration_slots: 1, requires_special_room: 0 },
});

watch(() => props.revision, (value) => { revision.value = value; });
watch(activeType, () => { editingId.value = null; });

const activeRecords = computed(() => records[activeType.value] ?? []);
const activeLabel = computed(() => kinds.find((kind) => kind.key === activeType.value)?.label ?? "资料");

function nameOf(type: string, id: unknown) {
  if (!id) return "未关联";
  return (records[type] ?? []).find((item) => item.id === id)?.name ?? "未知记录";
}

function subtitle(item: EntityRecord) {
  switch (activeType.value) {
    case "teacher": return [item.employee_no, item.department, item.status === "inactive" ? "停用" : "在用"].filter(Boolean).join(" · ");
    case "grade": return [item.code, `排序 ${item.sort_order}`].filter(Boolean).join(" · ");
    case "room_type": return String(item.code ?? item.description ?? "");
    case "room": return [item.room_no, nameOf("room_type", item.room_type_id), `容量 ${item.capacity ?? "未设"}`].filter(Boolean).join(" · ");
    case "homeroom": return [nameOf("grade", item.grade_id), nameOf("teacher", item.head_teacher_id), `${item.student_count ?? 0} 人`].join(" · ");
    case "subject": return [item.code, item.category, `默认 ${item.default_duration_slots} 课时`].filter(Boolean).join(" · ");
  }
}

async function loadAll() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const results = await Promise.all([
      ...kinds.map((kind) => localApi.listEntities(kind.key)),
      localApi.listEntities("term"),
    ]);
    kinds.forEach((kind, index) => { records[kind.key] = results[index].items; });
    terms.value = results[kinds.length].items;
    revision.value = Math.max(...results.map((result) => result.revision));
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

function cleanData(data: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(data).filter(([, value]) => value !== ""));
}

async function createActive() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const form = forms[activeType.value] as Record<string, unknown>;
    const data = cleanData(form);
    if (editingId.value) data.id = editingId.value;
    const result = await localApi.saveEntity(activeType.value, data, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    const name = String(form.name ?? "");
    Object.assign(form, emptyForm(activeType.value), { name: "" });
    editingId.value = null;
    if (name) await loadAll();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

function edit(item: EntityRecord) {
  const form = forms[activeType.value] as Record<string, unknown>;
  for (const key of Object.keys(form)) {
    form[key] = item[key] ?? emptyForm(activeType.value)[key] ?? "";
  }
  editingId.value = item.id;
}

function cancelEdit() {
  Object.assign(forms[activeType.value], emptyForm(activeType.value));
  editingId.value = null;
}

function emptyForm(type: string): Record<string, unknown> {
  switch (type) {
    case "grade": return { name: "", code: "", sort_order: 0 };
    case "teacher": return { name: "", employee_no: "", department: "", status: "active" };
    case "room_type": return { name: "", code: "", description: "" };
    case "room": return { name: "", room_no: "", room_type_id: "", capacity: 0, status: "active" };
    case "homeroom": return { name: "", grade_id: "", term_id: "", head_teacher_id: "", default_room_id: "", group_name: "", student_count: 0, status: "active" };
    default: return { name: "", code: "", category: "general", default_duration_slots: 1, requires_special_room: 0 };
  }
}

async function remove(item: EntityRecord) {
  if (!window.confirm(`确定删除“${String(item.name)}”吗？被课程计划引用的记录可能无法删除。`)) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const result = await localApi.deleteEntity(activeType.value, item.id, revision.value);
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
    <div class="module-heading">
      <div><p class="eyebrow">SCHOOL DIRECTORY</p><h2>基础资料</h2><p>所有教师、班级、科目和教室信息都写入当前本地项目。</p></div>
      <span>Revision {{ revision }}</span>
    </div>
    <div class="data-tabs" role="tablist">
      <button v-for="kind in kinds" :key="kind.key" :class="{ active: activeType === kind.key }" @click="activeType = kind.key">{{ kind.label }} <small>{{ records[kind.key]?.length ?? 0 }}</small></button>
    </div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <div class="directory-layout">
      <article class="panel data-panel">
        <p class="eyebrow">NEW RECORD</p><h3>新增{{ activeLabel }}</h3>
        <form class="compact-form" @submit.prevent="createActive">
          <template v-if="activeType === 'grade'">
            <input v-model="forms.grade.name" placeholder="年级名称" required /><input v-model="forms.grade.code" placeholder="代码（可选）" /><label>排序<input v-model.number="forms.grade.sort_order" type="number" /></label>
          </template>
          <template v-else-if="activeType === 'teacher'">
            <input v-model="forms.teacher.name" placeholder="教师姓名" required /><input v-model="forms.teacher.employee_no" placeholder="工号（可选）" /><input v-model="forms.teacher.department" placeholder="部门（可选）" /><select v-model="forms.teacher.status"><option value="active">在用</option><option value="inactive">停用</option></select>
          </template>
          <template v-else-if="activeType === 'room_type'">
            <input v-model="forms.room_type.name" placeholder="类型名称" required /><input v-model="forms.room_type.code" placeholder="代码（可选）" /><textarea v-model="forms.room_type.description" placeholder="说明（可选）"></textarea>
          </template>
          <template v-else-if="activeType === 'room'">
            <input v-model="forms.room.name" placeholder="教室名称" required /><input v-model="forms.room.room_no" placeholder="教室编号" /><select v-model="forms.room.room_type_id"><option value="">普通教室/未分类</option><option v-for="item in records.room_type" :key="item.id" :value="item.id">{{ item.name }}</option></select><label>容量<input v-model.number="forms.room.capacity" type="number" min="0" /></label><select v-model="forms.room.status"><option value="active">在用</option><option value="inactive">停用</option></select>
          </template>
          <template v-else-if="activeType === 'homeroom'">
            <input v-model="forms.homeroom.name" placeholder="班级名称" required /><select v-model="forms.homeroom.grade_id"><option value="">不关联年级</option><option v-for="item in records.grade" :key="item.id" :value="item.id">{{ item.name }}</option></select><select v-model="forms.homeroom.term_id"><option value="">不关联学期</option><option v-for="item in terms" :key="item.id" :value="item.id">{{ item.name }}</option></select><select v-model="forms.homeroom.head_teacher_id"><option value="">未指定班主任</option><option v-for="item in records.teacher" :key="item.id" :value="item.id">{{ item.name }}</option></select><select v-model="forms.homeroom.default_room_id"><option value="">未指定固定教室</option><option v-for="item in records.room" :key="item.id" :value="item.id">{{ item.name }}</option></select><div class="inline-fields"><input v-model="forms.homeroom.group_name" placeholder="分组（可选）" /><label>人数<input v-model.number="forms.homeroom.student_count" type="number" min="0" /></label></div>
          </template>
          <template v-else>
            <input v-model="forms.subject.name" placeholder="科目名称" required /><input v-model="forms.subject.code" placeholder="代码（可选）" /><input v-model="forms.subject.category" placeholder="类别" /><label>默认连续课时<input v-model.number="forms.subject.default_duration_slots" type="number" min="1" /></label><label class="check-label"><input v-model="forms.subject.requires_special_room" type="checkbox" :true-value="1" :false-value="0" />需要专用教室</label>
          </template>
          <button class="primary-button" :disabled="busy">{{ editingId ? `更新${activeLabel}` : `保存${activeLabel}` }}</button>
          <button v-if="editingId" type="button" class="secondary-button" @click="cancelEdit">取消编辑</button>
        </form>
      </article>

      <article class="panel data-panel records-panel">
        <div class="panel-heading"><div><p class="eyebrow">LOCAL RECORDS</p><h3>{{ activeLabel }}列表</h3></div><span>{{ activeRecords.length }} 条</span></div>
        <p v-if="activeRecords.length === 0" class="empty-copy">还没有{{ activeLabel }}记录。</p>
        <div v-else class="data-list tall-list"><div v-for="item in activeRecords" :key="item.id" class="data-row"><span><strong>{{ item.name }}</strong><small>{{ subtitle(item) || "本地记录" }}</small></span><div class="row-actions"><button @click="edit(item)">编辑</button><button class="danger-action" @click="remove(item)">删除</button></div></div></div>
      </article>
    </div>
  </section>
</template>
