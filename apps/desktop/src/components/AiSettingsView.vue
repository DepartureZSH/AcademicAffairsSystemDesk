<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { Check, LoaderCircle, PlugZap, Save, Trash2 } from 'lucide-vue-next';
import { aiAvailable, aiConnection, type AiConnectionStatus } from '../lib/ai';
import AiPrivacyNotice from './AiPrivacyNotice.vue';

const desktop = aiAvailable();
const saved = ref<AiConnectionStatus>({ baseUrl:'', model:'', hasApiKey:false });
const baseUrl = ref('');
const model = ref('');
const apiKey = ref('');
const busy = ref(false);
const loaded = ref(false);
const error = ref('');
const notice = ref('');
const testConsent = ref(false);
const clearing = ref(false);
const dirty = computed(() => baseUrl.value.trim().replace(/\/$/, '') !== saved.value.baseUrl || model.value.trim() !== saved.value.model || !!apiKey.value);
const keyRequired = computed(() => !saved.value.hasApiKey || baseUrl.value.trim().replace(/\/$/, '') !== saved.value.baseUrl);
const canTest = computed(() => desktop && loaded.value && !busy.value && saved.value.hasApiKey && !dirty.value && testConsent.value);

function showError(value: unknown) { error.value = typeof value === 'string' ? value : '操作未完成，请稍后重试'; }
function applyStatus(value: AiConnectionStatus) {
  saved.value = value;
  baseUrl.value = value.baseUrl;
  model.value = value.model;
  apiKey.value = '';
}
async function load() {
  if (!desktop) return;
  busy.value = true;
  error.value = '';
  try { applyStatus(await aiConnection.status()); loaded.value = true; }
  catch (e) { showError(e); }
  finally { busy.value = false; }
}
async function save() {
  if (busy.value || !desktop || !loaded.value) return;
  busy.value = true; error.value = ''; notice.value = '';
  try {
    applyStatus(await aiConnection.save({ baseUrl:baseUrl.value, model:model.value, apiKey:apiKey.value || null }));
    testConsent.value = false;
    notice.value = 'AI 设置已保存在这台电脑。尚未发送任何请求。';
  } catch (e) { showError(e); }
  finally { apiKey.value = ''; busy.value = false; }
}
async function test() {
  if (!canTest.value) return;
  busy.value = true; error.value = ''; notice.value = '';
  try { await aiConnection.test(testConsent.value); notice.value = '连接测试通过，所配置的模型已返回有效回复。'; }
  catch (e) { showError(e); }
  finally { busy.value = false; }
}
async function clear() {
  if (busy.value || !desktop) return;
  busy.value = true; error.value = ''; notice.value = '';
  try {
    await aiConnection.clear();
    applyStatus({baseUrl:'', model:'', hasApiKey:false});
    testConsent.value = false;
    loaded.value = true;
    notice.value = '已清除本机 AI 设置与密钥，项目资料不受影响。';
    clearing.value = false;
  } catch (e) { showError(e); }
  finally { busy.value = false; }
}
watch([baseUrl, model, apiKey], () => { notice.value = ''; testConsent.value = false; }, { flush: 'sync' });
onMounted(load);
</script>

<template>
  <section class="ai-settings">
    <header><h2>AI 设置</h2><p>使用你自己的 AI 服务账号，设置只保存在这台电脑。</p></header>
    <AiPrivacyNotice :destination="saved.baseUrl" />
    <p v-if="!desktop" class="preview-note" role="status">这里是页面预览。请在桌面应用中保存密钥和测试连接；浏览器预览不会保存或发送密钥。</p>
    <form class="ai-connection-form" @submit.prevent="save">
      <fieldset :disabled="busy || !desktop || !loaded">
        <legend>连接你的 AI 服务</legend>
        <label for="ai-base-url">API 地址</label>
        <input id="ai-base-url" v-model="baseUrl" type="url" maxlength="2048" placeholder="https://你的服务商地址/v1" autocomplete="off" spellcheck="false" required aria-describedby="ai-url-help" />
        <p id="ai-url-help" class="field-help">使用兼容 OpenAI 聊天接口的基础地址，不包含 /chat/completions。远程地址须为 HTTPS；本机服务可使用 HTTP。</p>
        <label for="ai-api-key">API Key <span v-if="saved.hasApiKey" class="key-status"><Check :size="14" />已保存</span></label>
        <input id="ai-api-key" v-model="apiKey" type="password" maxlength="2048" :required="keyRequired" :placeholder="keyRequired ? '粘贴服务商提供的密钥' : '留空保留当前密钥'" autocomplete="new-password" spellcheck="false" aria-describedby="ai-key-help" />
        <p id="ai-key-help" class="field-help">密钥保存在系统密钥库，不会放入项目文件或备份。更换地址时请重新填写，避免误发给其他服务。</p>
        <label for="ai-model">模型名称</label>
        <input id="ai-model" v-model="model" maxlength="200" placeholder="填写服务商提供的模型名称" autocomplete="off" spellcheck="false" required />
        <p class="field-help">请从服务商的模型列表复制准确名称。</p>
        <div class="settings-actions">
          <button type="submit" class="primary-button"><LoaderCircle v-if="busy" :size="16" class="spinning" /><Save v-else :size="16" />保存设置</button>
          <button type="button" class="secondary-button" :disabled="!saved.hasApiKey" @click="clearing = true"><Trash2 :size="16" />清除设置</button>
        </div>
      </fieldset>
      <section class="connection-test" aria-label="连接测试">
        <h3>测试连接</h3>
        <p>只向上面已保存的地址发送一条固定测试消息，不携带任何项目资料或附件。测试可能产生少量 API 费用。</p>
        <label class="consent"><input v-model="testConsent" type="checkbox" :disabled="busy || !desktop || !saved.hasApiKey || dirty" />我同意向已保存的 AI 服务发送测试请求</label>
        <button type="button" class="secondary-button" :disabled="!canTest" @click="test"><PlugZap :size="16" />{{ busy ? '请稍候…' : '测试连接' }}</button>
        <p v-if="dirty" class="field-help">请先保存修改，再测试连接。</p>
      </section>
    </form>
    <p v-if="error" class="settings-error" role="alert">{{ error }} <button v-if="!loaded && desktop" type="button" @click="load">重新读取</button></p>
    <p v-if="notice" class="settings-notice" role="status">{{ notice }}</p>
    <div v-if="clearing" class="clear-mask">
      <section class="clear-dialog" role="alertdialog" aria-modal="true" aria-labelledby="clear-ai-title">
        <h3 id="clear-ai-title">清除 AI 设置？</h3><p>将删除本机保存的 API 地址、密钥和模型名称。不会删除项目资料。</p>
        <div class="settings-actions"><button type="button" :disabled="busy" @click="clearing = false">取消</button><button type="button" :disabled="busy" @click="clear">确认清除</button></div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.ai-settings { display:grid; gap:22px; width:100%; max-width:1040px; padding:4px 0 24px; color:#283e35; font-family:"Inter", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", system-ui, sans-serif; }
.ai-settings header h2 { margin:0; font-size:22px; }
.ai-settings header p { margin:8px 0 0; color:#63726b; font-size:14px; }
.ai-connection-form { display:grid; gap:24px; }
fieldset { min-width:0; display:flex; flex-direction:column; gap:8px; padding:0; border:0; }
legend { padding:0 0 16px; font-size:16px; font-weight:650; }
fieldset > label { display:flex; align-items:center; gap:10px; margin-top:8px; font-size:14px; font-weight:600; }
fieldset > input { box-sizing:border-box; width:100%; max-width:720px; min-height:40px; padding:9px 12px; border:1px solid #d5dfd8; border-radius:7px; font:inherit; font-size:14px; background:#fff; color:inherit; }
fieldset > input:focus { outline:2px solid #87b6a6; outline-offset:1px; }
.field-help { margin:0 0 6px; color:#66776e; font-size:12px; line-height:1.6; }
.key-status { display:inline-flex; align-items:center; gap:4px; font-size:12px; font-weight:400; color:#26745e; }
.settings-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:10px; }
.ai-settings button { box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; gap:7px; height:38px; margin:0; padding:0 14px; border:1px solid #b9cbc3; border-radius:7px; background:#fff; color:#426258; font:inherit; font-size:14px; font-weight:600; line-height:20px; white-space:nowrap; }
.ai-settings button.primary-button { border-color:#23644f; background:#23644f; color:#fff; }
.ai-settings button:not(:disabled):hover { background:#edf4f0; border-color:#80a494; }
.ai-settings button.primary-button:not(:disabled):hover { background:#1d5543; border-color:#1d5543; }
.ai-settings button > svg { flex-shrink:0; }
.ai-settings button:disabled { opacity:.5; cursor:not-allowed; }
.connection-test { border-top:1px solid #e0e7e2; padding-top:20px; }
.connection-test h3 { margin:0; font-size:16px; }
.connection-test p { font-size:13px; line-height:1.7; color:#63726b; }
.consent { display:flex; align-items:flex-start; gap:8px; margin:14px 0; font-size:13px; line-height:1.5; }
.consent input { appearance:auto; flex:none; width:16px; height:16px; min-height:0; margin:2px 0 0; padding:0; accent-color:#287960; }
.preview-note { background:#edf3f0; padding:12px 16px; border-radius:7px; font-size:13px; line-height:1.7; }
.settings-error { color:#a33434; }
.settings-notice { color:#26745e; }
.clear-mask { position:fixed; inset:0; display:grid; place-items:center; z-index:1000; background:#14271f55; padding:20px; }
.clear-dialog { max-width:440px; background:#fff; padding:24px; border-radius:12px; box-shadow:0 12px 48px #14271f33; }
.clear-dialog h3 { margin-top:0; }
.clear-dialog p { font-size:14px; line-height:1.7; }
.spinning { animation:ai-spin 1s linear infinite; }
@keyframes ai-spin { to { transform:rotate(360deg); } }
</style>
