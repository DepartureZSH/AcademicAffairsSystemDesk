<script setup lang="ts">
import { ShieldAlert } from 'lucide-vue-next';
defineProps<{ destination?: string }>();
</script>

<template>
  <aside class="ai-privacy-notice" aria-label="AI 使用与数据提示">
    <ShieldAlert :size="21" aria-hidden="true" />
    <div>
      <strong>使用 AI 前，请先了解数据去向</strong>
      <p>当你发送消息、提交附件或使用 AI 识别与生成时，本次任务所需的内容会发送到你配置的 AI 服务，可能包括学校、教师、班级、课程、课表及附件中的信息。请确认有权提供这些资料，并尽量先做脱敏处理。</p>
      <p v-if="destination" class="ai-destination">当前服务：<b>{{ destination }}</b></p>
      <p>不使用 AI 时，教务数据和排课计算仍保留在本地。AI 调用费用由你的服务商收取；数据如何保存和使用，以该服务商的政策为准。</p>
      <p>AI 结果可能有误，请核对后再应用到项目。</p>
    </div>
  </aside>
</template>

<style scoped>
.ai-privacy-notice { display:flex; align-items:flex-start; gap:12px; padding:16px 18px; border:1px solid #ead8aa; border-radius:10px; background:#fffaf0; color:#66502b; font-size:13px; line-height:1.7; }
.ai-privacy-notice > svg { flex-shrink:0; margin-top:2px; }
.ai-privacy-notice strong { font-size:14px; font-weight:650; }
.ai-privacy-notice p { margin:6px 0 0; }
.ai-destination { overflow-wrap:anywhere; }
</style>
