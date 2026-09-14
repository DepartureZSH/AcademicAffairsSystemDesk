// Mechanical extraction of the current web timetable editor and its dependency closure.
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../apps/desktop/node_modules/typescript');
const root = path.resolve(__dirname, '..');
const web = path.resolve(root, '../STT/apps/web-admin/src');
const filename = path.join(web, 'composables/useAppController.ts');
const program = ts.createProgram([filename], {noResolve: true, target: ts.ScriptTarget.ESNext});
const checker = program.getTypeChecker();
const source = program.getSourceFile(filename);
const fn = source.statements.find(s => ts.isFunctionDeclaration(s) && s.name.text === 'useAppController');
let view = fs.readFileSync(path.join(web, 'components/TimetableSettingsView.vue'), 'utf8');
let template = view.slice(view.indexOf('<template>'), view.indexOf('<div v-if="showTimetablePreviewSheet"'));
if (!template || template.length > 100000) throw new Error('Unexpected template boundary');
template += '\n</template>\n';
// Online publication and paid customization are outside the local desktop product.
template = template.replace(/      <div v-if="showTimetableSaveChoice"[\s\S]*?(?=      <div v-if="hasTimetableTemplateEditor" class="template-inline-preview">)/, '');
template = template.replace(/              <button\s+type="button"\s+class="btn-secondary template-marketplace-customize"[\s\S]*?<\/button>/, '');
template = template.replace(/ :class="\{ 'timetable-ai-editor': props.embedded \}"/, '');
template = template.replaceAll('模板广场', '模板库').replaceAll('本机构模板', '本机模板').replaceAll('搜索模板名称、描述或机构', '搜索模板名称或描述');
// Dismiss editing dialogs only through their explicit cancel/close buttons.
template = template.replace(/\s+@click\.self="(?:cancelNewTimetableTemplate|closeTemplateMarketplacePreview|selectedPreviewCell = null)"/g, '');
const destructured = view.match(/const \{([\s\S]*?)\} = inject\(APP_CONTEXT_KEY\)!;/)[1].split(',').map(n=>n.trim()).filter(Boolean);
const inspector = fs.readFileSync(path.join(web,'components/CoursePeriodInspector.vue'),'utf8');
const inspectorNames = inspector.match(/const \{([\s\S]*?)\} = inject\(APP_CONTEXT_KEY\)!;/)[1].split(',').map(n=>n.trim()).filter(Boolean);
const roots = [...new Set([...destructured.filter(n=>new RegExp('\\b'+n+'\\b').test(template)), ...inspectorNames, 'schoolData', 'selectedTemplateId', 'updateActiveTerm', 'syncTimetableTemplateForms', 'error', 'periodDraftPayload', 'validateAllPeriodTimes', 'persistTimetableTemplate', 'loadSchoolData', 'periodTimeDrafts', 'periodTimeErrors', 'timetableTemplatePeriodSourceId', 'timetableTemplatePeriodsLocked', 'previewBlankRows', 'previewBlankColumns'])];
const overrides = new Set(['loadSchoolData','persistTimetableTemplate','loadTemplateMarketplace','updateActiveTerm','deleteTimetableTemplate','saveTimetableTemplate','organizationId','projectId']);
roots.push('localNotice');
const declarations = new Map();
const byName = new Map();
for (const statement of fn.body.statements) {
  const names = ts.isVariableStatement(statement) ? statement.declarationList.declarations.map(d=>d.name) : statement.name ? [statement.name] : [];
  for (const name of names) if (ts.isIdentifier(name)) {
    byName.set(name.text, statement);
    declarations.set(checker.getSymbolAtLocation(name), {name:name.text, statement});
  }
}
const selected = new Set();
const usedOverrides = new Set();
function add(name) {
  if(overrides.has(name)) { usedOverrides.add(name); return; }
  const statement = byName.get(name);
  if (!statement || selected.has(statement)) return;
  selected.add(statement);
  function visit(node) {
    if (ts.isIdentifier(node)) {
      const target = declarations.get(checker.getSymbolAtLocation(node));
      if (target && target.statement !== statement) add(target.name);
    }
    ts.forEachChild(node, visit);
  }
  visit(statement);
}
roots.forEach(add);
const target = path.join(root,'apps/desktop/src/web-timetable');
fs.mkdirSync(target,{recursive:true});
const body = fn.body.statements.filter(s=>selected.has(s)).map(s=>s.getText(source)).join('\n\n')
  .replaceAll('模板广场', '模板库').replaceAll('平台预设', '内置模板').replaceAll('本机构模板', '本机模板')
  .replace('function selectNumberValue(event: Event)', 'function selectNumberValue(event: Event | { target: { value: unknown } })')
  .replace(/[\t ]+(?=\r?$)/gm, '');
const persistence = fs.readFileSync(path.join(__dirname,'web-timetable-local-adapter.txt'),'utf8');
const imports = `import { computed, nextTick, ref } from 'vue';\nimport type { Cell as ExcelCell } from 'exceljs';\nimport { fitWorksheetToPrintedPage } from './excelPrintLayout';\nimport { compareNaturalClassNames, compareNaturalRoomNames } from './naturalClassNameSort';\nimport { localApi, sidecarRequest, formatLocalError } from '../lib/sidecar';\n`;
fs.writeFileSync(path.join(target,'useTimetableEditor.ts'), '// Extracted from STT/apps/web-admin/src/composables/useAppController.ts.\n'+imports+'\nexport function useTimetableEditor(onRevision: (revision: number) => void) {\nconst organizationId = ref("local");\nconst projectId = ref("local");\n'+body.replace('ref<SectionKey>("console")','ref<SectionKey>("timetable")')+'\n'+persistence+'\nreturn { '+[...new Set([...roots, 'loadSchoolData'])].join(', ')+' };\n}\n');
const exposed = [...new Set([...destructured.filter(n=>new RegExp('\\b'+n+'\\b').test(template)), 'schoolData','selectedTemplateId','termForm','loading','updateActiveTerm','error'])];
exposed.push('localNotice');
const script = `<script setup lang="ts">\nimport {computed, inject, watch, onBeforeUnmount} from 'vue';\nimport { APP_CONTEXT_KEY } from './appContext';\nimport CoursePeriodInspector from './CoursePeriodInspector.vue';\nimport TemplateMarketplacePreviewTable from './TemplateMarketplacePreviewTable.vue';\nimport TemplatePlanningMode from './TemplatePlanningMode.vue';\nimport SearchableSelect from './SearchableSelect.vue';\nconst props = defineProps<{embedded?:boolean}>();\nconst {${exposed.join(',')}} = inject(APP_CONTEXT_KEY)!;\nconst selectedTemplateIsPersistedDefault = computed(() => schoolData.value.weekly_timetable_templates.some(t => String(t.id) === selectedTemplateId.value && Boolean(t.is_default)));\nlet timer: ReturnType<typeof setTimeout> | undefined;\nwatch(() => termForm.value.week_count, value => { if(loading.value || value === Number(schoolData.value.active_term?.week_count) || value < 1 || value > 60) return; clearTimeout(timer); timer = setTimeout(updateActiveTerm, 500); });\nonBeforeUnmount(() => clearTimeout(timer));\n</script>\n`;
template = template.replace('  <div class="timetable-settings-layout">','  <p v-if="error" class="error local-editor-notice" role="alert">{{ error }}</p>\n  <div class="timetable-settings-layout">');
template = template.replace('<p v-if="error"', '<p v-if="localNotice && !error" class="muted" role="status">{{ localNotice }}</p>\n  <p v-if="error"');
fs.writeFileSync(path.join(target,'TimetableSettingsView.vue'),script+template);
for(const name of ['CoursePeriodInspector.vue','TemplateMarketplacePreviewTable.vue','TemplatePlanningMode.vue']) {
  let content = fs.readFileSync(path.join(web,'components',name),'utf8');
  if(name === 'CoursePeriodInspector.vue') content = content.replace('import { computed, inject }', 'import SearchableSelect from "./SearchableSelect.vue";\nimport { computed, inject }');
  fs.writeFileSync(path.join(target,name),content);
}
const select = fs.readFileSync(path.join(web,'components/common/SearchableSelect.vue'),'utf8')
  .replace('<Teleport to="body">', '<Teleport to="body"><div v-if="open" class="web-timetable">')
  .replace('</Teleport>', '</div></Teleport>');
fs.writeFileSync(path.join(target,'SearchableSelect.vue'),select);
for(const name of ['excelPrintLayout.ts','naturalClassNameSort.ts']) fs.copyFileSync(path.join(web,'utils',name),path.join(target,name));
fs.writeFileSync(path.join(target,'appContext.ts'), `import type { InjectionKey } from 'vue';\nimport type { useTimetableEditor } from './useTimetableEditor';\nexport const APP_CONTEXT_KEY: InjectionKey<ReturnType<typeof useTimetableEditor>> = Symbol.for('stt.desktop.local-timetable-editor');\n`);
// Scope the web stylesheet to this editor; other desktop pages keep their styles.
const postcss = require('../apps/desktop/node_modules/postcss');
const css = postcss.parse(fs.readFileSync(path.join(web,'styles.css'),'utf8'));
const editorCode = fs.readdirSync(target).filter(n=>/\.(vue|ts)$/.test(n)).map(n=>fs.readFileSync(path.join(target,n),'utf8')).join('\n');
const tokens = new Set(editorCode.match(/[a-zA-Z_][\w-]*/g));
const dynamicPrefixes = [...tokens].filter(t=>t.endsWith('-'));
css.walkRules(rule => {
  if (rule.parent.type === 'atrule' && /keyframes/.test(rule.parent.name)) return;
  const used = rule.selectors.filter(selector => [...selector.matchAll(/\.([a-zA-Z_][\w-]*)/g)].every(([,name])=>tokens.has(name) || dynamicPrefixes.some(prefix=>name.startsWith(prefix))));
  if (!used.length) { rule.remove(); return; }
  rule.selectors = used;
  rule.selectors = rule.selectors.map(selector => selector === ':root' || selector === 'body' ? '.web-timetable' : ':where(.web-timetable) '+selector);
});
css.walkAtRules(rule => { if(rule.nodes && !rule.nodes.length) rule.remove(); });
fs.writeFileSync(path.join(target,'web-timetable.css'),css.toString()+'\n'+fs.readFileSync(path.join(__dirname,'web-timetable-ui-overrides.css'),'utf8'));
console.log(`Extracted ${selected.size} declarations (${body.split('\n').length} lines) and the current web template.`);
require('./sync-ai-timetable.cjs');
