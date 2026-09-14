<script setup lang="ts">
// @ts-nocheck -- upstream component; its local adapter is checked separately.
import { computed, inject, onBeforeUnmount, ref, watch } from "vue";
import { APP_CONTEXT_KEY } from "./appContext";
import { LockKeyhole, Search, Sparkles } from "lucide-vue-next";
import { distributionLabel } from "../utils/itcConstraints";
import { compareNaturalClassNames } from "../utils/naturalClassNameSort";
import type { ExpansionSource, ExpansionPayload } from "../utils/constraintExpansion";

const props = withDefaults(defineProps<{ source: ExpansionSource; includeSource?: boolean; requireAi?: boolean; deferSave?: boolean; initialInstruction?: string }>(), { includeSource: true });
const emit = defineEmits<{ back: []; created: [result: any]; prepared: [payload: ExpansionPayload] }>();
const { request, projectId, organizationId, currentUserId, entitlement, loadAgentUsage } = inject(APP_CONTEXT_KEY)!;
const allowed = computed(() => entitlement.value.account_status === "member" && entitlement.value.membership_active === true && entitlement.value.ai_enabled === true);
const mode = ref("homeroom");
const ai = ref(!!props.initialInstruction);
const instruction = ref(props.initialInstruction || "");
const candidates = ref<any[]>([]);
const sourceRows = ref<any[][]>([]);
const selected = ref<string[]>([]);
const warnings = ref<string[]>([]);
const busy = ref(false);
const error = ref("");
const searched = ref(false);
const previewMode = ref("homeroom");
let generation = 0;
const title = computed(() => props.source.scenario_type.includes(':') ? distributionLabel(props.source.scenario_type.replace(/^[^:]+:/, "")) : props.source.name);
const modes = [{ value: "homeroom", label: "换到其他班级" }, { value: "same_group", label: "换到同分组班级" },
  { value: "subject", label: "换到其他科目" }, { value: "teacher", label: "换到其他教师" },
  { value: "task", label: "其他同科目授课任务" }, { value: "ordinal", label: "课次整体顺延" }];
function reset() { generation++; selected.value = []; candidates.value = []; searched.value = false; error.value = ""; warnings.value = []; }
watch([mode, ai, instruction, () => props.source, projectId, organizationId, currentUserId, allowed], reset, { deep: true });
onBeforeUnmount(() => { generation++; });
function readable(exc: unknown) { const raw = exc instanceof Error ? exc.message : "请求失败，请重试。"; try { return JSON.parse(raw).detail || raw; } catch { return raw; } }
async function preview() {
  if (busy.value || (ai.value && !allowed.value) || (props.requireAi && !allowed.value)) return;
  reset(); const current = generation; busy.value = true;
  try {
    const chosenMode = ai.value ? "all" : mode.value;
    const data = await request(`/api/projects/${projectId.value}/constraints/${ai.value ? 'ai/' : ''}expansion/preview`, {
      method: "POST", body: JSON.stringify({ source: props.source, mode: chosenMode, instruction: instruction.value }), silent: true, localError: true,
    });
    if (current !== generation) return;
    candidates.value = [...data.candidates].sort((a, b) => compareNaturalClassNames(a.lessons[0]?.homeroom || '', b.lessons[0]?.homeroom || ''));
    warnings.value = data.warnings; sourceRows.value = data.source_groups;
    previewMode.value = chosenMode; searched.value = true;
    if (ai.value) void loadAgentUsage().catch(() => {});
  } catch (exc) { if (current === generation) error.value = readable(exc); }
  finally { busy.value = false; }
}
async function save() {
  if (busy.value || (props.requireAi && !allowed.value) || (!props.includeSource && !selected.value.length)) return;
  const payload: ExpansionPayload = { source: props.source, mode: previewMode.value, instruction: instruction.value, include_source: props.includeSource, selected_ids: [...selected.value] };
  if (props.deferSave) { emit("prepared", payload); return; }
  const current = generation; busy.value = true; error.value = "";
  try {
    const data = await request(`/api/projects/${projectId.value}/constraints/${props.requireAi ? 'ai/' : ''}expansion/commit`, { method: "POST", body: JSON.stringify(payload), silent: true, localError: true });
    if (current === generation) emit("created", data);
  } catch (exc) { if (current === generation) error.value = readable(exc); }
  finally { busy.value = false; }
}
</script>

<template>
  <section class="expansion-step">
    <header><h3><span>4</span>扩展到相似课次 <small>可跳过</small></h3><button type="button" class="btn-secondary" :disabled="busy" @click="emit('back')">返回核对</button></header>
    <div class="expansion-source"><strong>{{ source.name }}</strong><span>{{ title }} · {{ source.required ? '必须满足' : `尽量满足，扣 ${source.penalty} 分` }} · 原约束 {{ source.groups.length }} 组</span></div>
    <p v-if="requireAi && !allowed" role="status"><LockKeyhole :size="16" />此功能仅正式会员可用。</p>
    <template v-else>
      <fieldset :disabled="busy">
        <div class="expansion-method" role="group" aria-label="扩展方式">
          <button type="button" :class="{ active: !ai }" :aria-pressed="!ai" @click="ai = false">按条件扩展</button>
          <button type="button" :class="{ active: ai }" :aria-pressed="ai" :disabled="!allowed" :title="allowed ? 'AI 推荐相似约束' : '仅正式会员可用'" @click="ai = true"><Sparkles :size="16" />AI 扩展</button>
        </div>
        <form class="expansion-search" @submit.prevent="preview">
          <input v-if="ai" v-model="instruction" maxlength="1000" aria-label="相似扩展规则" placeholder="例如：应用到其他班级的语文课，课次顺序不变" />
          <select v-else v-model="mode" aria-label="选择扩展条件"><option v-for="item in modes" :key="item.value" :value="item.value">{{ item.label }}</option></select>
          <button type="submit" class="btn-secondary"><Search :size="16" />{{ busy ? '查找中...' : '查找相似课次' }}</button>
        </form>
        <details v-if="sourceRows.length" class="source-details"><summary>原约束涉及课次</summary><p v-for="(rows, i) in sourceRows" :key="i">第 {{ i + 1 }} 组：{{ rows.map(r => `${r.homeroom} · ${r.subject} · ${r.teacher} · 第${r.ordinal}课次`).join('；') }}</p></details>
        <div v-if="candidates.length" class="expansion-selection"><label><input type="checkbox" :checked="selected.length === candidates.length" :indeterminate="selected.length > 0 && selected.length < candidates.length" @change="selected = selected.length === candidates.length ? [] : candidates.map(c => c.id)" />全选本次候选</label><span>已选 {{ selected.length }} / {{ candidates.length }} 组</span></div>
        <div class="expansion-candidates">
          <article v-for="item in candidates" :key="item.id" :class="{ selected: selected.includes(item.id) }">
            <label><input v-model="selected" type="checkbox" :value="item.id" /><strong>{{ item.title }}</strong><span>{{ item.lessons.length }} 个课次</span></label>
            <div class="expansion-table" tabindex="0"><table><thead><tr><th>班级</th><th>科目</th><th>教师</th><th>课次</th></tr></thead><tbody><tr v-for="row in item.lessons" :key="row.lesson_id"><td>{{ row.homeroom }}</td><td>{{ row.subject }}</td><td>{{ row.teacher }}</td><td>第{{ row.ordinal }}课次</td></tr></tbody></table></div>
            <p>{{ item.reason }}</p>
          </article>
        </div>
        <p v-if="searched && !candidates.length" role="status">没有找到符合条件的相似课次，可换一种扩展方式。</p>
        <details v-if="warnings.length"><summary>匹配说明（{{ warnings.length }}）</summary><p v-for="warning in warnings" :key="warning">{{ warning }}</p></details>
      </fieldset>
      <p v-if="error" class="expansion-error" role="alert">{{ error }}</p>
      <footer><span>{{ includeSource ? `保留原约束 ${source.groups.length} 组` : '不重复创建原约束' }} · 新增扩展 {{ selected.length }} 组</span><button type="button" class="btn-primary" :disabled="busy || (!includeSource && !selected.length)" @click="save">{{ busy ? '处理中...' : deferSave ? '确认本行，加入待创建' : selected.length ? '确认创建所选约束' : includeSource ? '不扩展，仅创建原约束' : '请选择扩展组' }}</button></footer>
    </template>
  </section>
</template>

<style scoped>
.expansion-step { min-width: 0; color: #29443e; }
header, footer, .expansion-selection, article > label { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
h3 { display: flex; align-items: center; gap: 8px; font-size: 17px; margin: 0; } h3 > span { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%; background: #e8f3ee; color: #24705e; }
small { font-weight: 400; font-size: 12px; color: #74857c; }
.expansion-source { display: grid; gap: 8px; padding: 18px 0; border-bottom: 1px solid #e1e8e4; overflow-wrap: anywhere; }
.expansion-source span, p, summary, footer, .expansion-selection { font-size: 13px; line-height: 1.6; }
fieldset { border: 0; margin: 0; padding: 0; min-width: 0; }
.expansion-method { display: flex; gap: 8px; margin: 18px 0; }
.expansion-method button { display: inline-flex; align-items: center; gap: 6px; border: 1px solid #d4e0d9; padding: 8px 12px; border-radius: 5px; background: white; color: #4e645a; }
.expansion-method button.active { background: #eaf5ef; border-color: #2a8068; color: #216b54; }
.expansion-method button:disabled { opacity: .5; }
.expansion-search { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.expansion-search input, .expansion-search select { flex: 1 1 220px; min-width: 0; max-width: 100%; border: 1px solid #cddbd3; padding: 10px; border-radius: 5px; background: white; color: #29443e; }
button { white-space: normal; } .expansion-search button { display: inline-flex; align-items: center; gap: 6px; }
.expansion-selection > label { display: flex; align-items: center; gap: 8px; margin: 0; }
.expansion-candidates { max-height: min(340px, 40dvh); overflow: auto; overscroll-behavior: contain; display: grid; gap: 12px; margin: 12px 0; }
article { border: 1px solid #d7e2db; border-radius: 6px; padding: 12px; min-width: 0; } article.selected { border-color: #39856b; }
article > label { justify-content: flex-start; font-size: 14px; } article > label span { margin-left: auto; font-size: 12px; color: #728078; }
input[type=checkbox] { width: 16px; height: 16px; accent-color: #2c8068; }
.expansion-table { overflow-x: auto; margin-top: 10px; } table { border-collapse: collapse; width: 100%; min-width: 360px; font-size: 12px; } th, td { text-align: left; padding: 8px; border-bottom: 1px solid #e6ebe8; } th { background: #f2f6f3; }
p, summary { color: #677b70; } footer { position: sticky; bottom: -22px; background: white; z-index: 1; padding: 16px 0 8px; border-top: 1px solid #e0e8e3; } .expansion-error { color: #a52b2b; } .source-details { margin: 12px 0; overflow-wrap: anywhere; }
</style>
