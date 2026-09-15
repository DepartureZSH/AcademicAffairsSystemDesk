<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Download, FileSpreadsheet, LockKeyhole, Search, Upload } from "lucide-vue-next";
import { APP_CONTEXT_KEY } from "./appContext";
import ConstraintAiWizard from "./ConstraintAiWizard.vue";
import type { ExpansionPayload } from "../utils/constraintExpansion";

const { downloadOfficialWorkbook, request, entitlement, projectId, organizationId, currentUserId, loadConstraints, loadOverview, showSection } = inject(APP_CONTEXT_KEY)!;
const allowed = computed(() => entitlement.value.account_status === "member" && entitlement.value.membership_active === true && entitlement.value.ai_enabled === true);
const templates = ref<any[]>([]);
const search = ref("");
const filename = ref("");
const loading = ref(false);
const filteredTemplates = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  return templates.value.filter(item => `${item.name} ${item.description || ''}`.toLocaleLowerCase().includes(query));
});
const rows = ref<any[]>([]);
const active = ref<number | null>(null);
const busy = ref(false);
const error = ref("");
const input = ref<HTMLInputElement | null>(null);
let version = 0;
const readyRows = computed(() => rows.value.filter(row => row.prepared && row.selected && row.status !== "done"));
const pendingAnalysis = computed(() => rows.value.filter(row => !row.error && !row.analysis && row.status !== "done"));
const path = () => `/api/projects/${projectId.value}/constraints/ai/`;
function readable(exc: unknown) { const raw = exc instanceof Error ? exc.message : "请求失败，请重试。"; try { return JSON.parse(raw).detail || raw; } catch { return raw; } }
watch([projectId, organizationId, currentUserId, allowed], () => { version++; rows.value = []; active.value = null; templates.value = []; filename.value = ''; search.value = ''; });
onBeforeUnmount(() => { version++; });
onMounted(async () => {
  if (!allowed.value) return;
  loading.value = true;
  const current = version;
  try { const data = await request(path() + "workbooks", { silent: true, localError: true }); if (current === version) templates.value = data.items; }
  catch (exc) { if (current === version) error.value = readable(exc); }
  finally { loading.value = false; }
});
async function download(item: any) {
  if (busy.value || !allowed.value) return;
  busy.value = true; error.value = ""; const current = version;
  try {
    await downloadOfficialWorkbook('constraints', item.id);
  } catch (exc) { if (current === version) error.value = readable(exc); }
  finally { busy.value = false; }
}
async function upload(event: Event) {
  const element = event.target as HTMLInputElement; const file = element.files?.[0]; element.value = "";
  if (!file || busy.value || !allowed.value) return;
  if (rows.value.some(r => r.prepared && r.status !== 'done') && !window.confirm('重新上传将清空尚未创建的核对结果，是否继续？')) return;
  const form = new FormData(); form.append("file", file); busy.value = true; error.value = ""; const current = ++version;
  try {
    const result = await request(path() + "workbooks/parse", { method: "POST", body: form, silent: true, localError: true });
    if (current === version) { rows.value = result.rows.map((r: any) => ({ ...r, status: "pending", selected: false })); active.value = null; filename.value = file.name; }
  } catch (exc) { if (current === version) error.value = readable(exc); }
  finally { busy.value = false; }
}
function prepared(payload: ExpansionPayload) {
  if (active.value === null) return;
  Object.assign(rows.value[active.value], { prepared: payload, selected: true, status: "ready", result: "" }); active.value = null;
}
async function analyzeAll() {
  if (busy.value || !allowed.value) return;
  busy.value = true; const current = version; const prefix = path();
  for (const row of [...pendingAnalysis.value]) {
    if (current !== version || !allowed.value) break;
    row.result = '正在解析规则和课次...';
    try {
      row.analysis = await request(prefix + 'workbooks/analyze-row', { method: 'POST', body: JSON.stringify({ query: row.query, scope: row.scope, required: row.required, penalty: row.penalty }), silent: true, localError: true });
      row.result = row.analysis.resolution?.status === 'resolved' ? '已解析，待核对四步并确认' : '需补充选择，请打开核对';
    } catch (exc) { row.result = readable(exc); }
  }
  busy.value = false;
}
async function saveAll() {
  if (busy.value || !allowed.value || !readyRows.value.length) return;
  busy.value = true; error.value = ""; const current = version; const prefix = path();
  for (const row of [...readyRows.value]) {
    if (current !== version || !allowed.value) break;
    row.status = "saving";
    try {
      const data = await request(prefix + "expansion/commit", { method: "POST", body: JSON.stringify(row.prepared), silent: true, localError: true });
      row.status = "done"; row.selected = false; row.result = `已创建 ${data.created_count || 0} 组，已有 ${data.skipped_count || 0} 组`;
    } catch (exc) { row.status = "failed"; row.result = readable(exc); }
  }
  try { await loadConstraints(); await loadOverview(); } catch { error.value = "保存结果见各行；列表刷新失败，请稍后刷新。"; }
  busy.value = false;
}
</script>

<template>
      <section class="template-gallery" aria-label="约束模板广场">
        <div class="gallery-body">
          <div v-if="!allowed" class="gallery-locked"><LockKeyhole :size="28" /><h3>正式会员专享</h3><button type="button" class="btn-primary" @click="showSection('ai-settings')">前往 AI 设置</button></div>
          <template v-else-if="active === null">
            <div class="gallery-section-heading"><h3>模板广场</h3><label class="gallery-search"><Search :size="16" /><input v-model="search" type="search" aria-label="搜索约束模板" placeholder="搜索模板" /></label></div>
            <p v-if="loading" class="gallery-empty" role="status">正在加载模板...</p>
            <div v-else-if="filteredTemplates.length" class="gallery-templates"><article v-for="item in filteredTemplates" :key="item.id"><FileSpreadsheet :size="22" /><strong>{{ item.name }}</strong><button type="button" class="btn-secondary" :disabled="busy" @click="download(item)"><Download :size="16" />下载 Excel</button></article></div>
            <p v-else class="gallery-empty" role="status">{{ search.trim() ? '没有匹配的模板' : '暂无可用模板' }}</p>
            <section class="gallery-upload-section" aria-label="上传解析">
              <h3>上传解析</h3>
              <div class="gallery-upload"><FileSpreadsheet :size="24" /><div class="gallery-file"><strong>{{ filename || '约束模板文件' }}</strong><span>{{ filename ? `${rows.length} 行约束` : '.xlsx' }}</span></div><input ref="input" type="file" accept=".xlsx" hidden @change="upload" /><button type="button" class="btn-secondary" :disabled="busy" @click="input?.click()"><Upload :size="16" />{{ filename ? '更换文件' : '上传约束表' }}</button><button v-if="pendingAnalysis.length" type="button" class="btn-primary" :disabled="busy" @click="analyzeAll">AI 批量解析（{{ pendingAnalysis.length }} 行）</button><span v-if="busy" role="status">处理中...</span></div>
            </section>
            <div class="gallery-section-heading"><h3>确认区域</h3><span>{{ rows.length }} 行约束</span></div>
            <p v-if="!rows.length" class="gallery-empty">暂无待确认约束</p>
            <div v-if="rows.length" class="gallery-table"><table><thead><tr><th>创建</th><th>行</th><th>约束规则</th><th>强度</th><th>涉及课次</th><th>相似扩展</th><th>核对结果</th></tr></thead><tbody><tr v-for="(row, index) in rows" :key="row.row"><td><input v-model="row.selected" type="checkbox" :disabled="busy || !row.prepared || row.status === 'done'" :aria-label="`选择第${row.row}行`" /></td><td>{{ row.row }}</td><td>{{ row.query }}<details v-if="row.notes"><summary>备注</summary>{{ row.notes }}</details></td><td>{{ row.required ? '必须满足' : `尽量满足（${row.penalty}）` }}</td><td>{{ row.scope }}</td><td>{{ row.expand ? row.instruction : '不扩展' }}</td><td><p v-if="row.error" class="gallery-error">{{ row.error }}</p><p v-if="row.result" :class="{ 'gallery-error': row.status === 'failed' }">{{ row.result }}</p><span v-if="row.status === 'ready'">已核对 {{ row.prepared.source.groups.length }} 组，扩展 {{ row.prepared.selected_ids.length }} 组</span><button v-if="!row.error && row.status !== 'done'" type="button" class="btn-secondary" :disabled="busy" @click="active = index">{{ row.prepared ? '重新核对' : 'AI 解析并核对' }}</button></td></tr></tbody></table></div>
          </template>
          <template v-else><div class="gallery-review-head"><button type="button" class="btn-secondary" @click="active = null">返回约束表</button><strong>第 {{ rows[active].row }} 行</strong><span>{{ rows[active].query }}</span></div><ConstraintAiWizard :key="active" :preset="{ query: rows[active].query, scope: rows[active].scope, required: rows[active].required, penalty: rows[active].penalty, instruction: rows[active].expand ? rows[active].instruction : '', analysis: rows[active].analysis }" defer-save @prepared="prepared" /></template>
          <p v-if="error" class="gallery-error" role="alert">{{ error }}</p>
        </div>
        <footer v-if="allowed && active === null && rows.length"><span>待创建 {{ readyRows.length }} 行 · 已完成 {{ rows.filter(r => r.status === 'done').length }} 行</span><button type="button" class="btn-primary" :disabled="busy || !readyRows.length" @click="saveAll">{{ busy ? '正在逐行创建...' : '创建已勾选的约束' }}</button></footer>
      </section>
</template>

<style scoped>
.template-gallery { display: flex; flex: 1; flex-direction: column; height: 100%; min-width: 0; margin-left: 5%; margin-right: 5%; width: 90%; overflow: hidden; box-sizing: border-box; color: #29453c; }
.gallery-body { min-width: 0; min-height: 0; flex: 1; overflow-y: auto; overscroll-behavior: contain; padding-bottom: 8px; scrollbar-width: none; }
.gallery-body::-webkit-scrollbar { display: none; }
.gallery-section-heading, footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 0 0 14px; }
h3 { margin: 0; font-size: 16px; } .gallery-section-heading > span, .gallery-file span { font-size: 12px; color: #738078; }
.gallery-search { display: flex; align-items: center; gap: 8px; width: min(240px, 100%); min-width: 0; padding: 8px 10px; border: 1px solid #d6e1d9; border-radius: 5px; }
.gallery-search:focus-within { outline: 2px solid #2e7d68; outline-offset: 1px; }
.gallery-search input { width: 100%; min-width: 0; border: 0; border-radius: 0; padding: 0; outline: 0; box-shadow: none; background: transparent; font-size: 14px; }
.gallery-search svg { flex-shrink: 0; }
.gallery-upload-section { margin: 24px 0; padding: 20px 0; border-block: 1px solid #e0e8e3; }
.gallery-file { display: grid; gap: 4px; flex: 1 1 150px; min-width: 0; overflow-wrap: anywhere; font-size: 14px; }
.gallery-upload > svg { flex-shrink: 0; color: #2e7d68; }
.gallery-empty { padding: 24px 12px; margin: 0; background: #f7f9f8; text-align: center; color: #738078; font-size: 13px; }
.gallery-templates { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: 12px; }
article { display: grid; align-content: start; gap: 14px; padding: 16px; border: 1px solid #d6e1d9; border-radius: 6px; } article strong { font-size: 14px; }
.gallery-upload, .gallery-review-head { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 16px 0 0; }
.gallery-review-head { margin: 0 0 20px; overflow-wrap: anywhere; }
button { white-space: normal; } article button, .gallery-upload button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
.gallery-table { overflow-x: auto; } table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 13px; } th, td { padding: 12px 8px; text-align: left; vertical-align: top; border-bottom: 1px solid #e1e8e3; max-width: 260px; overflow-wrap: anywhere; } th { background: #f0f6f2; } details { color: #64786d; margin-top: 8px; line-height: 1.6; } footer { border-top: 1px solid #e0e8e3; border-bottom: 0; font-size: 13px; }
.gallery-error { color: #ac3030; font-size: 13px; } .gallery-locked { text-align: center; padding: 36px; }
input[type=checkbox] { width: 16px; height: 16px; accent-color: #2e7d68; }
footer { margin-top: 16px; padding: 16px 0; }
</style>
