// Keep the three course dialogs structurally identical to the current web source.
const fs = require('node:fs'), path = require('node:path');
const ts = require('../apps/desktop/node_modules/typescript');
const root = path.resolve(__dirname, '..'), web = path.resolve(root, '../STT/apps/web-admin/src');
const filename = path.join(web, 'composables/useAppController.ts');
const program = ts.createProgram([filename], {noResolve:true, target:ts.ScriptTarget.ESNext});
const checker = program.getTypeChecker(), source = program.getSourceFile(filename);
const fn = source.statements.find(s => ts.isFunctionDeclaration(s) && s.name.text === 'useAppController');
const planning = fs.readFileSync(path.join(web,'components/PlanningView.vue'),'utf8');
const timetable = fs.readFileSync(path.join(web,'components/TimetableSettingsView.vue'),'utf8');
let subject = planning.slice(planning.indexOf('    <Teleport to="body">\n    <div v-if="subjectEditorOpen'), planning.indexOf('    </Teleport>', planning.indexOf('    <Teleport to="body">\n    <div v-if="subjectEditorOpen')) + '    </Teleport>'.length);
if (!subject) throw new Error('Subject dialog boundary changed');
subject = subject.replace('subjectEditorOpen && classPlanningDisplayMode === \'classic\' && planningFilterVisibleHomerooms.length', 'subjectEditorOpen');
let sheets = timetable.slice(timetable.indexOf('<div v-if="showLessonEditorSheet"'), timetable.lastIndexOf('</template>'));
if (!sheets.includes('course-preferred-sheet-mask')) throw new Error('Lesson dialog boundary changed');
const overlays=fs.readFileSync(path.join(web,'components/GlobalOverlays.vue'),'utf8');
const guide=overlays.slice(overlays.indexOf('<div v-if="showGuide"'),overlays.lastIndexOf('</template>'));
let template = (subject + '\n<Teleport to="body">'+sheets+guide+'</Teleport>')
  .replaceAll('<Teleport to="body">','<Teleport to="body"><div class="web-course-editor">')
  .replaceAll('</Teleport>','</div></Teleport>')
  .replace(/\s+@click\.self="(?:closeSubjectEditor|closeLessonEditorSheet|closeCoursePreferredPicker)"/g, '');
const byName = new Map(), declarations = new Map();
for (const statement of fn.body.statements) {
  const names = ts.isVariableStatement(statement) ? statement.declarationList.declarations.map(d=>d.name) : statement.name ? [statement.name] : [];
  for (const name of names) if(ts.isIdentifier(name)) { byName.set(name.text,statement); declarations.set(checker.getSymbolAtLocation(name), {name:name.text,statement}); }
}
const adapterPath = path.join(__dirname,'course-editor-local-adapter.txt');
const adapter = fs.existsSync(adapterPath) ? fs.readFileSync(adapterPath,'utf8') : '';
const overrides = new Set([...adapter.matchAll(/^(?:async )?(?:function|const|let) (\w+)/gm)].map(m=>m[1]));
const roots = [...new Set([...byName.keys(), ...overrides])].filter(n=>new RegExp('\\b'+n+'\\b').test(template));
const selected = new Set(), usedOverrides = new Set();
function add(name) {
  if(overrides.has(name)) {usedOverrides.add(name);return;}
  const statement=byName.get(name); if(!statement||selected.has(statement))return;
  selected.add(statement);
  function visit(node) { if(ts.isIdentifier(node)) {const target=declarations.get(checker.getSymbolAtLocation(node));if(target && target.statement!==statement)add(target.name);} ts.forEachChild(node,visit); }
  visit(statement);
}
[...roots, ...[...byName.keys()].filter(n=>new RegExp('\\b'+n+'\\b').test(adapter)), 'courseLessonDrafts','teachingTaskForm','selectedTeachingTaskId','error','showLessonEditorSheet','showCoursePreferredPicker','selectedSubject','schoolData','planningData','coursePreferredRuleKey','newCourseLessonDraft','lessonEditorSessionSnapshot','cloneLessonEditorDrafts','subjectEditorOpen'].forEach(add);
const body = fn.body.statements.filter(s=>selected.has(s)).map(s=>s.getText(source)).join('\n\n')
  .replace(/const defaultRules = Array\.from\([\s\S]*?forbidden: false,\s*\}\)\);/, `const defaultRules = selectedTemplatePeriods.value
        .filter(period => !isCoursePreferredPeriodDisabled(Number(period.period_index), period))
        .map(period => ({
          key: coursePreferredRuleKey(),
          week_bits: "1".repeat(termWeekCount.value),
          day_bits: bitsFromNumbers([Number(period.weekday)], termDayCount.value),
          period_index: Number(period.period_index), penalty: 0, forbidden: false,
        }));`);
const target=path.join(root,'apps/desktop/src/web-course-editor');
fs.mkdirSync(target,{recursive:true});
const guideSteps = Object.fromEntries(['lesson_editor_sheet','course_preferred_sheet'].map(name=>{
  const match=source.text.match(new RegExp('    '+name+': \\[([\\s\\S]*?)\\n    \\],'));
  if(!match)throw new Error('Guide source changed');
  return [name, Function('return ['+match[1]+']')()];
}));
fs.writeFileSync(path.join(target,'guideSteps.ts'),'// Extracted verbatim from web guide steps.\nexport const localGuideSteps: Record<string, {id:string;section:string;target:string;title:string;body:string;fallbackBody?:string}[]> = '+JSON.stringify(guideSteps,null,2)+';\n');
if(process.argv.includes('--inspect')) {console.log([...byName].filter(([,s])=>selected.has(s)).map(([n])=>n).join('\n')); console.log('LINES',body.split('\n').length,'OVERRIDES',[...usedOverrides]);process.exit();}
const exposed=[...new Set([...roots,'error'])];
fs.writeFileSync(path.join(target,'useCourseEditor.ts'), `// Generated from the web controller; see scripts/extract-course-editor.cjs.\nimport {computed, ref, nextTick, watch, onMounted, onBeforeUnmount} from 'vue';\nimport {localApi, formatLocalError} from '../lib/sidecar';\nimport {localGuideSteps} from './guideSteps';\nexport function useCourseEditor(props: any, emit: any) {\n${adapter}\n${body}\nreturn {${exposed.join(',')}};\n}\n`);
fs.writeFileSync(path.join(target,'CourseEditor.vue'), `<script setup lang="ts">\nimport {X} from 'lucide-vue-next';\nimport SearchableSelect from './SearchableSelect.vue';\nimport {useCourseEditor} from './useCourseEditor';\nconst props = defineProps<{context: Record<string, any>}>();\nconst emit = defineEmits<{close: []; saved: [revision: number]}>();\nconst {${exposed.join(',')}} = useCourseEditor(props,emit);\n</script>\n<template>\n${template}\n</template>\n<style src="./web-course-editor.css"></style>\n`);
let select=fs.readFileSync(path.join(web,'components/common/SearchableSelect.vue'),'utf8').replaceAll('<Teleport to="body">','<Teleport to="body"><div class="web-course-editor">').replaceAll('</Teleport>','</div></Teleport>');
fs.writeFileSync(path.join(target,'SearchableSelect.vue'),select);
// Full stylesheet, namespaced: preserve base selectors, dynamic classes and media rules.
const postcss=require('../apps/desktop/node_modules/postcss');
const scoped=planning.match(/<style scoped>([\s\S]*?)<\/style>/)?.[1]||'';
const css=postcss.parse(fs.readFileSync(path.join(web,'styles.css'),'utf8')+'\n'+scoped.replace(/:deep\(([^)]+)\)/g,'$1'));
const tokens = new Set((template+select+body+adapter+' planning-workspace-modal-open').match(/[a-zA-Z_][\w-]*/g));
const prefixes = [...tokens].filter(t=>t.endsWith('-'));
css.walkRules(rule=>{if(rule.parent.type==='atrule' && /keyframes/.test(rule.parent.name))return;rule.selectors=rule.selectors.map(s=>s===':root'||s==='body'?'.web-course-editor':s.startsWith('body.planning-workspace-modal-open')?s.replace('body.planning-workspace-modal-open','.web-course-editor'):`.web-course-editor ${s}`);});
css.walkAtRules(rule=>{if(rule.nodes&&!rule.nodes.length)rule.remove();});
fs.writeFileSync(path.join(target,'web-course-editor.css'),css.toString()+'\n'+(fs.existsSync(path.join(__dirname,'course-editor-local.css'))?fs.readFileSync(path.join(__dirname,'course-editor-local.css'),'utf8'):''));
console.log(`Generated web course dialogs with ${selected.size} declarations (${body.split('\n').length} lines).`);
// The desktop's old generic classes must not leak into transplanted web dialogs.
const basePath=path.join(root,'apps/desktop/src/styles.css');
const base=postcss.parse(fs.readFileSync(basePath,'utf8'));
base.walkRules(rule=>{if(rule.parent.type==='atrule' && /keyframes/.test(rule.parent.name))return;rule.selectors=rule.selectors.map(s=>s.includes(':where(:not(.web-course-editor *))')?s:s+':where(:not(.web-course-editor *))');});
fs.writeFileSync(basePath,base.toString());
const crypto=require('node:crypto');
const sha=text=>crypto.createHash('sha256').update(text.replaceAll('\r\n','\n')).digest('hex');
fs.writeFileSync(path.join(target,'provenance.json'),JSON.stringify({
  source:'../STT/apps/web-admin/src',
  adaptations:['local SQLite API and period units','namespaced CSS/Teleport wrappers','disable editor backdrop dismissal','local guide lifecycle'],
  templateSha256:sha(template),
  sources:Object.fromEntries(['components/PlanningView.vue','components/TimetableSettingsView.vue','components/GlobalOverlays.vue','components/common/SearchableSelect.vue','composables/useAppController.ts','styles.css'].map(p=>[p,sha(fs.readFileSync(path.join(web,p),'utf8'))]))
},null,2)+'\n');
if(process.argv.includes('--wire') && !fs.readFileSync(path.join(root,'apps/desktop/src/components/PlanningView.vue'),'utf8').includes('import CourseEditor')) {
  const viewPath=path.join(root,'apps/desktop/src/components/PlanningView.vue');
  let local=fs.readFileSync(viewPath,'utf8');
  local=local.replace(/import LessonEditor from [^;]+;/,"import CourseEditor from '../web-course-editor/CourseEditor.vue';");
  local=local.replace('const modalOpen = computed(() => editorOpen.value || filterKind.value !== null);','const modalOpen = computed(() => filterKind.value !== null);');
  local=local.replace(/const lessonEditor = ref<InstanceType<typeof LessonEditor> \| null>\(null\);/, '');
  local=local.replace('lessonEditor.value?.requestClose();','lessonEditorOpen.value = false;');
  const start=local.indexOf('    <Teleport to="body"><div v-if="modalOpen"');
  const end=local.indexOf('    </aside></div></Teleport>',start)+'    </aside></div></Teleport>'.length;
  if(start<0||end<start)throw new Error('Local dialog boundary changed');
  const old=local.slice(start,end), filter=old.slice(old.indexOf('<template v-else><input v-model="filterSearch"'),old.lastIndexOf('</template>')+'</template>'.length).replace('<template v-else>','<template>');
  local=local.slice(0,start)+`    <CourseEditor v-if="editorOpen && selectedHomeroom && selectedSubject && currentTerm" :context="{homeroom:selectedHomeroom,subject:selectedSubject,term:terms.find(t=>t.id===taskForm.term_id)||currentTerm,taskId:editingId,slots:lessonSlots,revision}" @close="editorOpen = false" @saved="loadAll" />\n    <Teleport to="body"><div v-if="modalOpen" class="web-planning planning-guided-page subject-editor-mask" @keydown="onDialogKey"><aside ref="dialog" class="plan-detail-panel subject-editor-dialog" role="dialog" aria-modal="true" :aria-label="\`指定\${filterKind ? filterLabels[filterKind] : ''}\`"><header class="subject-editor-dialog-header"><strong>指定{{ filterKind ? filterLabels[filterKind] : '' }}</strong><button class="subject-editor-close" aria-label="关闭弹窗" @click="closeDialog"><X :size="20" /></button></header>\n${filter}\n</aside></div></Teleport>`+local.slice(end);
  fs.writeFileSync(viewPath,local);
}
