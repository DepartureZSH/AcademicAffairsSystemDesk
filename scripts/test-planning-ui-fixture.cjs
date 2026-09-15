// Explicit, disposable records only in the isolated localhost browser-dev project.
const fs = require('node:fs'), path = require('node:path');
const statePath = path.resolve(__dirname, '../.local/planning-ui-fixture.json');
const base = 'http://127.0.0.1:1420/__desktop_dev/v1';
async function request(route, method = 'GET', body) {
  const res = await fetch(base + route, {method, headers: {'X-STT-Dev':'1','Content-Type':'application/json'}, body: body ? JSON.stringify(body) : undefined});
  const result = await res.json(); if (!res.ok) throw new Error(JSON.stringify(result)); return result;
}
(async () => {
  if (process.argv[2] === 'verify-copy') {
    const records = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    const classes = records.filter(r => r.type === 'homeroom');
    const term = (await request('/data/term')).items[0];
    const tasks = await request('/data/teaching_task');
    const original = tasks.items.filter(t => t.homeroom_id === classes[0].id);
    if (original.length !== 2) throw new Error('Complete the two test subjects through the UI first');
    const before = (await request('/data/task_lesson')).items.filter(l => original.some(t => t.id === l.teaching_task_id));
    const result = await request('/planning/copy-class','POST',{source_id:classes[0].id,target_id:classes[1].id,term_id:term.id,expected_revision:tasks.revision});
    const copied = (await request('/data/teaching_task')).items.filter(t => t.homeroom_id === classes[1].id);
    if (copied.length !== 2 || copied.some(t => t.primary_teacher_id || t.fixed_room_id)) throw new Error('Copy did not reset teacher/room');
    const after = (await request('/data/task_lesson')).items.filter(l => original.some(t => t.id === l.teaching_task_id));
    if (JSON.stringify(before) !== JSON.stringify(after)) throw new Error('Source lessons changed');
    console.log(JSON.stringify({copy:'passed',counts:result.counts,sourceLessons:'unchanged'})); return;
  }
  if (process.argv[2] === 'cleanup') {
    if (!fs.existsSync(statePath)) throw new Error('No owned fixture record found');
    const records = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    // Include tasks created by UI under the two owned test classes.
    const classes = new Set(records.filter(r => r.type === 'homeroom').map(r => r.id));
    for (const task of (await request('/data/teaching_task')).items.filter(t => classes.has(t.homeroom_id))) {
      if (!records.some(r => r.id === task.id)) records.push({type:'teaching_task', id:task.id});
    }
    for (const record of [...records].reverse()) {
      const current = await request(`/data/${record.type}`);
      if (current.items.some(item => item.id === record.id)) await request(`/data/${record.type}/${record.id}?expected_revision=${current.revision}`, 'DELETE');
    }
    fs.unlinkSync(statePath); console.log('Removed owned planning UI test records.'); return;
  }
  if (fs.existsSync(statePath)) throw new Error('Existing fixture must be cleaned first');
  const existing = await request('/data/homeroom');
  if (existing.items.length || (await request('/data/subject')).items.length) throw new Error('Fixture requires empty isolated preview; refusing to mix with existing data');
  let revision = existing.revision; const records = [];
  async function add(type, data) { const result = await request(`/data/${type}`, 'PUT', {data,expected_revision:revision}); revision = result.revision; records.push({type,id:result.item.id}); fs.writeFileSync(statePath,JSON.stringify(records)); return result.item.id; }
  const term = (await request('/data/term')).items[0];
  const teacher = await add('teacher',{name:'验证教师'});
  const room = await add('room',{name:'验证教室'});
  const subject = await add('subject',{name:'验证数学'});
  await add('subject',{name:'验证语文'});
  const homeroom = await add('homeroom',{name:'验证一班',term_id:term.id,group_name:'验证年级'});
  await add('homeroom',{name:'验证二班',term_id:term.id,group_name:'验证年级'});
  const result = await request('/planning/tasks','PUT',{expected_revision:revision,data:{homeroom_id:homeroom,term_id:term.id,subject_id:subject,primary_teacher_id:teacher,fixed_room_id:room,weekly_slots:5,duration_slots:2,week_bits:'1'.repeat(term.week_count),day_bits:'11111'}});
  records.push({type:'teaching_task',id:result.task.id}); fs.writeFileSync(statePath,JSON.stringify(records));
  console.log('Created temporary local UI fixture; cleanup uses recorded IDs only.');
})().catch(error => { console.error(error.message); process.exitCode = 1; });
