<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject, nextTick, ref, watch } from "vue";
import { BookOpen, Check, LockKeyhole, MessageSquare, Plus, Search, SlidersHorizontal, X } from "lucide-vue-next";
import AgentConversation from "./AgentConversation.vue";
import { appendAgentPrompt } from "../utils/agentPromptTemplates";
import { APP_CONTEXT_KEY } from "./appContext";
import { sameExpectedTimes } from '../utils/expectedPolicy';
import { configurationFromPicker, editExpectedConfiguration } from "../utils/expectedTimes";

type PlanningAiMode = "conversation" | "expected";
type ExpectedOperation = "add" | "delete" | "modify";

const {
  entitlement,
  hasOrganization,
  loadOverview,
  loadPlanningData,
  planningData,
  planningHomerooms,
  classConfigurationStatus,
  coursePlanningPeriodsForHomeroom,
  projectId,
  openCoursePreferredPickerForDraft,
  request,
  schoolData,
  showCoursePreferredPicker,
  showSection,
  termWeekCount,
} = inject(APP_CONTEXT_KEY)!;

const allowed = computed(() => entitlement.value.account_status === "member" && entitlement.value.membership_active === true && entitlement.value.ai_enabled === true);
const mode = ref<PlanningAiMode>("conversation");
const configurationProgress = computed(() => {
  const statuses = planningHomerooms.value.map((room) => classConfigurationStatus(room.id));
  return {
    total: statuses.length,
    complete: statuses.filter((status) => status.complete).length,
    percent: statuses.length ? Math.round(statuses.reduce((sum, status) => sum + status.progress, 0) / statuses.length) : 0,
    missingTime: statuses.reduce((sum, status) => sum + status.missingTimeCount, 0),
  };
});

const operation = ref<ExpectedOperation>("add");
const operationOptions: Array<{ value: ExpectedOperation; label: string; hint: string }> = [
  { value: "add", label: "新增", hint: "对选中范围内的所有课次，增加选中的时间模板" },
  { value: "modify", label: "修改", hint: "对选中范围内的所有课次，调整选中的时间模板" },
  { value: "delete", label: "删除", hint: "对选中范围内的所有课次，恢复到默认期望时间" },
];
const prompt = ref("");
const promptPresetOpen = ref(false);
const promptPanel = ref<HTMLDialogElement | null>(null);
const promptPresets: Record<ExpectedOperation, Array<{ id: string; title: string; text: string }>> = {
  add: [
    { id: "add-skip", title: "已有时间则跳过", text: "新增-对选中范围内的所有课次增加选中的时间；若该课次已有非默认期望时间，则跳过该课次。" },
    { id: "add-overwrite", title: "已有时间则覆盖", text: "新增-对选中范围内的所有课次增加选中的时间；若该课次已有非默认期望时间，则用选中的时间覆盖。" },
    { id: "add-cancel", title: "已有时间则取消本次任务", text: "新增-对选中范围内的所有课次增加选中的时间；若存在任何课次已有非默认期望时间，则取消本次任务。" },
  ],
  modify: [
    { id: "modify-remove", title: "去掉选中的时间", text: "修改-对选中范围内的所有课次，去掉选中的时间。" },
    { id: "modify-replace", title: "用选中的时间替换", text: "修改-对选中范围内的所有课次，用选中的时间替换现有期望时间。" },
  ],
  delete: [
    { id: "delete-match", title: "恢复与模板相同的时间", text: "删除-将选中范围内与时间模板相同的课次删除期望时间（恢复到默认期望时间）。" },
    { id: "delete-all", title: "恢复全部选中课次", text: "删除-将选中范围内的所有课次恢复到默认期望时间（全可行时间、最高优先）。" },
  ],
};
const activePromptPresets = computed(() => promptPresets[operation.value]);
const search = ref("");
const resolvedRows = ref<Array<{ id: string; label: string; subject: string; homeroom: string; teacher: string; text: string; timeLabel: string }> | null>(null);
const interpretation = ref("");
const searching = ref(false);
const searched = ref(false);
const selectedLessonIds = ref<string[]>([]);
const preferredRules = ref<Array<Record<string, any>>>([]);
const pickerDraft = ref<Record<string, any> | null>(null);
const pickerOpenedByWorkflow = ref(false);
const saving = ref(false);
const notice = ref("");
const error = ref("");

const taskById = computed(() => new Map((planningData.value.teaching_tasks || []).map((task) => [String(task.id), task])));
const lessonById = computed(() => new Map((planningData.value.task_lessons || []).map((lesson) => [String(lesson.id), lesson])));
const subjectNames = computed(() => new Map((schoolData.value.subjects || []).map((subject) => [String(subject.id), String(subject.name || "未命名科目")])));
const homeroomNames = computed(() => new Map((schoolData.value.homerooms || []).map((homeroom) => [String(homeroom.id), String(homeroom.name || "未命名班级")])));
const teacherNames = computed(() => new Map((schoolData.value.teachers || []).map((teacher) => [String(teacher.id), String(teacher.name || "未指定教师")])));
function timeLabelFor(lesson: Record<string, unknown>) {
  const preferences = Array.isArray(lesson.time_preferences) ? lesson.time_preferences : [];
  return preferences.length ? `${preferences.length} 组` : "全可行时间·最高优先";
}
const localRows = computed(() => {
  const query = search.value.trim().toLocaleLowerCase("zh-CN");
  return (planningData.value.task_lessons || []).map((lesson) => {
    const task = taskById.value.get(String(lesson.teaching_task_id)) || {};
    const label = String(lesson.label || `第${lesson.lesson_index || 1}课次`);
    const subject = String(task?.subject_name || subjectNames.value.get(String(task?.subject_id || "")) || "未命名科目");
    const homeroom = String(task?.homeroom_name || homeroomNames.value.get(String(task?.homeroom_id || "")) || "未命名班级");
    const teacher = String(task?.teacher_name || teacherNames.value.get(String(task?.primary_teacher_id || "")) || "未指定教师");
    const text = `${label} ${subject} ${homeroom} ${teacher}`.toLocaleLowerCase("zh-CN");
    return { id: String(lesson.id), label, subject, homeroom, teacher, text, timeLabel: timeLabelFor(lesson) };
  }).filter((item) => !query || item.text.includes(query));
});
const lessons = computed(() => resolvedRows.value ?? localRows.value);
const selectedLessons = computed(() => selectedLessonIds.value.map((id) => {
  const lesson = lessonById.value.get(id);
  if (!lesson) return null;
  const task = taskById.value.get(String(lesson.teaching_task_id || "")) || {};
  return { lesson, task };
}).filter((item): item is { lesson: Record<string, any>; task: Record<string, any> } => item !== null));
const selectionError = computed(() => (selectedLessons.value.length) ? "" : "请选择课次");
const operationIndex = computed(() => operationOptions.findIndex((item) => item.value === operation.value) + 1);

function resetExpected() {
  operation.value = "add";
  prompt.value = "";
  search.value = "";
  resolvedRows.value = null;
  interpretation.value = "";
  searched.value = false;
  searching.value = false;
  selectedLessonIds.value = [];
  preferredRules.value = [];
  pickerDraft.value = null;
  pickerOpenedByWorkflow.value = false;
  notice.value = "";
  error.value = "";
}
function selectMode(value: PlanningAiMode) {
  mode.value = value;
  if (value === "expected") resetExpected();
}
async function openPromptPreset() {
  promptPresetOpen.value = true;
  await nextTick();
  promptPanel.value?.showModal();
}
function closePromptPreset() {
  promptPresetOpen.value = false;
  promptPanel.value?.close();
}
function applyPromptTemplate(item: { text: string }) {
  prompt.value = appendAgentPrompt(prompt.value, item.text);
  closePromptPreset();
}
function toggleLesson(id: string) {
  selectedLessonIds.value = selectedLessonIds.value.includes(id)
    ? selectedLessonIds.value.filter((item) => item !== id)
    : [...selectedLessonIds.value, id];
}
function selectAllLessons() {
  selectedLessonIds.value = lessons.value.map((item) => item.id);
}
function clearLessons() {
  selectedLessonIds.value = [];
}
async function searchLessons() {
  const query = search.value.trim();
  if (!query) {
    resolvedRows.value = null;
    interpretation.value = "";
    searched.value = false;
    selectedLessonIds.value = [];
    return;
  }
  searching.value = true;
  error.value = "";
  try {
    const data = await request(`/api/projects/${projectId.value}/planning/ai/search-lessons`, {
      method: "POST",
      body: JSON.stringify({ scope_text: query }),
      silent: true,
      localError: true,
    });
    resolvedRows.value = (data.rows || []).map((row: Record<string, unknown>) => ({
      id: String(row.id),
      label: String(row.label || `第${row.ordinal}课次`),
      subject: String(row.subject_name || "未命名科目"),
      homeroom: String(row.homeroom_name || "未命名班级"),
      teacher: String(row.teacher_name || "未指定教师"),
      text: [row.label, row.subject_name, row.homeroom_name, row.teacher_name].filter(Boolean).join(" ").toLocaleLowerCase("zh-CN"),
      timeLabel: Number(row.time_preferences_count) ? `${row.time_preferences_count} 组` : "全可行时间·最高优先",
    }));
    interpretation.value = String(data.interpretation || "");
    searched.value = true;
    selectedLessonIds.value = (data.rows || []).map((row: Record<string, unknown>) => String(row.id));
  } catch (exception) {
    resolvedRows.value = localRows.value;
    interpretation.value = "未连接到 AI，已按本地关键词匹配";
    searched.value = true;
    selectedLessonIds.value = [];
  } finally {
    searching.value = false;
  }
}
async function applyExpectedChanges() {
  if (!selectedLessons.value.length) {
    error.value = "请至少选择一个课次";
    return;
  }
  if (!preferredRules.value.length) {
    error.value = "请先在第二步选择期望时间";
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    const targetProject = projectId.value;
    const selected = [...selectedLessons.value];
    const selectedRules = preferredRules.value.map(rule => ({ ...rule }));
    const selectedOperation = operation.value;
    const policy = prompt.value.trim() ? await request(`/api/projects/${targetProject}/planning/ai/expected-policy`, {method:'POST',body:JSON.stringify({prompt:prompt.value,operation:selectedOperation})}) : {policy:'default'};
    const current = await request(`/api/projects/${targetProject}/lesson-expected-times`);
    const byId = new Map<string, any>(current.items.map((item: any) => [String(item.lesson_id), item]));
    const items = selected.map(item => {
      const existing = byId.get(String(item.lesson.id));
      if (!existing) throw new Error("所选课次已变更，请重新搜索");
      const config = configurationFromPicker(selectedRules, coursePlanningPeriodsForHomeroom(item.task.homeroom_id));
      const hasExisting = existing.configuration.rules.length > 0;
      if (policy.policy === 'cancel_if_existing' && hasExisting) throw new Error('有课次已设置期望时间，按你的要求取消整批操作');
      if (policy.policy === 'skip_existing' && hasExisting) return null;
      const next = policy.policy === 'clear_all' ? {schema_version:2, default_policy:'inherit', rules:[]} : editExpectedConfiguration(existing.configuration, config, policy.policy === 'replace' ? 'modify' : policy.policy === 'remove_selected' ? 'delete' : selectedOperation);
      if (policy.policy === 'clear_matching') {
        if (!sameExpectedTimes(existing.configuration, config)) return null;
        next.rules=[]; next.default_policy='inherit';
      }
      return { lesson_id: String(item.lesson.id), revision: existing.revision,
        configuration: next };
    });
    const filtered = items.filter(Boolean);
    if (!filtered.length) throw new Error('按补充要求筛选后，没有需要修改的课次');
    if (targetProject !== projectId.value) throw new Error("项目已切换，本次操作已取消");
    await request(`/api/projects/${targetProject}/lesson-expected-times`, { method: "PATCH", body: JSON.stringify({ items: filtered }) });
    const successMessage = operation.value === "delete" ? "已删除选中课次的期望时间。" : "期望时间已应用。";
    resetExpected();
    notice.value = successMessage;
    try {
      await Promise.all([loadPlanningData({ refreshSelected: true }), loadOverview()]);
    } catch {
      error.value = "期望时间已保存，但课程计划数据刷新失败，请刷新页面；无需重复应用。";
    }
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "应用失败，请重试。";
  } finally {
    saving.value = false;
  }
}
async function openExpectedTimePicker() {
  try {
    pickerDraft.value = {
      id: "",
      key: `planning-ai-picker-${Date.now()}`,
      label: "专项设置",
      duration_slots: 1,
      enabled: true,
      room_mode: "default",
      room_ids: [],
      preferred_period_ids: [],
      preferred_slots: [],
      preferred_rules: [],
    };
    pickerOpenedByWorkflow.value = true;
    openCoursePreferredPickerForDraft(pickerDraft.value as any, "专项期望时间设置");
  } catch (exception) {
    pickerOpenedByWorkflow.value = false;
    error.value = exception instanceof Error ? exception.message : "无法打开期望时间选择器";
  }
}
watch(showCoursePreferredPicker, (open) => {
  if (open || !pickerOpenedByWorkflow.value) return;
  preferredRules.value = pickerDraft.value ? pickerDraft.value.preferred_rules.map((rule: Record<string, unknown>) => ({ ...rule })) : [];
  pickerOpenedByWorkflow.value = false;
});
watch([projectId], resetExpected);
</script>

<template>
  <section class="planning-ai-creator">
    <div class="planning-configuration-progress" aria-label="课程计划配置进度">
      <div class="configuration-progress-main">
        <strong>配置进度 {{ configurationProgress.percent }}%</strong>
        <progress :value="configurationProgress.percent" max="100" aria-label="课程计划配置完成度"></progress>
      </div>
      <div class="configuration-progress-stats">
        <span>完整班级 {{ configurationProgress.complete }} / {{ configurationProgress.total }}</span>
        <span>待配置期望时间 {{ configurationProgress.missingTime }} 课次</span>
      </div>
    </div>
    <div class="creator-tabs" role="tablist" aria-label="课程计划 AI 工作流">
      <button type="button" role="tab" :aria-selected="mode === 'conversation'" :tabindex="mode === 'conversation' ? 0 : -1" @click="selectMode('conversation')"><MessageSquare :size="16" />对话模式</button>
      <button type="button" role="tab" :aria-selected="mode === 'expected'" :tabindex="mode === 'expected' ? 0 : -1" @click="selectMode('expected')"><SlidersHorizontal :size="16" />期望时间专项模式</button>
    </div>
    <div v-if="mode === 'conversation'" class="planning-ai-conversation">
      <div class="planning-ai-notice"><strong>课程计划对话模式</strong><span>用于课程、课次、教师、教室等信息的增删改查。期望时间修改请切换到“期望时间专项模式”，避免普通对话误改排课偏好。</span></div>
      <AgentConversation />
    </div>
    <div v-else class="expected-wizard">
      <div v-if="!allowed" class="wizard-locked" role="status">
        <LockKeyhole :size="28" aria-hidden="true" /><strong>AI 期望时间专项仅对正式会员开放</strong>
        <p>试用、未开通或已到期账号暂不可使用。</p>
        <button type="button" class="btn-primary" @click="showSection('ai-settings')">前往 AI 设置</button>
      </div>
      <p v-else-if="!hasOrganization" class="wizard-message">请先选择机构和项目。</p>
      <template v-else>
        <section class="wizard-step">
          <h3><span>1</span>选择操作</h3>
          <div class="operation-segment" :class="`seg-${operationIndex}`" role="group" aria-label="期望时间操作">
            <button v-for="item in operationOptions" :key="item.value" type="button" :aria-pressed="operation === item.value" :class="{ active: operation === item.value }" @click="operation = item.value">{{ item.label }}</button>
          </div>
          <p class="wizard-message">{{ operationOptions.find((item) => item.value === operation)?.hint }}</p>
          <div class="wizard-prompt-box">
            <textarea v-model="prompt" rows="2" maxlength="1000" aria-label="期望时间操作要求" placeholder="补充具体要求，例如：已有期望时间的课次跳过" />
            <div class="wizard-prompt-actions">
              <button type="button" class="wizard-prompt-library-btn" @click="openPromptPreset"><BookOpen :size="16" aria-hidden="true" /><span>提示词</span></button>
            </div>
          </div>
        </section>
        <section class="wizard-step">
          <h3><span>2</span>选择时间模板</h3>
          <button type="button" class="wizard-picker-launch" @click="openExpectedTimePicker">
            <span class="wizard-picker-title">选择期望时间</span>
            <span class="wizard-picker-summary">{{ preferredRules.length ? `已选择 ${preferredRules.length} 组时间模板` : '尚未选择时间' }}</span>
            <SlidersHorizontal :size="16" aria-hidden="true" />
          </button>
        </section>
        <section class="wizard-step">
          <h3><span>3</span>搜索课次</h3>
          <form class="wizard-search" @submit.prevent="searchLessons">
            <input v-model="search" aria-label="搜索课次" type="search" placeholder="例如：一年级1班数学、张老师、第1课次" @input="if (!search.trim()) { resolvedRows = null; interpretation = ''; searched = false; }" />
            <button type="submit" :disabled="!search.trim()" aria-label="搜索课次" title="搜索课次"><Search :size="18" /></button>
          </form>
          <p v-if="searching" class="wizard-message" role="status">正在匹配项目中的课次...</p>
          <template v-if="searched && lessons.length">
            <p v-if="interpretation" class="wizard-interpretation">{{ interpretation }}</p>
            <div class="wizard-selection-tools">
              <label><input type="checkbox" :checked="selectedLessonIds.length === lessons.length" :indeterminate="selectedLessonIds.length > 0 && selectedLessonIds.length < lessons.length" @change="selectedLessonIds = selectedLessonIds.length === lessons.length ? [] : lessons.map(row => row.id)" />全选</label>
              <span>已选 {{ selectedLessonIds.length }} / {{ lessons.length }} 课次</span>
            </div>
            <div class="wizard-table-wrap" tabindex="0" aria-label="匹配课次列表">
              <table><thead><tr><th>选择</th><th>班级</th><th>科目</th><th>教师</th><th>课次</th><th>当前期望时间</th></tr></thead><tbody>
                <tr v-for="row in lessons" :key="row.id"><td><input type="checkbox" :aria-label="`${row.homeroom} ${row.subject} ${row.label}`" :checked="selectedLessonIds.includes(row.id)" @change="toggleLesson(row.id)" /></td><td>{{ row.homeroom }}</td><td>{{ row.subject }}</td><td>{{ row.teacher }}</td><td>{{ row.label }}</td><td>{{ row.timeLabel }}</td></tr>
              </tbody></table>
            </div>
          </template>
          <p v-else-if="searched" class="wizard-message">没有找到匹配的课次。</p>
        </section>
        <p v-if="error" class="wizard-error" role="alert">{{ error }}</p>
        <p v-if="notice" class="wizard-success" role="status"><Check :size="15" />{{ notice }}</p>
        <footer v-if="searched && lessons.length" class="wizard-footer">
          <div><strong>{{ operationOptions.find((item) => item.value === operation)?.label }}期望时间</strong><span>{{ selectedLessons.length }} 个课次 · {{ preferredRules.length }} 组期望时间</span><small v-if="selectionError" class="wizard-warning">{{ selectionError }}</small></div>
          <button type="button" class="btn-primary" :disabled="saving || !selectedLessons.length" @click="applyExpectedChanges">{{ saving ? '应用中...' : '确认应用' }}</button>
        </footer>
        <dialog v-if="promptPresetOpen" ref="promptPanel" class="wizard-prompt-dialog" aria-modal="true" aria-label="提示词预设" @cancel.prevent="closePromptPreset">
          <header><strong>提示词预设 · {{ operationOptions.find((item) => item.value === operation)?.label }}</strong><button type="button" class="wizard-prompt-close" aria-label="关闭提示词" title="关闭" @click="closePromptPreset"><X :size="18" /></button></header>
          <div class="wizard-prompt-list">
            <button v-for="tpl in activePromptPresets" :key="tpl.id" type="button" class="wizard-prompt-template" @click="applyPromptTemplate(tpl)">
              <span><strong>{{ tpl.title }}</strong><span>{{ tpl.text }}</span></span><Plus :size="18" aria-hidden="true" />
            </button>
          </div>
        </dialog>
      </template>
    </div>
  </section>
</template>

<style scoped>
.planning-configuration-progress { display: flex; flex: 0 0 auto; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px 24px; padding: 12px 20px; border-bottom: 1px solid #e2e9e5; font-size: 12px; color: #52665e; font-variant-numeric: tabular-nums; }
.configuration-progress-main { display: flex; align-items: center; gap: 14px; flex: 1 1 250px; max-width: 360px; min-width: 0; }
.configuration-progress-stats { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 6px 20px; margin-left: auto; }
.configuration-progress-stats span { white-space: nowrap; }
.planning-configuration-progress strong { color: #285f52; white-space: nowrap; }
.planning-configuration-progress progress { flex: 1 1 100px; min-width: 40px; width: 100%; height: 5px; appearance: none; border: 0; border-radius: 3px; overflow: hidden; }
.planning-configuration-progress progress::-webkit-progress-bar { background: #e8eeeb; }
.planning-configuration-progress progress::-webkit-progress-value { background: #2d7b6c; }
.planning-configuration-progress progress::-moz-progress-bar { background: #2d7b6c; }
.planning-ai-creator { display: flex; flex: 1; flex-direction: column; min-width: 0; min-height: 0; width: 100%; height: 100%; overflow: hidden; }
.creator-tabs { display: flex; gap: 20px; flex: none; padding-left: 10px; border-bottom: 1px solid #dce5df; }
.creator-tabs button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 44px; padding: 10px 2px; border: 0; border-bottom: 2px solid transparent; border-radius: 0; background: transparent; color: #65766d; font-size: 14px; font-weight: 600; }
.creator-tabs button[aria-selected="true"] { color: #257866; border-bottom-color: #257866; }
.creator-tabs button:focus-visible { outline: 2px solid #257866; outline-offset: 2px; }
.planning-ai-conversation { display: flex; flex: 1; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }
.planning-ai-conversation > :deep(.agent-conversation) { min-height: 0; flex: 1; }
.planning-ai-notice { display: flex; gap: 10px; flex: none; padding: 8px 14px; border-bottom: 1px solid #e8eee9; background: #fffaf0; color: #80621d; font-size: 12px; line-height: 1.5; }
.planning-ai-notice strong { white-space: nowrap; }
.expected-wizard { display: block; flex: 1; width: 100%; height: 100%; min-width: 0; min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: none; padding: 18px 20px; box-sizing: border-box; background: #fff; color: #29443e; font-size: 14px; }
.expected-wizard::-webkit-scrollbar { display: none; }
.wizard-step { padding: 0 0 20px; margin-bottom: 20px; border-bottom: 1px solid #e1e9e5; }
.wizard-step:last-of-type { margin-bottom: 0; border-bottom: 0; }
h3 { display: flex; align-items: center; gap: 10px; font-size: 16px; margin: 0 0 14px; color: #29443e; }
h3 > span { display: grid; place-items: center; width: 24px; height: 24px; background: #edf4f1; color: #267663; border-radius: 50%; font-size: 13px; }
.wizard-strength { display: flex; flex-wrap: wrap; gap: 8px; }
.wizard-strength button { padding: 9px 18px; background: #f8faf9; color: #566960; border: 1px solid #d9e4de; border-radius: 5px; font-size: 14px; }
.wizard-strength .selected { color: #21634f; border-color: #398670; background: #edf6f0; }
.operation-segment { position: relative; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0; overflow: hidden; border: 1px solid #d8e4dd; border-radius: 9px; background: #f4f8f5; padding: 3px; box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8); }
.operation-segment::before { content: ""; position: absolute; z-index: 0; top: 3px; left: 3px; width: calc((100% - 6px) / 3); height: calc(100% - 6px); border-radius: 7px; background: #2f7d6d; box-shadow: 0 6px 16px rgba(47, 125, 109, 0.22); transform: translateX(0); transition: transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1); }
.operation-segment.seg-2::before { transform: translateX(100%); }
.operation-segment.seg-3::before { transform: translateX(200%); }
.operation-segment button { position: relative; z-index: 1; min-height: 38px; border: 0; border-radius: 7px; background: transparent; color: #49605a; font-size: 13px; font-weight: 800; cursor: pointer; }
.operation-segment button.active { color: #ffffff; }
.operation-segment button:not(:disabled):hover { color: #21634f; }
.operation-segment button.active:hover { color: #ffffff; }
.wizard-message, .wizard-interpretation { font-size: 13px; line-height: 1.7; color: #697b72; margin: 12px 0; }
.wizard-prompt-box { display: flex; flex-direction: column; margin-top: 4px; border: 1px solid #cddbd3; border-radius: 8px; background: #fff; box-shadow: 0 3px 12px rgba(28, 56, 43, 0.045); transition: border-color 0.15s, box-shadow 0.15s; }
.wizard-prompt-box:focus-within { border-color: #438b72; box-shadow: 0 0 0 3px rgba(67, 139, 114, 0.1); }
.wizard-prompt-box textarea { display: block; width: 100%; min-height: 76px; max-height: 180px; resize: vertical; padding: 12px 12px 8px; background: transparent; border: 0; border-radius: 0; box-sizing: border-box; font: inherit; font-size: 14px; line-height: 1.65; color: #29443e; box-shadow: none; }
.wizard-prompt-box textarea:focus { outline: none; }
.wizard-prompt-actions { display: flex; align-items: center; gap: 10px; padding: 6px 10px 10px 12px; border-top: 1px solid #eef2ef; }
.wizard-prompt-library-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 34px; padding: 5px 10px; border: 1px solid #d7e3dd; border-radius: 6px; background: #f5f9f7; color: #2f7d6d; font-size: 13px; }
.wizard-prompt-library-btn:hover { background: #e7f3ee; border-color: #9fcbbd; }
.wizard-prompt-hint { color: #88948e; font-size: 12px; }
.wizard-prompt-dialog { width: min(560px, calc(100vw - 32px)); max-width: none; max-height: min(560px, calc(100dvh - 48px)); margin: auto; padding: 0; overflow: hidden; border: 1px solid #d6e2da; border-radius: 8px; background: #fff; color: #304f42; box-shadow: 0 20px 60px rgba(22, 43, 32, 0.18); }
.wizard-prompt-dialog[open] { display: flex; flex-direction: column; }
.wizard-prompt-dialog::backdrop { background: rgba(24, 36, 30, 0.32); }
.wizard-prompt-dialog > header { display: flex; align-items: center; justify-content: space-between; flex: none; gap: 12px; padding: 12px 18px; color: #304f42; font-size: 15px; }
.wizard-prompt-close { display: grid; place-items: center; width: 32px; height: 32px; padding: 0; border: 0; background: transparent; color: #677a6e; }
.wizard-prompt-list { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 0 18px; }
.wizard-prompt-template { display: flex; width: 100%; align-items: center; gap: 16px; padding: 14px 0; border: 0; border-bottom: 1px solid #e9eeeb; border-radius: 0; background: transparent; color: #354c40; text-align: left; }
.wizard-prompt-template:hover { background: #f6f9f7; }
.wizard-prompt-template > span { display: grid; gap: 6px; flex: 1; min-width: 0; }
.wizard-prompt-template strong { font-size: 14px; }
.wizard-prompt-template > span > span { color: #6b7c70; font-size: 12px; font-weight: 400; line-height: 1.65; overflow-wrap: anywhere; }
.wizard-prompt-template > svg { flex-shrink: 0; color: #357b5a; }
.wizard-picker-launch { display: flex; align-items: center; gap: 12px; width: 100%; padding: 14px 16px; border: 1px solid #dae4df; border-radius: 6px; background: #f8faf9; color: #38584c; text-align: left; }
.wizard-picker-launch:hover { border-color: #32846e; background: #f4faf6; }
.wizard-picker-title { font-size: 14px; font-weight: 700; }
.wizard-picker-summary { flex: 1; min-width: 0; color: #6d7c75; font-size: 12px; }
.wizard-picker-launch svg { flex: none; color: #2d7767; }
.wizard-search { display: flex; border: 1px solid #b9cfc6; border-radius: 6px; overflow: hidden; background: white; }
.wizard-search:focus-within { border-color: #2d8270; box-shadow: 0 0 0 2px #2d82701a; }
.wizard-search input { flex: 1; min-width: 0; width: 0; border: 0; outline: none; box-shadow: none; border-radius: 0; padding: 12px; font-size: 14px; }
.wizard-search button { flex: 0 0 44px; display: grid; place-items: center; border: 0; border-radius: 0; background: transparent; color: #2d7767; padding: 0; }
.wizard-selection-tools { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 12px 0; font-size: 12px; color: #697b72; }
.wizard-selection-tools label { display: flex; align-items: center; gap: 6px; }
input[type="checkbox"] { width: 16px; height: 16px; padding: 0; flex: none; accent-color: #2d8270; }
.wizard-table-wrap { max-height: 300px; overflow: auto; overscroll-behavior: contain; border: 1px solid #e0e7e3; }
table { width: 100%; min-width: 560px; border-collapse: collapse; font-size: 12px; }
th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid #e5ebe7; }
th { position: sticky; top: 0; background: #f2f6f3; font-weight: 600; white-space: nowrap; }
.wizard-footer { display: flex; flex-wrap: wrap; gap: 14px; justify-content: space-between; align-items: center; padding: 16px 0 0; }
.wizard-footer > div { display: grid; gap: 5px; flex: 1 1 180px; min-width: 0; overflow-wrap: anywhere; }
.wizard-footer strong { font-size: 14px; }
.wizard-footer span { font-size: 12px; color: #6b7c72; }
.wizard-footer button { flex: none; font-size: 14px; }
.wizard-warning { color: #916122; font-size: 12px; line-height: 1.6; margin-top: 10px; }
.wizard-error { display: flex; align-items: center; gap: 6px; color: #a43f33; background: #fff3ef; padding: 10px; font-size: 13px; overflow-wrap: anywhere; }
.wizard-success { display: flex; align-items: center; gap: 6px; color: #24684b; background: #edf7ef; padding: 10px; font-size: 13px; }
.wizard-locked { display: flex; flex-direction: column; gap: 14px; align-items: center; justify-content: center; min-height: 260px; text-align: center; }
.wizard-locked p { margin: 0; font-size: 13px; color: #728177; }
@media (max-width: 760px) {
  .creator-tabs { gap: 12px; }
  .planning-ai-notice { flex-direction: column; gap: 2px; }
  .expected-wizard { padding: 16px 14px; }
  .wizard-strength button { flex: 1 1 40%; }
  .wizard-footer > button { width: 100%; }
}
</style>
<style scoped src="../styles/aiCreatorLayout.css"></style>
