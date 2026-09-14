// Mechanically reuse the web draft-to-editor mapping; never save an AI draft automatically.
const fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..');
const ts = require('../apps/desktop/node_modules/typescript');
const source = fs.readFileSync(path.join(root, '../STT/apps/web-admin/src/composables/useAppController.ts'), 'utf8');
const ast = ts.createSourceFile('controller.ts', source, ts.ScriptTarget.Latest, true);
const controller = ast.statements.find(s => ts.isFunctionDeclaration(s) && s.name?.text === 'useAppController');
const fn = controller.body.statements.find(s => ts.isFunctionDeclaration(s) && s.name?.text === 'applyAiTimetableDraft');
if (!fn) throw new Error('Missing web draft mapper');
const file = path.join(root, 'apps/desktop/src/web-timetable/useTimetableEditor.ts');
let text = fs.readFileSync(file, 'utf8');
text = text.replace('useTimetableEditor(onRevision: (revision: number) => void)', 'useTimetableEditor(onRevision: (revision: number) => void, onTemplateSaved: (revision: number) => void = () => {})');
text = text.replace(/    onTemplateSaved\(localRevision\);\r?\n/g, '');
text = text.replace('    localNotice.value = "课表模板已保存到本机";', '    localNotice.value = "课表模板已保存到本机";\n    onTemplateSaved(localRevision);');
text = text.replace(/\/\/ AI_DRAFT_BEGIN[\s\S]*?\/\/ AI_DRAFT_END\r?\n/g, '');
text = text.replace('return { applyAiTimetableDraft, activeSection,', 'return { activeSection,');
const functionText = fn.getText(ast).replaceAll("import('../utils/timetableAi')", "import('../web-ai/utils/timetableAi')");
text = text.replace('return { activeSection,', `// AI_DRAFT_BEGIN\n${functionText}\n// AI_DRAFT_END\nreturn { applyAiTimetableDraft, activeSection,`);
fs.writeFileSync(file, text);
