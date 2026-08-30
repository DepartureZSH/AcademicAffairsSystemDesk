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
  <section class="module-view">
    <div class="module-heading">
      <div><p class="eyebrow">LOCAL CP-SAT</p><h2>排课运行与候选方案</h2><p>输入快照、求解算法、候选课表和诊断日志全部保存在当前项目。</p></div>
      <span>Revision {{ revision }}</span>
    </div>

    <div class="invariant-banner"><strong>本地算法门禁</strong><span>只有完整满足硬约束的结果才会保存为候选；无解轮次只留下可定位诊断。</span></div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <article class="panel run-result-panel" :class="{ 'error-panel': preflight && !preflight.ready }">
      <div class="panel-heading"><div><p class="eyebrow">DATA PREFLIGHT</p><h3>运行前数据预检</h3></div><button class="secondary-button" :disabled="busy || Boolean(activeRound)" @click="runPreflight">{{ busy ? "检查中…" : "立即检查" }}</button></div>
      <p v-if="!preflight">只读编译当前项目，检查课时平衡、教师与教室引用、可用课节和约束编译；不会创建轮次或修改 Revision。</p>
      <template v-else>
        <p>{{ preflight.ready ? "预检通过，可以启动本地排课。" : `发现 ${preflight.summary.errorCount} 个阻断问题。` }} 活跃任务 {{ preflight.summary.activeTaskCount }} 个、课次 {{ preflight.summary.activeLessonCount }} 个、可选位置 {{ preflight.summary.optionCount }} 个。</p>
        <ul v-if="preflight.errors.length" class="diagnostic-list"><li v-for="(item, index) in preflight.errors.slice(0, 12)" :key="`error-${index}`">{{ item.message || item.code }}</li></ul>
        <ul v-if="preflight.warnings.length" class="diagnostic-list"><li v-for="(item, index) in preflight.warnings.slice(0, 8)" :key="`warning-${index}`">警告：{{ item.message || item.code }}</li></ul>
      </template>
    </article>

    <div class="directory-layout planning-layout">
      <article class="panel data-panel">
        <p class="eyebrow">OPTIMIZATION ROUND</p><h3>{{ selectedCandidateCanWarmStart ? "基于候选继续优化" : "开始新的优化会话" }}</h3>
        <form class="compact-form" @submit.prevent="runRound">
          <label v-if="!selectedCandidateCanWarmStart">会话名称<input v-model="sessionName" maxlength="200" required /></label>
          <label v-else>Warm start 候选<input :value="`${selectedCandidate?.id.slice(0, 8)} · 得分 ${selectedCandidate?.total_score}`" disabled /></label>
          <p v-if="selectedCandidate?.based_on_old_data" class="form-copy">所选候选基于旧 Revision，只能查看；本轮将在当前数据上创建新会话。</p>
          <p v-else-if="selectedCandidate && selectedCandidate.status !== 'valid'" class="form-copy">所选历史候选含硬约束违例或已被替代，不能作为 Warm start；本轮将创建新会话。</p>
          <div class="inline-fields">
            <label>本轮时长（秒）<input v-model.number="timeBudgetSeconds" type="number" min="10" max="1800" /></label>
            <label>随机种子<input v-model.number="randomSeed" type="number" min="0" max="2147483647" /></label>
          </div>
          <button class="primary-button" :disabled="busy || Boolean(activeRound)">
            {{ busy ? "正在启动…" : activeRound ? "本机算法进程运行中" : selectedCandidateCanWarmStart ? "以上一候选继续优化" : "生成第一轮候选" }}
          </button>
          <button v-if="activeRound" type="button" class="secondary-button" :disabled="busy" @click="cancelRound">取消当前轮次</button>
          <button v-else-if="selectedCandidateCanWarmStart" type="button" class="text-button" :disabled="busy" @click="selectedCandidateId = ''">改为新建会话</button>
        </form>
        <div v-if="activeRound" class="solver-progress" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100"><span :style="{ width: `${progressPercent}%` }"></span></div>
        <p class="form-copy">默认 60 秒。算法在独立本机进程运行；界面保持可用，取消不会保存半成品候选。</p>
      </article>

      <article class="panel data-panel records-panel">
        <div class="panel-heading"><div><p class="eyebrow">CANDIDATES</p><h3>候选方案</h3></div><span>{{ candidates.length }} 个</span></div>
        <p v-if="candidates.length === 0" class="empty-copy">尚无候选。请先完成作息、教学任务和硬约束配置。</p>
        <div v-else class="data-list tall-list">
          <button
            v-for="item in candidates"
            :key="item.id"
            class="data-row candidate-row"
            :class="{ selected: selectedCandidateId === item.id }"
            @click="selectedCandidateId = item.id"
          >
            <span><strong>{{ item.status !== 'valid' || item.based_on_old_data ? '只读' : '可用' }} · 得分 {{ item.total_score }} · {{ item.entry_count }} 课次</strong><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }} · {{ item.based_on_old_data ? '旧数据' : item.parent_candidate_id ? '续轮优化' : '首轮' }}</small></span>
            <b>{{ selectedCandidateId === item.id ? "已选" : "选择" }}</b>
          </button>
        </div>
      </article>
    </div>

    <article v-if="selectedCandidate" class="panel score-breakdown-panel">
      <div class="panel-heading"><div><p class="eyebrow">SCORE EXPLANATION</p><h3>候选评分说明</h3></div><span>总分 {{ selectedCandidate.total_score }}</span></div>
      <div class="score-breakdown-grid">
        <div v-for="item in scoreComponents" :key="item.key"><small>{{ item.label }}</small><strong>{{ item.value }}</strong></div>
        <div><small>硬约束违例</small><strong>{{ Number(selectedCandidate.hard_violations ?? 0) }}</strong></div>
        <div><small>求解耗时</small><strong>{{ Math.round(Number(selectedMetrics.elapsed_ms ?? 0)) }} ms</strong></div>
        <div><small>求解器候选数</small><strong>{{ Number(selectedMetrics.candidate_count ?? 0) }}</strong></div>
      </div>
      <p :class="scoreComponentsTotal === selectedCandidate.total_score ? 'score-consistent' : 'score-warning'">
        {{ scoreComponentsTotal === selectedCandidate.total_score ? `总分 = ${scoreComponentsTotal}，由三类软约束罚分相加；越低越优。` : `评分组成 ${scoreComponentsTotal} 与总分 ${selectedCandidate.total_score} 不一致，请保留项目并报告问题。` }}
      </p>
    </article>

    <article v-if="latestRound" class="panel run-result-panel" :class="{ 'error-panel': latestRound.status !== 'succeeded' }">
      <div class="panel-heading"><div><p class="eyebrow">LATEST ROUND</p><h3>{{ statusLabel(latestRound.status) }}</h3></div><span>{{ latestRound.id.slice(0, 8) }}</span></div>
      <p>{{ latestRound.error_message || (latestRound.status === 'succeeded' ? `已保存候选，得分 ${latestRound.total_score ?? 0}` : '本轮没有创建候选。') }}</p>
      <ul v-if="diagnostics(latestRound).length" class="diagnostic-list">
        <li v-for="(item, index) in diagnostics(latestRound).slice(0, 8)" :key="index">
          {{ item.message || item.summary || item.constraintName || item.code }}
        </li>
      </ul>
    </article>

    <article class="panel history-panel">
      <div class="panel-heading"><div><p class="eyebrow">ROUND HISTORY</p><h3>轮次记录</h3></div><span>{{ rounds.length }} 轮</span></div>
      <div class="data-list">
        <div v-for="item in rounds" :key="item.id" class="data-row">
          <span><strong>{{ statusLabel(item.status) }}</strong><small>{{ item.time_budget_seconds }} 秒 · Seed {{ item.random_seed }} · {{ item.created_at }}</small></span>
          <b v-if="item.candidate_id">得分 {{ item.total_score }}</b><b v-else>无候选</b>
        </div>
      </div>
    </article>
  </section>
</template>
