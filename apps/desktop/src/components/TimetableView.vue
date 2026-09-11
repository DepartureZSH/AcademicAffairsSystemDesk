<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { save } from "@tauri-apps/plugin-dialog";
import {
  formatLocalError,
  localApi,
  type EntityRecord,
  type ManualMovePreview,
  type SchedulingCandidate,
  type TimetableEntry,
} from "../lib/sidecar";

const props = withDefaults(defineProps<{ revision: number; embedded?: boolean; initialCandidateId?: string }>(), { embedded: false });
const emit = defineEmits<{ revision: [value: number]; candidate: [value: string] }>();

const revision = ref(props.revision);
const candidates = ref<SchedulingCandidate[]>([]);
const candidateId = ref(props.initialCandidateId ?? "");
const entries = ref<TimetableEntry[]>([]);
const slots = ref<EntityRecord[]>([]);
const rooms = ref<EntityRecord[]>([]);
const teachers = ref<EntityRecord[]>([]);
const homerooms = ref<EntityRecord[]>([]);
const grades = ref<EntityRecord[]>([]);
const filterType = ref("");
const filterId = ref("");
const basedOnOldData = ref(false);
const selectedEntry = ref<TimetableEntry | null>(null);
const targetWeekday = ref(1);
const targetStartSlot = ref(0);
const targetRoomId = ref("");
const candidateName = ref("手工调整候选");
const preview = ref<ManualMovePreview | null>(null);
const busy = ref(false);
const errorMessage = ref("");
const exportType = ref("xlsx");
const exportNotice = ref("");
const exportHistory = ref<Array<Record<string, unknown>>>([]);
const compareCandidateId = ref("");
const compareEntries = ref<TimetableEntry[]>([]);
const weekMode = ref<"all" | "odd" | "even">("all");
const exportLayout = ref<"landscape" | "portrait">("landscape");
const colorMode = ref<"color" | "grayscale">("color");

watch(() => props.revision, (value) => { revision.value = value; });
watch([filterType, filterId], () => {
  if (candidateId.value) void loadTimetable();
  if (compareCandidateId.value) void loadComparison();
});
watch(compareCandidateId, () => { void loadComparison(); });
watch(candidateId, () => { emit('candidate', candidateId.value); if (compareCandidateId.value) void loadComparison(); });

const selectedCandidate = computed(() => candidates.value.find((item) => item.id === candidateId.value) ?? null);
const selectedCandidateIsValid = computed(() => selectedCandidate.value?.status === "valid");
const filterOptions = computed(() => filterType.value === "teacher" ? teachers.value : filterType.value === "homeroom" ? homerooms.value : filterType.value === "room" ? rooms.value : filterType.value === "grade" ? grades.value : []);
const compareCandidate = computed(() => candidates.value.find((item) => item.id === compareCandidateId.value) ?? null);
const comparison = computed(() => {
  if (!compareCandidate.value || compareCandidateId.value === candidateId.value) return null;
  const left = new Map(entries.value.map((item) => [item.task_lesson_id, item]));
  const right = new Map(compareEntries.value.map((item) => [item.task_lesson_id, item]));
  let moved = 0;
  let added = 0;
  let removed = 0;
  let unchanged = 0;
  for (const lessonId of new Set([...left.keys(), ...right.keys()])) {
    const before = left.get(lessonId);
    const after = right.get(lessonId);
    if (!before) added += 1;
    else if (!after) removed += 1;
    else if (before.weekday !== after.weekday || before.start_slot !== after.start_slot || before.room_id !== after.room_id || before.week_bits !== after.week_bits) moved += 1;
    else unchanged += 1;
  }
  return {
    moved, added, removed, unchanged,
    scoreDelta: compareCandidate.value.total_score - (selectedCandidate.value?.total_score ?? 0),
  };
});
const isRawXmlExport = computed(() => exportType.value.endsWith("_xml"));
const exportPreviewCount = computed(() => entries.value.filter((item) => {
  if (weekMode.value === "all") return true;
  const parity = weekMode.value === "odd" ? 0 : 1;
  return [...item.week_bits].some((bit, index) => bit === "1" && index % 2 === parity);
}).length);
const weekdays = [1, 2, 3, 4, 5, 6, 7];
const visibleStartSlots = computed(() => {
  const values = slots.value.filter((item) => Number(item.weekday) === targetWeekday.value);
  return values.sort((a, b) => Number(a.period_index) - Number(b.period_index));
});
const gridRows = computed(() => {
  const values = new Map<number, string>();
  for (const item of slots.value) values.set(Number(item.start_slot), String(item.label));
  return [...values.entries()].sort((a, b) => a[0] - b[0]);
});

function cellEntries(weekday: number, startSlot: number) {
  return entries.value.filter((item) => item.weekday === weekday && item.start_slot === startSlot);
}

function filterLabel(item: EntityRecord) {
  return String(item.name ?? item.id);
}

async function loadBase() {
  busy.value = true;
  errorMessage.value = "";
  try {
    const [candidateResult, slotResult, roomResult, teacherResult, homeroomResult, gradeResult] = await Promise.all([
      localApi.listSchedulingCandidates(),
      localApi.listEntities("time_slot"),
      localApi.listEntities("room"),
      localApi.listEntities("teacher"),
      localApi.listEntities("homeroom"),
      localApi.listEntities("grade"),
    ]);
    candidates.value = candidateResult.items;
    slots.value = slotResult.items;
    rooms.value = roomResult.items;
    teachers.value = teacherResult.items;
    homerooms.value = homeroomResult.items;
    grades.value = gradeResult.items;
    revision.value = Math.max(candidateResult.revision, slotResult.revision, roomResult.revision, teacherResult.revision, homeroomResult.revision, gradeResult.revision);
    emit("revision", revision.value);
    if (!candidateId.value && candidates.value.length) candidateId.value = candidates.value[0].id;
    if (candidateId.value) await loadTimetable();
    if (compareCandidateId.value) await loadComparison();
    const exportsResult = await localApi.listExports();
    exportHistory.value = exportsResult.items;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function loadComparison() {
  if (!compareCandidateId.value || compareCandidateId.value === candidateId.value) {
    compareEntries.value = [];
    return;
  }
  try {
    const result = await localApi.getTimetable(compareCandidateId.value, filterType.value || undefined, filterId.value || undefined);
    compareEntries.value = result.items;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
    compareEntries.value = [];
  }
}

async function loadTimetable() {
  if (!candidateId.value) return;
  errorMessage.value = "";
  selectedEntry.value = null;
  preview.value = null;
  try {
    const result = await localApi.getTimetable(candidateId.value, filterType.value || undefined, filterId.value || undefined);
    entries.value = result.items;
    basedOnOldData.value = result.basedOnOldData;
    revision.value = result.revision;
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  }
}

function selectEntry(item: TimetableEntry) {
  if (!selectedCandidateIsValid.value) return;
  selectedEntry.value = item;
  targetWeekday.value = item.weekday;
  targetStartSlot.value = item.start_slot;
  targetRoomId.value = item.room_id ? String(item.room_id) : "";
  preview.value = null;
}

function movePayload() {
  if (!selectedEntry.value) return null;
  return {
    candidate_id: candidateId.value,
    task_lesson_id: selectedEntry.value.task_lesson_id,
    weekday: targetWeekday.value,
    start_slot: targetStartSlot.value,
    room_id: targetRoomId.value || null,
    name: candidateName.value.trim(),
  };
}

async function validateMove() {
  const payload = movePayload();
  if (!payload) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    preview.value = await localApi.validateManualMove(payload);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function applyMove() {
  const payload = movePayload();
  if (!payload || !preview.value?.valid) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const result = await localApi.applyManualMove(payload);
    const newCandidateId = String(result.round.candidate_id);
    candidateId.value = newCandidateId;
    selectedEntry.value = null;
    preview.value = null;
    await loadBase();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

const exportOptions: Record<string, { label: string; extension: string }> = {
  xlsx: { label: "Excel 工作簿", extension: "xlsx" },
  csv: { label: "CSV 明细", extension: "csv" },
  pdf: { label: "PDF 打印表", extension: "pdf" },
};

async function exportCandidate() {
  if (!candidateId.value || !selectedCandidateIsValid.value) return;
  const option = exportOptions[exportType.value];
  const destination = await save({
    defaultPath: `时奕课表-${candidateId.value.slice(0, 8)}.${option.extension}`,
    filters: [{ name: option.label, extensions: [option.extension] }],
  });
  if (!destination) return;
  busy.value = true;
  errorMessage.value = "";
  exportNotice.value = "";
  try {
    const result = await localApi.exportCandidate({
      candidate_id: candidateId.value,
      export_type: exportType.value,
      destination_path: destination,
      overwrite: true,
      entity_type: filterType.value && filterId.value ? filterType.value : null,
      entity_id: filterType.value && filterId.value ? filterId.value : null,
      week_mode: weekMode.value,
      layout: exportLayout.value,
      color_mode: colorMode.value,
    });
    exportNotice.value = `已成功导出：${String(result.export.fileName)}`;
    exportHistory.value = (await localApi.listExports()).items;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

function undoToParent() {
  const parentId = selectedCandidate.value?.parent_candidate_id;
  if (parentId && candidates.value.some((item) => item.id === parentId)) {
    candidateId.value = parentId;
    void loadTimetable();
  }
}

onMounted(loadBase);
</script>

<template>
  <section class="module-view timetable-view" :class="{ 'embedded-timetable': embedded }">
    <div v-if="!embedded" class="module-heading"><div><p class="eyebrow">排课结果</p><h2>候选课表</h2><p>像网页版一样按班级、教师、年级或教室查看，也可以导出和手工调整。</p></div><span>已自动保存</span></div>
    <h2 v-else class="embedded-timetable-title">候选课表</h2>
    <div v-if="basedOnOldData" class="invariant-banner stale-banner"><strong>项目资料已经更新</strong><span>这份课表仍可查看，建议使用最新资料重新运行自动排课。</span></div>
    <div v-if="selectedCandidate && !selectedCandidateIsValid" class="invariant-banner stale-banner"><strong>历史方案仅供查看</strong><span>这份方案不符合当前设置，不能调整或导出。</span></div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <article class="panel timetable-toolbar">
      <label>候选方案<select v-model="candidateId" @change="loadTimetable"><option v-for="item in candidates" :key="item.id" :value="item.id">{{ item.status === 'valid' ? '可用' : '只读' }} · 得分 {{ item.total_score }} · {{ item.entry_count }} 课次 · {{ item.name }}</option></select></label>
      <label>查看维度<select v-model="filterType" @change="filterId = ''"><option value="">全部课表</option><option value="grade">年级课表</option><option value="homeroom">班级课表</option><option value="teacher">教师课表</option><option value="room">教室课表</option></select></label>
      <label v-if="filterType">对象<select v-model="filterId"><option value="">全部</option><option v-for="item in filterOptions" :key="item.id" :value="item.id">{{ filterLabel(item) }}</option></select></label>
      <button v-if="selectedCandidate?.parent_candidate_id" class="secondary-button" @click="undoToParent">回到父候选（撤销）</button>
    </article>

    <article v-if="candidates.length > 1" class="panel comparison-toolbar">
      <div><p class="eyebrow">方案对比</p><strong>看看两份课表哪里不同</strong><small>对比课程时间、教室和周次的变化。</small></div>
      <select v-model="compareCandidateId"><option value="">选择对比候选</option><option v-for="item in candidates.filter((candidate) => candidate.id !== candidateId)" :key="item.id" :value="item.id">得分 {{ item.total_score }} · {{ item.name }}</option></select>
      <div v-if="comparison" class="comparison-metrics"><span><b>{{ comparison.moved }}</b> 移动/变更</span><span><b>{{ comparison.added }}</b> 新增</span><span><b>{{ comparison.removed }}</b> 缺失</span><span><b>{{ comparison.unchanged }}</b> 未变</span><span :class="comparison.scoreDelta <= 0 ? 'better' : 'worse'"><b>{{ comparison.scoreDelta > 0 ? '+' : '' }}{{ comparison.scoreDelta }}</b> 得分差</span></div>
    </article>

    <article v-if="candidates.length" class="panel export-toolbar">
      <div><p class="eyebrow">导出课表</p><strong>保存或打印当前课表</strong><small>可以按当前查看范围导出，也可以导出全部课表。</small></div>
      <select v-model="exportType"><option v-for="(item, key) in exportOptions" :key="key" :value="key">{{ item.label }}</option></select>
      <select v-model="weekMode" :disabled="isRawXmlExport"><option value="all">全部周次</option><option value="odd">仅单周</option><option value="even">仅双周</option></select>
      <select v-model="exportLayout" :disabled="isRawXmlExport"><option value="landscape">横向</option><option value="portrait">纵向</option></select>
      <select v-model="colorMode" :disabled="isRawXmlExport"><option value="color">彩色</option><option value="grayscale">黑白</option></select>
      <button class="primary-button" :disabled="busy || !selectedCandidateIsValid" @click="exportCandidate">{{ busy ? "处理中…" : "选择位置并导出" }}</button>
      <span v-if="exportNotice" class="export-notice">{{ exportNotice }}</span>
      <small v-else>将导出 {{ exportPreviewCount }} 条课程 · {{ filterId ? '当前查看范围' : '全部课表' }} · {{ weekMode === 'odd' ? '单周' : weekMode === 'even' ? '双周' : '全部周次' }}</small>
    </article>

    <div v-if="!candidates.length" class="state-panel compact-state"><h2>尚无可查看候选</h2><p>先在“排课运行”生成完整可行候选。</p></div>
    <div v-else class="timetable-layout">
      <article class="panel timetable-grid-panel">
        <div class="timetable-grid" :style="{ gridTemplateColumns: `92px repeat(7, minmax(128px, 1fr))` }">
          <div class="grid-head">课节</div><div v-for="day in weekdays" :key="`head-${day}`" class="grid-head">周{{ day }}</div>
          <template v-for="[startSlot, label] in gridRows" :key="startSlot">
            <div class="grid-time"><strong>{{ label }}</strong><small>第 {{ Number(startSlot) + 1 }} 节</small></div>
            <div v-for="day in weekdays" :key="`${day}-${startSlot}`" class="grid-cell">
              <button v-for="item in cellEntries(day, startSlot)" :key="item.id" class="lesson-chip" :disabled="!selectedCandidateIsValid" :class="{ selected: selectedEntry?.id === item.id }" @click="selectEntry(item)">
                <strong>{{ item.subject_name || "未命名课程" }}</strong><span>{{ item.homeroom_name }} · {{ item.teacher_name }}</span><small>{{ item.room_name || "无指定教室" }} · {{ item.duration_slots }} 课时</small>
              </button>
            </div>
          </template>
        </div>
      </article>

      <aside class="panel manual-panel">
        <p class="eyebrow">手工调整</p><h3>移动一节课</h3>
        <p v-if="!selectedCandidateIsValid" class="empty-copy">当前候选为只读历史记录，不能用于手工调整。</p>
        <p v-else-if="!selectedEntry" class="empty-copy">在课表中选择一个课次开始调整。</p>
        <form v-else class="compact-form" @submit.prevent="validateMove">
          <div class="selected-lesson"><strong>{{ selectedEntry.subject_name }}</strong><span>{{ selectedEntry.homeroom_name }} · {{ selectedEntry.teacher_name }}</span></div>
          <label>目标星期<select v-model.number="targetWeekday" @change="targetStartSlot = Number(visibleStartSlots[0]?.start_slot ?? 0); preview = null"><option v-for="day in weekdays" :key="day" :value="day">星期 {{ day }}</option></select></label>
          <label>目标课节<select v-model.number="targetStartSlot" @change="preview = null"><option v-for="item in visibleStartSlots" :key="item.id" :value="Number(item.start_slot)">{{ item.label }}</option></select></label>
          <label>目标教室<select v-model="targetRoomId" @change="preview = null"><option value="">无指定教室</option><option v-for="item in rooms" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label>新候选名称<input v-model="candidateName" maxlength="200" /></label>
          <button class="secondary-button" :disabled="busy">{{ busy ? "校验中…" : "即时冲突检查" }}</button>
          <div v-if="preview" class="move-preview" :class="{ valid: preview.valid, invalid: !preview.valid }">
            <strong>{{ preview.valid ? "可移动" : "存在硬冲突" }}</strong>
            <span v-if="preview.score">预估得分 {{ preview.score.total_score }}</span>
            <ul v-if="preview.conflicts.length"><li v-for="(item, index) in preview.conflicts" :key="index">{{ item.message || item.code }}</li></ul>
          </div>
          <button type="button" class="primary-button" :disabled="busy || !preview?.valid" @click="applyMove">生成手工调整子候选</button>
        </form>
      </aside>
    </div>
  </section>
</template>
