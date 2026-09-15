<script setup lang="ts">
import { ref } from "vue";
import { CalendarDays, DoorOpen, Users, SlidersHorizontal, Play } from "lucide-vue-next";
import CalendarView from "./components/CalendarView.vue";
import SchoolDataView from './components/SchoolDataView.vue';
import ConstraintsView from './components/ConstraintsView.vue';
import RunsWorkspace from './components/RunsWorkspace.vue';
import PlanningView from './components/PlanningView.vue';
import AiSettingsView from './components/AiSettingsView.vue';
import AiAssistantView from './components/AiAssistantView.vue';
const revision = ref(0);
const active = ref('calendar');
const pages = [{id:'calendar',label:'课表设置',icon:CalendarDays},{id:'rooms',label:'教室设置',icon:DoorOpen},{id:'school',label:'学校数据',icon:Users},{id:'planning',label:'课程计划',icon:CalendarDays},{id:'constraints',label:'约束配置',icon:SlidersHorizontal},{id:'runs',label:'排课运行',icon:Play}];
const aiPages = [{id:'ai-settings',label:'AI 设置',icon:SlidersHorizontal},{id:'agent',label:'AI 助手',icon:Users}];
</script>
<template>
  <div class="browser-preview">
    <header class="browser-preview-header">
      <img src="/app-icon.png" alt="" width="32" height="32" /><strong>时奕教务排课</strong><span>本地开发预览 · v0.2.10</span>
      <small>独立测试项目 · 修改自动保留在本机（模板需点击保存）</small>
    </header>
    <div class="browser-preview-body">
      <aside class="browser-preview-nav">
        <nav class="preview-primary-nav" aria-label="主要功能"><button v-for="page in pages" :key="page.id" :class="{active:active === page.id}" @click="active = page.id"><component :is="page.icon" :size="18" />{{ page.label }}</button></nav>
        <nav class="preview-ai-nav" aria-label="AI 功能"><button v-for="page in aiPages" :key="page.id" :class="{active:active === page.id}" @click="active = page.id"><component :is="page.icon" :size="18" />{{ page.label }}</button></nav>
      </aside>
      <main><AiAssistantView v-if="active === 'agent'" project-id="browser-preview" project-name="本地开发项目" @navigate="active = $event === 'workspace' ? 'calendar' : $event" /><AiSettingsView v-else-if="active === 'ai-settings'" /><CalendarView v-else-if="active === 'calendar'" :revision="revision" @revision="revision = $event" /><SchoolDataView v-else-if="active === 'rooms' || active === 'school'" :key="active" :mode="active === 'rooms' ? 'rooms' : 'school'" :revision="revision" @revision="revision = $event" /><PlanningView v-else-if="active === 'planning'" :revision="revision" @revision="revision = $event" /><ConstraintsView v-else-if="active === 'constraints'" :revision="revision" @revision="revision = $event" /><RunsWorkspace v-else :revision="revision" @revision="revision = $event" /></main>
    </div>
  </div>
</template>
<style scoped>
:global(body:has(.browser-preview)) { min-width: 0; }
.browser-preview { min-height: 100vh; background: #f7f8f5; }
.browser-preview-header { display: flex; align-items: center; gap: 18px; padding: 14px 24px; border-bottom: 1px solid #e2e5df; background: #fff; }
.browser-preview-header strong { font-size: 18px; }
.browser-preview-header span { font-size: 12px; background: #e8f2ee; color: #246354; border-radius: 5px; padding: 4px 8px; }
.browser-preview-header small { margin-left: auto; color: #62716f; }
.browser-preview-body { display: grid; grid-template-columns: 160px minmax(0, 1fr); }
.browser-preview-nav { position: sticky; top: 0; height: calc(100dvh - 61px); min-height: 240px; display:flex; flex-direction:column; padding: 20px 12px; border-right: 1px solid #e2e5df; }
.preview-primary-nav { min-height:0; overflow-y:auto; }
.preview-ai-nav { margin-top:auto; flex-shrink:0; padding-top:12px; border-top:1px solid #e2e5df; }
.browser-preview-nav button { display: flex; width:100%; gap: 10px; align-items: center; padding: 12px; margin-bottom:8px; border:0; border-radius: 6px; color: #50675e; background: transparent; font-weight: 600; }
.browser-preview-nav button.active { color:#246354; background:#e8f2ee; }
main { min-width: 0; padding: 24px; }
@media (max-width: 800px) { .browser-preview-body { grid-template-columns: 1fr; } .browser-preview-nav { display:flex; flex-wrap:wrap; } .browser-preview-nav button {width:auto;} main { padding: 16px; } .browser-preview-header small { display: none; } }
@media (max-width: 800px) { .browser-preview-nav { position:static; height:auto; min-height:0; flex-direction:row; } .preview-primary-nav, .preview-ai-nav { display:flex; flex-wrap:wrap; } .preview-ai-nav { width:100%; margin-top:8px; } }
</style>
