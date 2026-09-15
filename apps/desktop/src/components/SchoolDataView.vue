<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { formatLocalError, localApi, type EntityRecord } from "../lib/sidecar";
import "../ledger.css";

const props = withDefaults(defineProps<{ revision: number; mode?: "school" | "rooms" }>(), { mode: "school" });
const emit = defineEmits<{ revision: [value: number] }>();

const kinds = [
  { key: "grade", label: "年级" },
  { key: "teacher", label: "教师" },
  { key: "room_type", label: "教室类型" },
  { key: "room", label: "教室" },
  { key: "homeroom", label: "班级" },
  { key: "subject", label: "科目" },
] as const;

const activeType = ref<(typeof kinds)[number]["key"]>(props.mode === "rooms" ? "room" : "teacher");
const editingId = ref<string | null>(null);
const revision = ref(props.revision);
const records = reactive<Record<string, EntityRecord[]>>({});
const terms = ref<EntityRecord[]>([]);
const busy = ref(false);
const errorMessage = ref("");
const page = ref(1);
const pageRecords = ref<EntityRecord[]>([]);
const totals = reactive<Record<string, number>>({});
const search = ref("");
const dialogOpen = ref(false);
const selectedRecord = ref<EntityRecord | null>(null);
const exportTemplateId = ref("");
const templates = ref<EntityRecord[]>([]);
const templateAssignments = ref<EntityRecord[]>([]);
const PAGE_SIZE = 50;
const LOOKUP_LIMIT = 500;

const forms = reactive({
  grade: { name: "", code: "", sort_order: 0 },
  teacher: { name: "", department: "", status: "active" },
  room_type: { name: "", code: "", description: "" },
  room: { name: "", room_no: "", room_type_id: "", capacity: 0, status: "active" },
  homeroom: { name: "", grade_id: "", term_id: "", head_teacher_id: "", default_room_id: "", group_name: "", student_count: 0, status: "active" },
  subject: { name: "", code: "", category: "general", default_duration_slots: 1, default_duration_minutes: 40, requires_special_room: 0 },
});

watch(() => props.revision, (value) => { revision.value = value; });
watch(() => props.mode, (mode) => {
  activeType.value = mode === "rooms" ? "room" : "teacher";
});
watch(activeType, () => {
  editingId.value = null;
  selectedRecord.value = null;
  dialogOpen.value = false;
  search.value = "";
  page.value = 1;
  void loadPage();
});

const activeRecords = computed(() => {
  const keyword = search.value.trim().toLocaleLowerCase("zh-CN");
  if (!keyword) return pageRecords.value;
  return pageRecords.value.filter((item) => Object.values(item).some((value) => String(value ?? "").toLocaleLowerCase("zh-CN").includes(keyword)));
});
const visibleKinds = computed(() => props.mode === "rooms"
  ? kinds.filter((kind) => kind.key === "room_type" || kind.key === "room")
  : kinds.filter((kind) => kind.key === "teacher" || kind.key === "homeroom" || kind.key === "subject"));
const activeLabel = computed(() => kinds.find((kind) => kind.key === activeType.value)?.label ?? "资料");
const intro = computed(() => props.mode === "rooms" ? "维护教室类型和教室容量。" : "维护教师、班级和科目，供课程计划与排课使用。");
const totalPages = computed(() => Math.max(1, Math.ceil((totals[activeType.value] ?? 0) / PAGE_SIZE)));
const hasExportTemplate = computed(() => ["teacher", "homeroom", "room_type"].includes(activeType.value));
const normalTemplates = computed(() => templates.value.filter((item) => {
  try { return JSON.parse(String(item.display_config || "{}"))._web_template?.template_kind !== "special"; }
  catch { return false; }
}));
const defaultTemplate = computed(() => normalTemplates.value.find((item) => Number(item.is_default) === 1) ?? normalTemplates.value[0]);

function assignedTemplateId(type: string, id: string) {
  return String(templateAssignments.value.find((item) => item.entity_type === type && item.entity_id === id)?.bell_schedule_id ?? "");
}

function inheritedTemplate(type: string, roomTypeId?: unknown) {
  if (type === "room" && roomTypeId) {
    const inherited = templates.value.find((item) => item.id === assignedTemplateId("room_type", String(roomTypeId)));
    if (inherited) return `${String(inherited.name)}（沿用教室类型）`;
  }
  return defaultTemplate.value ? `${String(defaultTemplate.value.name)}（项目默认）` : "未设置，请先在课表设置中新建模板";
}

function templateName(item: EntityRecord) {
  const assigned = templates.value.find((template) => template.id === assignedTemplateId(activeType.value, item.id));
  return assigned ? String(assigned.name) : inheritedTemplate(activeType.value, item.room_type_id);
}

async function loadTemplateLookup(type: string) {
  const items: EntityRecord[] = [];
  let result;
  do {
    result = await localApi.listEntities(type, { limit: LOOKUP_LIMIT, offset: items.length });
    items.push(...result.items);
  } while (result.items.length === LOOKUP_LIMIT && items.length < (result.total ?? Infinity));
  return { items, total: result.total ?? items.length, revision: result.revision };
}

function nameOf(type: string, id: unknown) {
  if (!id) return "未指定";
  return (records[type] ?? []).find((item) => item.id === id)?.name ?? "未知记录";
}

const numberFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
function formatCount(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? numberFormatter.format(number) : "—";
}

function groupTags(value: unknown) {
  return [...new Set(String(value ?? "").split(/[,，、;；\n]+/).map((tag) => tag.trim()).filter(Boolean))];
}

function subtitle(item: EntityRecord) {
  switch (activeType.value) {
    case "teacher": return String(item.department || "未分组");
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
      ...kinds.map((kind) => localApi.listEntities(kind.key, { limit: LOOKUP_LIMIT })),
      localApi.listEntities("term", { limit: LOOKUP_LIMIT }),
      loadTemplateLookup("bell_schedule"),
      loadTemplateLookup("timetable_template_assignment"),
    ]);
    kinds.forEach((kind, index) => {
      records[kind.key] = results[index].items;
      totals[kind.key] = results[index].total ?? results[index].items.length;
    });
    terms.value = results[kinds.length].items;
    templates.value = results[kinds.length + 1].items;
    templateAssignments.value = results[kinds.length + 2].items;
    revision.value = Math.max(...results.map((result) => result.revision));
    emit("revision", revision.value);
    if (page.value > totalPages.value) page.value = totalPages.value;
    await loadPage(false);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function loadPage(manageBusy = true) {
  if (manageBusy) busy.value = true;
  errorMessage.value = "";
  const requestedType = activeType.value;
  try {
    const result = await localApi.listEntities(requestedType, {
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    });
    if (requestedType !== activeType.value) return;
    pageRecords.value = result.items;
    totals[requestedType] = result.total ?? result.items.length;
    revision.value = Math.max(revision.value, result.revision);
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    if (manageBusy) busy.value = false;
  }
}

async function changePage(nextPage: number) {
  page.value = Math.min(Math.max(1, nextPage), totalPages.value);
  editingId.value = null;
  await loadPage();
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
    if (hasExportTemplate.value) data.export_template_id = exportTemplateId.value || null;
    if (editingId.value) data.id = editingId.value;
    const result = await localApi.saveEntity(activeType.value, data, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    const name = String(form.name ?? "");
    Object.assign(form, emptyForm(activeType.value), { name: "" });
    editingId.value = null;
    dialogOpen.value = false;
    selectedRecord.value = null;
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
  exportTemplateId.value = assignedTemplateId(activeType.value, item.id);
  selectedRecord.value = item;
  dialogOpen.value = true;
}

function cancelEdit() {
  Object.assign(forms[activeType.value], emptyForm(activeType.value));
  editingId.value = null;
  selectedRecord.value = null;
  dialogOpen.value = false;
}

function createNew() {
  Object.assign(forms[activeType.value], emptyForm(activeType.value));
  editingId.value = null;
  selectedRecord.value = null;
  exportTemplateId.value = "";
  dialogOpen.value = true;
}

function emptyForm(type: string): Record<string, unknown> {
  switch (type) {
    case "grade": return { name: "", code: "", sort_order: 0 };
    case "teacher": return { name: "", department: "", status: "active" };
    case "room_type": return { name: "", code: "", description: "" };
    case "room": return { name: "", room_no: "", room_type_id: "", capacity: 0, status: "active" };
    case "homeroom": return { name: "", grade_id: "", term_id: "", head_teacher_id: "", default_room_id: "", group_name: "", student_count: 0, status: "active" };
    default: return { name: "", code: "", category: "general", default_duration_slots: 1, default_duration_minutes: 40, requires_special_room: 0 };
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
    selectedRecord.value = null;
    dialogOpen.value = false;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

onMounted(loadAll);
</script>

<template>
  <section class="module-view master-data-panel ledger-page">
    <header class="section-heading school-data-heading">
      <h2>{{ mode === "rooms" ? "教室设置" : "学校数据维护" }}</h2>
      <dl class="school-data-totals">
        <template v-if="mode === 'rooms'">
          <div><dt>教室类型</dt><dd>{{ totals.room_type ?? 0 }}</dd></div><div><dt>教室</dt><dd>{{ totals.room ?? 0 }}</dd></div>
        </template>
        <template v-else>
          <div><dt>教师</dt><dd>{{ totals.teacher ?? 0 }}</dd></div><div><dt>班级</dt><dd>{{ totals.homeroom ?? 0 }}</dd></div><div><dt>科目</dt><dd>{{ totals.subject ?? 0 }}</dd></div>
        </template>
      </dl>
      <p>{{ intro }}</p>
    </header>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <div class="data-workbench">
      <aside class="subnav">
        <button v-for="kind in visibleKinds" :key="kind.key" :class="{ active: activeType === kind.key }" @click="activeType = kind.key">
          <div><strong>{{ kind.label }}</strong><span>{{ kind.key === 'teacher' ? '教师姓名与分组' : kind.key === 'homeroom' ? '班级、人数与班主任' : kind.key === 'subject' ? '科目与默认课长' : kind.key === 'room' ? '教室、类型与容量' : '教室分类说明' }}</span></div>
          <em>{{ totals[kind.key] ?? 0 }}</em>
        </button>
      </aside>

      <article class="data-table-panel">
        <div class="table-title data-table-title"><div><h3>{{ activeLabel }}台账</h3><p>{{ mode === 'rooms' ? '课程计划会从这里选择可用教室。' : '后续课程计划和约束会从这里选择。' }}</p></div><button class="ledger-create-button" @click="createNew">新增</button></div>
        <div class="table-toolbar"><label class="search-field"><span>搜索</span><input v-model="search" type="search" :placeholder="`搜索本页${activeLabel}`" /></label><span class="table-count">本页 {{ formatCount(activeRecords.length) }} 条 · 共 {{ formatCount(totals[activeType] ?? 0) }} 条</span></div>
        <div class="ledger-table-scroll" role="region" :aria-label="`${activeLabel}台账，可横向滚动`" tabindex="0">
        <table class="data-table">
          <caption class="visually-hidden">{{ activeLabel }}台账</caption>
          <thead><tr>
            <template v-if="activeType === 'teacher'"><th scope="col">姓名</th><th scope="col">分组标签</th></template>
            <template v-else-if="activeType === 'homeroom'"><th scope="col">班级</th><th scope="col" class="ledger-number-column">人数（人）</th><th scope="col">分组</th><th scope="col">班主任</th><th scope="col">默认教室</th></template>
            <template v-else-if="activeType === 'subject'"><th scope="col">科目</th><th scope="col" class="ledger-number-column">默认课长</th></template>
            <template v-else-if="activeType === 'room'"><th scope="col">教室</th><th scope="col">类型</th><th scope="col" class="ledger-number-column">容量（人）</th></template>
            <template v-else><th scope="col">类型</th><th scope="col">说明</th></template>
            <th v-if="hasExportTemplate" scope="col">导出模板</th>
            <th scope="col" class="ledger-detail-column">详情</th>
          </tr></thead>
          <tbody><tr v-for="item in activeRecords" :key="item.id">
            <template v-if="activeType === 'teacher'">
              <td class="ledger-name-cell">{{ item.name }}</td>
              <td><div v-if="groupTags(item.department).length" class="ledger-tag-list"><span v-for="tag in groupTags(item.department)" :key="tag" class="ledger-tag">{{ tag }}</span></div><span v-else class="ledger-muted">未分组</span></td>
            </template>
            <template v-else-if="activeType === 'homeroom'">
              <td class="ledger-name-cell">{{ item.name }}</td><td class="ledger-number-column">{{ formatCount(item.student_count) }}</td><td :class="{ 'ledger-muted': !item.group_name }">{{ item.group_name || '未分组' }}</td><td :class="{ 'ledger-muted': !item.head_teacher_id }">{{ nameOf('teacher', item.head_teacher_id) }}</td><td :class="{ 'ledger-muted': !item.default_room_id }">{{ nameOf('room', item.default_room_id) }}</td>
            </template>
            <template v-else-if="activeType === 'subject'">
              <td class="ledger-name-cell">{{ item.name }}</td><td class="ledger-number-column">{{ item.default_duration_minutes ? `${formatCount(item.default_duration_minutes)} 分钟` : `${formatCount(item.default_duration_slots ?? 1)} 节（原配置）` }}</td>
            </template>
            <template v-else-if="activeType === 'room'">
              <td class="ledger-name-cell">{{ item.name }}</td><td :class="{ 'ledger-muted': !item.room_type_id }">{{ nameOf('room_type', item.room_type_id) }}</td><td class="ledger-number-column">{{ formatCount(item.capacity) }}</td>
            </template>
            <template v-else><td class="ledger-name-cell">{{ item.name }}</td><td :class="{ 'ledger-muted': !item.description }">{{ item.description || '—' }}</td></template>
            <td v-if="hasExportTemplate" data-label="导出模板"><span class="ledger-template-name" :title="templateName(item)">{{ templateName(item) }}</span></td>
            <td class="ledger-detail-column"><button class="ledger-detail-button" :aria-label="`查看${item.name}详情`" @click="edit(item)">查看详情</button></td>
          </tr></tbody>
        </table>
        </div>
        <div v-if="activeRecords.length === 0" class="empty-state"><strong>没有匹配数据</strong><span>换一个关键词，或点击右上角“新增”录入{{ activeLabel }}。</span></div>
        <nav v-if="totalPages > 1" class="pagination-controls" aria-label="台账分页"><button :disabled="busy || page <= 1" @click="changePage(page - 1)">上一页</button><span>第 {{ page }} / {{ totalPages }} 页</span><button :disabled="busy || page >= totalPages" @click="changePage(page + 1)">下一页</button></nav>
      </article>
    </div>

    <div v-if="dialogOpen" class="modal-mask">
      <section class="modal-panel ledger-detail-modal" role="dialog" aria-modal="true" aria-labelledby="ledger-dialog-title" @keydown.esc="cancelEdit">
        <header class="modal-header"><div><span>台账维护</span><h3 id="ledger-dialog-title">{{ editingId ? `编辑${activeLabel}` : `新增${activeLabel}` }}</h3><p>填写并确认资料后保存。</p></div><button class="icon-button" type="button" aria-label="关闭" @click="cancelEdit">×</button></header>
        <form class="detail-form ledger-detail-form" @submit.prevent="createActive">
          <p v-if="errorMessage" class="form-message error-copy ledger-form-notice" role="alert">{{ errorMessage }}</p>
          <template v-if="activeType === 'grade'">
            <label>年级名称<input v-model="forms.grade.name" placeholder="一年级" required /></label><label>代码<input v-model="forms.grade.code" placeholder="可选" /></label>
          </template>
          <template v-else-if="activeType === 'teacher'">
            <label>姓名<input v-model="forms.teacher.name" placeholder="张老师" required /></label><label>分组标签<input v-model="forms.teacher.department" placeholder="例如：班主任、数学组" /></label>
          </template>
          <template v-else-if="activeType === 'room_type'">
            <label>类型名称<input v-model="forms.room_type.name" placeholder="普通教室" required /></label><label>说明<input v-model="forms.room_type.description" placeholder="常规文化课教室" /></label>
          </template>
          <template v-else-if="activeType === 'room'">
            <label>教室名称<input v-model="forms.room.name" placeholder="一号教室" required /></label><label>类型<select v-model="forms.room.room_type_id"><option value="">请选择教室类型</option><option v-for="item in records.room_type" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>容量<input v-model.number="forms.room.capacity" type="number" min="0" /></label>
          </template>
          <template v-else-if="activeType === 'homeroom'">
            <label>班级名称<input v-model="forms.homeroom.name" placeholder="一年级 1 班" required /></label><label>人数<input v-model.number="forms.homeroom.student_count" type="number" min="0" /></label><label>分组<input v-model="forms.homeroom.group_name" placeholder="例如：一年级" /></label><label>班主任<select v-model="forms.homeroom.head_teacher_id"><option value="">未指定班主任</option><option v-for="item in records.teacher" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>默认教室<select v-model="forms.homeroom.default_room_id"><option value="">未指定默认教室</option><option v-for="item in records.room" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          </template>
          <template v-else>
            <label>科目名称<input v-model="forms.subject.name" placeholder="数学" required /></label><label>默认课长（分钟）<input v-model.number="forms.subject.default_duration_minutes" type="number" min="5" max="1440" step="5" required /></label>
          </template>
          <label v-if="hasExportTemplate" class="ledger-template-field">导出模板
            <select v-model="exportTemplateId" :disabled="busy">
              <option value="">{{ inheritedTemplate(activeType, forms.room.room_type_id) }}</option>
              <option v-for="item in normalTemplates" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
            <small>选择“课表设置”中已有的模板；选择默认项可取消单独指定。</small>
          </label>
          <div class="ledger-form-actions"><button type="button" class="secondary-button" @click="cancelEdit">取消</button><button class="primary-button" :disabled="busy">{{ editingId ? "保存修改" : "确认新增" }}</button><button v-if="editingId && selectedRecord" type="button" class="danger-button" @click="remove(selectedRecord)">删除</button></div>
        </form>
      </section>
    </div>
  </section>
</template>
