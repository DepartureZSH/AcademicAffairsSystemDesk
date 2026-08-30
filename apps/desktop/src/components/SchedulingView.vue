<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  formatLocalError,
  localApi,
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

watch(() => props.revision, (value) => { revision.value = value; });

const selectedCandidate = computed(() =>
  candidates.value.find((item) => item.id === selectedCandidateId.value) ?? null,
);

const statusLabel = (status: string) => ({
  succeeded: "已生成候选",
  infeasible: "硬约束无解",
  failed_recoverable: "运行失败，可重试",
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
    revision.value = Math.max(roundResult.revision, candidateResult.revision);
    emit("revision", revision.value);
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  }
}

async function runRound() {
  busy.value = true;
  errorMessage.value = "";
  latestRound.value = null;
  try {
    const parent = selectedCandidate.value;
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
    if (result.round.candidate_id) selectedCandidateId.value = result.round.candidate_id;
  } catch (error) {
    errorMessage.value = formatLocalError(error);
  } finally {
    busy.value = false;
  }
}

onMounted(loadRuns);
</script>

<template>
  <section class="module-view">
    <div class="module-heading">
      <div><p class="eyebrow">LOCAL CP-SAT</p><h2>排课运行与候选方案</h2><p>输入快照、求解算法、候选课表和诊断日志全部保存在当前项目。</p></div>
      <span>Revision {{ revision }}</span>
    </div>

    <div class="invariant-banner"><strong>本地算法门禁</strong><span>只有完整满足硬约束的结果才会保存为候选；无解轮次只留下可定位诊断。</span></div>
    <p v-if="errorMessage" class="form-message error-copy">{{ errorMessage }}</p>

    <div class="directory-layout planning-layout">
      <article class="panel data-panel">
        <p class="eyebrow">OPTIMIZATION ROUND</p><h3>{{ selectedCandidate ? "基于候选继续优化" : "开始新的优化会话" }}</h3>
        <form class="compact-form" @submit.prevent="runRound">
          <label v-if="!selectedCandidate">会话名称<input v-model="sessionName" maxlength="200" required /></label>
          <label v-else>Warm start 候选<input :value="`${selectedCandidate.id.slice(0, 8)} · 得分 ${selectedCandidate.total_score}`" disabled /></label>
          <div class="inline-fields">
            <label>本轮时长（秒）<input v-model.number="timeBudgetSeconds" type="number" min="10" max="1800" /></label>
            <label>随机种子<input v-model.number="randomSeed" type="number" min="0" max="2147483647" /></label>
          </div>
          <button class="primary-button" :disabled="busy">
            {{ busy ? "本机求解中…" : selectedCandidate ? "以上一候选继续优化" : "生成第一轮候选" }}
          </button>
          <button v-if="selectedCandidate" type="button" class="text-button" :disabled="busy" @click="selectedCandidateId = ''">改为新建会话</button>
        </form>
        <p class="form-copy">默认 60 秒。运行期间窗口可以继续显示状态，但请不要关闭项目；算法不访问网络。</p>
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
            <span><strong>得分 {{ item.total_score }} · {{ item.entry_count }} 课次</strong><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }} · {{ item.parent_candidate_id ? '续轮优化' : '首轮' }}</small></span>
            <b>{{ selectedCandidateId === item.id ? "已选" : "选择" }}</b>
          </button>
        </div>
      </article>
    </div>

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
