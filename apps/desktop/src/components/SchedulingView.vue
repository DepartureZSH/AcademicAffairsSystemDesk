<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { CalendarDays, CircleStop, Play } from 'lucide-vue-next';
import RunDashboardCards from '../web-workflows/RunDashboardCards.vue';
import type { RunCardState } from '../web-workflows/runTypes';
import TimetableView from './TimetableView.vue';
import '../web-workflows/web-workflows.css';
import {
  formatLocalError,
  localApi,
  type PreflightValidation,
  type SchedulingCandidate,
  type SchedulingRound,
} from "../lib/sidecar";

const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();

const revision = ref(props.revision);
const rounds = ref<SchedulingRound[]>([]);
const candidates = ref<SchedulingCandidate[]>([]);
const selectedCandidateId = ref("");
const timeBudgetSeconds = ref(60);
const randomSeed = ref(0);
const sessionName = ref("本地优化会话");
const busy = ref(false);
const errorMessage = ref("");
const latestRound = ref<SchedulingRound | null>(null);
const preflight = ref<PreflightValidation | null>(null);
const inputCounts = ref({rooms: 0, constraints: 0, teachers: 0, homerooms: 0});
const showPreflight = ref(false);
const preflightStep = ref(0);
const optimizationMode = ref(false);
const steps = ['选择算法', '检查数据', '确认排课'];
const resultElement = ref<HTMLElement | null>(null);
let pollTimer: ReturnType<typeof setInterval> | null = null;

watch(() => props.revision, (value) => {
  if (revision.value !== value) preflight.value = null;
  revision.value = value;
});

const selectedCandidate = computed(() =>
  candidates.value.find((item) => item.id === selectedCandidateId.value) ?? null,
);
const selectedCandidateCanWarmStart = computed(() =>
  selectedCandidate.value?.status === "valid" && !selectedCandidate.value.based_on_old_data,
);
const selectedMetrics = computed(() => selectedCandidate.value?.metrics ?? {});
const scoreComponents = computed(() => [
  { key: "time_penalty", label: "时间偏好", value: selectedMetrics.value.time_penalty ?? 0 },
  { key: "room_penalty", label: "教室偏好", value: selectedMetrics.value.room_penalty ?? 0 },
  { key: "distribution_penalty", label: "分散/负载", value: selectedMetrics.value.distribution_penalty ?? 0 },
]);
const scoreComponentsTotal = computed(() => scoreComponents.value.reduce((sum, item) => sum + item.value, 0));
const activeRound = computed(() => {
  const active = new Set(["queued", "preparing", "solving", "validating"]);
  return rounds.value.find((item) => active.has(item.status)) ??
    (latestRound.value && active.has(latestRound.value.status) ? latestRound.value : null);
});
const progressPercent = computed(() => {
  const item = activeRound.value;
  if (!item) return 0;
  if (item.status === "preparing" || item.status === "queued") return 3;
  if (item.status === "validating") return 97;
  const started = item.started_at ? new Date(String(item.started_at)).getTime() : Date.now();
  const budget = Number(item.time_budget_seconds || 60) * 1000;
  return Math.max(5, Math.min(95, Math.round(((Date.now() - started) / budget) * 90 + 5)));
});
const currentStatus = computed(() => activeRound.value ? statusLabel(activeRound.value.status) : latestRound.value ? statusLabel(latestRound.value.status) : candidates.value.length ? "排课完成" : "尚未开始");
const currentStage = computed(() => activeRound.value ? "正在计算" : latestRound.value?.status === "succeeded" || candidates.value.length ? "结果已保存" : "等待发起");

const statusLabel = (status: string) => ({
  succeeded: "已生成候选",
  infeasible: "硬约束无解",
  failed_recoverable: "运行失败，可重试",
  cancelled: "已取消",
  solving: "正在求解",
  preparing: "正在准备",
  queued: '等待运行', validating: '校验结果', interrupted: '运行已中断',
}[status] ?? '运行结束');

const cardState = computed<RunCardState>(() => {
  const candidate = selectedCandidate.value;
  const round = activeRound.value ?? latestRound.value ?? rounds.value[0];
  const succeeded = round?.status === 'succeeded';
  const failures = preflight.value?.errors ?? [];
  const conflicts = round ? diagnostics(round) : [];
  return {
    run: round ? {status: round.status === 'failed_recoverable' || round.status === 'infeasible' ? 'failed' : round.status} : null,
    active: Boolean(activeRound.value), optimizing: Boolean(activeRound.value && optimizationMode.value), busy: busy.value,
    progress: activeRound.value ? progressPercent.value : succeeded ? 100 : 0, candidateId: candidate?.id ?? '',
    display: {tone: activeRound.value ? 'running' : succeeded ? 'success' : round ? 'warning' : 'idle', label: round ? statusLabel(round.status) : '尚未开始',
      algorithm: '约束优化排课', description: activeRound.value ? '正在根据课程计划和约束生成课表，请稍候。' : round?.error_message || '选择排课算法，检查数据后发起排课。',
      stage: activeRound.value ? statusLabel(activeRound.value.status) : succeeded ? '结果已保存' : '等待发起', hasSolution: Boolean(candidate)},
    steps: ['准备输入', '运行算法', '校验结果'].map((label,index) => ({label, state: succeeded ? 'complete' : activeRound.value ? (index === (activeRound.value.status === 'validating' ? 2 : activeRound.value.status === 'solving' ? 1 : 0) ? 'active' : 'pending') : 'pending'})),
    input: {generated: Boolean(preflight.value), classText: preflight.value?.summary.activeLessonCount ?? '—', roomText: inputCounts.value.rooms, constraintText: inputCounts.value.constraints},
    result: {title: round ? statusLabel(round.status) : '等待排课', detail: round?.error_message || (candidate ? `已保留 ${candidates.value.length} 个候选方案，选择任一可用方案可继续优化。` : '排课完成后，候选课表会直接显示在下方。')},
    validation: {tone: failures.length ? 'error' : candidate?.status === 'valid' ? 'success' : 'idle', title: failures.length ? '需要处理' : candidate ? '校验完成' : preflight.value?.ready ? '检查通过' : '尚未检查',
      detail: failures.length ? `有 ${failures.length} 个问题需要处理。` : candidate ? '展示所选候选的校验结果。' : '发起排课前会检查课程计划与约束配置。',
      summary: candidate ? {total_cost: candidate.total_score, missing_time: candidate.metrics.missing_time ?? 0, missing_room: candidate.metrics.missing_room ?? 0,
        hard_violations: candidate.hard_violations, soft_violations: candidate.metrics.soft_violations, time_penalty: candidate.metrics.time_penalty ?? 0,
        room_penalty: candidate.metrics.room_penalty ?? 0, soft_penalty: candidate.metrics.distribution_penalty ?? 0} : null,
      qualityItems: scoreComponents.value.filter(i => i.value > 0)},
    qualityGroups: candidate ? scoreComponents.value.filter(i => i.value > 0).map(i => ({key:i.key,label:i.label,total:i.value,items:[{title:i.label,detail:'所选候选的累计扣分',penalty:i.value}]})) : [],
    issueGroups: [...failures, ...conflicts].length ? [{key:'input', tone:'error',label:'需要处理的问题',items:[...failures,...conflicts].map(i=>({category:String(i.code ?? 'constraint'),title:String(i.title ?? '排课条件冲突'),detail:String(i.message ?? i.description ?? '请检查关联课次与约束配置'),severity:'error'}))}] : [],
  };
});

async function openPreflight(optimize = false) {
  optimizationMode.value = optimize;
  preflightStep.value = 0;
  showPreflight.value = true;
  await runPreflight();
}
async function confirmRun() {
  await runRound();
  if (!errorMessage.value && preflight.value?.ready) showPreflight.value = false;
}
function locateResult() { resultElement.value?.scrollIntoView({behavior:'smooth',block:'start'}); }

function diagnostics(round: SchedulingRound): Array<Record<string, unknown>> {
  const events = Array.isArray(round.events) ? round.events : [];
  const item = events.find((event) => event.event_type === "infeasible_diagnostics");
  const payload = item?.payload as Record<string, unknown> | undefined;
  return Array.isArray(payload?.conflicts) ? payload.conflicts as Array<Record<string, unknown>> : [];
}

async function loadRuns() {
  errorMessage.value = "";
  try {
    const [roundResult, candidateResult] = await Promise.all([
      localApi.listSchedulingRounds(),
      localApi.listSchedulingCandidates(),
    ]);
    rounds.value = roundResult.items;
    candidates.value = candidateResult.items;
    if (!selectedCandidateId.value && candidates.value.length) selectedCandidateId.value = candidates.value[0].id;
    const running = rounds.value.find((item) => ["queued", "preparing", "solving", "validating"].includes(item.status));
    if (running) latestRound.value = running;
    revision.value = Math.max(roundResult.revision, candidateResult.revision);
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  }
}

function ensurePolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const watchedId = latestRound.value?.id;
    await loadRuns();
    if (watchedId) {
      latestRound.value = rounds.value.find((item) => item.id === watchedId) ?? latestRound.value;
    }
    if (!activeRound.value && pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
      const candidateId = latestRound.value?.candidate_id;
      if (candidateId) selectedCandidateId.value = candidateId;
    }
  }, 1000);
}

async function runRound() {
  busy.value = true;
  errorMessage.value = "";
  latestRound.value = null;
  try {
    preflight.value = await localApi.validateProject();
    if (!preflight.value.ready) {
      errorMessage.value = `数据预检发现 ${preflight.value.summary.errorCount} 个阻断问题，请先修复后再运行。`;
      return;
    }
    const parent = optimizationMode.value && selectedCandidateCanWarmStart.value ? selectedCandidate.value : null;
    const result = await localApi.runSchedulingRound({
      timeBudgetSeconds: timeBudgetSeconds.value,
      randomSeed: randomSeed.value,
      sessionId: parent?.session_id,
      parentCandidateId: parent?.id,
      name: parent ? undefined : sessionName.value.trim(),
    });
    latestRound.value = result.round;
    revision.value = result.revision;
    emit("revision", revision.value);
    await loadRuns();
    if (["queued", "preparing", "solving", "validating"].includes(result.round.status)) ensurePolling();
    else if (result.round.candidate_id) selectedCandidateId.value = result.round.candidate_id;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function runPreflight() {
  busy.value = true;
  errorMessage.value = "";
  try {
    preflight.value = await localApi.validateProject();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

async function cancelRound() {
  const item = activeRound.value;
  if (!item) return;
  busy.value = true;
  errorMessage.value = "";
  try {
    const result = await localApi.cancelSchedulingRound(item.id);
    latestRound.value = result.round;
    await loadRuns();
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  await loadRuns();
  try {
    const results = await Promise.all(['room','constraint','teacher','homeroom'].map(type => localApi.listEntities(type)));
    inputCounts.value = {rooms: results[0].items.length, constraints: results[1].items.filter(i=>i.enabled !== 0).length, teachers:results[2].items.length, homerooms:results[3].items.length};
  } catch(error) { errorMessage.value = formatLocalError(error); }
  if (activeRound.value) ensurePolling();
});
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<template>
  <div class="web-workflow desktop-runs-page">
    <header class="section-heading"><h2>排课运行</h2><div class="sheet-actions"><button v-if="!activeRound" type="button" :disabled="busy" @click="openPreflight(false)"><Play :size="16" />发起排课</button><button v-else type="button" class="btn-secondary" :disabled="busy" @click="cancelRound"><CircleStop :size="16" />停止排课</button></div></header>
    <p v-if="errorMessage" class="form-message error-copy" role="alert">{{ errorMessage }}</p>
    <section class="runs-dashboard">
      <RunDashboardCards :state="cardState" @optimize="openPreflight(true)" @restart="openPreflight(false)" @cancel="cancelRound" @locate="locateResult" @validate="runPreflight" />
      <article ref="resultElement" class="run-card run-timetable-card">
        <h2>候选课表</h2>
        <template v-if="candidates.length">
          <label class="local-candidate-select">候选方案<select v-model="selectedCandidateId"><option v-for="c in candidates" :key="c.id" :value="c.id">{{ c.name || '候选方案' }} · 得分 {{ c.total_score }} · {{ c.entry_count }} 课次</option></select></label>
          <p v-if="selectedCandidate?.based_on_old_data" class="local-run-notice">此方案基于旧数据，请重新排课后再继续优化。</p>
          <TimetableView :key="selectedCandidateId" embedded :initial-candidate-id="selectedCandidateId" :revision="revision" @revision="emit('revision', $event)" @candidate="selectedCandidateId = $event" />
        </template>
        <div v-else class="empty-timetable-state"><CalendarDays :size="32" :stroke-width="1.5" aria-hidden="true" /><strong>尚未生成候选课表</strong><p>发起排课完成后，候选课表会直接显示在这里。</p><button type="button" :disabled="busy || Boolean(activeRound)" @click="openPreflight(false)">发起排课</button></div>
      </article>
      <details v-if="rounds.length" class="run-card local-run-history"><summary>排课记录（{{ rounds.length }} 次）</summary><div v-for="item in rounds" :key="item.id" class="local-run-history-row"><strong>{{ statusLabel(item.status) }}</strong><span>{{ item.created_at }}</span><span>计算 {{ item.time_budget_seconds }} 秒</span><span>{{ item.candidate_id ? `得分 ${item.total_score}` : '未生成候选' }}</span></div></details>
    </section>
    <div v-if="showPreflight" class="bottom-sheet-mask">
      <section class="bottom-sheet run-data-overview-sheet" role="dialog" aria-modal="true" aria-label="排课前数据清单">
        <header class="bottom-sheet-header run-data-sheet-header"><div><span>{{ optimizationMode ? '继续优化' : '发起排课' }}</span><h2>{{ steps[preflightStep] }}</h2></div><div class="run-data-sheet-status" :class="{ready: preflight?.ready}"><strong>{{ busy ? '正在检查数据' : preflight?.ready ? '可以发起排课' : '需要补齐数据' }}</strong></div><button type="button" class="btn-secondary" :disabled="busy" @click="showPreflight = false">关闭</button></header>
        <ol class="run-preflight-steps" aria-label="排课准备进度"><li v-for="(label,index) in steps" :key="label" :class="{current:preflightStep === index,complete:preflightStep > index}" :aria-current="preflightStep === index ? 'step' : undefined"><span>{{ index+1 }}</span>{{ label }}</li></ol>
        <div class="run-data-overview-body">
          <fieldset v-if="preflightStep === 0" class="run-algorithm-selection" :disabled="busy"><legend>选择排课算法</legend><label class="run-algorithm-option selected"><input type="radio" name="scheduling-algorithm" checked /><div><strong>约束优化排课</strong><span class="algorithm-tag">本地运行</span><p>先寻找满足硬约束的课表，再按软约束改善排课质量。</p><small>所有计算均在本机完成，可选择已有候选继续优化。</small></div></label><label class="local-run-budget">每轮计算时长（秒）<input v-model.number="timeBudgetSeconds" type="number" min="10" max="1800" required /></label></fieldset>
          <template v-else-if="preflightStep === 1">
            <section class="run-overview-stat-grid"><article v-for="item in [{label:'课次',value:preflight?.summary.activeLessonCount ?? '—'},{label:'教师',value:inputCounts.teachers},{label:'班级',value:inputCounts.homerooms},{label:'教室',value:inputCounts.rooms}]" :key="item.label" class="run-overview-stat-card"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></article></section>
            <section class="run-overview-issue-panel"><h3>{{ preflight?.ready ? '当前项目可以发起排课' : '当前项目还需要处理以下问题' }}</h3><div class="run-overview-issue-list"><article v-for="(issue,index) in [...(preflight?.errors ?? []),...(preflight?.warnings ?? [])]" :key="index" class="run-overview-issue"><strong>{{ issue.title || '数据检查' }}</strong><span>{{ issue.message || issue.code }}</span></article><p v-if="preflight?.ready && !preflight?.warnings.length">课程计划和约束检查通过。</p></div></section>
            <details class="run-preflight-details"><summary>查看详细数据清单</summary><dl class="run-preflight-summary"><div><dt>教学任务</dt><dd>{{ preflight?.summary.activeTaskCount }}</dd></div><div><dt>课次</dt><dd>{{ preflight?.summary.activeLessonCount }}</dd></div><div><dt>教室</dt><dd>{{ inputCounts.rooms }}</dd></div><div><dt>约束</dt><dd>{{ inputCounts.constraints }}</dd></div></dl></details>
          </template>
          <template v-else><dl class="run-preflight-summary"><div><dt>排课算法</dt><dd>约束优化排课</dd></div><div><dt>本轮时长</dt><dd>{{ timeBudgetSeconds }} 秒</dd></div><div><dt>数据检查</dt><dd>{{ preflight?.ready ? '已通过，可发起排课' : '需要补齐数据' }}</dd></div><div v-if="optimizationMode"><dt>继续优化的方案</dt><dd>{{ selectedCandidate?.name || '所选候选方案' }}</dd></div></dl><label v-if="!optimizationMode">方案名称<input v-model="sessionName" maxlength="200" required /></label><p class="local-run-notice">本轮输入、运行记录和候选结果均保存在本机。原有候选方案不会被覆盖。</p></template>
          <p v-if="errorMessage" class="error-copy" role="alert">{{ errorMessage }}</p>
        </div>
        <footer class="bottom-sheet-footer run-data-sheet-footer"><button v-if="preflightStep === 1" type="button" class="btn-secondary" :disabled="busy" @click="runPreflight">刷新数据清单</button><button v-if="preflightStep > 0" type="button" class="btn-secondary" :disabled="busy" @click="preflightStep--">上一步</button><button v-if="preflightStep < 2" type="button" :disabled="busy || !Number.isInteger(timeBudgetSeconds) || timeBudgetSeconds < 10 || timeBudgetSeconds > 1800 || (preflightStep === 1 && !preflight?.ready)" @click="preflightStep++">下一步</button><button v-else type="button" :disabled="busy || !preflight?.ready || (optimizationMode && !selectedCandidateCanWarmStart) || (!optimizationMode && !sessionName.trim())" @click="confirmRun">{{ busy ? '正在启动…' : '继续排课' }}</button></footer>
      </section>
    </div>
  </div>
</template>
<style scoped>
.sheet-actions button {display:inline-flex;align-items:center;gap:6px;}
.local-candidate-select {display:flex;align-items:center;gap:12px;margin:14px 0;}
.local-run-history {grid-column:1 / -1;}
.local-run-history-row {display:flex;flex-wrap:wrap;gap:18px;padding:12px 0;border-bottom:1px solid #e1e8e4;}
.local-run-notice {padding:12px;background:#f2f7f4;color:#53665e;margin:12px 0;}
.local-run-budget {display:flex;align-items:center;gap:12px;margin-top:20px;}
.web-workflow input[type="radio"] {appearance:auto;width:18px;height:18px;padding:0;margin:0;accent-color:#2f7d6d;flex-shrink:0;}
</style>
