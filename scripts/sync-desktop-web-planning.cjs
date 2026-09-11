// Mechanical extraction of current web CSS; never replaces the local controller.
const fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..'), web = path.resolve(root, '../STT/apps/web-admin/src');
const postcss = require('../apps/desktop/node_modules/postcss');
const view = fs.readFileSync(path.join(web, 'components/PlanningView.vue'), 'utf8');
const local = fs.readFileSync(path.join(root, 'apps/desktop/src/components/PlanningView.vue'), 'utf8');
const tokens = new Set(local.match(/[a-zA-Z_][\w-]*/g));
const scoped = view.match(/<style scoped>([\s\S]*?)<\/style>/)[1];
const css = postcss.parse(fs.readFileSync(path.join(web, 'styles.css'), 'utf8') + '\n' + scoped.replace(/:deep\(([^)]+)\)/g, '$1'));
css.walkRules(rule => {
  if (rule.parent.type === 'atrule' && /keyframes/.test(rule.parent.name)) {rule.remove(); return;}
  const used = rule.selectors.filter(selector => { const classes = [...selector.matchAll(/\.([a-zA-Z_][\w-]*)/g)].map(match => match[1]); return classes.length && classes.every(name => tokens.has(name)); });
  if (!used.length) {rule.remove(); return;}
  rule.selectors = used.map(selector => `.web-planning${selector.startsWith('.planning-guided-page') ? '' : ' '}${selector}`);
});
css.walkAtRules(rule => {if (rule.nodes && !rule.nodes.length) rule.remove();});
fs.writeFileSync(path.join(root, 'apps/desktop/src/web-workflows/web-planning.css'), '/* Generated from current web PlanningView and styles.css. */\n' + css.toString() + '\n' + fs.readFileSync(path.join(__dirname, 'web-planning-ui-overrides.css'), 'utf8'));
console.log('Synced current web planning styles including component layout.');
