<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject, ref, watch } from "vue";
import { FileSpreadsheet, MessageSquare } from "lucide-vue-next";
import { APP_CONTEXT_KEY } from "./appContext";
import ConstraintAiWizard from "./ConstraintAiWizard.vue";
import ConstraintTemplateGallery from "./ConstraintTemplateGallery.vue";

const { entitlement, projectId, organizationId, currentUserId } = inject(APP_CONTEXT_KEY)!;
const allowed = computed(() => entitlement.value.account_status === "member" && entitlement.value.membership_active === true && entitlement.value.ai_enabled === true);
const mode = ref("conversation");
const templatesOpened = ref(false);
function selectMode(value: string) {
  mode.value = value;
  if (value === "file") templatesOpened.value = true;
}
function navigateTabs(event: KeyboardEvent) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  selectMode(event.key === "Home" ? "conversation" : event.key === "End" ? "file" : mode.value === "file" ? "conversation" : "file");
  const tabs = (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]');
  tabs[mode.value === "file" ? 1 : 0]?.focus();
}
watch([projectId, organizationId, currentUserId, allowed], () => { mode.value = "conversation"; templatesOpened.value = false; });
</script>

<template>
  <section class="constraint-ai-creator">
    <template v-if="allowed">
      <div class="creator-tabs" role="tablist" aria-label="AI 约束创建方式" @keydown="navigateTabs">
        <button type="button" role="tab" :aria-selected="mode === 'conversation'" :tabindex="mode === 'conversation' ? 0 : -1" @click="selectMode('conversation')"><MessageSquare :size="16" />从对话新建</button>
        <button type="button" role="tab" :aria-selected="mode === 'file'" :tabindex="mode === 'file' ? 0 : -1" @click="selectMode('file')"><FileSpreadsheet :size="16" />从模板文件新建</button>
      </div>
      <div v-show="mode === 'conversation'" role="tabpanel" aria-label="从对话新建"><ConstraintAiWizard /></div>
      <div v-if="templatesOpened" v-show="mode === 'file'" role="tabpanel" aria-label="从模板文件新建"><ConstraintTemplateGallery /></div>
    </template>
    <ConstraintAiWizard v-else />
  </section>
</template>

<style scoped>
.constraint-ai-creator { display: flex; flex: 1; flex-direction: column; min-width: 0; min-height: 0; width: 100%; height: 100%; overflow: hidden; }
.constraint-ai-creator > [role=tabpanel] { display: flex; flex: 1; min-width: 0; min-height: 0; width: 100%; overflow: hidden; }
.creator-tabs { display: flex; gap: 20px; padding-left: 10px; border-bottom: 1px solid #dce5df; margin-bottom: 20px; }
.creator-tabs button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 44px; padding: 10px 2px; border: 0; border-bottom: 2px solid transparent; border-radius: 0; background: transparent; color: #65766d; font-size: 14px; font-weight: 600; }
.creator-tabs button[aria-selected=true] { color: #257866; border-bottom-color: #257866; }
.creator-tabs button:focus-visible { outline: 2px solid #257866; outline-offset: 2px; }
@media (max-width: 480px) { .creator-tabs { gap: 12px; } .creator-tabs button { flex: 1; font-size: 13px; } .creator-tabs svg { flex-shrink: 0; } }
</style>
<style scoped src="../styles/aiCreatorLayout.css"></style>
