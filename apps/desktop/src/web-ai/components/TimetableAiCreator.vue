<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue';
import { ArrowLeft, ArrowRight, FileSpreadsheet, Upload, X } from 'lucide-vue-next';
import { APP_CONTEXT_KEY } from './appContext';
import TemplatePlanningMode from './TemplatePlanningMode.vue';
import TimetableSettingsView from './TimetableSettingsView.vue';
import TimetableSheetAnnotator from './TimetableSheetAnnotator.vue';
import type { TimetableAiOptions, TimetableAiResult, TimetableSheet, TimetableZoning } from '../utils/timetableAi';
defineProps<{ production?: boolean }>();

const { projectId, schoolData, request, applyAiTimetableDraft, timetableTemplateSaveRevision, loading } = inject(APP_CONTEXT_KEY)!;
const step = ref<'setup' | 'upload' | 'review'>('setup');
const example = ref<'axis' | 'fixed' | null>(null);
const examples = {
  axis: [
    { title: '是 · 横轴星期，纵轴时间', headers: ['时间', '周一', '周二'], rows: [['08:00–08:40', '语文', '数学'], ['08:50–09:30', '数学', '英语']] },
    { title: '否 · 例如班级为纵轴', headers: ['班级', '周一第1节', '周一第2节'], rows: [['七年级1班', '语文', '数学'], ['七年级2班', '英语', '语文']] },
  ],
  fixed: [
    { title: '是 · 同一课次每天时间相同', headers: ['课次', '周一', '周二'], rows: [['第1节', '08:00–08:40', '08:00–08:40'], ['第2节', '08:50–09:30', '08:50–09:30']] },
    { title: '否 · 同一课次每天时间可不同', headers: ['课次', '周一', '周二'], rows: [['第1节', '08:00–08:40', '08:10–08:50'], ['第2节', '08:50–09:30', '09:00–09:40']] },
  ],
};
function toggleExample(value: 'axis' | 'fixed') { example.value = example.value === value ? null : value; }
const options = ref<TimetableAiOptions>({ name: '', planning_mode: 'independent', regular: true, fixed: true, sheet: '' });
const mode = ref<'create' | 'modify'>('create');
const targetId = ref('');
const busy = ref(false);
const status = ref('');
const error = ref('');
const file = ref<File | null>(null);
const sheets = ref<TimetableSheet[]>([]);
const zoning = ref<TimetableZoning | null>(null);
const selectedSheet = computed(() => sheets.value.find(s => s.name === options.value.sheet));
const cellRoles = computed({ get: () => options.value.cell_roles || {}, set: value => {
  options.value.cell_roles = value;
  if (zoning.value) {
    for (const [source, role] of Object.entries(value)) {
      const zone = zoning.value.cells.find(c => c.source === source);
      if (zone) { if (zone.role !== role && role === 'custom') zone.placement = 'display'; zone.role = role; }
      else zoning.value.cells.push({ source, role });
    }
    zoning.value.cells = zoning.value.cells.filter(c => c.role === 'ignored' || value[c.source]);
  }
} });
watch(() => options.value.sheet, () => { options.value.cell_roles = {}; zoning.value = null; });
const result = ref<TimetableAiResult | null>(null);
const saved = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const canReuse = computed(() => Boolean(schoolData.value.default_weekly_timetable_template));
const valid = computed(() => options.value.name.trim() && (mode.value === 'create' || targetId.value) && (options.value.planning_mode !== 'reuse' || canReuse.value));
let controller: AbortController | null = null;
let sequence = 0;
function errorMessage(exc: unknown) {
  const text = exc instanceof Error ? exc.message : '请求失败，请重试';
  try { const parsed = JSON.parse(text); return typeof parsed.detail === 'string' ? parsed.detail : text; } catch { return text; }
}
function reset() {
  sequence++; controller?.abort(); busy.value = false;
  step.value = 'setup'; file.value = null; sheets.value = []; result.value = null; zoning.value = null; error.value = ''; targetId.value = ''; options.value.cell_roles = {};
}
watch(projectId, reset);
watch(timetableTemplateSaveRevision, () => { if (step.value === 'review') saved.value = true; });
onBeforeUnmount(() => { sequence++; controller?.abort(); });
watch(targetId, id => {
  const template = schoolData.value.weekly_timetable_templates.find(t => String(t.id) === id);
  if (template) {
    options.value.name = String(template.name || '');
    const config = (template.display_config || {}) as Record<string, unknown>;
    options.value.regular = (config.layout_kind || 'weekly') === 'weekly';
    options.value.fixed = config.time_mode !== 'variable';
    options.value.planning_mode = template.periods_locked ? 'reuse' : 'independent';
  }
});
function next() { if (valid.value) { options.value.name = options.value.name.trim(); step.value = 'upload'; error.value = ''; } }
async function upload(event: Event) {
  const selected = (event.target as HTMLInputElement).files?.[0];
  if (!selected) return;
  const current = ++sequence;
  controller?.abort(); controller = new AbortController();
  file.value = null; sheets.value = []; result.value = null; zoning.value = null; error.value = ''; options.value.cell_roles = {}; busy.value = true; status.value = '正在解析Excel单元格与合并区域…';
  try {
    const form = new FormData(); form.append('file', selected);
    const parsed = await request(`/api/projects/${projectId.value}/timetable/ai/parse`, { method: 'POST', body: form, signal: controller.signal, localError: true, silent: true });
    if (current !== sequence) return;
    sheets.value = parsed.sheets; file.value = selected;
    options.value.sheet = parsed.sheets.length === 1 ? parsed.sheets[0].name : '';
  } catch (exc) { if (current === sequence) error.value = errorMessage(exc); }
  finally { if (current === sequence) busy.value = false; }
}
async function analyze() {
  if (!file.value || !options.value.sheet || busy.value) return;
  const current = ++sequence;
  controller?.abort(); controller = new AbortController();
  busy.value = true; error.value = ''; status.value = 'AI正在判断模板并划分表头、课程与自定义区域…';
  try {
    const form = new FormData(); form.append('file', file.value); form.append('options', JSON.stringify(options.value));
    const response: { zoning: TimetableZoning } = await request(`/api/projects/${projectId.value}/timetable/ai/analyze`, { method: 'POST', body: form, signal: controller.signal, localError: true, silent: true });
    if (current !== sequence) return;
    zoning.value = response.zoning;
    zoning.value.columns = Array.from({ length: selectedSheet.value?.columns || 0 }, (_, i) => response.zoning.columns.find(c => c.source_column === i + 1) || { source_column: i + 1, kind: 'custom' as const, weekday: 0 });
    options.value.cell_roles = Object.fromEntries(response.zoning.cells.filter(c => c.role !== 'ignored').map(c => [c.source, c.role])) as NonNullable<TimetableAiOptions['cell_roles']>;
    if (!response.zoning.suitable) error.value = response.zoning.reason;
  } catch (exc) { if (current === sequence) error.value = errorMessage(exc); }
  finally { if (current === sequence) busy.value = false; }
}
async function confirmAnnotations() {
  if (!file.value || !zoning.value || busy.value) return;
  const current = ++sequence;
  controller?.abort(); controller = new AbortController();
  busy.value = true; error.value = ''; status.value = '正在根据确认标注生成预览…';
  try {
    const form = new FormData(); form.append('file', file.value); form.append('options', JSON.stringify(options.value)); form.append('zoning', JSON.stringify(zoning.value));
    const response: TimetableAiResult = await request(`/api/projects/${projectId.value}/timetable/ai/preview`, { method: 'POST', body: form, signal: controller.signal, localError: true, silent: true });
    if (current !== sequence) return;
    applyAiTimetableDraft(response, options.value, mode.value === 'modify' ? targetId.value : '');
    result.value = response; saved.value = false; step.value = 'review';
  } catch (exc) { if (current === sequence) error.value = errorMessage(exc); }
  finally { if (current === sequence) busy.value = false; }
}
const zoneLabels: Record<string, string> = { header: '表头', course: '课程', detail: '课程附属信息', custom: '自定义', axis: '星期与时间', ignored: '忽略' };
</script>

<template>
  <section class="timetable-ai-workflow" aria-label="课表创建与修改">
    <header class="timetable-ai-heading"><h2>课表创建与修改</h2><ol aria-label="处理步骤"><li :aria-current="step === 'setup' ? 'step' : undefined"><span>1</span>规划方式</li><li :aria-current="step === 'upload' ? 'step' : undefined"><span>2</span>Excel识别</li><li :aria-current="step === 'review' ? 'step' : undefined"><span>3</span>检查与保存</li></ol></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <form v-if="step === 'setup'" class="timetable-ai-setup" @submit.prevent="next">
      <fieldset class="timetable-ai-operation timetable-ai-modes" aria-label="操作"><label><input v-model="mode" type="radio" name="timetable-ai-operation" value="create" />创建模板</label><label><input v-model="mode" type="radio" name="timetable-ai-operation" value="modify" />修改模板</label></fieldset>
      <label v-if="mode === 'modify'" class="timetable-ai-field"><span>现有模板</span><select v-model="targetId" required><option value="" disabled>选择模板</option><option v-for="template in schoolData.weekly_timetable_templates" :key="String(template.id)" :value="String(template.id)">{{ template.name }}</option></select></label>
      <label class="timetable-ai-field"><span>模板名称</span><input v-model="options.name" maxlength="80" required /></label>
      <div class="timetable-ai-field"><span aria-hidden="true">课次规划方式</span><TemplatePlanningMode v-model="options.planning_mode" :can-reuse="canReuse" /></div>
      <div class="timetable-ai-field"><span id="timetable-ai-axis-label">横轴星期、纵轴时间</span><div class="timetable-ai-field-controls"><fieldset class="timetable-ai-modes" aria-labelledby="timetable-ai-axis-label"><label><input v-model="options.regular" name="timetable-ai-axis" type="radio" :value="true" />是</label><label><input v-model="options.regular" name="timetable-ai-axis" type="radio" :value="false" />否</label></fieldset><button type="button" class="timetable-ai-example-link" :aria-expanded="example === 'axis'" aria-controls="timetable-ai-example-axis" @click="toggleExample('axis')">{{ example === 'axis' ? '收起示例' : '查看示例' }}</button></div>
        <div v-if="example === 'axis'" id="timetable-ai-example-axis" class="timetable-ai-examples" role="region" aria-label="坐标布局示例"><table v-for="item in examples.axis" :key="item.title"><caption>{{ item.title }}</caption><thead><tr><th v-for="heading in item.headers" :key="heading" scope="col">{{ heading }}</th></tr></thead><tbody><tr v-for="(row, index) in item.rows" :key="index"><td v-for="(cell, column) in row" :key="column">{{ cell }}</td></tr></tbody></table></div>
      </div>
      <div class="timetable-ai-field"><span id="timetable-ai-fixed-label">每天课次时间固定</span><div class="timetable-ai-field-controls"><fieldset class="timetable-ai-modes" aria-labelledby="timetable-ai-fixed-label"><label><input v-model="options.fixed" name="timetable-ai-fixed" type="radio" :value="true" />是</label><label><input v-model="options.fixed" name="timetable-ai-fixed" type="radio" :value="false" />否</label></fieldset><button type="button" class="timetable-ai-example-link" :aria-expanded="example === 'fixed'" aria-controls="timetable-ai-example-fixed" @click="toggleExample('fixed')">{{ example === 'fixed' ? '收起示例' : '查看示例' }}</button></div>
        <div v-if="example === 'fixed'" id="timetable-ai-example-fixed" class="timetable-ai-examples" role="region" aria-label="课次时间示例"><table v-for="item in examples.fixed" :key="item.title"><caption>{{ item.title }}</caption><thead><tr><th v-for="heading in item.headers" :key="heading" scope="col">{{ heading }}</th></tr></thead><tbody><tr v-for="(row, index) in item.rows" :key="index"><td v-for="(cell, column) in row" :key="column">{{ cell }}</td></tr></tbody></table><p>时间固定不代表每天所上科目相同。</p></div>
      </div>
      <footer><button :disabled="!valid">下一步<ArrowRight :size="16" /></button></footer>
    </form>
    <div v-else-if="step === 'upload'" class="timetable-ai-upload">
      <header><button type="button" class="btn-secondary" :disabled="busy" @click="step = 'setup'"><ArrowLeft :size="16" />返回</button><strong>{{ options.name }}</strong></header>
      <input ref="fileInput" class="timetable-ai-file-input" type="file" accept=".xlsx" :disabled="busy" @change="upload" />
      <button type="button" class="timetable-ai-file" :disabled="busy" @click="fileInput?.click()"><FileSpreadsheet :size="36" /><strong>{{ file?.name || '上传课表Excel模板' }}</strong><span>.xlsx · 最大5MB</span><Upload :size="20" /></button>
      <label v-if="sheets.length">工作表<select v-model="options.sheet" :disabled="busy"><option value="" disabled>选择要识别的工作表</option><option v-for="sheet in sheets" :key="sheet.name" :value="sheet.name">{{ sheet.name }} · {{ sheet.rows }}行 × {{ sheet.columns }}列</option></select></label>
      <TimetableSheetAnnotator v-if="selectedSheet?.cells?.length" :key="selectedSheet.name" v-model="cellRoles" :sheet="selectedSheet" :header-row="zoning?.column_header_row" :disabled="busy" />
      <p v-if="busy" role="status">{{ status }}</p>
      <footer><button v-if="busy" type="button" class="btn-secondary" @click="sequence++; controller?.abort(); busy = false"><X :size="16" />取消等待</button><button type="button" class="btn-secondary" :disabled="busy || !file || !options.sheet" @click="analyze">{{ busy ? '处理中…' : zoning ? '重新识别标注' : 'AI识别并标注' }}</button><button v-if="zoning" type="button" :disabled="busy || !zoning.suitable" @click="confirmAnnotations">确认标注，生成预览</button></footer>
    </div>
    <div v-else>
      <header class="timetable-ai-review-heading"><button type="button" class="btn-secondary" :disabled="loading" @click="step = 'upload'"><ArrowLeft :size="16" />重新识别</button><span role="status">{{ saved ? '上次保存成功' : '识别草稿 · 尚未保存' }}</span><button v-if="saved" type="button" class="btn-secondary" @click="reset">创建或修改其他模板</button></header>
      <details v-if="result" class="timetable-ai-zones"><summary>分区结果 · {{ result.draft.zones.length }} 个单元格</summary><p>{{ result.draft.reason }}</p><ul><li v-for="zone in result.draft.zones" :key="zone.source"><code>{{ zone.source }}</code><span>{{ zoneLabels[zone.role] }}</span><span>{{ zone.reason }}</span></li></ul></details>
      <TimetableSettingsView embedded :production="production" />
    </div>
  </section>
</template>

<style scoped>
.timetable-ai-workflow { width: 100%; min-width: 0; min-height: 0; padding: 0 24px 24px; overflow: auto; color: #29443e; background: #fff; font-size: 14px; box-sizing: border-box; container-type: inline-size; scrollbar-width: thin; }
.timetable-ai-heading, .timetable-ai-upload > header, .timetable-ai-review-heading { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
.timetable-ai-heading { padding: 16px 0; border-bottom: 1px solid #e1e9e5; margin-bottom: 0; }
h2 { font-size: 14px; line-height: 24px; margin: 0; }
ol { list-style: none; display: flex; flex-wrap: wrap; gap: 20px; padding: 0; margin: 0 0 0 auto; color: #63766e; font-size: 13px; }
ol li { display: flex; align-items: center; gap: 7px; line-height: 24px; }
ol li > span { display: grid; place-items: center; width: 22px; height: 22px; flex: none; border-radius: 50%; background: #f0f4f2; color: #64736d; font-size: 12px; }
ol li[aria-current] > span { background: #2d7b6c; color: white; }
li[aria-current] { color: #19766a; font-weight: 700; }
.timetable-ai-setup, .timetable-ai-upload { width: 100%; max-width: 960px; margin: auto; display: grid; gap: 0; }
.timetable-ai-upload { max-width: 780px; padding-top: 24px; gap: 16px; }
.timetable-ai-field { display: grid; grid-template-columns: 156px minmax(0, 1fr); align-items: center; gap: 24px; padding: 18px 0; border-bottom: 1px solid #e1e9e5; min-width: 0; }
.timetable-ai-field > span { font-weight: 600; line-height: 24px; }
.timetable-ai-field-controls { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-width: 0; flex-wrap: wrap; }
.timetable-ai-example-link { padding: 6px 0; border: 0; background: transparent; box-shadow: none; color: #287668; font-size: 13px; font-weight: 500; }
.timetable-ai-example-link:hover { background: transparent; text-decoration: underline; }
.timetable-ai-example-link:focus-visible { outline: 2px solid #388a73; outline-offset: 3px; }
.timetable-ai-examples { grid-column: 2; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; min-width: 0; }
.timetable-ai-examples table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 12px; }
.timetable-ai-examples caption { text-align: left; font-size: 13px; font-weight: 600; padding: 0 0 8px; color: #47675c; }
.timetable-ai-examples th, .timetable-ai-examples td { padding: 8px 5px; border: 1px solid #dce5df; text-align: center; overflow-wrap: anywhere; }
.timetable-ai-examples th { background: #f0f4f2; }
.timetable-ai-examples p { grid-column: 1 / -1; margin: 0; font-size: 12px; color: #64736d; }
@container (max-width: 800px) { .timetable-ai-examples { grid-template-columns: minmax(0, 1fr); } }
.timetable-ai-modes { display: inline-flex; justify-self: start; gap: 3px; padding: 3px; border: 1px solid #dce5df; border-radius: 6px; background: #f4f7f5; margin: 0; min-width: 0; }
.timetable-ai-modes label { position: relative; justify-content: center; min-width: 66px; min-height: 32px; padding: 5px 14px; box-sizing: border-box; border: 1px solid transparent; border-radius: 4px; font-size: 13px; color: #64736d; cursor: pointer; }
.timetable-ai-modes label:has(input:checked) { background: #fff; border-color: #dce5df; color: #236957; box-shadow: 0 1px 3px #203c2e14; }
.timetable-ai-modes label:has(input:focus-visible) { outline: 2px solid #388a73; outline-offset: 2px; }
.timetable-ai-modes input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.timetable-ai-operation { width: min(360px, 100%); justify-self: center; margin: 12px 0 8px; padding: 4px; border-radius: 8px; background: #f0f4f2; }
.timetable-ai-operation label { flex: 1; min-height: 34px; border-radius: 6px; }
:deep(.template-planning-mode) { padding: 0; gap: 20px; font-size: 13px; }
:deep(.template-planning-mode legend) { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
:deep(.template-planning-mode input) { accent-color: #2d7b6c; }
:deep(.template-planning-mode label:has(input:disabled)) { color: #89968f; cursor: not-allowed; }
label:not(.timetable-ai-field) { display: grid; gap: 8px; }
fieldset label { display: flex; align-items: center; gap: 8px; }
input[type=radio] { width: auto; }
input, select { min-width: 0; max-width: 100%; }
footer { display: flex; justify-content: flex-end; gap: 12px; padding-top: 20px; }
footer button { min-height: 36px; font-size: 13px; padding: 8px 16px; }
.timetable-ai-field > input, .timetable-ai-field > select { width: 100%; min-height: 40px; font-size: 14px; border-radius: 6px; }
.timetable-ai-review-heading { margin-top: 20px; }
button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
.timetable-ai-file-input { display: none; }
.timetable-ai-file { display: flex; flex-direction: column; width: 100%; min-height: 200px; padding: 24px; border: 1px dashed #6e9b91; background: #f6faf9; color: #294f44; border-radius: 8px; }
.timetable-ai-file strong { overflow-wrap: anywhere; }
.timetable-ai-zones { margin-bottom: 16px; }
.timetable-ai-zones ul { max-height: 240px; overflow: auto; list-style: none; padding: 0; }
.timetable-ai-zones li { display: grid; grid-template-columns: 70px 100px 1fr; gap: 12px; padding: 6px; border-bottom: 1px solid #e4eae8; }
:deep(.timetable-ai-editor) { border: 0; padding: 0; box-shadow: none; }
:deep(.timetable-ai-editor .settings-card) { border: 0; box-shadow: none; padding: 0; }
@container (max-width: 640px) { .timetable-ai-field { grid-template-columns: minmax(0, 1fr); gap: 10px; padding: 14px 0; } .timetable-ai-examples { grid-column: 1; } .timetable-ai-heading { gap: 10px; } ol { width: 100%; margin: 0; gap: 12px; } }
@media(max-width: 760px) { .timetable-ai-workflow { padding: 0 12px 16px; } }
</style>
