<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { ArrowDown, ArrowUp, BookOpen, FileText, Headset, Paperclip, Plus, RefreshCw, Trash2, X } from "lucide-vue-next";
import { APP_CONTEXT_KEY } from "./appContext";
import OfficialWorkbookButton from "./OfficialWorkbookButton.vue";
import { agentQuestions, agentQuestionContent } from "../utils/agentQuestions";
import { agentPromptCategories, agentPromptTemplates, appendAgentPrompt, type AgentPromptCategory, type AgentPromptTemplate } from "../utils/agentPromptTemplates";

const {
  activeAgentScene, agentSceneOptions, agentAttachmentDrafts, agentError, agentInput, agentMessages,
  agentMessageAttachments, agentSessionLoading, agentStreaming, agentUploading,
  currentAgentConversationId, entitlement, hasOrganization, loadAgentProjectSession,
  removeAgentAttachmentDraft, renderMarkdown, submitAgentDraft, uploadAgentAttachments,
  clearCurrentAgentConversation, agentActions,
} = inject(APP_CONTEXT_KEY)!;
const fileInput = ref<HTMLInputElement | null>(null);
const messageList = ref<HTMLElement | null>(null);
const followLatest = ref(true);
const promptLibraryOpen = ref(false);
const promptCategory = ref<AgentPromptCategory>("task");
const promptPanel = ref<HTMLDialogElement | null>(null);
let promptPreviousOverflow: string | null = null;
const promptButton = ref<HTMLButtonElement | null>(null);
const textInput = ref<HTMLTextAreaElement | null>(null);
const sceneLabel = computed(() => agentSceneOptions.find((scene) => scene.key === activeAgentScene.value)?.label || "当前场景");
const scenePrompts = computed(() => agentPromptTemplates[activeAgentScene.value].filter((item) => item.category === promptCategory.value));
const allowed = computed(() => Boolean(entitlement.value.ai_enabled && hasOrganization.value));
const busy = computed(() => agentSessionLoading.value || agentStreaming.value || agentUploading.value);
const disabled = computed(() => !allowed.value || busy.value || !currentAgentConversationId.value);
const editingDisabled = computed(() => !allowed.value || agentSessionLoading.value || agentStreaming.value || !currentAgentConversationId.value);
const answers = ref<string[]>([]);
const skippedAnswers = ref<boolean[]>([]);
function toggleQuestionSkip(index: number) {
  if (editingDisabled.value) return;
  skippedAnswers.value[index] = !skippedAnswers.value[index];
}
const questions = computed(() => agentQuestions(messages.value[messages.value.length - 1]));
const canSend = computed(() => !disabled.value && Boolean(agentInput.value.trim() || agentAttachmentDrafts.value.length || (questions.value.length && questions.value.every((_, index) => skippedAnswers.value[index] || answers.value[index]?.trim()))));
const messages = computed(() => agentMessages.value.filter((item) => item.role === "user" || item.role === "assistant"));
const canClear = computed(() => !disabled.value && !agentActions.value.some(action => action.status === "executing"));
async function clearConversation() {
  if (!canClear.value) return;
  if (await clearCurrentAgentConversation()) {
    answers.value = [];
    skippedAnswers.value = [];
    followLatest.value = true;
    await nextTick();
    textInput.value?.focus();
  }
}
const prompts: Record<string, string> = {
  timetable: "例如：每周一到周五，上午 4 节、下午 3 节，每节 40 分钟",
  rooms: "例如：新增两个实验室，分别可容纳 40 人",
  school: "例如：从附件整理教师、班级和科目",
  planning: "例如：按附件生成课程计划，每周课时数以表格为准",
  constraints: "例如：张老师周三下午不排课",
};

async function openPromptLibrary() {
  if (editingDisabled.value) return;
  promptLibraryOpen.value = true;
  await nextTick();
  if (!promptLibraryOpen.value || !promptPanel.value) return;
  promptPanel.value.showModal();
  promptPreviousOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  promptPanel.value?.querySelector<HTMLButtonElement>("[aria-pressed='true']")?.focus();
}
function releasePromptDialog() {
  promptPanel.value?.close();
  if (promptPreviousOverflow !== null) {
    document.body.style.overflow = promptPreviousOverflow;
    promptPreviousOverflow = null;
  }
}
function closePromptBackdrop(event: MouseEvent) {
  const dialog = promptPanel.value;
  if (!dialog || event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) void closePromptLibrary();
}
async function closePromptLibrary() {
  promptLibraryOpen.value = false;
  await nextTick();
  promptButton.value?.focus();
}
async function applyPrompt(template: AgentPromptTemplate) {
  if (editingDisabled.value || !agentPromptTemplates[activeAgentScene.value].some((item) => item.id === template.id)) return;
  agentInput.value = appendAgentPrompt(agentInput.value, template.text);
  promptLibraryOpen.value = false;
  await nextTick();
  textInput.value?.focus();
  const placeholder = /【[^】]+】/.exec(template.text);
  const start = placeholder ? agentInput.value.lastIndexOf(template.text) + placeholder.index : agentInput.value.length;
  textInput.value?.setSelectionRange(start, start + (placeholder?.[0].length || 0));
}
watch([activeAgentScene, editingDisabled], () => { promptLibraryOpen.value = false; });
watch(promptLibraryOpen, (open) => { if (!open) releasePromptDialog(); }, { flush: "sync" });
onBeforeUnmount(releasePromptDialog);

function trackScroll() {
  const list = messageList.value;
  if (list) followLatest.value = list.scrollHeight - list.scrollTop - list.clientHeight < 72;
}
async function scrollLatest() {
  followLatest.value = true;
  await nextTick();
  const list = messageList.value;
  if (list) list.scrollTop = list.scrollHeight;
}
async function send() {
  if (!canSend.value) return;
  followLatest.value = true;
  if (questions.value.length && (answers.value.some(answer => answer?.trim()) || skippedAnswers.value.some(Boolean))) {
    const reply = questions.value.map((question, index) => `${index + 1}. ${question}\n回答：${skippedAnswers.value[index] ? "已跳过（未提供答案，不代表同意或授权；不要猜测该问题的答案）" : answers.value[index]?.trim() || "暂未回答"}`).join("\n\n");
    agentInput.value = [reply, agentInput.value.trim()].filter(Boolean).join("\n\n");
  }
  answers.value = [];
  skippedAnswers.value = [];
  try { await submitAgentDraft(); }
  catch (error) { agentError.value = error instanceof Error ? error.message : "发送失败，请重试。"; }
}
async function reload() {
  if (!allowed.value || busy.value) return;
  try { await loadAgentProjectSession(); }
  catch { /* The request helper displays the scoped error. */ }
}
watch(() => [messages.value.length, messages.value[messages.value.length - 1]?.content], async () => {
  if (followLatest.value) await scrollLatest();
}, { flush: "post" });
watch(currentAgentConversationId, () => { void scrollLatest(); }, { immediate: true });
watch([currentAgentConversationId, activeAgentScene, () => questions.value.join("\n")], () => { answers.value = []; skippedAnswers.value = []; });
</script>

<template>
    <div class="agent-conversation">
    <div class="conversation-history">
      <slot name="history-tools"></slot>
      <button type="button" class="conversation-clear" title="清空对话和 AI 记忆" aria-label="清空对话和 AI 记忆" :disabled="!canClear" @click="clearConversation"><Trash2 :size="17" /></button>
      <dialog v-if="promptLibraryOpen && !editingDisabled" ref="promptPanel" class="conversation-prompt-library" aria-modal="true" :aria-label="sceneLabel + '提示词模板'" @cancel.prevent="closePromptLibrary" @click="closePromptBackdrop">
        <header><strong>{{ sceneLabel }}提示词</strong><button type="button" class="prompt-close" aria-label="关闭提示词" title="关闭提示词" @click="closePromptLibrary"><X :size="18" /></button></header>
        <div class="prompt-categories" role="group" aria-label="提示词分类">
          <button v-for="category in agentPromptCategories" :key="category.key" type="button" :aria-pressed="promptCategory === category.key" @click="promptCategory = category.key">{{ category.label }}</button>
        </div>
        <div class="prompt-template-list">
          <button v-for="template in scenePrompts" :key="template.id" type="button" class="prompt-template" :aria-label="'加入输入框：' + template.title" @click="applyPrompt(template)">
            <span><strong>{{ template.title }}</strong><span>{{ template.text }}</span></span><Plus :size="18" aria-hidden="true" />
          </button>
        </div>
      </dialog>
      <div ref="messageList" class="conversation-messages" role="log" aria-label="对话记录" :aria-busy="agentStreaming" @scroll="trackScroll">
        <div v-if="agentSessionLoading" class="conversation-empty" role="status">正在加载对话...</div>
        <div v-else-if="!currentAgentConversationId" class="conversation-empty">
          <strong>暂未连接到会话</strong>
          <button type="button" class="btn-secondary" :disabled="!allowed || busy" @click="reload"><RefreshCw :size="16" />重新加载</button>
        </div>
        <div v-else-if="!messages.length" class="conversation-empty">
          <span class="conversation-empty-symbol" aria-hidden="true"><Headset :size="32" :stroke-width="1.5" /></span>
          <strong>今天需要处理什么？</strong>
        </div>
        <article v-for="message in messages" :key="String(message.id)" class="conversation-message" :class="{ 'from-user': message.role === 'user', 'has-error': message.error }">
          <span class="conversation-author">{{ message.role === 'user' ? '你' : 'AI 助手' }}</span>
          <div v-if="agentMessageAttachments(message).length" class="conversation-files">
            <span v-for="file in agentMessageAttachments(message)" :key="file.id" class="conversation-file"><FileText :size="15" /><span>{{ file.filename }}</span></span>
          </div>
          <div v-if="message.role === 'user'" class="conversation-text">{{ message.content }}</div>
          <div v-else-if="message.content" class="agent-markdown conversation-markdown" v-html="renderMarkdown(agentQuestionContent(message))"></div>
          <span v-else-if="message.pending" class="conversation-thinking" role="status">正在整理...</span>
        </article>
      </div>
      <button v-if="!promptLibraryOpen && !followLatest && messages.length" type="button" class="conversation-latest btn-secondary" title="回到最新消息" aria-label="回到最新消息" @click="scrollLatest"><ArrowDown :size="17" /></button>
      <slot name="history-actions"></slot>
    </div>
    <slot name="actions"></slot>
    <form class="conversation-composer" data-guide-id="agent-composer" @submit.prevent="send">
      <div v-if="agentError" class="conversation-error" role="alert">{{ agentError }}</div>
      <div class="conversation-composer-inner" :class="{ 'is-disabled': editingDisabled }">
      <fieldset v-if="questions.length && !agentStreaming" class="conversation-questions" :disabled="editingDisabled">
        <legend>请补充以下信息</legend>
        <div v-for="(question, index) in questions" :key="question" class="conversation-question">
          <div class="conversation-question-header">
            <label :for="`question-${currentAgentConversationId}-${index}`">{{ index + 1 }}. {{ question }}</label>
            <button type="button" class="question-skip" :aria-label="`${skippedAnswers[index] ? '撤销跳过' : '跳过'}第 ${index + 1} 个问题`" :aria-pressed="Boolean(skippedAnswers[index])" @click="toggleQuestionSkip(index)">{{ skippedAnswers[index] ? '撤销跳过' : '跳过' }}</button>
          </div>
          <p v-if="skippedAnswers[index]" class="question-skipped" role="status">已跳过</p>
          <input v-else :id="`question-${currentAgentConversationId}-${index}`" v-model="answers[index]" type="text" :aria-label="question" placeholder="请输入回答" />
        </div>
      </fieldset>
      <div v-if="agentAttachmentDrafts.length || agentUploading" class="conversation-files conversation-drafts" aria-label="待发送附件">
        <span v-for="file in agentAttachmentDrafts" :key="String(file.id)" class="conversation-file">
          <FileText :size="15" /><span :title="String(file.filename || '附件')">{{ file.filename || '附件' }}</span>
          <button type="button" :title="`移除 ${file.filename || '附件'}`" :aria-label="`移除 ${file.filename || '附件'}`" :disabled="disabled" @click="removeAgentAttachmentDraft(file.id)"><X :size="14" /></button>
        </span>
        <span v-if="agentUploading" class="conversation-uploading" role="status">正在上传...</span>
      </div>
      <textarea ref="textInput" v-model="agentInput" aria-label="消息或附件补充说明" :placeholder="questions.length ? '其他补充，或直接在这里回答' : prompts[activeAgentScene]" :disabled="editingDisabled" :rows="questions.length ? 2 : 3"></textarea>
      <div class="conversation-composer-actions">
        <OfficialWorkbookButton v-if="activeAgentScene === 'rooms' || activeAgentScene === 'school' || activeAgentScene === 'planning'" :scene="activeAgentScene" />
        <button type="button" class="conversation-attach" title="添加附件" aria-label="添加附件" :disabled="disabled" @click="fileInput?.click()"><Paperclip :size="18" /><span>添加附件</span></button>
        <button ref="promptButton" type="button" class="conversation-attach" title="提示词模板" aria-label="提示词模板" :aria-expanded="promptLibraryOpen" :disabled="editingDisabled" @click="promptLibraryOpen ? closePromptLibrary() : openPromptLibrary()"><BookOpen :size="18" /><span>提示词</span></button>
        <button type="submit" class="btn-primary conversation-send" :title="agentStreaming ? '回复中...' : '发送'" :aria-label="agentStreaming ? '回复中...' : '发送'" :disabled="!canSend"><span aria-live="polite">{{ agentStreaming ? '回复中...' : '发送' }}</span></button>
      </div>
      <input ref="fileInput" class="agent-hidden-file-input" type="file" multiple accept=".txt,.csv,.xlsx,.doc,.docx,.md,.json" :disabled="disabled" @change="uploadAgentAttachments" />
      </div>
    </form>
  </div>
</template>

<style scoped>
.agent-conversation { min-width: 0; min-height: 0; height: 100%; display: flex; flex-direction: column; background: #fff; }
.conversation-history { position: relative; flex: 1 1 0; min-height: 82px; overflow: hidden; }
.conversation-clear { position: absolute; top: 10px; right: 16px; z-index: 2; display: grid; place-items: center; width: 34px; height: 34px; padding: 0; border: 0; border-radius: 6px; background: #fff; color: #647a6e; }
.conversation-clear:hover:not(:disabled) { color: #a23430; background: #fff1ef; }
.conversation-clear:disabled { opacity: .4; cursor: not-allowed; }
.conversation-prompt-library { width: min(560px, calc(100vw - 32px)); max-width: none; max-height: min(520px, calc(100dvh - 48px)); margin: auto; padding: 0; overflow: hidden; border: 1px solid #d6e2da; border-radius: 8px; background: #fff; color: #304f42; box-shadow: 0 20px 60px rgba(22, 43, 32, .18); }
.conversation-prompt-library[open] { display: flex; flex-direction: column; }
.conversation-prompt-library::backdrop { background: rgba(24, 36, 30, .32); }
.conversation-prompt-library > header { display: flex; align-items: center; justify-content: space-between; flex: none; gap: 12px; padding: 12px 18px; color: #304f42; font-size: 15px; }
.prompt-close { display: grid; place-items: center; width: 32px; height: 32px; padding: 0; border: 0; background: transparent; color: #677a6e; }
.prompt-categories { display: flex; flex: none; gap: 4px; padding: 0 12px 10px; border-bottom: 1px solid #e4ebe6; overflow-x: auto; }
.prompt-categories button { flex: 1 0 auto; min-height: 34px; padding: 6px 8px; border: 0; border-radius: 4px; color: #63776a; background: #f5f7f6; font-size: 12px; white-space: nowrap; }
.prompt-categories button[aria-pressed="true"] { color: #215f49; background: #e6f1eb; font-weight: 700; }
.prompt-template-list { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 0 18px; }
.prompt-template { display: flex; width: 100%; align-items: center; gap: 16px; padding: 14px 0; border: 0; border-bottom: 1px solid #e9eeeb; border-radius: 0; background: transparent; color: #354c40; text-align: left; }
.prompt-template:hover { background: #f6f9f7; }
.prompt-template > span { display: grid; gap: 6px; flex: 1; min-width: 0; }
.prompt-template strong { font-size: 14px; }
.prompt-template > span > span { color: #6b7c70; font-size: 12px; font-weight: 400; line-height: 1.65; overflow-wrap: anywhere; }
.prompt-template > svg { flex-shrink: 0; color: #357b5a; }
.conversation-messages { position: absolute; inset: 0; box-sizing: border-box; overflow: auto; overscroll-behavior: contain; padding: 58px 24px 24px; scrollbar-width: none; }
.conversation-messages::-webkit-scrollbar { display: none; }
.conversation-empty { min-height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; text-align: center; color: #74817b; font-size: 14px; }
.conversation-empty-symbol { display: grid; place-items: center; width: 64px; height: 64px; border-radius: 8px; color: #397b67; background: #eef5f1; border: 1px solid #dfebe4; }
.conversation-empty strong { color: #3b5148; font-size: 18px; font-weight: 600; }
.conversation-empty button { display: flex; gap: 8px; align-items: center; }
.conversation-message { min-width: 0; max-width: 800px; margin: 0 auto 28px; font-size: 14px; line-height: 1.8; overflow-wrap: anywhere; }
.conversation-message.from-user { width: fit-content; max-width: min(88%, 680px); margin-right: max(0px, calc((100% - 800px) / 2)); margin-left: auto; padding: 12px 16px; background: #f1f5f3; border: 1px solid #e5ece8; border-radius: 8px; }
.conversation-author { display: block; margin-bottom: 6px; font-size: 12px; font-weight: 700; color: #37725f; }
.conversation-text { white-space: pre-wrap; }
.conversation-thinking, .conversation-uploading, .conversation-progress { color: #69766f; font-size: 12px; }
.has-error { color: #a23430; }
.conversation-markdown { min-width: 0; overflow: visible; overflow-wrap: anywhere; word-break: break-word; }
.conversation-markdown :deep(pre) { max-width: 100%; box-sizing: border-box; overflow-x: auto; overflow-y: hidden; }
.conversation-markdown :deep(table) { font-size: 13px; }
.conversation-markdown :deep(h1), .conversation-markdown :deep(h2), .conversation-markdown :deep(h3) { font-size: 16px; }
.conversation-markdown :deep(img) { max-width: 100%; }
.conversation-latest { position: absolute; right: 16px; bottom: 12px; width: 34px; height: 34px; padding: 0; display: grid; place-items: center; }
.conversation-composer { position: relative; flex: 0 1 auto; min-height: 0; max-height: 65%; overflow-y: auto; overscroll-behavior: contain; padding: 12px; background: #fff; box-sizing: border-box; }
.conversation-questions { display: grid; gap: 12px; max-height: min(32dvh, 280px); overflow-y: auto; min-width: 0; margin: 0 0 8px; padding: 8px 0; border: 0; }
.conversation-questions legend { font-size: 14px; font-weight: 600; color: #305d4e; }
.conversation-questions label { display: grid; gap: 6px; min-width: 0; font-size: 14px; line-height: 1.6; overflow-wrap: anywhere; }
.conversation-questions input { width: 100%; min-width: 0; box-sizing: border-box; min-height: 38px; font-size: 14px; }
.conversation-question { display: grid; gap: 6px; min-width: 0; }
.conversation-question-header { display: flex; align-items: flex-start; gap: 12px; }
.conversation-question-header label { flex: 1; }
.question-skip { flex: 0 0 auto; border: 0; padding: 4px 8px; background: transparent; color: #2f7d6d; font-size: 13px; white-space: nowrap; }
.question-skip:hover { background: #edf5f1; }
.question-skip:focus-visible { outline: 2px solid #2f7d6d; outline-offset: 2px; }
.question-skipped { margin: 0; color: #63736e; font-size: 13px; }
.conversation-error { max-width: 820px; margin: 0 auto 8px; color: #a23430; font-size: 13px; }
.conversation-composer-inner { max-width: 820px; margin: 0 auto; padding: 10px 12px; border: 1px solid #cddbd3; border-radius: 8px; background: #fff; box-shadow: 0 3px 12px rgba(28, 56, 43, .045); transition: border-color .15s, box-shadow .15s; }
.conversation-composer-inner:focus-within { border-color: #438b72; box-shadow: 0 0 0 3px rgba(67, 139, 114, .1); }
.conversation-composer-inner.is-disabled { background: #f8faf9; }
.conversation-composer textarea { display: block; width: 100%; min-height: 72px; max-height: 144px; resize: vertical; padding: 6px 2px; background: transparent; border: 0; border-radius: 0; box-sizing: border-box; font: inherit; font-size: 14px; line-height: 1.65; box-shadow: none; }
.conversation-composer textarea:focus { outline: none; border: 0; box-shadow: none; }
.conversation-composer textarea::placeholder { color: #88948e; }
.conversation-composer textarea:disabled { color: #76847c; background: transparent; }
.conversation-composer-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 10px; padding-top: 8px; border-top: 1px solid #eef2ef; }
.conversation-composer-actions button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 36px; font-size: 13px; padding: 6px 10px; }
.conversation-attach { color: #4b6257; background: transparent; border: 1px solid transparent; }
.conversation-attach:hover:not(:disabled) { background: #e8f0ec; }
.conversation-send { margin-left: auto; flex-shrink: 0; border-radius: 6px; }
.conversation-send:disabled { opacity: 1; background: #e8eeea; border-color: #e0e8e3; color: #8a9b90; }
.conversation-files { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; min-width: 0; }
.conversation-drafts { max-height: 90px; overflow-y: auto; }
.conversation-file { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; min-width: 0; padding: 4px 7px; border: 1px solid #dce3df; background: #fff; border-radius: 4px; color: #52685c; font-size: 12px; }
.conversation-file > span { min-width: 0; overflow-wrap: anywhere; }
.conversation-file svg { flex-shrink: 0; }
.conversation-file button { width: 24px; height: 24px; padding: 0; display: grid; place-items: center; flex-shrink: 0; color: #5e6f66; background: transparent; border: 0; }
button:focus-visible { outline: 2px solid #388a73; outline-offset: 2px; }
@media (max-width: 600px) { .conversation-messages { padding: 24px 14px 14px; } .conversation-composer { padding: 10px; } .conversation-empty-symbol { width: 52px; height: 52px; } .conversation-message.from-user { max-width: 94%; } }
@media (max-height: 540px) {
  .conversation-history { min-height: 56px; }
  .conversation-messages { padding-top: 44px; padding-bottom: 12px; }
  .conversation-composer textarea { min-height: 44px; max-height: 80px; }
  .conversation-composer-actions { margin-top: 6px; padding-top: 6px; }
}
</style>
