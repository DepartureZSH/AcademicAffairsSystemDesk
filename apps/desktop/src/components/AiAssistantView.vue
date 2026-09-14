<script setup lang="ts">
import { provide } from 'vue';
import AgentView from '../web-ai/components/AgentView.vue';
import { APP_CONTEXT_KEY } from '../web-ai/components/appContext';
import { useDesktopAgent } from '../web-ai/useDesktopAgent';
import AiExpectedTimePicker from './AiExpectedTimePicker.vue';
const props=defineProps<{projectId:string;projectName:string}>();
const emit=defineEmits<{navigate:[section:string]}>();
const agent=useDesktopAgent(props,section=>emit('navigate',section));
provide(APP_CONTEXT_KEY,agent);
const {showCoursePreferredPicker,expectedPickerContext}=agent;
</script>
<template>
  <section class="desktop-agent">
    <AiExpectedTimePicker v-if="showCoursePreferredPicker && expectedPickerContext" :context="expectedPickerContext" @close="showCoursePreferredPicker=false;expectedPickerContext=null" />
    <div class="web-ai"><AgentView><template #notice>
    <details class="agent-data-notice">
      <summary>AI 会向自选服务发送对话、附件及按需查询的项目资料，可能产生费用。修改须经你确认。查看说明</summary>
      <p>每次发送前会确认服务地址和数据范围。使用 AI 时，本场景涉及的学校资料、课表、课程计划及约束可能发送给服务商；普通排课仍在本地运行。</p>
      <p>AI 先生成变更清单，你确认后才会备份并保存至本地项目。对话和审核记录随项目保留。不能安全转换的操作会拒绝执行，不会跳过错误后声称成功。</p>
    </details>
    </template></AgentView></div>
  </section>
</template>
<style src="../web-ai/web-ai.css"></style>
<style scoped>
.desktop-agent { width:100%; min-width:0; }
.agent-data-notice { flex:none; margin:8px 12px; padding:8px 12px; background:#fffaf0; border:1px solid #ead8aa; border-radius:8px; color:#66502b; font-size:12px; line-height:1.7; max-height:150px; overflow:auto; }
.agent-data-notice summary { cursor:pointer; }
.agent-data-notice p { margin:6px 0; }
.web-ai { font-family:"Inter","PingFang SC","Microsoft YaHei UI","Microsoft YaHei",system-ui,sans-serif; }
.web-ai :deep(.agent-simple-page:not(.is-fullscreen)) { height:calc(100dvh - 150px); min-height:520px; border-radius:10px; border:1px solid #e1e9e4; }
.web-ai :deep(.conversation-messages:has(.conversation-empty)) { padding:12px 24px; }
@media(max-height:800px) { .web-ai :deep(.conversation-empty-symbol) { width:40px; height:40px; } .web-ai :deep(.conversation-empty) { gap:8px; } }
</style>
