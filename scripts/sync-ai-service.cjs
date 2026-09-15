// Mechanical upstream migration. Local persistence/provider adapters live outside upstream/.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const source = process.argv[2] || path.resolve(root, '../STT');
const out = path.join(root, 'sidecar/stt_desktop/agent/upstream');
fs.mkdirSync(out, {recursive:true});
const files = ['compiler','tools','business_prompts','official_workbooks','workbook_layouts','workbook_presentation','constraint_resolver','constraint_wizard','constraint_workbooks','timetable_workflow','constraint_expansion','file_parser','import_coverage','lesson_import'];
const provenance = {};
for (const name of [...files, 'distributions']) {
  const file = name === 'distributions' ? 'packages/xml-adapter/xml_adapter/distributions.py' : name === 'constraint_expansion' ? 'apps/api/app/constraint_expansion.py' : `apps/api/app/agent/${name}.py`;
  const raw = fs.readFileSync(path.join(source,file),'utf8');
  let text = raw.replace('from app.repository import SchedulingRepository','from typing import Any\nSchedulingRepository = Any')
    .replace('from app.services import build_preview_problem, create_scheduling_run','from stt_desktop.agent.repository import build_preview_problem, create_scheduling_run')
    .replaceAll('from app.agent.', 'from stt_desktop.agent.upstream.')
    .replaceAll('from stt_desktop.agent.upstream.service import _normalized_usage, _estimate_usage', 'from stt_desktop.agent.workflows import _normalized_usage, _estimate_usage')
    .replace('from xml_adapter.distributions import', 'from stt_desktop.agent.upstream.distributions import');
  if (name === 'file_parser') {
    // Refuse excessive input rather than silently importing a truncated prefix.
    text = text.replaceAll('[:20000]', '').replaceAll('.splitlines()[:200]', '.splitlines()');
    text = text.replace('rows.append("...")\n            break', 'raise HTTPException(400, "CSV超过200行，请拆分后导入；不会截断数据。")');
  }
  fs.writeFileSync(path.join(out,`${name}.py`),text);
  provenance[file] = crypto.createHash('sha256').update(raw).digest('hex');
}
fs.writeFileSync(path.join(out,'__init__.py'),'');
fs.writeFileSync(path.join(out,'provenance.json'),JSON.stringify(provenance,null,2)+'\n');
