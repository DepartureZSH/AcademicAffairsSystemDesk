<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { confirm, open, save } from "@tauri-apps/plugin-dialog";
import { formatLocalError, localApi, type ImportPreview } from "../lib/sidecar";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();

const revision = ref(props.revision);
const entityType = ref("teacher");
const sourcePath = ref("");
const preview = ref<ImportPreview | null>(null);
const mapping = ref<Record<string, string>>({});
const selectedSheet = ref("");
const history = ref<Array<Record<string, unknown>>>([]);
const busy = ref(false);
const errorMessage = ref("");
const notice = ref("");

watch(() => props.revision, (value) => { revision.value = value; });
watch(entityType, () => { preview.value = null; sourcePath.value = ""; mapping.value = {}; });

const entityOptions = [
  ["teacher", "教师"], ["subject", "科目"], ["grade", "年级"],
  ["room_type", "教室类型"], ["room", "教室"], ["homeroom", "班级"],
  ["course_plan", "课程计划"], ["teaching_task", "教学任务"],
];
const targetFields: Record<string, Array<[string, string]>> = {
  teacher: [["employee_no", "工号"], ["name", "姓名（必填）"], ["department", "部门"], ["status", "状态"]],
  subject: [["name", "科目名称（必填）"], ["code", "代码"], ["category", "分类"], ["default_duration_slots", "默认连续课时"], ["requires_special_room", "需要专用教室"]],
  grade: [["name", "年级名称（必填）"], ["code", "代码"], ["sort_order", "排序"]],
  room_type: [["name", "类型名称（必填）"], ["code", "代码"], ["description", "说明"]],
  room: [["name", "教室名称（必填）"], ["room_no", "编号"], ["capacity", "容量"], ["status", "状态"], ["room_type_name", "教室类型名称"]],
  homeroom: [["name", "班级名称（必填）"], ["group_name", "分组"], ["student_count", "学生人数"], ["status", "状态"], ["grade_name", "年级名称"], ["term_name", "学期名称"], ["head_teacher_name", "班主任姓名"], ["default_room_name", "默认教室名称"]],
  course_plan: [["term_name", "学期名称"], ["homeroom_name", "班级名称（必填）"], ["subject_name", "科目名称（必填）"], ["weekly_slots", "每周课时（必填）"], ["duration_slots", "连续课时"], ["allow_double_period", "允许连堂"], ["priority", "优先级"], ["week_bits", "周次位图"], ["day_bits", "星期位图"]],
  teaching_task: [["term_name", "学期名称"], ["homeroom_name", "班级名称（必填）"], ["subject_name", "科目名称（必填）"], ["primary_teacher_name", "主讲教师（必填）"], ["weekly_slots", "每周课时（必填）"], ["duration_slots", "连续课时"], ["required_room_type_name", "要求教室类型"], ["fixed_room_name", "固定教室"], ["status", "状态"], ["week_bits", "周次位图"], ["day_bits", "星期位图"]],
};
const mappedColumns = computed(() => preview.value?.headers.filter((header) => mapping.value[header]) ?? []);

async function loadHistory() {
  try {
    const result = await localApi.listImports();
    history.value = result.items;
    revision.value = result.revision;
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  }
}

async function chooseFile() {
  const path = await open({
    multiple: false,
    directory: false,
    filters: [{ name: "教务数据", extensions: ["csv", "xlsx"] }],
  });
  if (typeof path !== "string") return;
  sourcePath.value = path;
  await previewFile();
}

async function previewFile() {
  if (!sourcePath.value) return;
  busy.value = true;
  errorMessage.value = "";
  notice.value = "";
  try {
    const result = await localApi.previewImport({
      source_path: sourcePath.value,
      entity_type: entityType.value,
      sheet_name: selectedSheet.value || null,
    });
    preview.value = result.preview;
    mapping.value = { ...result.preview.mapping };
    selectedSheet.value = result.preview.sheetName ?? "";
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function remap() {
  if (!preview.value) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const result = await localApi.remapImport(preview.value.id, {
      mapping: mapping.value,
      sheet_name: selectedSheet.value || null,
    });
    preview.value = result.preview;
    mapping.value = { ...result.preview.mapping };
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function confirmImport() {
  if (!preview.value?.canConfirm) return;
  const accepted = await confirm(
    `即将把 ${preview.value.rowCount} 行数据写入当前项目。\n\n原文件：${sourcePath.value}\n\n确认前会强制创建 pre-import 完整备份，全部数据在一个事务中写入。是否继续？`,
    { title: "确认批量导入", kind: "warning" },
  );
  if (!accepted) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const result = await localApi.confirmImport(preview.value.id, revision.value);
    revision.value = result.revision;
    emit("revision", revision.value);
    const generated = Number(result.import.generatedLessonCount ?? 0);
    notice.value = `已导入 ${result.import.importedCount} 条记录${generated ? `，自动生成 ${generated} 个课次` : ""}；操作前备份 ${result.import.backupId}`;
    preview.value = null;
    sourcePath.value = "";
    mapping.value = {};
    await loadHistory();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function abandon() {
  if (!preview.value) return;
  try {
    await localApi.abandonImport(preview.value.id);
    preview.value = null;
    sourcePath.value = "";
    await loadHistory();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  }
}

async function createTemplate(fileFormat: "csv" | "xlsx") {
  const label = entityOptions.find(([key]) => key === entityType.value)?.[1] ?? "数据";
  const path = await save({
    defaultPath: `${label}导入模板.${fileFormat}`,
    filters: [{ name: `${label}导入模板`, extensions: [fileFormat] }],
  });
  if (!path) return;
  busy.value = true;
  try {
    const result = await localApi.createImportTemplate({
      entity_type: entityType.value,
      file_format: fileFormat,
      destination_path: path,
      overwrite: true,
    });
    notice.value = `模板已保存：${result.template.destinationPath}`;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

onMounted(loadHistory);
</script>

<template>
  <section class="module-view">
    <div class="module-heading"><div><p class="eyebrow">LOCAL IMPORT</p><h2>CSV / Excel 批量导入</h2><p>原文件、预览、字段映射和确认结果只保存在当前本地项目。</p></div><span>Revision {{ revision }}</span></div>
    <div class="invariant-banner"><strong>预览不写业务数据</strong><span>确认前重新校验文件哈希、字段和引用，并先创建完整备份；任一行失败则整批回滚。</span></div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>
    <p v-if="notice" class="form-message notice-copy">{{ notice }}</p>

    <article class="panel import-toolbar">
      <label>数据类型<select v-model="entityType"><option v-for="[key, label] in entityOptions" :key="key" :value="key">{{ label }}</option></select></label>
      <button class="secondary-button" :disabled="busy" @click="createTemplate('csv')">CSV 模板</button>
      <button class="secondary-button" :disabled="busy" @click="createTemplate('xlsx')">Excel 模板</button>
      <button class="primary-button" :disabled="busy" @click="chooseFile">{{ busy ? "正在解析…" : "选择 CSV / XLSX" }}</button>
      <small v-if="sourcePath">{{ sourcePath }}</small>
    </article>

    <div v-if="preview" class="import-layout">
      <article class="panel data-panel">
        <div class="panel-heading"><div><p class="eyebrow">FIELD MAPPING</p><h3>字段映射</h3></div><span>{{ preview.rowCount }} 行</span></div>
        <label v-if="preview.availableSheets.length > 1" class="mapping-sheet">工作表<select v-model="selectedSheet" @change="remap"><option v-for="item in preview.availableSheets" :key="item">{{ item }}</option></select></label>
        <div class="mapping-list">
          <label v-for="header in preview.headers" :key="header"><span>{{ header }}</span><select v-model="mapping[header]"><option value="">不导入</option><option v-for="[key, label] in targetFields[entityType]" :key="key" :value="key">{{ label }}</option></select></label>
        </div>
        <button class="secondary-button" :disabled="busy" @click="remap">按当前映射重新预览</button>
      </article>

      <article class="panel preview-panel">
        <div class="panel-heading"><div><p class="eyebrow">PREVIEW</p><h3>数据预览</h3></div><span :class="{ 'error-copy': preview.errors.length }">{{ preview.errors.length }} 错误 · {{ preview.warnings.length }} 警告</span></div>
        <div class="preview-table-wrap"><table><thead><tr><th v-for="header in mappedColumns" :key="header">{{ header }}</th></tr></thead><tbody><tr v-for="(row, index) in preview.previewRows.slice(0, 20)" :key="index"><td v-for="header in mappedColumns" :key="header">{{ row[mapping[header]] }}</td></tr></tbody></table></div>
        <ul v-if="preview.errors.length" class="issue-list error-copy"><li v-for="item in preview.errors.slice(0, 20)" :key="item.row">第 {{ item.row }} 行：{{ item.messages.join('；') }}</li></ul>
        <ul v-if="preview.warnings.length" class="issue-list"><li v-for="item in preview.warnings.slice(0, 10)" :key="`${item.row}-${item.message}`">第 {{ item.row }} 行：{{ item.message }}</li></ul>
        <div class="preview-actions"><button class="text-button" :disabled="busy" @click="abandon">放弃预览</button><button class="primary-button" :disabled="busy || !preview.canConfirm" @click="confirmImport">确认导入并先备份</button></div>
      </article>
    </div>

    <article class="panel history-panel">
      <div class="panel-heading"><div><p class="eyebrow">IMPORT HISTORY</p><h3>导入记录</h3></div><span>{{ history.length }} 次</span></div>
      <div class="data-list"><div v-for="item in history" :key="String(item.id)" class="data-row"><span><strong>{{ item.source_name }} · {{ item.status }}</strong><small>{{ item.created_at }} · {{ (item.summary as Record<string, unknown>).entityType }} · {{ (item.summary as Record<string, unknown>).rowCount }} 行</small></span><b v-if="item.status === 'confirmed'">已写入</b><b v-else>未写入</b></div></div>
    </article>
  </section>
</template>
