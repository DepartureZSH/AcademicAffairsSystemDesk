<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, ClipboardCheck, DoorOpen, FolderOpen, Headset, Maximize2, Menu, Minimize2, NotebookPen, SlidersHorizontal, UsersRound, X } from "lucide-vue-next";
import AgentConversation from "./AgentConversation.vue";
import ConstraintAiCreator from "./ConstraintAiCreator.vue";
import PlanningAiCreator from "./PlanningAiCreator.vue";
import TimetableAiCreator from "./TimetableAiCreator.vue";
import AgentActionChanges from "./AgentActionChanges.vue";
import { APP_CONTEXT_KEY } from "./appContext";

const {
  activeAgentScene, activeSection, agentSceneOptions, agentSessionLoading, agentStreaming, agentUploading,
  currentProjectName, hasProject, hasOrganization, entitlement, agentUsage, showSection, selectAgentScene,
  agentError, agentActions, agentActionDisplaySummary, agentActionStatusLabel, agentActionTitle,
  openAgentActionDetail, selectedAgentAction, closeAgentActionDetail, agentActionOperationLabel,
  agentActionTargetLabel, agentActionCountItems, agentActionDetailTables, agentActionWarnings,
  agentActionFailures, rejectAgentAction, confirmAgentAction, loading,
} = inject(APP_CONTEXT_KEY)!;
const auditDockOpen = ref(true);
const tokenDetailsOpen = ref(false);
const tokenDetails = ref<HTMLElement | null>(null);
function closeTokenDetailsOutside(event: PointerEvent) {
  if (!tokenDetails.value?.contains(event.target as Node)) tokenDetailsOpen.value = false;
}
function closeTokenDetails() {
  tokenDetailsOpen.value = false;
  tokenDetails.value?.querySelector<HTMLButtonElement>("button")?.focus();
}
const mobileNavigationOpen = defineModel<boolean>("mobileNavigationOpen", { default: false });
const auditGroupOpen = ref<Record<string, boolean>>({ pending: true, incomplete: false, executed: false });
const auditDockPosition = ref({ left: 16, top: 72 });
const auditDockDragged = ref(false);
let auditDragState: { container: HTMLElement; dock: HTMLElement; offsetX: number; offsetY: number } | null = null;
let auditViewportQuery: MediaQueryList | null = null;
const isFullscreen = ref(false);
const sceneIcons = { timetable: CalendarDays, rooms: DoorOpen, school: UsersRound, planning: NotebookPen, constraints: SlidersHorizontal };
const busy = computed(() => agentStreaming.value || agentUploading.value || agentSessionLoading.value);
const tokenUsage = computed(() => {
  const account = agentUsage.value?.entitlement as Record<string, unknown> | undefined;
  const used = account?.token_used == null ? null : Math.max(Number(account.token_used), 0);
  const balance = Math.max(Number(entitlement.value.token_balance || 0), 0);
  return { used, balance, total: used == null ? null : used + balance };
});
const formatTokens = (value: number | null) => value == null ? "--" : value.toLocaleString("zh-CN");
const tokenUsagePercent = computed(() => tokenUsage.value.total == null ? null
  : tokenUsage.value.total > 0 ? Math.min(100, tokenUsage.value.used! / tokenUsage.value.total * 100) : 0);
const tokenUsagePercentLabel = computed(() => tokenUsagePercent.value == null ? "--"
  : `${Number(tokenUsagePercent.value.toFixed(2))}%`);
const auditGroups = computed(() => [
  {
    key: "pending",
    label: "待审核",
    actions: agentActions.value.filter((action) => ["pending_confirmation", "executing", "needs_resolution"].includes(String(action.status || "pending_confirmation"))),
  },
  {
    key: "incomplete",
    label: "未完成",
    actions: agentActions.value.filter((action) => ["failed", "stale", "superseded", "rejected"].includes(String(action.status))),
  },
  {
    key: "executed",
    label: "已执行",
    actions: agentActions.value.filter((action) => String(action.status) === "executed"),
  },
]);
const pendingAuditCount = computed(() => auditGroups.value[0].actions.length);
const auditDockStyle = computed(() => ({
  left: `${auditDockPosition.value.left}px`,
  top: `${auditDockPosition.value.top}px`,
}));
let previousBodyOverflow = "";
watch(isFullscreen, (value) => {
  if (value) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  } else {
    document.body.style.overflow = previousBodyOverflow;
  }
});
function handleFullscreenKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && isFullscreen.value) isFullscreen.value = false;
}
function handleAuditViewportChange(event: MediaQueryListEvent | MediaQueryList) {
  if (event.matches) auditDockOpen.value = false;
}
onMounted(() => {
  document.addEventListener("pointerdown", closeTokenDetailsOutside);
  document.addEventListener("keydown", handleFullscreenKeydown);
  auditViewportQuery = window.matchMedia("(max-width: 760px)");
  handleAuditViewportChange(auditViewportQuery);
  auditViewportQuery.addEventListener("change", handleAuditViewportChange);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", closeTokenDetailsOutside);
  document.removeEventListener("keydown", handleFullscreenKeydown);
  auditViewportQuery?.removeEventListener("change", handleAuditViewportChange);
  auditViewportQuery = null;
  stopAuditDockDrag();
  if (isFullscreen.value) document.body.style.overflow = previousBodyOverflow;
});
function toggleAuditGroup(key: string) {
  auditGroupOpen.value = { ...auditGroupOpen.value, [key]: !auditGroupOpen.value[key] };
}
function startAuditDockDrag(event: PointerEvent) {
  if (event.button !== 0) return;
  const target = event.currentTarget as HTMLElement;
  const dock = target.closest<HTMLElement>(".agent-audit-dock");
  const container = dock?.closest<HTMLElement>(".agent-simple-chat");
  if (!dock || !container) return;
  const dockRect = dock.getBoundingClientRect();
  auditDragState = {
    container,
    dock,
    offsetX: event.clientX - dockRect.left,
    offsetY: event.clientY - dockRect.top,
  };
  auditDockDragged.value = false;
  document.addEventListener("pointermove", moveAuditDock);
  document.addEventListener("pointerup", stopAuditDockDrag);
  event.preventDefault();
}
function moveAuditDock(event: PointerEvent) {
  if (!auditDragState) return;
  const { container, dock, offsetX, offsetY } = auditDragState;
  const bounds = container.getBoundingClientRect();
  const nextLeft = event.clientX - bounds.left - offsetX;
  const nextTop = event.clientY - bounds.top - offsetY;
  auditDockDragged.value ||= Math.abs(nextLeft - auditDockPosition.value.left) > 4 || Math.abs(nextTop - auditDockPosition.value.top) > 4;
  auditDockPosition.value = {
    left: Math.max(8, Math.min(nextLeft, bounds.width - dock.offsetWidth - 8)),
    top: Math.max(8, Math.min(nextTop, bounds.height - dock.offsetHeight - 8)),
  };
}
function stopAuditDockDrag() {
  auditDragState = null;
  document.removeEventListener("pointermove", moveAuditDock);
  document.removeEventListener("pointerup", stopAuditDockDrag);
}
function openAuditDock() {
  if (auditDockDragged.value) {
    auditDockDragged.value = false;
    return;
  }
  auditDockOpen.value = true;
}
async function changeScene(scene: typeof activeAgentScene.value) {
  auditDockOpen.value = true;
  try { await selectAgentScene(scene); }
  catch { /* The request helper displays the scoped error. */ }
}
async function moveScene(event: KeyboardEvent) {
  if (busy.value || !hasOrganization.value) return;
  const index = agentSceneOptions.findIndex((scene) => scene.key === activeAgentScene.value);
  const count = agentSceneOptions.length;
  const next = event.key === "Home" ? 0 : event.key === "End" ? count - 1
    : event.key === "ArrowRight" ? (index + 1) % count : event.key === "ArrowLeft" ? (index + count - 1) % count : -1;
  if (next < 0) return;
  event.preventDefault();
  const tabs = event.currentTarget as HTMLElement;
  await changeScene(agentSceneOptions[next].key);
  await nextTick();
  tabs.querySelector<HTMLButtonElement>("[aria-selected='true']")?.focus();
}
</script>

<template>
<section v-if="activeSection === 'agent'" class="agent-simple-page" :class="{ 'is-fullscreen': isFullscreen }">
  <header class="agent-context-bar" aria-label="当前 AI 工作项目">
    <div class="agent-header-identity">
      <Headset :size="16" aria-hidden="true" />
      <strong>AI 助手</strong>
    </div>
    <span class="agent-context-divider" aria-hidden="true"></span>
    <span class="agent-simple-project" :title="hasProject ? currentProjectName : '尚未选择项目'">
      <FolderOpen :size="14" aria-hidden="true" />
      <span>{{ hasProject ? currentProjectName : "尚未选择项目" }}</span>
    </span>
    <button type="button" class="agent-token-toggle" @click="showSection('ai-settings')">AI 设置</button>
  </header>
  <slot name="notice"></slot>
  <nav class="agent-simple-tabs" aria-label="AI 场景会话" role="tablist" data-guide-id="agent-scenes" @keydown="moveScene">
    <button v-if="isFullscreen" type="button" class="agent-navigation-trigger" aria-controls="admin-navigation"
      :aria-expanded="mobileNavigationOpen" :aria-label="mobileNavigationOpen ? '收起导航栏' : '展开导航栏'"
      title="展开导航栏" @keydown.stop @click="isFullscreen = false; mobileNavigationOpen = !mobileNavigationOpen">
      <Menu :size="22" aria-hidden="true" />
    </button>
    <div class="agent-scene-tabs-scroll">
      <button v-for="scene in agentSceneOptions" :id="'agent-tab-' + scene.key" :key="scene.key"
        type="button" role="tab" :aria-selected="activeAgentScene === scene.key" aria-controls="agent-scene-conversation"
        :tabindex="activeAgentScene === scene.key ? 0 : -1"
        :class="{ active: activeAgentScene === scene.key }" :disabled="busy || !hasOrganization"
        @click="changeScene(scene.key)"><component :is="sceneIcons[scene.key]" :size="18" aria-hidden="true" /><span>{{ scene.label }}</span></button>
    </div>
    <button
      type="button"
      class="agent-tabs-fullscreen-toggle"
      :aria-pressed="isFullscreen"
      :aria-label="isFullscreen ? '退出全屏对话' : '全屏显示对话'"
      :title="isFullscreen ? '退出全屏对话' : '全屏显示对话'"
      @click="isFullscreen = !isFullscreen"
    >
      <Minimize2 v-if="isFullscreen" :size="22" aria-hidden="true" />
      <Maximize2 v-else :size="22" aria-hidden="true" />
    </button>
  </nav>
  <div v-if="false" class="agent-simple-locked" role="status">
    <strong>请配置你的 AI 服务</strong>
    <p>当前账号暂无 AI 使用权限。</p>
    <button type="button" class="btn-primary" @click="showSection('ai-settings')">前往 AI 设置</button>
  </div>
  <div v-else-if="!hasOrganization" class="agent-simple-locked">
    <strong>请先打开一个本地项目</strong>
    <button type="button" class="btn-secondary" @click="showSection('workspace')">返回工作台</button>
  </div>
  <template v-else>
    <div id="agent-scene-conversation" class="agent-simple-chat" role="tabpanel" :aria-labelledby="'agent-tab-' + activeAgentScene">
      <PlanningAiCreator v-if="activeAgentScene === 'planning'" class="agent-constraint-wizard" />
      <ConstraintAiCreator v-else-if="activeAgentScene === 'constraints'" class="agent-constraint-wizard" />
      <TimetableAiCreator v-else-if="activeAgentScene === 'timetable'" />
      <AgentConversation v-else>
      </AgentConversation>
          <section v-if="agentActions.length && !['constraints', 'timetable'].includes(activeAgentScene)" class="agent-audit-dock" :style="auditDockStyle" data-guide-id="agent-action-entry">
            <div v-if="auditDockOpen" class="agent-audit-panel">
              <header class="agent-audit-header" @pointerdown="startAuditDockDrag">
                <span><ClipboardCheck :size="17" aria-hidden="true" /><strong>操作审核</strong><em v-if="pendingAuditCount">{{ pendingAuditCount }} 待审核</em></span>
                <button type="button" class="agent-audit-collapse" aria-label="收起操作审核" title="收起" @pointerdown.stop @click.stop="auditDockOpen = false"><ChevronLeft :size="16" aria-hidden="true" /></button>
              </header>
              <div class="agent-audit-groups">
                <section v-for="group in auditGroups" :key="group.key" class="agent-audit-group">
                  <button type="button" class="agent-audit-group-toggle" :aria-expanded="auditGroupOpen[group.key]" @click="toggleAuditGroup(group.key)">
                    <span><ChevronDown v-if="auditGroupOpen[group.key]" :size="15" aria-hidden="true" /><ChevronRight v-else :size="15" aria-hidden="true" /><strong>{{ group.label }}</strong></span>
                    <em>{{ group.actions.length }}</em>
                  </button>
                  <div v-if="auditGroupOpen[group.key] && group.actions.length" class="agent-audit-action-list">
                    <button v-for="action in group.actions" :key="String(action.id)" type="button" :disabled="loading || busy" @click="openAgentActionDetail(action)">
                      <span class="agent-action-row-content">
                        <strong>{{ agentActionTitle(action) }}</strong>
                        <span class="agent-action-row-target">{{ agentActionTargetLabel(action) }}</span>
                        <span class="agent-action-row-counts"><span v-for="item in agentActionCountItems(action)" :key="item.label" :class="{ destructive: item.label === '删除' || item.label === '失败' }">{{ item.label }} {{ item.value }}</span></span>
                      </span>
                      <span class="agent-action-row-end"><strong class="agent-action-badge" :class="'status-' + action.status">{{ agentActionStatusLabel(action.status) }}</strong><ChevronRight :size="16" aria-hidden="true" /></span>
                    </button>
                  </div>
                  <span v-else-if="auditGroupOpen[group.key]" class="agent-audit-empty">暂无记录</span>
                </section>
              </div>
            </div>
            <button v-else type="button" class="agent-audit-fab" aria-label="展开操作审核" title="展开操作审核" @pointerdown="startAuditDockDrag" @click="openAuditDock">
              <ClipboardCheck :size="20" aria-hidden="true" />
              <i v-if="pendingAuditCount" class="agent-audit-dot" aria-label="有待审核事项"></i>
            </button>
          </section>
    </div>
  <div v-if="selectedAgentAction" class="bottom-sheet-mask agent-action-mask">
    <section class="bottom-sheet agent-action-detail-sheet" role="dialog" aria-modal="true" aria-label="变更确认">
      <header class="bottom-sheet-header">
        <div>
          <span class="agent-action-badge" :class="'status-' + selectedAgentAction.status">{{ agentActionStatusLabel(selectedAgentAction.status) }}</span>
          <h3>{{ agentActionTitle(selectedAgentAction) }}</h3>
          <p class="agent-action-detail-target">{{ agentActionTargetLabel(selectedAgentAction) }}</p>
        </div>
        <button class="btn-secondary agent-action-close" type="button" aria-label="关闭变更详情" title="关闭" @click="closeAgentActionDetail"><X :size="19" /></button>
      </header>
      <div class="agent-action-detail-body">
        <div class="agent-preview-counts large">
          <span v-for="item in agentActionCountItems(selectedAgentAction)" :key="item.label" :class="{ destructive: item.label === '删除' || item.label === '失败' }">
            {{ item.label }} {{ item.value }}
          </span>
          <span v-if="!agentActionCountItems(selectedAgentAction).length && Number(selectedAgentAction.schema_version || 1) >= 2">
            无可执行明细
          </span>
          <span v-else-if="!agentActionCountItems(selectedAgentAction).length">旧版记录</span>
        </div>
        <details class="agent-action-explanation" :key="String(selectedAgentAction.id)">
          <summary>AI 处理说明</summary>
          <p>{{ agentActionDisplaySummary(selectedAgentAction) }}</p>
        </details>
        <AgentActionChanges v-if="Number(selectedAgentAction.schema_version || 1) >= 2" />
        <div
          v-if="Number(selectedAgentAction.schema_version || 1) < 2"
          v-for="table in agentActionDetailTables(selectedAgentAction)"
          :key="table.key"
          class="agent-action-detail-section"
          :class="`tone-${table.tone}`"
        >
          <h4>{{ table.title }}</h4>
          <div class="agent-action-impact-table">
            <div class="agent-action-impact-row head">
              <span>对象</span>
              <span>信息</span>
              <span>状态</span>
              <span>说明</span>
            </div>
            <div
              v-for="(row, index) in table.rows"
              :key="`${table.key}-${index}-${row.name}`"
              class="agent-action-impact-row"
            >
              <span>{{ row.name }}</span>
              <span>{{ row.detail || "待确认" }}</span>
              <span>{{ row.status }}</span>
              <span>{{ row.reason || "—" }}</span>
            </div>
          </div>
        </div>
        <div v-if="agentActionWarnings(selectedAgentAction).length" class="agent-action-detail-section">
          <h4>提示</h4>
          <ul class="agent-action-notes">
            <li v-for="warning in agentActionWarnings(selectedAgentAction)" :key="warning">{{ warning }}</li>
          </ul>
        </div>
        <div v-if="agentActionFailures(selectedAgentAction).length || selectedAgentAction.error_message" class="agent-action-detail-section danger">
          <h4>需要处理的问题</h4>
          <ul class="agent-action-notes danger">
            <li v-for="failure in agentActionFailures(selectedAgentAction)" :key="failure">{{ failure }}</li>
            <li v-if="selectedAgentAction.error_message">{{ selectedAgentAction.error_message }}</li>
          </ul>
        </div>
      </div>
      <footer class="bottom-sheet-footer">
        <button class="btn-secondary" type="button" @click="closeAgentActionDetail">稍后处理</button>
        <button
          v-if="String(selectedAgentAction.status) === 'pending_confirmation'"
          class="btn-secondary danger"
          type="button"
          @click="rejectAgentAction(selectedAgentAction.id)"
          :disabled="loading"
        >
          拒绝
        </button>
        <button
          v-if="String(selectedAgentAction.status) === 'pending_confirmation'"
          type="button"
          @click="confirmAgentAction(selectedAgentAction.id)"
          :disabled="loading || Number(selectedAgentAction.item_count || 0) < 1"
        >
          确认执行
        </button>
      </footer>
    </section>
  </div>

  </template>
</section>
</template>

<style scoped>
.agent-simple-page { position: relative; display: flex; flex-direction: column; width: 100%; height: 100dvh; min-height: 0; max-height: none; min-width: 0; background: #fff; overflow: hidden; }
.agent-simple-page.is-fullscreen { position: fixed; inset: 0; z-index: 500; width: 100vw; height: 100dvh; }
.agent-context-bar { display: flex; flex: none; align-items: center; gap: 12px; min-width: 0; min-height: 36px; box-sizing: border-box; padding: 6px 16px; border-bottom: 1px solid #e8edeb; background: #f8faf9; }
.agent-header-identity { display: inline-flex; flex: none; align-items: center; gap: 7px; color: #38695c; }
.agent-header-identity > strong { color: #365148; font-size: 12px; line-height: 20px; white-space: nowrap; }
.agent-context-divider { flex: 0 0 1px; height: 14px; background: #d9e3de; }
.agent-token-entry { position: relative; flex: none; margin-left: auto; }
.agent-token-toggle { display: inline-flex; align-items: center; gap: 6px; height: 24px; padding: 0 4px; border: 0; border-radius: 4px; background: transparent; color: #65756b; font-size: 11px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.agent-token-toggle strong { color: #2f7d6d; min-width: 44px; text-align: right; }
.agent-token-toggle:hover { background: #eaf1ed; }
.agent-token-toggle:focus-visible { outline: 2px solid #388a73; outline-offset: 2px; }
.agent-token-toggle .is-open { transform: rotate(180deg); }
.usage-low .agent-token-toggle strong { color: #986320; }
.agent-token-usage { position: absolute; z-index: 20; top: calc(100% + 8px); right: 0; display: grid; gap: 10px; box-sizing: border-box; width: min(280px, calc(100vw - 24px)); padding: 14px; border: 1px solid #dce9e3; border-radius: 8px; background: #fff; font-size: 12px; color: #667d77; font-variant-numeric: tabular-nums; box-shadow: 0 6px 20px rgba(35, 70, 58, 0.12); }
.agent-token-usage dl { display: grid; gap: 8px; margin: 0; }
.agent-token-usage dl > div { display: flex; justify-content: space-between; gap: 16px; }
.agent-token-usage dd { margin: 0; color: #234d44; font-weight: 600; }
.agent-token-usage p { margin: 0; padding-top: 10px; border-top: 1px solid #e8edeb; font-size: 11px; line-height: 1.6; }
.agent-token-caption { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px; }
.agent-token-caption > span:last-child { color: #2f7d6d; font-weight: 600; }
.agent-token-usage strong { color: #234d44; font-size: 13px; line-height: 1.3; overflow-wrap: anywhere; }
.agent-token-usage small { font-size: 11px; }
.agent-token-meter { display: block; width: 100%; height: 4px; margin: 2px 0; border: 0; border-radius: 2px; appearance: none; overflow: hidden; background: #eaf0ed; color: #2f7d6d; }
.agent-token-meter::-webkit-progress-bar { background: #eaf0ed; }
.agent-token-meter::-webkit-progress-value { background: #2f7d6d; border-radius: 2px; }
.agent-token-meter::-moz-progress-bar { background: #2f7d6d; border-radius: 2px; }
.usage-low .agent-token-caption > span:last-child { color: #986320; }
.usage-low .agent-token-meter::-webkit-progress-value { background: #b88432; }
.usage-low .agent-token-meter::-moz-progress-bar { background: #b88432; }
.agent-simple-project { display: inline-flex; flex: 1; align-items: center; gap: 6px; min-width: 0; color: #65756b; font-size: 12px; line-height: 20px; }
.agent-simple-project svg { flex-shrink: 0; }
.agent-simple-project > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.agent-simple-tabs { position: relative; z-index: 1; display: flex; flex: none; box-sizing: border-box; min-width: 0; overflow: hidden; border-bottom: 1px solid #dce5e0; padding: 0 8px 0 12px; gap: 4px; }
.agent-scene-tabs-scroll { display: flex; flex: 1 1 auto; min-width: 0; overflow-x: auto; gap: 4px; scrollbar-width: none; }
.agent-scene-tabs-scroll::-webkit-scrollbar { display: none; }
.agent-simple-tabs button { display: inline-flex; justify-content: center; align-items: center; gap: 7px; flex: 1 0 auto; min-height: 42px; border: 0; border-bottom: 3px solid transparent; border-radius: 6px 6px 0 0; background: transparent; color: #65756b; padding: 8px 12px; font-size: 13px; white-space: nowrap; transition: background-color .15s, color .15s; }
.agent-simple-tabs button svg { flex-shrink: 0; }
.agent-simple-tabs button:hover:not(:disabled) { background: #f3f6f5; color: #2e6251; }
.agent-simple-tabs button.active { border-bottom-color: #2f7d6d; color: #236957; background: #edf5f1; font-weight: 700; }
.agent-simple-tabs button:focus-visible { outline: 2px solid #388a73; outline-offset: -3px; }
.agent-simple-tabs .agent-tabs-fullscreen-toggle,
.agent-simple-tabs .agent-navigation-trigger { position: static; flex: 0 0 42px; width: 42px; height: 42px; align-self: center; margin: 0; padding: 0; border: 0; border-radius: 6px; background: transparent; box-shadow: none; }
.agent-simple-chat { position: relative; display: flex; flex-direction: column; min-height: 0; flex: 1; min-width: 0; overflow: hidden; }
.agent-constraint-wizard { height: 100%; box-sizing: border-box; }
.agent-simple-chat :deep(.conversation-composer) { padding: 16px 24px 22px; }
.agent-simple-page :deep(.agent-audit-dock) { position: absolute; z-index: 8; width: min(280px, calc(100vw - 28px)); pointer-events: none; }
.agent-simple-page :deep(.agent-audit-panel) { display: flex; flex-direction: column; max-height: min(540px, calc(100dvh - 110px)); overflow: hidden; border: 1px solid #d6e4dd; border-radius: 10px; background: rgba(255, 255, 255, 0.98); box-shadow: 0 14px 34px rgba(25, 58, 46, 0.18); pointer-events: auto; }
.agent-simple-page :deep(.agent-audit-header) { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 12px; border-bottom: 1px solid #e4ece7; background: #f4f9f6; color: #315b4d; cursor: grab; touch-action: none; user-select: none; }
.agent-simple-page :deep(.agent-audit-header:active) { cursor: grabbing; }
.agent-simple-page :deep(.agent-audit-header > span) { display: inline-flex; align-items: center; gap: 7px; min-width: 0; }
.agent-simple-page :deep(.agent-audit-header strong) { font-size: 13px; }
.agent-simple-page :deep(.agent-audit-header em) { padding: 2px 6px; border-radius: 999px; background: #fff0ed; color: #ad4133; font-size: 11px; font-style: normal; white-space: nowrap; }
.agent-simple-page :deep(.agent-audit-collapse) { display: grid; place-items: center; width: 28px; height: 28px; padding: 0; border: 0; border-radius: 5px; background: transparent; color: #60776c; }
.agent-simple-page :deep(.agent-audit-collapse:hover) { background: #e4f0ea; color: #2f6d5d; }
.agent-simple-page :deep(.agent-audit-groups) { min-height: 0; overflow-y: auto; scrollbar-width: none; }
.agent-simple-page :deep(.agent-audit-groups::-webkit-scrollbar) { display: none; }
.agent-simple-page :deep(.agent-audit-group + .agent-audit-group) { border-top: 1px solid #edf2ef; }
.agent-simple-page :deep(.agent-audit-group-toggle) { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 9px 12px; border: 0; border-radius: 0; background: #fff; color: #4c665b; text-align: left; }
.agent-simple-page :deep(.agent-audit-group-toggle:hover) { background: #f4f8f5; }
.agent-simple-page :deep(.agent-audit-group-toggle > span) { display: inline-flex; align-items: center; gap: 5px; }
.agent-simple-page :deep(.agent-audit-group-toggle strong) { font-size: 12px; }
.agent-simple-page :deep(.agent-audit-group-toggle em) { min-width: 20px; padding: 2px 5px; border-radius: 999px; background: #edf3ef; color: #6b7d73; font-size: 11px; font-style: normal; text-align: center; }
.agent-simple-page :deep(.agent-audit-group:first-child .agent-audit-group-toggle em) { background: #fff0ed; color: #ad4133; }
.agent-simple-page :deep(.agent-audit-action-list) { padding: 0 10px 8px; }
.agent-simple-page :deep(.agent-audit-action-list > button) { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; padding: 8px 4px; border: 0; border-top: 1px solid #edf2ef; border-radius: 0; background: transparent; color: #354f40; text-align: left; }
.agent-simple-page :deep(.agent-audit-action-list > button:hover:not(:disabled)) { background: #f2f7f4; }
.agent-simple-page :deep(.agent-audit-action-list .agent-action-row-content) { display: grid; gap: 3px; min-width: 0; }
.agent-simple-page :deep(.agent-audit-action-list .agent-action-row-content > strong) { font-size: 12px; line-height: 1.45; }
.agent-simple-page :deep(.agent-audit-action-list .agent-action-row-target) { max-width: 160px; font-size: 11px; }
.agent-simple-page :deep(.agent-audit-action-list .agent-action-row-counts) { gap: 4px 8px; font-size: 11px; }
.agent-simple-page :deep(.agent-audit-action-list .agent-action-row-end) { gap: 4px; }
.agent-simple-page :deep(.agent-audit-action-list .agent-action-badge) { padding: 2px 5px; font-size: 10px; }
.agent-simple-page :deep(.agent-audit-empty) { display: block; padding: 0 12px 10px; color: #8b9992; font-size: 11px; }
.agent-simple-page :deep(.agent-audit-fab) { position: relative; display: grid; place-items: center; width: 46px; height: 46px; padding: 0; border: 1px solid #bdd6ca; border-radius: 50%; background: #f4fbf7; color: #2e7561; box-shadow: 0 10px 24px rgba(29, 73, 57, 0.2); cursor: grab; pointer-events: auto; touch-action: none; }
.agent-simple-page :deep(.agent-audit-fab:active) { cursor: grabbing; }
.agent-simple-page :deep(.agent-audit-fab:hover) { border-color: #82bba7; background: #e5f4ec; }
.agent-simple-page :deep(.agent-audit-dot) { position: absolute; top: 1px; right: 1px; width: 10px; height: 10px; border: 2px solid #f4fbf7; border-radius: 50%; background: #d94a3f; }
.agent-simple-actions { flex: none; border-top: 1px solid #dce5e0; background: #f5f9f6; }
.agent-simple-actions-toggle { width: 100%; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding: 12px 18px; border: 0; border-radius: 0; color: #346a50; background: transparent; text-align: left; font-size: 13px; }
.agent-simple-actions-toggle > span:first-child { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.agent-simple-actions-toggle small { font-size: 12px; color: #697b6d; }
.agent-simple-action-list { max-height: 160px; overflow: auto; overscroll-behavior: contain; padding: 0 16px 8px; }
.agent-simple-action-list button { display: flex; justify-content: space-between; align-items: center; gap: 16px; width: 100%; padding: 10px 0; border: 0; border-top: 1px solid #e0e7e2; border-radius: 0; background: transparent; color: #354f40; font-size: 13px; text-align: left; }
.agent-simple-action-list button span { min-width: 0; overflow-wrap: anywhere; }
.agent-simple-action-list button strong { flex-shrink: 0; font-size: 12px; }
.agent-simple-action-list button:hover:not(:disabled) { background: #edf4ef; }
.agent-action-row-content { display: grid; flex: 1; min-width: 0; gap: 5px; }
.agent-action-row-content > strong { font-size: 14px; line-height: 1.5; }
.agent-action-row-target { color: #6d7b72; font-size: 12px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.agent-action-row-counts { display: flex; flex-wrap: wrap; gap: 6px 14px; color: #416753; font-size: 12px; font-weight: 500; }
.agent-action-row-end { display: flex; flex: none; align-items: center; gap: 10px; color: #7c8a81; }
.agent-action-badge { display: inline-flex; width: fit-content; padding: 3px 8px; border-radius: 4px; background: #edf1ee; color: #5f7166; font-size: 12px; font-weight: 600; line-height: 1.5; white-space: nowrap; }
.agent-action-badge.status-pending_confirmation { color: #886018; background: #fff3d9; }
.agent-action-badge.status-executed { color: #26704b; background: #e8f5ec; }
.agent-action-badge.status-failed, .agent-action-badge.status-stale { color: #a34232; background: #fff0ec; }
.agent-action-mask { align-items: center; justify-content: center; }
.agent-action-detail-sheet { width: min(1040px, calc(100vw - 32px)); height: min(78dvh, 740px); min-height: 0; max-height: calc(100dvh - 32px); margin: 0; border-radius: 8px; }
.agent-action-detail-sheet .bottom-sheet-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 18px 22px; background: #fff; }
.agent-action-detail-sheet .bottom-sheet-header > div { flex: 1; min-width: 0; }
.agent-action-detail-sheet .bottom-sheet-header h3 { margin: 8px 0 4px; font-size: 20px; line-height: 1.4; overflow-wrap: anywhere; }
.agent-action-detail-target { margin: 0; color: #6a7b6f; font-size: 12px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.agent-action-detail-sheet .agent-action-close { display: grid; place-items: center; flex-shrink: 0; width: 34px; height: 34px; padding: 0; }
.agent-action-detail-body { min-height: 0; padding: 16px 22px; overscroll-behavior: contain; }
.agent-action-explanation { padding: 10px 0; border-bottom: 1px solid #e5ebe7; font-size: 13px; }
.agent-action-explanation summary { width: fit-content; cursor: pointer; color: #5a7162; font-weight: 600; }
.agent-action-explanation p { margin: 10px 0 0; color: #697b6e; font-size: 13px; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; }
.destructive, .agent-preview-counts.large .destructive { color: #ad4133; }
.agent-preview-counts.large .destructive { background: #fff0eb; border-color: #edc4b9; }
.agent-action-detail-sheet .bottom-sheet-footer { padding: 12px 22px; background: #fff; border-top: 1px solid #e5ebe7; }
.agent-action-detail-sheet .agent-action-item-filters { grid-template-columns: minmax(0, 1fr) 140px 130px auto; }
.agent-action-detail-sheet .agent-action-audit-item { grid-template-columns: minmax(0, .8fr) minmax(0, 1.5fr) auto; }
.agent-action-audit-item pre { min-width: 0; }
@media (max-width: 700px) {
  .agent-action-detail-sheet { width: calc(100vw - 20px); height: calc(100dvh - 24px); max-height: calc(100dvh - 24px); }
  .agent-action-detail-sheet .bottom-sheet-header, .agent-action-detail-body, .agent-action-detail-sheet .bottom-sheet-footer { padding: 12px; }
  .agent-action-detail-sheet .agent-action-item-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .agent-action-item-filters > input { grid-column: 1 / -1; }
  .agent-action-detail-sheet .agent-action-audit-item { grid-template-columns: minmax(0, 1fr); gap: 8px; }
  .agent-action-audit-item em { justify-self: end; }
  .agent-action-row-end { gap: 4px; }
}
.agent-simple-error { flex: none; max-height: 72px; overflow: auto; padding: 8px 16px; color: #a33730; background: #fff3f0; font-size: 13px; overflow-wrap: anywhere; }
.agent-simple-locked { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 24px; text-align: center; background: #f2f6f4; }
.agent-simple-tabs .agent-navigation-trigger { display: none; }
@media (max-width: 760px) {
  .agent-simple-tabs { padding: 0 8px; }
  .agent-simple-tabs .agent-navigation-trigger { display: inline-flex; }
  .agent-context-bar { padding: 5px 12px; gap: 9px; }
}
@media (max-width: 600px) { .agent-simple-page { height: 100dvh; min-height: 0; } .agent-simple-tabs { gap: 2px; } .agent-simple-tabs button { padding: 8px 10px; font-size: 13px; } .agent-simple-chat :deep(.conversation-composer) { padding: 12px; } }
</style>
