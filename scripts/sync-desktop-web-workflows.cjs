// Copy presentational web assets. Local data/algorithm adapters are authored separately.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const web = path.resolve(root, '../STT/apps/web-admin/src');
const target = path.join(root, 'apps/desktop/src/web-workflows');
fs.mkdirSync(target, {recursive: true});
for (const name of ['ConstraintCategoryStrip.vue', 'ConstraintParameters.vue']) {
  const source = fs.readFileSync(path.join(web, 'components', name), 'utf8');
  fs.writeFileSync(path.join(target, name), source.replaceAll('../utils/itcConstraints', './itcConstraints'));
}
fs.copyFileSync(path.join(web, 'utils/itcConstraints.ts'), path.join(target, 'itcConstraints.ts'));
// Extract the four dashboard cards verbatim; data is supplied by the desktop adapter.
const runs = fs.readFileSync(path.join(web, 'components/RunsView.vue'), 'utf8');
const cards = runs.slice(runs.indexOf('        <article class="run-card run-status-card"'), runs.indexOf('        <article class="run-card run-timetable-card"'))
  .replace('validationDisplay.summary.soft_violations }}', "validationDisplay.summary.soft_violations ?? '—' }}");
fs.writeFileSync(path.join(target, 'RunDashboardCards.vue'), fs.readFileSync(path.join(__dirname, 'web-run-cards-adapter.txt'), 'utf8') + '\n<template>\n' + cards + '\n</template>\n');
const localRun = path.join(root, 'apps/desktop/src/components/SchedulingView.vue');
const controller = fs.readFileSync(localRun, 'utf8').split('<template>')[0];
fs.writeFileSync(localRun, controller + fs.readFileSync(path.join(__dirname, 'web-run-page-template.txt'), 'utf8'));
// Scope exact web rules to the desktop workflow, leaving other modules untouched.
const postcss = require('../apps/desktop/node_modules/postcss');
const runStyles = runs.match(/<style scoped>([\s\S]*?)<\/style>/)?.[1] ?? '';
const css = postcss.parse(fs.readFileSync(path.join(web, 'styles.css'), 'utf8') + '\n' + runStyles.replace(/:deep\(([^)]+)\)/g,'$1'));
const code = fs.readdirSync(target).filter(n => /\.(vue|ts)$/.test(n)).map(n => fs.readFileSync(path.join(target,n),'utf8')).join('\n') + fs.readFileSync(localRun, 'utf8');
const tokens = new Set(code.match(/[a-zA-Z_][\w-]*/g));
css.walkRules(rule => {
  if(rule.parent.type === 'atrule' && /keyframes/.test(rule.parent.name)) return;
  const used = rule.selectors.filter(s => [...s.matchAll(/\.([a-zA-Z_][\w-]*)/g)].every(([,n]) => tokens.has(n) || /^(run-|step-|validation-|quality-|issue-|constraint-|common-|transfer-|lesson-directory|bottom-sheet|field-|form-|btn-|checkbox-|penalty-|input-)/.test(n)));
  if(!used.length) {rule.remove(); return;}
  rule.selectors = used.map(s => s === ':root' || s === 'body' ? '.web-workflow' : ':where(.web-workflow) ' + s);
});
css.walkAtRules(rule => {if(rule.nodes && !rule.nodes.length) rule.remove();});
fs.writeFileSync(path.join(target, 'web-workflows.css'), css.toString() + '\n' + fs.readFileSync(path.join(__dirname,'web-workflow-ui-overrides.css'),'utf8'));
console.log('Copied web constraint catalog, parameter widgets, dashboard cards and scoped styles.');
