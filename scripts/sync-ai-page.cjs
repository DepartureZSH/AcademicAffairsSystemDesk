// Reproducible copy of the web assistant's component graph, including scoped CSS.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const source = path.resolve(root, '../STT/apps/web-admin/src');
const target = path.join(root, 'apps/desktop/src/web-ai');
const visited = new Set(), manifest = {};
function copy(relative) {
  if (visited.has(relative)) return;
  visited.add(relative);
  if (relative === 'components/appContext.ts' || relative === 'components/TimetableSettingsView.vue') return;
  const raw = fs.readFileSync(path.join(source, relative), 'utf8');
  manifest[relative] = crypto.createHash('sha256').update(raw.replaceAll('\r\n', '\n')).digest('hex');
  let text = raw.replace('<script setup lang="ts">', '<script setup lang="ts">\n// @ts-nocheck -- upstream component; its local adapter is checked separately.');
  if (relative.endsWith('.ts')) text = '// @ts-nocheck -- upstream source\n' + text;
  if (relative === 'components/AgentView.vue') {
    text = text.replace('  <nav class="agent-simple-tabs"', '  <slot name="notice"></slot>\n  <nav class="agent-simple-tabs"');
    text = text.replace(/    <div ref="tokenDetails"[\s\S]*?\n    <\/div>\n  <\/header>/,
      '    <button type="button" class="agent-token-toggle" @click="showSection(\'ai-settings\')">AI 设置</button>\n  </header>');
    text = text.replace("!entitlement.ai_enabled && activeAgentScene !== 'constraints'", 'false');
    text = text.replaceAll('请先选择机构和项目', '请先打开一个本地项目').replaceAll("showSection('profile')", "showSection('workspace')").replaceAll('前往个人中心', '返回工作台');
  }
  if (relative === 'components/AgentConversation.vue') {
    text = text.replace('accept=".txt,.csv,.xlsx,.xls,.doc,.docx,.pdf"', 'accept=".txt,.csv,.xlsx,.doc,.docx,.md,.json"');
  }
  if (relative === 'components/OfficialWorkbookButton.vue') {
    text = text.replace('apiBaseFor', 'downloadOfficialWorkbook');
    text = text.replace(/    const response = await fetch[\s\S]*?    setTimeout\(\(\) => URL.revokeObjectURL\(url\), 1000\);/, '    await downloadOfficialWorkbook(scene);');
  }
  if (relative === 'components/PlanningAiCreator.vue') {
    text = text.replace('import { configurationFromPicker', "import { sameExpectedTimes } from '../utils/expectedPolicy';\nimport { configurationFromPicker");
    text = text.replace('    const selectedOperation = operation.value;', "    const selectedOperation = operation.value;\n    const policy = prompt.value.trim() ? await request(`/api/projects/${targetProject}/planning/ai/expected-policy`, {method:'POST',body:JSON.stringify({prompt:prompt.value,operation:selectedOperation})}) : {policy:'default'};");
    text = text.replace('    const items = selected.map(item => {', "    const items = selected.map(item => {");
    text = text.replace('      return { lesson_id: String(item.lesson.id), revision: existing.revision,', `      const hasExisting = existing.configuration.rules.length > 0;
      if (policy.policy === 'cancel_if_existing' && hasExisting) throw new Error('有课次已设置期望时间，按你的要求取消整批操作');
      if (policy.policy === 'skip_existing' && hasExisting) return null;
      const next = policy.policy === 'clear_all' ? {schema_version:2, default_policy:'inherit', rules:[]} : editExpectedConfiguration(existing.configuration, config, policy.policy === 'replace' ? 'modify' : policy.policy === 'remove_selected' ? 'delete' : selectedOperation);
      if (policy.policy === 'clear_matching') {
        if (!sameExpectedTimes(existing.configuration, config)) return null;
        next.rules=[]; next.default_policy='inherit';
      }
      return { lesson_id: String(item.lesson.id), revision: existing.revision,`);
    text = text.replace('configuration: editExpectedConfiguration(existing.configuration, config, selectedOperation) };','configuration: next };');
    text = text.replace('    if (targetProject !== projectId.value)', "    const filtered = items.filter(Boolean);\n    if (!filtered.length) throw new Error('按补充要求筛选后，没有需要修改的课次');\n    if (targetProject !== projectId.value)");
    text = text.replace('JSON.stringify({ items })','JSON.stringify({ items: filtered })');
  }
  if (relative === 'components/ConstraintTemplateGallery.vue') {
    text = text.replace(/    const blob = await request[\s\S]*?setTimeout\(\(\) => URL.revokeObjectURL\(url\), 10000\);/, "    await downloadOfficialWorkbook('constraints', item.id);");
    text = text.replace('const {', 'const { downloadOfficialWorkbook,');
  }
  // Membership quota does not apply to a user-owned provider. Sending is gated by the adapter.
  text = text.replaceAll('AI 助手仅对会员开放', '请配置你的 AI 服务').replaceAll('查看会员方案', '前往 AI 设置').replaceAll("showSection('billing')", "showSection('ai-settings')");
  // Keep all portal styles in the same namespace, including prompt dialogs.
  text = text.replaceAll('<Teleport to="body">', '<Teleport to="body"><div class="web-ai">').replaceAll('</Teleport>', '</div></Teleport>');
  fs.mkdirSync(path.dirname(path.join(target, relative)), { recursive:true });
  fs.writeFileSync(path.join(target, relative), text);
  for (const m of raw.matchAll(/(?:from\s*|src=)["'](\.[^"']+)["']/g)) {
    let dep = path.posix.normalize(path.posix.join(path.posix.dirname(relative), m[1]));
    if (!path.extname(dep)) dep += '.ts';
    if (!dep.startsWith('../')) copy(dep);
  }
}
copy('components/AgentView.vue');
const ts = require('../apps/desktop/node_modules/typescript');
const controller = ts.createSourceFile('controller.ts', fs.readFileSync(path.join(source,'composables/useAppController.ts'),'utf8'), ts.ScriptTarget.Latest, true);
const app = controller.statements.find(s => ts.isFunctionDeclaration(s) && s.name?.text === 'useAppController');
const markdownNames = ['escapeHtml','renderInlineMarkdown','splitMarkdownTableRow','isMarkdownTableSeparator','isMarkdownTableRow','normalizeMarkdownSource','renderMarkdown'];
const markdown = markdownNames.map(name=>{
  // Upstream's compressed-table repair splits valid separator rows. Preserve standard Markdown.
  if(name==='normalizeMarkdownSource')return 'function normalizeMarkdownSource(value: string) { return value.replace(/\\r\\n/g, "\\n"); }';
  const fn=app.body.statements.find(s=>ts.isFunctionDeclaration(s)&&s.name?.text===name);
  if(!fn)throw new Error(`Missing web markdown function ${name}`);
  return (name==='renderMarkdown'?'export ':'')+fn.getText(controller);
}).join('\n\n');
fs.writeFileSync(path.join(target,'utils/markdown.ts'), '// Extracted from the web controller by sync-ai-page.cjs.\n'+markdown+'\n');
const presentationNames = ['agentActionCountItems','agentActionDetailTables','agentActionFailures','agentActionWarnings','agentActionStatusLabel','agentActionTargetLabel','agentActionOperationLabel','agentActionTitle','agentActionDisplaySummary'];
const functions = new Map(app.body.statements.filter(s=>ts.isFunctionDeclaration(s)).map(s=>[s.name?.text,s]));
const presentation = new Set();
function addPresentation(name) {
  if(presentation.has(name) || !functions.has(name))return;
  presentation.add(name);
  function visit(node){if(ts.isIdentifier(node)&&node.text!==name&&functions.has(node.text))addPresentation(node.text);ts.forEachChild(node,visit);}
  visit(functions.get(name));
}
presentationNames.forEach(addPresentation);
fs.writeFileSync(path.join(target,'utils/actionPresentation.ts'),'// @ts-nocheck -- pure display helpers extracted from the web controller.\n'+[...presentation].map(name=>(presentationNames.includes(name)?'export ':'')+functions.get(name).getText(controller)).join('\n\n')+'\n');
const postcss = require('../apps/desktop/node_modules/postcss');
const css = postcss.parse(fs.readFileSync(path.join(source,'styles.css'),'utf8'));
css.walkRules(rule => {
  if (rule.parent.type === 'atrule' && /keyframes/.test(rule.parent.name)) return;
  rule.selectors = rule.selectors.map(s => s === ':root' || s === 'body' ? '.web-ai' : `.web-ai ${s}`);
});
fs.writeFileSync(path.join(target, 'web-ai.css'), css.toString());
fs.writeFileSync(path.join(target, 'provenance.json'), JSON.stringify({ source:'STT/apps/web-admin/src', files:manifest }, null, 2)+'\n');
console.log(`Copied ${Object.keys(manifest).length} web assistant sources.`);
