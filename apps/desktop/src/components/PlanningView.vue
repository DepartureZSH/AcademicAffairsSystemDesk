<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { ArrowLeft, ChevronRight, X } from 'lucide-vue-next';
import { formatLocalError, localApi, type EntityRecord } from '../lib/sidecar';
import CourseEditor from '../web-course-editor/CourseEditor.vue';

// Latest web PlanningView presentation, backed exclusively by the local project.
const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();
const revision = ref(props.revision);
watch(() => props.revision, value => { revision.value = value; });
const busy = ref(false), errorMessage = ref(''), notice = ref('');
const tasks = ref<EntityRecord[]>([]), lessons = ref<EntityRecord[]>([]), terms = ref<EntityRecord[]>([]);
const homerooms = ref<EntityRecord[]>([]), subjects = ref<EntityRecord[]>([]), teachers = ref<EntityRecord[]>([]);
const coursePlans = ref<EntityRecord[]>([]);
const rooms = ref<EntityRecord[]>([]), roomTypes = ref<EntityRecord[]>([]);
const slots = ref<EntityRecord[]>([]), schedules = ref<EntityRecord[]>([]), assignments = ref<EntityRecord[]>([]);

const selectedHomeroomId = ref(''), selectedSubjectId = ref(''), editingId = ref<string | null>(null);
const classPageOpen = ref(false), editorOpen = ref(false), displayMode = ref<'classic' | 'table'>('classic');
const classSearch = ref(''), groupFilter = ref(''), statusFilter = ref('');
const subjectSearch = ref(''), teacherSearch = ref(''), roomSearch = ref('');
type FilterKind = 'subject' | 'teacher' | 'room';
const filterKinds: FilterKind[] = ['subject', 'teacher', 'room'];
const filterLabels = { subject: '科目', teacher: '教师', room: '教室' };
const draftFilters = reactive<Record<FilterKind, string[]>>({subject: [], teacher: [], room: []});
const filters = reactive<Record<FilterKind, string[]>>({subject: [], teacher: [], room: []});
const filterKind = ref<FilterKind | null>(null), filterSearch = ref(''), filterSelection = ref<string[]>([]);
const dialog = ref<HTMLElement | null>(null);
const copySourceId = ref('');
const copySources = computed(() => homerooms.value.filter(item => item.id !== selectedHomeroomId.value && (!item.term_id || item.term_id === (selectedHomeroom.value?.term_id || currentTerm.value?.id)) && homeroomStatus(item.id).complete));
const lessonCounts = computed(() => { const result = new Map<string, number>(); for (const item of lessons.value) if (item.enabled !== 0) { const id = String(item.teaching_task_id); result.set(id, (result.get(id) ?? 0) + 1); } return result; });
let returnFocus: HTMLElement | null = null;
let previousOverflow = '';
const taskForm = reactive({ term_id: '', course_plan_id: '', homeroom_id: '', subject_id: '', primary_teacher_id: '', weekly_slots: 5, duration_slots: 1, required_room_type: '', fixed_room_id: '', status: 'active', week_bits: '', day_bits: '' });
const currentTerm = computed(() => terms.value.find(item => item.active === 1) ?? terms.value[0]);
const selectedHomeroom = computed(() => homerooms.value.find(item => item.id === selectedHomeroomId.value));
const selectedSubject = computed(() => subjects.value.find(item => item.id === selectedSubjectId.value));
const currentTasks = computed(() => classTasks(selectedHomeroomId.value));
const selectedSubjectTasks = computed(() => subjectTasks(selectedSubjectId.value));
const selectedSchedule = computed(() => {
  for (const [kind, id] of [['homeroom', selectedHomeroomId.value], ['teacher', taskForm.primary_teacher_id], ['subject', selectedSubjectId.value], ['all', null]]) {
    const assignment = assignments.value.find(item => item.entity_type === kind && (item.entity_id || null) === id);
    const schedule = schedules.value.find(item => item.id === assignment?.bell_schedule_id);
    if (schedule && slots.value.some(slot => slot.bell_schedule_id === schedule.id && slot.active)) return schedule;
  }
  const options = schedules.value.filter(item => (!item.term_id || item.term_id === taskForm.term_id) && slots.value.some(slot => slot.bell_schedule_id === item.id && slot.active));
  return options.find(item => item.is_default) || options[0];
});
const lessonSlots = computed(() => slots.value.filter(item => item.bell_schedule_id === selectedSchedule.value?.id && item.active !== 0));
const groups = computed(() => [...new Set(homerooms.value.map(item => String(item.group_name || '')).filter(Boolean))].sort());
const completeClassCount = computed(() => homerooms.value.filter(item => homeroomStatus(item.id).complete).length);
const currentTotals = computed(() => ({subjects: new Set(currentTasks.value.map(item => item.subject_id)).size, lessons: currentTasks.value.reduce((n, item) => n + lessonCount(item.id), 0), teachers: new Set(currentTasks.value.map(item => item.primary_teacher_id).filter(Boolean)).size}));
const subjectRows = computed(() => subjects.value.flatMap(subject => { const rows = subjectTasks(subject.id); return (rows.length ? rows : [null]).map(task => ({subject, task})); }));
const tableRows = computed(() => subjectRows.value.filter(({subject, task}) => matchesText(subject.name, subjectSearch.value) && matchesText(task ? teacherName(task) : '未指定教师', teacherSearch.value) && matchesText(task ? roomName(task) : '未指定教室', roomSearch.value)));
const filterOptions = computed(() => (filterKind.value === 'subject' ? subjects.value : filterKind.value === 'teacher' ? teachers.value : rooms.value).filter(item => matchesText(item.name, filterSearch.value)));
const filteredHomerooms = computed(() => homerooms.value.filter(item => {
  if (!matchesText(item.name, classSearch.value)) return false;
  if (groupFilter.value && (groupFilter.value === '__ungrouped' ? Boolean(item.group_name) : item.group_name !== groupFilter.value)) return false;
  const status = homeroomStatus(item.id);
  if (statusFilter.value === 'complete' && !status.complete || statusFilter.value === 'incomplete' && status.complete || statusFilter.value === 'teacher' && !status.missingTeacher || statusFilter.value === 'lesson' && !status.missingLesson) return false;
  if (!filterKinds.some(kind => filters[kind].length)) return true;
  return classTasks(item.id).some(task => (!filters.subject.length || filters.subject.includes(String(task.subject_id))) && (!filters.teacher.length || filters.teacher.includes(String(task.primary_teacher_id))) && (!filters.room.length || taskRoomIds(task).some(id => filters.room.includes(id))));
}));
const modalOpen = computed(() => filterKind.value !== null);
watch(modalOpen, async open => {
  if (open) { returnFocus = document.activeElement as HTMLElement; previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; await nextTick(); dialog.value?.querySelector<HTMLElement>('button, input, select')?.focus(); }
  else { document.body.style.overflow = previousOverflow; returnFocus?.focus(); }
});
function onDialogKey(event: KeyboardEvent) {
  if (event.key === 'Escape' && !busy.value) { event.preventDefault(); closeDialog(); }
  if (event.key !== 'Tab') return;
  const items = [...(dialog.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)') ?? [])].filter(item => item.getClientRects().length);
  if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus(); }
  else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0]?.focus(); }
}
function closeDialog() { if (!busy.value) { editorOpen.value = false; filterKind.value = null; } }
function matchesText(value: unknown, query: string) { return String(value ?? '').toLocaleLowerCase('zh-CN').includes(query.trim().toLocaleLowerCase('zh-CN')); }
function label(items: EntityRecord[], id: unknown, fallback = '未指定') { return String(items.find(item => item.id === id)?.name ?? fallback); }
function teacherName(task: EntityRecord) { return label(teachers.value, task.primary_teacher_id, '未指定教师'); }
function taskRoomIds(task: EntityRecord): string[] {
  const config = typeof task.planning_config === 'string' ? JSON.parse(task.planning_config) : task.planning_config as any;
  if(config?.uses_rooms === false) return [];
  const fallback = task.fixed_room_id || homerooms.value.find(item=>item.id===task.homeroom_id)?.default_room_id;
  const defaults = config?.room_ids ?? (fallback ? [String(fallback)] : []);
  const custom = lessons.value.filter(item=>item.teaching_task_id===task.id && item.enabled !== 0).flatMap(item=>{
    const cfg=typeof item.planning_config==='string'?JSON.parse(item.planning_config):item.planning_config as any;
    return cfg?.room_mode === 'custom' ? cfg.room_ids : [];
  });
  return [...new Set<string>([...defaults,...custom])];
}
function roomName(task: EntityRecord) {
  const config = typeof task.planning_config === 'string' ? JSON.parse(task.planning_config) : task.planning_config as any;
  if(config && 'uses_rooms' in config) return config.uses_rooms ? config.room_ids.map((id: string) => label(rooms.value,id)).join('、') || '默认无教室' : '不使用教室';
  return label(rooms.value, task.fixed_room_id || homerooms.value.find(item => item.id === task.homeroom_id)?.default_room_id, '不指定固定教室');
}
function lessonCount(id: string) { return lessonCounts.value.get(id) ?? 0; }
function classTasks(id: string) { const term = homerooms.value.find(item => item.id === id)?.term_id || currentTerm.value?.id; return tasks.value.filter(item => item.homeroom_id === id && item.status !== 'inactive' && (!item.term_id || item.term_id === term)); }
function subjectTasks(id: string) { return currentTasks.value.filter(item => item.subject_id === id); }
function courseNotScheduled(classId: string, subjectId: string) {
  const term = homerooms.value.find(item=>item.id===classId)?.term_id || currentTerm.value?.id;
  return !classTasks(classId).some(t=>t.subject_id===subjectId) && coursePlans.value.some(p=>p.homeroom_id===classId && p.subject_id===subjectId && p.term_id===term && p.weekly_slots===0);
}
function homeroomStatus(id: string) {
  const items = classTasks(id), configured = subjects.value.filter(subject => items.some(t=>t.subject_id===subject.id) || courseNotScheduled(id,subject.id)).length;
  const completeSubjects = subjects.value.filter(subject => { const rows = items.filter(item => item.subject_id === subject.id); return courseNotScheduled(id,subject.id) || rows.length > 0 && rows.every(item => item.primary_teacher_id && lessonCount(item.id) > 0); }).length;
  return {configured, lessons: items.reduce((n,item) => n + lessonCount(item.id),0), progress: subjects.value.length ? Math.round(100 * completeSubjects / subjects.value.length) : 0, complete: subjects.value.length > 0 && completeSubjects === subjects.value.length, missingTeacher: items.some(item => !item.primary_teacher_id), missingLesson: configured < subjects.value.length || items.some(item => !lessonCount(item.id))};
}
function selectHomeroom(id: string) { selectedHomeroomId.value = id; copySourceId.value = ''; classPageOpen.value = true; subjectSearch.value = ''; teacherSearch.value = ''; roomSearch.value = ''; }
async function copyClass() {
  if (busy.value || !copySourceId.value) return;
  if (!window.confirm('复制来源班级的课程、课次和课次时间规则？教师和固定教室将留空，班级间约束不会复制。')) return;
  busy.value = true; errorMessage.value = ''; notice.value = '';
  try {
    const result = await localApi.copyClassCourses(copySourceId.value, selectedHomeroomId.value, String(selectedHomeroom.value?.term_id || currentTerm.value?.id || ''), revision.value);
    revision.value = result.revision; emit('revision', revision.value); await loadAll();
    notice.value = '已复制课程、课次与课次时间规则，请逐科补充本班教师和教室。';
  } catch (error) { errorMessage.value = formatLocalError(error); } finally { busy.value = false; }
}
function resetForm() {
  editingId.value = null;
  const term = terms.value.find(item => item.id === selectedHomeroom.value?.term_id) ?? currentTerm.value;
  Object.assign(taskForm, {term_id: term?.id ?? '', course_plan_id: '', homeroom_id: selectedHomeroomId.value, subject_id: selectedSubjectId.value, primary_teacher_id: '', weekly_slots: 5, duration_slots: Number(selectedSubject.value?.default_duration_slots ?? 1), required_room_type: '', fixed_room_id: '', status: 'active', week_bits: '1'.repeat(Number(term?.week_count ?? 20)), day_bits: '1'.repeat(Number(term?.day_count ?? 5))});
}
function edit(task: EntityRecord) { resetForm(); editingId.value = task.id; for (const key of Object.keys(taskForm)) (taskForm as Record<string, unknown>)[key] = task[key] ?? (taskForm as Record<string, unknown>)[key]; }
function openSubject(id: string, task?: EntityRecord | null) { selectedSubjectId.value = id; const existing = task ?? subjectTasks(id)[0]; if (existing) edit(existing); else resetForm(); errorMessage.value = ''; notice.value = ''; editorOpen.value = true; }
async function loadAll() {
  const results = await Promise.all(['teaching_task','task_lesson','term','homeroom','subject','teacher','room','room_type','time_slot','bell_schedule','timetable_template_assignment','course_plan'].map(type => localApi.listEntities(type)));
  [tasks.value, lessons.value, terms.value, homerooms.value, subjects.value, teachers.value, rooms.value, roomTypes.value, slots.value, schedules.value, assignments.value, coursePlans.value] = results.map(result => result.items);
  revision.value = Math.max(...results.map(result => result.revision)); emit('revision', revision.value);
}
async function remove(task: EntityRecord) {
  if (busy.value || !window.confirm('确定删除这条授课任务及其课次吗？')) return;
  busy.value = true; errorMessage.value = '';
  try { const result = await localApi.deleteEntity('teaching_task', task.id, revision.value); revision.value = result.revision; emit('revision', revision.value); await loadAll(); editorOpen.value = false; }
  catch (error) { errorMessage.value = formatLocalError(error); } finally { busy.value = false; }
}
function openFilter(kind: FilterKind) { filterKind.value = kind; filterSelection.value = [...draftFilters[kind]]; filterSearch.value = ''; }
function confirmFilter() { if (filterKind.value) draftFilters[filterKind.value] = [...filterSelection.value]; closeDialog(); }
function applyFilters() { for (const kind of filterKinds) filters[kind] = [...draftFilters[kind]]; }
function clearFilters() { for (const kind of filterKinds) { draftFilters[kind] = []; filters[kind] = []; } }
onMounted(async () => { busy.value = true; try { await loadAll(); } catch (error) { errorMessage.value = formatLocalError(error); } finally { busy.value = false; } });
onBeforeUnmount(() => { if (modalOpen.value) document.body.style.overflow = previousOverflow; });
</script>

<template>
  <section class="module-view planning-panel planning-guided-page web-planning">
    <header v-if="classPageOpen" class="planning-class-page-heading"><button class="secondary-button" @click="classPageOpen = false"><ArrowLeft :size="16" />返回班级列表</button><h2>{{ selectedHomeroom?.name }}</h2><div class="master-summary"><span>科目 {{ currentTotals.subjects }} 门</span><span>课次 {{ currentTotals.lessons }} 节</span><span>教师 {{ currentTotals.teachers }} 人</span></div></header>
    <p v-if="errorMessage && !editorOpen" role="alert" class="form-message error-copy">{{ errorMessage }}</p><p v-if="notice && !editorOpen" role="status" class="form-message">{{ notice }}</p>
    <div class="planning-class-workbench" :class="{'class-page-open': classPageOpen}" :aria-busy="busy">
      <template v-if="!classPageOpen">
        <section class="official-class-flow" :class="completeClassCount ? 'stage-copy' : 'stage-build'">
          <header><div><span class="official-flow-badge">官方建议流程</span><h3>{{ completeClassCount ? '复制同类班级的完整配置' : '先完整配置一个示范班级' }}</h3><p>{{ completeClassCount ? '已有完整班级可作来源，进入尚未配置的班级复制课程，再补充本班教师和教室。' : '先选择班级，再逐科配置课次、教师和教室，最后检查本班的差异项。' }}</p></div><div class="class-flow-progress"><strong>{{ completeClassCount }} / {{ homerooms.length }}</strong><span>课程配置完整的班级</span></div></header>
          <div class="official-flow-steps"><div :class="{active: !completeClassCount}"><span>1</span><div><strong>完整示范班级</strong><small>逐科配置全部信息</small></div></div><div :class="{active: !!completeClassCount}"><span>2</span><div><strong>复制同类班级</strong><small>继承课次与时间规则</small></div></div><div><span>3</span><div><strong>补充差异信息</strong><small>教师、教室及差异项</small></div></div></div>
        </section>
        <section class="planning-filter-bar"><div class="planning-filter-heading"><strong>过滤器</strong><span>组合筛选已配置的授课任务</span></div><div class="planning-filter-actions"><button v-for="kind in filterKinds" :key="kind" class="secondary-button" @click="openFilter(kind)">指定{{ filterLabels[kind] }} <span>{{ draftFilters[kind].length }}</span></button><button class="secondary-button" @click="clearFilters">清空</button><button class="primary-button" @click="applyFilters">应用</button></div></section>
        <aside class="planning-class-panel"><div class="table-title"><div><h3>行政班</h3><span>选择班级，查看并配置各科课程</span></div></div><div class="class-overview-filters"><label class="planning-class-search"><input v-model="classSearch" type="search" placeholder="搜索行政班" aria-label="搜索行政班" /></label><select v-model="groupFilter" aria-label="班级分组"><option value="">全部分组</option><option value="__ungrouped">未分组</option><option v-for="group in groups" :key="group" :value="group">{{ group }}</option></select><select v-model="statusFilter" aria-label="配置状态"><option value="">全部配置状态</option><option value="complete">配置完整</option><option value="incomplete">待完善</option><option value="teacher">缺少教师</option><option value="lesson">缺少课程或课次</option></select><button class="secondary-button" @click="classSearch = ''; groupFilter = ''; statusFilter = ''">重置</button><span class="class-filter-count">{{ filteredHomerooms.length }} / {{ homerooms.length }} 个班级</span></div><div class="class-list"><button v-for="homeroom in filteredHomerooms" :key="homeroom.id" class="class-list-item" :class="{complete: homeroomStatus(homeroom.id).complete}" @click="selectHomeroom(homeroom.id)"><div class="class-list-item-heading"><strong>{{ homeroom.name }}</strong><em>{{ homeroomStatus(homeroom.id).lessons }} 课次</em></div><span>{{ homeroomStatus(homeroom.id).configured }} / {{ subjects.length }} 门科目已配置</span><div class="class-card-progress"><progress :value="homeroomStatus(homeroom.id).progress" max="100" :aria-label="`${homeroom.name}配置完整度`" /><span>{{ homeroomStatus(homeroom.id).progress }}%</span></div><div class="class-card-footer"><span>{{ homeroomStatus(homeroom.id).complete ? '配置完整' : '待完善' }}</span><ChevronRight :size="16" /></div></button></div><p v-if="!filteredHomerooms.length" class="class-list-empty">{{ busy ? '正在读取班级…' : homerooms.length ? '没有匹配的行政班，请调整筛选条件。' : '还没有行政班，请先在学校数据中添加班级。' }}</p></aside>
      </template>
      <template v-else>
        <section class="planning-import-card subject-import-card"><div><strong>从完整班级复制</strong><span>{{ currentTasks.length ? '本班已有课程配置，不覆盖现有数据。' : copySources.length ? '复制课程、课次和课次时间规则；教师和固定教室留待本班配置。' : '暂无完整来源班级，请先完成一个示范班级。' }}</span></div><select v-model="copySourceId" aria-label="完整来源班级" :disabled="busy || !!currentTasks.length || !copySources.length"><option value="">选择完整来源班级</option><option v-for="item in copySources" :key="item.id" :value="item.id">{{ item.name }} · 已完整</option></select><button class="secondary-button" :disabled="busy || !!currentTasks.length || !copySourceId" @click="copyClass">复制配置</button></section>
        <div class="class-planning-view-switch"><div><strong>配置视图</strong><span>可在逐科配置和表格视图之间切换。</span></div><div class="planning-mode-tabs" role="tablist" aria-label="按班级配置展示方式"><button role="tab" :aria-selected="displayMode === 'classic'" :class="{active: displayMode === 'classic'}" @click="displayMode = 'classic'">原有视图</button><button role="tab" :aria-selected="displayMode === 'table'" :class="{active: displayMode === 'table'}" @click="displayMode = 'table'">表格视图</button></div></div>
        <div class="planning-class-page-workspace"><article v-if="displayMode === 'classic'" class="subject-plan-panel"><div class="table-title"><div><h3>科目配置</h3><span>选择科目，配置授课教师、教室和课次</span></div></div><div class="subject-plan-list"><button v-for="subject in subjects" :key="subject.id" class="subject-plan-row" @click="openSubject(subject.id)"><div><strong>{{ subject.name }}</strong><span>{{ courseNotScheduled(selectedHomeroomId,subject.id) ? '本班不安排' : subjectTasks(subject.id).length ? subjectTasks(subject.id).map(teacherName).join('、') : '未指定教师' }}</span></div><em>{{ subjectTasks(subject.id).reduce((n, item) => n + lessonCount(item.id), 0) }} 课次</em><small>{{ courseNotScheduled(selectedHomeroomId,subject.id) ? '不安排' : subjectTasks(subject.id).length && subjectTasks(subject.id).every(item => item.primary_teacher_id && lessonCount(item.id)) ? '已配置' : '待完善' }}</small></button></div></article>
          <article v-else class="class-planning-table-panel"><div class="table-column-filters"><label>科目<input v-model="subjectSearch" placeholder="搜索科目" /></label><label>教师<input v-model="teacherSearch" placeholder="搜索教师" /></label><label>教室<input v-model="roomSearch" placeholder="搜索教室" /></label><span>{{ tableRows.length }} 条授课配置</span><button class="secondary-button" @click="subjectSearch = ''; teacherSearch = ''; roomSearch = ''">重置筛选</button></div><div class="planning-table-scroll"><table class="class-planning-table"><thead><tr><th>科目</th><th>教师</th><th>教室</th><th>课次</th><th>操作</th></tr></thead><tbody><tr v-for="row in tableRows" :key="row.task?.id || row.subject.id" class="course-table-row"><td><strong>{{ row.subject.name }}</strong></td><td><button class="course-table-cell-button" @click="openSubject(row.subject.id, row.task)">{{ row.task ? teacherName(row.task) : '未指定教师' }}</button></td><td><button class="course-table-cell-button" @click="openSubject(row.subject.id, row.task)">{{ row.task ? roomName(row.task) : '未配置' }}</button></td><td><button class="course-table-cell-button" @click="openSubject(row.subject.id, row.task)">{{ row.task ? lessonCount(row.task.id) : 0 }} 课次</button></td><td><div class="course-table-actions"><button class="secondary-button" @click="openSubject(row.subject.id, row.task)">配置</button><button v-if="row.task" class="danger-button" :disabled="busy" @click="remove(row.task)">删除</button></div></td></tr></tbody></table></div><p v-if="!tableRows.length" class="class-list-empty">没有匹配的授课配置</p></article><p v-if="!subjects.length" class="class-list-empty">请先在学校数据中添加科目。</p></div>
      </template>
    </div>
    <CourseEditor v-if="editorOpen && selectedHomeroom && selectedSubject && currentTerm" :context="{homeroom:selectedHomeroom,subject:selectedSubject,term:terms.find(t=>t.id===taskForm.term_id)||currentTerm,taskId:editingId,slots:lessonSlots,allSlots:slots,schedules,assignments,revision}" @close="editorOpen = false" @saved="loadAll" />
    <Teleport to="body"><div v-if="modalOpen" class="web-planning planning-guided-page subject-editor-mask" @keydown="onDialogKey"><aside ref="dialog" class="plan-detail-panel subject-editor-dialog" role="dialog" aria-modal="true" :aria-label="`指定${filterKind ? filterLabels[filterKind] : ''}`"><header class="subject-editor-dialog-header"><strong>指定{{ filterKind ? filterLabels[filterKind] : '' }}</strong><button class="subject-editor-close" aria-label="关闭弹窗" @click="closeDialog"><X :size="20" /></button></header>
<template><input v-model="filterSearch" type="search" :placeholder="`搜索${filterKind ? filterLabels[filterKind] : ''}`" aria-label="搜索筛选项" /><div class="planning-filter-options"><label v-for="item in filterOptions" :key="item.id"><input v-model="filterSelection" type="checkbox" :value="item.id" /><span>{{ item.name }}</span></label><p v-if="!filterOptions.length">没有匹配项</p></div><div class="planning-dialog-actions"><span>已选 {{ filterSelection.length }} 项</span><button class="secondary-button" @click="filterSelection = []">清空选择</button><button class="primary-button" @click="confirmFilter">确定</button></div><p class="planning-help">确定后，点击过滤器中的“应用”更新班级列表。</p></template>
</aside></div></Teleport>
  </section>
</template>

<style src="../web-workflows/web-planning.css"></style>
