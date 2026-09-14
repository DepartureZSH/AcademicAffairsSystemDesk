<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ArrowDown, ArrowUp, Check, LockKeyhole, Search, Sparkles } from "lucide-vue-next";
import { APP_CONTEXT_KEY } from "./appContext";
import ConstraintParameters from "./ConstraintParameters.vue";
import ConstraintExpansionStep from "./ConstraintExpansionStep.vue";
import type { ExpansionSource, ExpansionPayload } from "../utils/constraintExpansion";
import { constraintDefinition, distributionLabel } from "../utils/itcConstraints";

type Rule = { id: string; name: string; description: string; scenario_type: string; template_id: string | null; source: string; match_label: string; reason: string };
type Lesson = { id: string; xml_class_id: string; ordinal: number; label: string; homeroom: string; subject: string; teacher: string; task: string };
const props = defineProps<{ preset?: { query: string; scope: string; required: boolean; penalty: number; instruction?: string; analysis?: any }; deferSave?: boolean }>();
const emit = defineEmits<{ created: []; prepared: [payload: ExpansionPayload] }>();
const expansionSource = ref<ExpansionSource | null>(null);
const { entitlement, projectId, organizationId, currentUserId, hasProject, request, loadConstraints, loadOverview, loadAgentUsage, showSection } = inject(APP_CONTEXT_KEY)!;
const allowed = computed(() => entitlement.value.account_status === "member" && entitlement.value.membership_active === true && entitlement.value.ai_enabled === true);
const query = ref("");
const rules = ref<Rule[]>([]);
const searched = ref(false);
const ruleMessage = ref("");
const buildUnsupported = ref(false);
const rule = ref<Rule | null>(null);
const validParameters = ref(true);
const required = ref(true);
const penalty = ref(10);
const scope = ref("");
const resolution = ref<Record<string, any> | null>(null);
const selected = ref<string[]>([]);
const grouping = ref("teaching_task_id");
const busy = ref("");
const error = ref("");
const notice = ref("");
let version = 0;
const ruleType = computed({
  get: () => rule.value?.scenario_type.split(":").slice(1).join(":") || "",
  set: (value: string) => { if (rule.value) rule.value.scenario_type = rule.value.scenario_type.split(":")[0] + ":" + value; invalidateScope(); },
});
const combined = computed(() => rule.value?.scenario_type.startsWith("common:ParallelLimit(") || false);
const ordered = computed(() => ["course_consecutive", "itc2019:Consecutive", "itc2019:Precedence"].includes(rule.value?.scenario_type || ""));
const rows = computed<Lesson[]>(() => {
  const result: Lesson[] = [];
  for (const group of resolution.value?.groups || []) for (const lesson of group.lessons || []) {
    if (result.some(row => row.xml_class_id === lesson.xml_class_id)) continue;
    result.push({ ...lesson, homeroom: lesson.homeroom_name || group.homeroom_name,
      subject: lesson.subject_name || group.subject_name, teacher: lesson.teacher_name || group.teacher_name,
      task: lesson.teaching_task_id || group.teaching_task_id });
  }
  return result;
});
const selectedRows = computed(() => selected.value.map(id => rows.value.find(row => row.xml_class_id === id)).filter((row): row is Lesson => !!row));
const groupCount = computed(() => !selectedRows.value.length ? 0 : grouping.value === "all" ? 1 : new Set(selectedRows.value.map(row => row.task)).size);
const selectedTitle = computed(() => ruleType.value ? distributionLabel(ruleType.value) : rule.value?.name || "");
const supported = computed(() => resolution.value?.status === "resolved" && !!resolution.value?.compile_schema?.distribution_type);
const selectionError = computed(() => {
  if (!selectedRows.value.length) return "请选择课次";
  const minimum = Number(resolution.value?.compile_schema?.minimum_items || 1);
  const counts = new Map<string, number>();
  for (const row of selectedRows.value) { const key = grouping.value === "all" ? "all" : row.task; counts.set(key, (counts.get(key) || 0) + 1); }
  return [...counts.values()].some(count => count < minimum) ? `每组至少需要 ${minimum} 个课次，请调整勾选或分组` : "";
});
function invalidateScope() { version++; expansionSource.value = null; resolution.value = null; selected.value = []; error.value = ""; notice.value = ""; }
function invalidateRule() { invalidateScope(); rule.value = null; rules.value = []; searched.value = false; ruleMessage.value = ""; buildUnsupported.value = false; }
function readable(exc: unknown) {
  const text = exc instanceof Error ? exc.message : "请求失败，请稍后重试。";
  try { const data = JSON.parse(text); return typeof data.detail === "string" ? data.detail : "请求内容有误，请检查后重试。"; } catch { return text; }
}
async function run(kind: string, action: () => Promise<any>, apply: (data: any) => void) {
  if (!allowed.value || !hasProject.value || busy.value) return;
  const current = ++version;
  busy.value = kind; error.value = ""; notice.value = "";
  try {
    const result = await action();
    if (current === version && allowed.value) {
      apply(result);
      if (kind !== "create") void loadAgentUsage().catch(() => {});
    }
  }
  catch (exc) { if (current === version) error.value = readable(exc); }
  finally { busy.value = ""; }
}
const api = (path: string, body: unknown) => request(`/api/projects/${projectId.value}/constraints/ai/${path}`, {
  method: "POST", body: JSON.stringify(body), silent: true, localError: true,
});
async function searchRules(build = false) {
  if (!query.value.trim()) return;
  invalidateScope(); rule.value = null;
  await run("rules", () => api("rules/search", { query: query.value.trim(), build }), data => {
    rules.value = data.items || []; ruleMessage.value = data.message || ""; searched.value = true;
    buildUnsupported.value = !!data.unsupported;
  });
}
function choose(item: Rule) {
  invalidateScope(); rule.value = { ...item }; validParameters.value = true;
  grouping.value = item.scenario_type.startsWith("common:ParallelLimit(") ? "all" : "teaching_task_id";
}
async function searchLessons(choice: Record<string, unknown> | null = null) {
  if (!rule.value || !scope.value.trim() || !validParameters.value) return;
  const chosen = { ...rule.value };
  resolution.value = null; selected.value = [];
  await run("lessons", () => api("resolve", { template_id: chosen.template_id, scenario_type: chosen.scenario_type,
    constraint_description: chosen.name, required: required.value, penalty: required.value ? null : penalty.value,
    scope_text: scope.value.trim(), clarification_choice: choice, preview_only: true }), data => {
    resolution.value = data;
    grouping.value = combined.value || data.group_by?.includes("all") ? "all" : "teaching_task_id";
    selected.value = rows.value.map(row => row.xml_class_id);
  });
}
function toggle(id: string) { selected.value = selected.value.includes(id) ? selected.value.filter(value => value !== id) : [...selected.value, id]; }
function move(id: string, offset: number) {
  const values = [...selected.value], i = values.indexOf(id), j = i + offset;
  if (i < 0 || j < 0 || j >= values.length) return;
  [values[i], values[j]] = [values[j], values[i]]; selected.value = values;
}
async function create() {
  if (!rule.value || !supported.value || selectionError.value || !validParameters.value) return;
  const groups = new Map<string, string[]>();
  for (const row of selectedRows.value) {
    const key = grouping.value === "all" ? "all" : row.task;
    groups.set(key, [...(groups.get(key) || []), row.xml_class_id]);
  }
  expansionSource.value = { template_id: rule.value.template_id, scenario_type: rule.value.scenario_type,
    name: rule.value.name, required: required.value, penalty: required.value ? null : penalty.value,
    groups: [...groups.values()] };
}
function onCreated(data: any) {
    notice.value = `已创建 ${data.created_count || 0} 组约束${data.skipped_count ? `，跳过 ${data.skipped_count} 组已有约束` : ""}。`;
    expansionSource.value = null; resolution.value = null; selected.value = [];
    void Promise.all([loadConstraints(), loadOverview()]).catch(() => { error.value = "约束已保存，但列表刷新失败，请刷新页面。"; });
    emit("created");
}
onMounted(() => {
  if (!props.preset) return;
  query.value = props.preset.query; scope.value = props.preset.scope;
  required.value = props.preset.required; penalty.value = props.preset.penalty;
  if (props.preset.analysis) {
    rules.value = props.preset.analysis.rules || []; searched.value = true; ruleMessage.value = props.preset.analysis.message || '';
    if (rules.value.length === 1 && props.preset.analysis.resolution) {
      choose(rules.value[0]); resolution.value = props.preset.analysis.resolution;
      grouping.value = combined.value || resolution.value?.group_by?.includes('all') ? 'all' : 'teaching_task_id';
      selected.value = rows.value.map(row => row.xml_class_id);
    }
    return;
  }
  void searchRules();
});
watch([projectId, organizationId, currentUserId, allowed], () => { invalidateRule(); query.value = ""; scope.value = ""; });
onBeforeUnmount(() => { version++; });
</script>

<template>
  <div class="constraint-ai-wizard">
    <div v-if="!allowed" class="wizard-locked" role="status">
      <LockKeyhole :size="28" aria-hidden="true" /><strong>AI 创建约束仅对正式会员开放</strong>
      <p>试用、未开通或已到期账号暂不可使用。</p>
      <button type="button" class="btn-primary" @click="showSection('ai-settings')">前往 AI 设置</button>
    </div>
    <p v-else-if="!hasProject" class="wizard-message">请先选择项目。</p>
    <template v-else>
      <ConstraintExpansionStep v-if="expansionSource" :source="expansionSource" require-ai :defer-save="deferSave" :initial-instruction="preset?.instruction" @back="expansionSource = null" @created="onCreated" @prepared="emit('prepared', $event)" />
      <template v-else>
      <fieldset :disabled="!!busy">
        <section class="wizard-step">
          <h3><span>1</span>找约束规则</h3>
          <form class="wizard-search" @submit.prevent="searchRules()">
            <input v-model="query" aria-label="搜索约束规则" type="search" maxlength="1000" placeholder="例如：同一时间最多安排4节体育课" @input="invalidateRule" />
            <button type="submit" :disabled="!query.trim()" :aria-label="busy === 'rules' ? '正在搜索规则' : '搜索规则'" title="搜索规则"><Search :size="18" /></button>
          </form>
          <p v-if="busy === 'rules'" class="wizard-message" role="status">正在查找合适规则...</p>
          <div v-if="rules.length" class="wizard-rules" role="radiogroup" aria-label="匹配规则">
            <button v-for="item in rules" :key="item.id" type="button" role="radio" :aria-checked="rule?.id === item.id" :class="{ selected: rule?.id === item.id }" @click="choose(item)">
              <span class="rule-top"><strong>{{ item.name }}</strong><small :class="{ partial: item.match_label === '部分匹配' }">{{ item.match_label }}</small><Check v-if="rule?.id === item.id" :size="16" /></span>
              <span>{{ item.description }}</span><small>{{ item.source }} · {{ item.reason }}</small>
            </button>
          </div>
          <div v-if="searched && !rules.length" class="wizard-message">
            <p>{{ ruleMessage || '没有找到合适的规则。' }}</p>
            <button v-if="!buildUnsupported" type="button" class="btn-secondary" @click="searchRules(true)"><Sparkles :size="16" />尝试根据描述构建规则</button>
            <p v-else class="wizard-warning">需要补充算法支持，暂不能创建此规则。</p>
          </div>
          <ConstraintParameters v-if="rule && !rule.template_id && constraintDefinition(ruleType)" v-model="ruleType" :key="rule.id" @validity="validParameters = $event" />
        </section>
        <section class="wizard-step" :class="{ 'step-pending': !rule }">
          <h3><span>2</span>设置约束强度</h3>
          <div class="wizard-strength" role="group" aria-label="约束强度">
            <button type="button" :disabled="!rule" :aria-pressed="required" :class="{ selected: required }" @click="required = true">必须满足</button>
            <button type="button" :disabled="!rule" :aria-pressed="!required" :class="{ selected: !required }" @click="required = false">尽量满足</button>
          </div>
          <label v-if="!required" class="wizard-priority">优先级
            <select v-model.number="penalty" :disabled="!rule" aria-label="尽量满足的优先级"><option :value="10">普通（10）</option><option :value="30">较高（30）</option><option :value="60">最高（60）</option></select>
          </label>
        </section>
        <section class="wizard-step" :class="{ 'step-pending': !rule }">
          <h3><span>3</span>找涉及课次</h3>
          <form class="wizard-search" @submit.prevent="searchLessons()">
            <input v-model="scope" :disabled="!rule" type="search" aria-label="搜索涉及课次" placeholder="例如：全校体育课，不包括六年级" @input="invalidateScope" />
            <button type="submit" :disabled="!rule || !scope.trim() || !validParameters" aria-label="搜索课次" title="搜索课次"><Search :size="18" /></button>
          </form>
          <p v-if="busy === 'lessons'" class="wizard-message" role="status">正在匹配项目中的课次...</p>
          <div v-if="resolution?.status === 'needs_clarification'" class="wizard-clarify">
            <p>{{ resolution.question }}</p>
            <button v-for="candidate in resolution.candidates || []" :key="candidate.id" type="button" class="btn-secondary" @click="searchLessons(candidate)">{{ candidate.title }}</button>
          </div>
          <p v-else-if="resolution && !rows.length" class="wizard-message">{{ resolution.message || '没有找到匹配课次。' }}</p>
          <template v-if="rows.length">
            <p class="wizard-interpretation">{{ resolution?.interpretation }}</p>
            <div class="wizard-selection-tools">
              <label><input type="checkbox" :checked="selected.length === rows.length" :indeterminate="selected.length > 0 && selected.length < rows.length" @change="selected = selected.length === rows.length ? [] : rows.map(row => row.xml_class_id)" />全选</label>
              <span>已选 {{ selected.length }} / {{ rows.length }} 课次</span>
              <select v-model="grouping" :disabled="combined" aria-label="课次分组方式"><option value="teaching_task_id">每个授课任务分别创建</option><option value="all">所有选中课次合为一组</option></select>
            </div>
            <div class="wizard-table-wrap" tabindex="0" aria-label="匹配课次列表">
              <table><thead><tr><th>选择</th><th>班级</th><th>科目</th><th>教师</th><th>课次</th></tr></thead><tbody>
                <tr v-for="row in rows" :key="row.xml_class_id"><td><input type="checkbox" :aria-label="`${row.homeroom} ${row.subject} 第${row.ordinal}课次`" :checked="selected.includes(row.xml_class_id)" @change="toggle(row.xml_class_id)" /></td><td>{{ row.homeroom }}</td><td>{{ row.subject }}</td><td>{{ row.teacher }}</td><td>第{{ row.ordinal }}课次</td></tr>
              </tbody></table>
            </div>
            <details v-if="ordered && selectedRows.length" class="wizard-order"><summary>课次顺序</summary>
              <div v-for="(row, index) in selectedRows" :key="row.xml_class_id"><span>{{ index + 1 }}. {{ row.homeroom }} · {{ row.subject }} · 第{{ row.ordinal }}课次</span><button type="button" :disabled="index === 0" title="前移" aria-label="前移课次" @click="move(row.xml_class_id, -1)"><ArrowUp :size="15" /></button><button type="button" :disabled="index === selectedRows.length - 1" title="后移" aria-label="后移课次" @click="move(row.xml_class_id, 1)"><ArrowDown :size="15" /></button></div>
            </details>
            <p v-if="!supported" class="wizard-warning">该规则尚无可执行算法，暂不能创建。</p>
            <details v-if="resolution?.warnings?.length" class="wizard-warning"><summary>部分课次未纳入</summary><p v-for="(warning, index) in resolution.warnings" :key="index">{{ warning.homeroom }} {{ warning.subject }} {{ warning.reason }}</p></details>
          </template>
        </section>
      </fieldset>
      <p v-if="error" class="wizard-error" role="alert">{{ error }}</p>
      <p v-if="notice" class="wizard-success" role="status">{{ notice }}</p>
      <footer v-if="rows.length" class="wizard-footer">
        <div><strong>{{ selectedTitle }}</strong><span>{{ required ? '必须满足' : `尽量满足 · 优先级 ${penalty}` }} · {{ selected.length }} 个课次 · {{ groupCount }} 组</span><small v-if="selectionError" class="wizard-warning">{{ selectionError }}</small></div>
        <button type="button" class="btn-primary" :disabled="!!busy || !supported || !!selectionError || !validParameters" @click="create">下一步：相似扩展</button>
      </footer>
      </template>
    </template>
  </div>
</template>

<style scoped>
.constraint-ai-wizard { display: block; flex: 1; width: 100%; height: 100%; min-width: 0; min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: none; padding: 18px 20px; box-sizing: border-box; background: #fff; color: #29443e; font-size: 14px; container-type: inline-size; }
.constraint-ai-wizard::-webkit-scrollbar { display: none; }
fieldset { min-width: 0; padding: 0; margin: 0; border: 0; }
.wizard-step { padding: 0 0 20px; margin-bottom: 20px; border-bottom: 1px solid #e1e9e5; }
.wizard-step:last-child { margin-bottom: 0; }
.step-pending { color: #7d8b83; }
h3 { display: flex; align-items: center; gap: 10px; font-size: 16px; margin: 0 0 14px; }
h3 > span { display: grid; place-items: center; width: 24px; height: 24px; background: #edf4f1; color: #267663; border-radius: 50%; font-size: 13px; }
.wizard-search { display: flex; border: 1px solid #b9cfc6; border-radius: 6px; overflow: hidden; background: white; }
.wizard-search:focus-within { border-color: #2d8270; box-shadow: 0 0 0 2px #2d82701a; }
.wizard-search input { flex: 1; min-width: 0; width: 0; border: 0; outline: none; box-shadow: none; border-radius: 0; padding: 12px; font-size: 14px; }
.wizard-search button { flex: 0 0 44px; display: grid; place-items: center; border: 0; border-radius: 0; background: transparent; color: #2d7767; padding: 0; }
.wizard-rules { display: grid; gap: 8px; margin: 12px 0; }
.wizard-rules button { display: grid; gap: 6px; width: 100%; padding: 12px; text-align: left; background: #fff; border: 1px solid #dae4df; border-radius: 6px; color: #38584c; font-weight: 400; line-height: 1.5; }
.wizard-rules button > span, .wizard-rules small { overflow-wrap: anywhere; }
.rule-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.rule-top strong { flex: 1; font-size: 14px; }
.rule-top small { font-size: 11px; background: #e6f3eb; color: #24714e; padding: 2px 6px; border-radius: 3px; }
.rule-top small.partial { color: #8c631b; background: #fff4d9; }
.wizard-rules button > small { color: #6d7c75; font-size: 12px; }
.wizard-rules button.selected { border-color: #32846e; background: #f4faf6; }
.wizard-strength { display: flex; gap: 8px; }
.wizard-strength button { padding: 9px 18px; background: #f8faf9; color: #566960; border: 1px solid #d9e4de; border-radius: 5px; font-size: 14px; }
.wizard-strength .selected { color: #21634f; border-color: #398670; background: #edf6f0; }
.wizard-priority { display: flex; gap: 12px; align-items: center; margin-top: 12px; }
select { min-width: 0; max-width: 100%; border: 1px solid #d6e0da; border-radius: 5px; padding: 8px; color: #3d5d50; background: white; font-size: 13px; }
.wizard-message, .wizard-interpretation { font-size: 13px; line-height: 1.7; color: #697b72; margin: 12px 0; }
.wizard-message button { display: inline-flex; gap: 8px; align-items: center; white-space: normal; }
.wizard-selection-tools { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 12px 0; font-size: 12px; }
.wizard-selection-tools label { display: flex; align-items: center; gap: 6px; }
input[type=checkbox] { width: 16px; height: 16px; padding: 0; flex: none; accent-color: #2d8270; }
.wizard-selection-tools select { margin-left: auto; }
.wizard-table-wrap { max-height: 260px; overflow: auto; overscroll-behavior: contain; border: 1px solid #e0e7e3; }
table { width: 100%; min-width: 440px; border-collapse: collapse; font-size: 12px; }
th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid #e5ebe7; }
th { position: sticky; top: 0; background: #f2f6f3; font-weight: 600; white-space: nowrap; }
.wizard-clarify { display: grid; gap: 8px; }
.wizard-clarify button { white-space: normal; text-align: left; }
.wizard-footer { display: flex; flex-wrap: wrap; gap: 14px; justify-content: space-between; align-items: center; padding: 16px 0 0; }
.wizard-footer > div { display: grid; gap: 5px; flex: 1 1 180px; min-width: 0; overflow-wrap: anywhere; }
.wizard-footer strong { font-size: 14px; }.wizard-footer span { font-size: 12px; color: #6b7c72; }
.wizard-footer button { flex: none; font-size: 14px; }
.wizard-warning { color: #916122; font-size: 12px; line-height: 1.6; margin-top: 10px; }
.wizard-error { color: #a43f33; background: #fff3ef; padding: 10px; font-size: 13px; overflow-wrap: anywhere; }
.wizard-success { color: #24684b; background: #edf7ef; padding: 10px; }
.wizard-locked { display: flex; flex-direction: column; gap: 14px; align-items: center; justify-content: center; min-height: 260px; text-align: center; }
.wizard-locked p { margin: 0; font-size: 13px; color: #728177; }
.wizard-order { font-size: 12px; margin-top: 12px; }.wizard-order > div { display: flex; align-items: center; gap: 6px; padding: 6px 0; }.wizard-order span { flex: 1; }.wizard-order button { display: grid; place-items: center; padding: 5px; background: white; border: 1px solid #d8e3dc; color: #476a5a; }
@container (max-width: 430px) { .wizard-selection-tools select { flex-basis: 100%; margin-left: 0; }.wizard-footer > button { width: 100%; } }
</style>
<style scoped src="../styles/aiCreatorLayout.css"></style>
