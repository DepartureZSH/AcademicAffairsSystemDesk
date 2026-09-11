<script setup lang="ts">
import { computed, ref } from 'vue';
import { CircleStop, Sparkles } from 'lucide-vue-next';
import type { RunCardState } from '../web-workflows/runTypes';
const props = defineProps<{ state: RunCardState }>();
const emit = defineEmits<{ optimize: []; restart: []; cancel: []; locate: []; validate: [] }>();
const runDisplay = computed(() => props.state.display);
const run = computed(() => props.state.run);
const optimizationActive = computed(() => props.state.optimizing);
const isSchedulingActive = computed(() => props.state.active);
const runProgress = computed(() => props.state.progress);
const solutionId = computed(() => props.state.candidateId);
const runActionLoading = computed(() => props.state.busy);
const runCancelLoading = runActionLoading;
const canStartScheduling = computed(() => !props.state.active && !props.state.busy);
const canLoadSolution = computed(() => Boolean(props.state.candidateId));
const loading = runActionLoading;
const showOptimizationDialog = computed({get: () => false, set: () => emit('optimize')});
const runSteps = computed(() => props.state.steps);
const problemInputSummary = computed(() => props.state.input);
const resultSummary = computed(() => props.state.result);
const validationDisplay = computed(() => props.state.validation);
const validationQualityExpanded = ref(false);
const validationQualityGroups = computed(() => props.state.qualityGroups);
const validationIssueGroups = computed(() => props.state.issueGroups);
const validationIssueDetail = (issue: {detail: string}) => issue.detail;
const validationReasonTitle = (reason: {title: string}) => reason.title;
const validationReasonDetail = (reason: {detail: string}) => reason.detail;
const rerunScheduling = () => emit('restart');
const cancelRun = () => emit('cancel');
const loadSolution = () => emit('locate');
const loadSolutionValidation = () => emit('validate');
</script>

<template>
        <article class="run-card run-status-card" data-guide-id="runs-status" :class="`run-${runDisplay.tone}`">
          <div class="run-card-heading">
            <div>
              <span>当前状态</span>
              <h2>{{ runDisplay.label }}</h2>
            </div>
            <strong>{{ runDisplay.algorithm }}</strong>
          </div>
          <p>{{ runDisplay.description }}</p>
          <div class="run-stage-pill">{{ runDisplay.stage }}</div>
          <div v-if="!optimizationActive" class="run-progress-track in-card" role="progressbar" :aria-valuenow="runProgress" :aria-valuemin="0" :aria-valuemax="100" aria-label="排课进度">
            <span :style="{ width: `${runProgress}%` }"></span>
          </div>
          <div v-if="!isSchedulingActive && run?.status" class="run-card-actions">
            <button v-if="solutionId" type="button" class="btn-primary" :disabled="runActionLoading" @click="showOptimizationDialog = true"><Sparkles :size="16" />继续优化</button>
            <button
              v-if="run?.status === 'succeeded' || run?.status === 'failed' || run?.status === 'cancelled'"
              type="button"
              @click="rerunScheduling"
              :disabled="runActionLoading || !canStartScheduling"
            >
              重新排课
            </button>
          </div>
          <div v-if="optimizationActive" class="run-card-actions"><button type="button" class="btn-secondary" :disabled="runCancelLoading" @click="cancelRun"><CircleStop :size="16" />{{ runCancelLoading ? "停止中" : "停止优化" }}</button></div>
          <div class="run-step-list">
            <div
              v-for="step in runSteps"
              :key="step.label"
              class="run-step"
              :class="`step-${step.state}`"
            >
              <span></span>
              <strong>{{ step.label }}</strong>
            </div>
          </div>
        </article>

        <article class="run-card run-input-summary" data-guide-id="runs-input-summary">
          <div class="run-card-heading">
            <div>
              <span>排课输入</span>
              <h2>{{ problemInputSummary.generated ? "输入摘要" : "等待输入" }}</h2>
            </div>
          </div>
          <div class="run-stat-grid">
            <div>
              <span>课次</span>
              <strong>{{ problemInputSummary.classText }}</strong>
            </div>
            <div>
              <span>教室</span>
              <strong>{{ problemInputSummary.roomText }}</strong>
            </div>
            <div>
              <span>约束</span>
              <strong>{{ problemInputSummary.constraintText }}</strong>
            </div>
          </div>
        </article>

        <article class="run-card run-result-card">
          <div class="run-card-heading">
            <div>
              <span>运行结果</span>
              <h2>{{ resultSummary.title }}</h2>
            </div>
          </div>
          <p>{{ resultSummary.detail }}</p>
          <button
            v-if="runDisplay.hasSolution"
            class="btn-secondary"
            @click="loadSolution"
            :disabled="!canLoadSolution"
          >
            定位到候选课表
          </button>
        </article>

        <article class="run-card validation-card" data-guide-id="runs-validation" :class="`validation-${validationDisplay.tone}`">
          <div class="run-card-heading">
            <div>
              <span>校验结果</span>
              <h2>{{ validationDisplay.title }}</h2>
            </div>
            <button
              v-if="solutionId"
              class="btn-secondary compact-action"
              @click="loadSolutionValidation"
              :disabled="loading"
            >
              重新校验
            </button>
          </div>
          <p>{{ validationDisplay.detail }}</p>
          <div v-if="validationDisplay.summary" class="validation-stat-grid">
            <div>
              <span>质量</span>
              <strong>{{ validationDisplay.summary.total_cost ?? 0 }}</strong>
            </div>
            <div>
              <span>未排入</span>
              <strong>{{ validationDisplay.summary.missing_time }}</strong>
            </div>
            <div>
              <span>无教室</span>
              <strong>{{ validationDisplay.summary.missing_room }}</strong>
            </div>
            <div>
              <span>硬约束</span>
              <strong>{{ validationDisplay.summary.hard_violations }}</strong>
            </div>
            <div>
              <span>软约束</span>
              <strong>{{ validationDisplay.summary.soft_violations ?? '—' }}</strong>
            </div>
          </div>
          <div v-if="validationDisplay.summary" class="validation-cost-line">
            质量由时间优先级 {{ validationDisplay.summary.time_penalty ?? 0 }}、教室选项 {{ validationDisplay.summary.room_penalty ?? 0 }}、软约束 {{ validationDisplay.summary.soft_penalty ?? 0 }} 组成，数值越低越好。
          </div>
          <div v-if="validationDisplay.summary" class="validation-quality-panel">
            <button
              class="quality-toggle"
              type="button"
              @click="validationQualityExpanded = !validationQualityExpanded"
            >
              <span>质量明细</span>
              <strong>{{ validationDisplay.qualityItems.length }} 项惩罚</strong>
              <em>{{ validationQualityExpanded ? "收起" : "展开" }}</em>
            </button>
            <div v-if="validationQualityExpanded" class="quality-detail-list">
              <div v-if="validationQualityGroups.length" class="quality-group-list">
                <section
                  v-for="group in validationQualityGroups"
                  :key="group.key"
                  class="quality-group"
                >
                  <div class="quality-group-heading">
                    <strong>{{ group.label }}</strong>
                    <span>合计 {{ group.total }}</span>
                  </div>
                  <div
                    v-for="item in group.items"
                    :key="`${group.key}-${item.title}-${item.detail}-${item.penalty}`"
                    class="quality-item"
                  >
                    <div>
                      <strong>{{ item.title }}</strong>
                      <span>{{ item.detail }}</span>
                    </div>
                    <b>{{ item.penalty }}</b>
                  </div>
                </section>
              </div>
              <p v-else class="quality-empty">当前没有时间、教室或软约束惩罚项。</p>
            </div>
          </div>
          <div v-if="validationIssueGroups.length" class="validation-issue-groups">
            <details
              v-for="group in validationIssueGroups"
              :key="group.key"
              class="validation-issue-group"
              :class="`issue-group-${group.tone}`"
            >
              <summary>
                <span>{{ group.label }}</span>
                <strong>{{ group.items.length }} 项</strong>
                <em>展开/收起</em>
              </summary>
              <div class="validation-issue-list">
                <div
                  v-for="issue in group.items"
                  :key="`${issue.category}-${issue.title}-${issue.detail}`"
                  class="validation-issue"
                  :class="`issue-${issue.severity}`"
                >
                  <strong>{{ issue.title }}</strong>
                  <span class="validation-issue-summary">{{ validationIssueDetail(issue) }}</span>
                  <div
                    v-if="issue.diagnostic?.reason_groups?.length"
                    class="validation-diagnostic"
                  >
                    <strong class="validation-diagnostic-heading">具体是哪些规则挡住了它：</strong>
                    <div class="validation-diagnostic-list">
                      <div
                        v-for="reason in issue.diagnostic.reason_groups"
                        :key="`${issue.diagnostic.class_id}-${reason.code}-${reason.title}`"
                        class="validation-diagnostic-item"
                      >
                        <span>
                          <strong>{{ validationReasonTitle(reason) }}：</strong>
                          {{ validationReasonDetail(reason) }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </details>
          </div>
        </article>


</template>
