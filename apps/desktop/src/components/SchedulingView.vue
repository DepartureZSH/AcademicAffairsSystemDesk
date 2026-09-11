<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
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
}[status] ?? status);

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
    const parent = selectedCandidateCanWarmStart.value ? selectedCandidate.value : null;
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
  if (activeRound.value) ensurePolling();
});
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<template>
  <section class="module-view runs-dashboard">
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>
    <article class="run-card run-status-card"><div class="run-card-heading"><div><span>当前状态</span><h2>{{ currentStatus }}</h2></div><strong>本地自动排课</strong></div><p>{{ activeRound ? '正在根据课程计划和约束生成课表，请稍候。' : candidates.length ? '已生成可用候选课表，可以继续优化或查看结果。' : '完成数据准备后即可发起排课。' }}</p><div class="run-stage-pill">{{ currentStage }}</div><div class="run-progress-track"><span :style="{ width: `${activeRound ? progressPercent : candidates.length ? 100 : 0}%` }"></span></div><div class="run-step-list"><div class="run-step step-complete"><span></span><strong>准备输入</strong></div><div class="run-step" :class="activeRound ? 'step-active' : candidates.length ? 'step-complete' : ''"><span></span><strong>运行算法</strong></div><div class="run-step" :class="candidates.length ? 'step-complete' : ''"><span></span><strong>校验结果</strong></div></div><div class="run-card-actions"><button v-if="!activeRound" class="primary-button" :disabled="busy" @click="runRound">{{ selectedCandidateCanWarmStart ? '继续优化' : candidates.length ? '重新排课' : '发起排课' }}</button><button v-if="activeRound" class="secondary-button" :disabled="busy" @click="cancelRound">停止排课</button></div></article>

    <article class="run-card run-input-summary"><div class="run-card-heading"><div><span>排课输入</span><h2>{{ preflight ? '输入摘要' : '等待检查' }}</h2></div><button class="secondary-button" :disabled="busy || Boolean(activeRound)" @click="runPreflight">{{ busy ? '检查中…' : '检查数据' }}</button></div><div class="run-stat-grid"><div><span>课次</span><strong>{{ preflight?.summary.activeLessonCount ?? '-' }}</strong></div><div><span>教学任务</span><strong>{{ preflight?.summary.activeTaskCount ?? '-' }}</strong></div><div><span>可选位置</span><strong>{{ preflight?.summary.optionCount ?? '-' }}</strong></div></div></article>

    <article class="run-card run-result-card"><div class="run-card-heading"><div><span>运行结果</span><h2>{{ latestRound ? statusLabel(latestRound.status) : candidates.length ? '已有候选方案' : '等待排课' }}</h2></div></div><p>{{ latestRound?.error_message || (latestRound?.status === 'succeeded' ? `已保存候选，得分 ${latestRound.total_score ?? 0}` : candidates.length ? `共保存 ${candidates.length} 个候选方案。` : '排课完成后在下方查看候选课表。') }}</p><div v-if="candidates.length" class="candidate-selector"><button v-for="item in candidates" :key="item.id" :class="{ active: selectedCandidateId === item.id }" @click="selectedCandidateId = item.id"><strong>{{ item.name || '候选方案' }}</strong><span>得分 {{ item.total_score }} · {{ item.entry_count }} 课次</span></button></div></article>

    <article class="run-card validation-card" :class="{ 'validation-error': preflight && !preflight.ready }"><div class="run-card-heading"><div><span>校验结果</span><h2>{{ preflight ? preflight.ready ? '检查通过' : '需要处理' : '尚未检查' }}</h2></div><button class="secondary-button" :disabled="busy" @click="runPreflight">重新校验</button></div><p>{{ preflight ? preflight.ready ? '当前项目可以发起排课。' : `当前项目有 ${preflight.summary.errorCount} 个问题需要处理。` : '检查课程计划、教师、教室、课节和约束是否完整。' }}</p><div v-if="selectedCandidate" class="validation-stat-grid"><div><span>质量</span><strong>{{ selectedCandidate.total_score }}</strong></div><div><span>课次</span><strong>{{ selectedCandidate.entry_count }}</strong></div><div><span>硬约束</span><strong>{{ selectedCandidate.hard_violations ?? 0 }}</strong></div></div><details v-if="preflight?.errors.length" class="validation-issue-group"><summary>需要处理的问题 <strong>{{ preflight.errors.length }} 项</strong></summary><ul class="diagnostic-list"><li v-for="(item, index) in preflight.errors" :key="index">{{ item.message || item.code }}</li></ul></details><details v-if="selectedCandidate" class="validation-issue-group"><summary>质量明细 <strong>展开/收起</strong></summary><div class="score-breakdown-grid"><div v-for="item in scoreComponents" :key="item.key"><small>{{ item.label }}</small><strong>{{ item.value }}</strong></div></div></details></article>

    <article class="run-card run-settings-card"><div class="run-card-heading"><div><span>排课设置</span><h2>{{ selectedCandidateCanWarmStart ? '继续优化当前方案' : '开始新的排课' }}</h2></div></div><form class="run-settings-form" @submit.prevent="runRound"><label>方案名称<input v-model="sessionName" maxlength="200" :disabled="selectedCandidateCanWarmStart" required /></label><label>计算时长<input v-model.number="timeBudgetSeconds" type="number" min="10" max="1800" /><span>秒</span></label><button class="primary-button" :disabled="busy || Boolean(activeRound)">{{ activeRound ? '正在排课…' : selectedCandidateCanWarmStart ? '继续优化' : '开始排课' }}</button></form></article>

    <details v-if="rounds.length" class="run-card run-history-card"><summary>排课记录（{{ rounds.length }} 次）</summary><div class="data-list"><div v-for="item in rounds" :key="item.id" class="data-row"><span><strong>{{ statusLabel(item.status) }}</strong><small>计算 {{ item.time_budget_seconds }} 秒 · {{ item.created_at }}</small></span><b v-if="item.candidate_id">得分 {{ item.total_score }}</b><b v-else>无候选</b></div></div></details>
  </section>
</template>
