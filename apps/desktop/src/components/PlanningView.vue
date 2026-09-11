<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { ArrowLeft, ChevronRight, X, Plus } from 'lucide-vue-next';
import { formatLocalError, localApi, type EntityRecord } from '../lib/sidecar';
import LessonEditor from './LessonEditor.vue';
import { cloneLessons, draftLesson, serializeLesson, type LessonDraft } from '../lib/lessonPlanning';

// Latest web PlanningView presentation, backed exclusively by the local project.
const props = defineProps<{ revision: number }>();
const emit = defineEmits<{ revision: [value: number] }>();
const revision = ref(props.revision);
watch(() => props.revision, value => { revision.value = value; });
const busy = ref(false), errorMessage = ref(''), notice = ref('');
const tasks = ref<EntityRecord[]>([]), lessons = ref<EntityRecord[]>([]), terms = ref<EntityRecord[]>([]);
const homerooms = ref<EntityRecord[]>([]), subjects = ref<EntityRecord[]>([]), teachers = ref<EntityRecord[]>([]);
const rooms = ref<EntityRecord[]>([]), roomTypes = ref<EntityRecord[]>([]);
const slots = ref<EntityRecord[]>([]), schedules = ref<EntityRecord[]>([]), assignments = ref<EntityRecord[]>([]);
const lessonDrafts = ref<LessonDraft[]>([]), lessonEditorOpen = ref(false);
const lessonEditor = ref<InstanceType<typeof LessonEditor> | null>(null);
watch(lessonEditorOpen, async () => { await nextTick(); dialog.value?.querySelector<HTMLElement>('button:not(:disabled)')?.focus(); });
const selectedHomeroomId = ref(''), selectedSubjectId = ref(''), editingId = ref<string | null>(null);
const classPageOpen = ref(false), editorOpen = ref(false), displayMode = ref<'classic' | 'table'>('classic');
const classSearch = ref(''), groupFilter = ref(''), statusFilter = ref('');
const subjectSearch = ref(''), teacherSearch = ref(''), roomSearch = ref(''), importTaskId = ref('');
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
const selectedTask = computed(() => selectedSubjectTasks.value.find(item => item.id === editingId.value));
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
  return classTasks(item.id).some(task => (!filters.subject.length || filters.subject.includes(String(task.subject_id))) && (!filters.teacher.length || filters.teacher.includes(String(task.primary_teacher_id))) && (!filters.room.length || filters.room.includes(String(task.fixed_room_id || item.default_room_id))));
}));
const modalOpen = computed(() => editorOpen.value || filterKind.value !== null);
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
function closeDialog() { if (!busy.value) { if (lessonEditorOpen.value) { lessonEditor.value?.requestClose(); return; } editorOpen.value = false; filterKind.value = null; } }
function matchesText(value: unknown, query: string) { return String(value ?? '').toLocaleLowerCase('zh-CN').includes(query.trim().toLocaleLowerCase('zh-CN')); }
function label(items: EntityRecord[], id: unknown, fallback = '未指定') { return String(items.find(item => item.id === id)?.name ?? fallback); }
function teacherName(task: EntityRecord) { return label(teachers.value, task.primary_teacher_id, '未指定教师'); }
function roomName(task: EntityRecord) { return label(rooms.value, task.fixed_room_id || homerooms.value.find(item => item.id === task.homeroom_id)?.default_room_id, '不指定固定教室'); }
function lessonCount(id: string) { return lessonCounts.value.get(id) ?? 0; }
function classTasks(id: string) { const term = homerooms.value.find(item => item.id === id)?.term_id || currentTerm.value?.id; return tasks.value.filter(item => item.homeroom_id === id && item.status !== 'inactive' && (!item.term_id || item.term_id === term)); }
function subjectTasks(id: string) { return currentTasks.value.filter(item => item.subject_id === id); }
function homeroomStatus(id: string) {
  const items = classTasks(id), configured = new Set(items.map(item => item.subject_id)).size;
  const completeSubjects = subjects.value.filter(subject => { const rows = items.filter(item => item.subject_id === subject.id); return rows.length > 0 && rows.every(item => item.primary_teacher_id && lessonCount(item.id) > 0); }).length;
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
  editingId.value = null; importTaskId.value = '';
  const term = terms.value.find(item => item.id === selectedHomeroom.value?.term_id) ?? currentTerm.value;
  Object.assign(taskForm, {term_id: term?.id ?? '', course_plan_id: '', homeroom_id: selectedHomeroomId.value, subject_id: selectedSubjectId.value, primary_teacher_id: '', weekly_slots: 5, duration_slots: Number(selectedSubject.value?.default_duration_slots ?? 1), required_room_type: '', fixed_room_id: '', status: 'active', week_bits: '1'.repeat(Number(term?.week_count ?? 20)), day_bits: '1'.repeat(Number(term?.day_count ?? 5))});
  lessonDrafts.value = [draftLesson({ duration_slots: taskForm.duration_slots }, taskForm.week_bits, taskForm.day_bits)];
}
function edit(task: EntityRecord) { resetForm(); editingId.value = task.id; for (const key of Object.keys(taskForm)) (taskForm as Record<string, unknown>)[key] = task[key] ?? (taskForm as Record<string, unknown>)[key]; lessonDrafts.value = lessons.value.filter(item => item.teaching_task_id === task.id).sort((a,b) => Number(a.lesson_index) - Number(b.lesson_index)).map((item, index) => draftLesson(item, taskForm.week_bits, taskForm.day_bits, index)); }
function openSubject(id: string, task?: EntityRecord | null) { selectedSubjectId.value = id; const existing = task ?? subjectTasks(id)[0]; if (existing) edit(existing); else resetForm(); errorMessage.value = ''; notice.value = ''; editorOpen.value = true; }
function importLessonSettings() { const source = tasks.value.find(item => item.id === importTaskId.value); if (!source) return; if (source.term_id !== taskForm.term_id) { errorMessage.value = '只能导入同一学期的课次设置。'; return; } lessonDrafts.value = lessons.value.filter(item => item.teaching_task_id === source.id).sort((a,b) => Number(a.lesson_index)-Number(b.lesson_index)).map((item,index) => { const draft = draftLesson(item, taskForm.week_bits, taskForm.day_bits,index); delete draft.id; return draft; }); notice.value = '已导入课次、期望时间和课次教室；教师不变。保存授课任务后生效。'; }
function applyLessons(value: LessonDraft[]) { lessonDrafts.value = cloneLessons(value); lessonEditorOpen.value = false; }
async function saveLessons(value: LessonDraft[]) { lessonDrafts.value = cloneLessons(value); await saveTask(); }
async function loadAll() {
  const results = await Promise.all(['teaching_task','task_lesson','term','homeroom','subject','teacher','room','room_type','time_slot','bell_schedule','timetable_template_assignment'].map(type => localApi.listEntities(type)));
  [tasks.value, lessons.value, terms.value, homerooms.value, subjects.value, teachers.value, rooms.value, roomTypes.value, slots.value, schedules.value, assignments.value] = results.map(result => result.items);
  revision.value = Math.max(...results.map(result => result.revision)); emit('revision', revision.value);
}
async function saveTask() {
  if (busy.value) return;
  busy.value = true; errorMessage.value = ''; notice.value = '';
  try {
    const data: Record<string, unknown> = {...taskForm, primary_teacher_id: taskForm.primary_teacher_id || null, fixed_room_id: taskForm.fixed_room_id || null, course_plan_id: taskForm.course_plan_id || null};
    if (!data.term_id) throw new Error('请先在课表设置中设置学期。');
    if (editingId.value) data.id = editingId.value;
    const result = await localApi.saveCourseArrangement(data, lessonDrafts.value.map(serializeLesson), revision.value);
    revision.value = result.revision; emit('revision', revision.value); await loadAll(); lessonEditorOpen.value = false; editorOpen.value = false; notice.value = '课程配置已保存。';
  } catch (error) { errorMessage.value = formatLocalError(error); }
  finally { busy.value = false; }
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
        <div class="planning-class-page-workspace"><article v-if="displayMode === 'classic'" class="subject-plan-panel"><div class="table-title"><div><h3>科目配置</h3><span>选择科目，配置授课教师、教室和课次</span></div></div><div class="subject-plan-list"><button v-for="subject in subjects" :key="subject.id" class="subject-plan-row" @click="openSubject(subject.id)"><div><strong>{{ subject.name }}</strong><span>{{ subjectTasks(subject.id).length ? subjectTasks(subject.id).map(teacherName).join('、') : '未指定教师' }}</span></div><em>{{ subjectTasks(subject.id).reduce((n, item) => n + lessonCount(item.id), 0) }} 课次</em><small>{{ subjectTasks(subject.id).length && subjectTasks(subject.id).every(item => item.primary_teacher_id && lessonCount(item.id)) ? '已配置' : '待完善' }}</small></button></div></article>
          <article v-else class="class-planning-table-panel"><div class="table-column-filters"><label>科目<input v-model="subjectSearch" placeholder="搜索科目" /></label><label>教师<input v-model="teacherSearch" placeholder="搜索教师" /></label><label>教室<input v-model="roomSearch" placeholder="搜索教室" /></label><span>{{ tableRows.length }} 条授课配置</span><button class="secondary-button" @click="subjectSearch = ''; teacherSearch = ''; roomSearch = ''">重置筛选</button></div><div class="planning-table-scroll"><table class="class-planning-table"><thead><tr><th>科目</th><th>教师</th><th>教室</th><th>课次</th><th>操作</th></tr></thead><tbody><tr v-for="row in tableRows" :key="row.task?.id || row.subject.id" class="course-table-row"><td><strong>{{ row.subject.name }}</strong></td><td><button class="course-table-cell-button" @click="openSubject(row.subject.id, row.task)">{{ row.task ? teacherName(row.task) : '未指定教师' }}</button></td><td><button class="course-table-cell-button" @click="openSubject(row.subject.id, row.task)">{{ row.task ? roomName(row.task) : '未配置' }}</button></td><td><button class="course-table-cell-button" @click="openSubject(row.subject.id, row.task)">{{ row.task ? lessonCount(row.task.id) : 0 }} 课次</button></td><td><div class="course-table-actions"><button class="secondary-button" @click="openSubject(row.subject.id, row.task)">配置</button><button v-if="row.task" class="danger-button" :disabled="busy" @click="remove(row.task)">删除</button></div></td></tr></tbody></table></div><p v-if="!tableRows.length" class="class-list-empty">没有匹配的授课配置</p></article><p v-if="!subjects.length" class="class-list-empty">请先在学校数据中添加科目。</p></div>
      </template>
    </div>
    <Teleport to="body"><div v-if="modalOpen" class="web-planning planning-guided-page subject-editor-mask" :class="{'lesson-sheet-mask': lessonEditorOpen}" @keydown="onDialogKey"><aside ref="dialog" class="plan-detail-panel subject-editor-dialog" role="dialog" aria-modal="true" :aria-label="lessonEditorOpen ? '编辑课次' : editorOpen ? '科目配置' : `指定${filterKind ? filterLabels[filterKind] : ''}`"><header class="subject-editor-dialog-header"><strong>{{ editorOpen ? `${selectedHomeroom?.name} · ${selectedSubject?.name} · 科目配置` : `指定${filterKind ? filterLabels[filterKind] : ''}` }}</strong><button class="subject-editor-close" aria-label="关闭弹窗" :disabled="busy" @click="closeDialog"><X :size="20" /></button></header>
      <LessonEditor v-if="lessonEditorOpen" ref="lessonEditor" :lessons="lessonDrafts" :slots="lessonSlots" :rooms="rooms.filter(item => item.status !== 'inactive')" :weeks="taskForm.week_bits" :days="taskForm.day_bits" :default-duration="Number(selectedSubject?.default_duration_slots || 1)" :busy="busy" :error="errorMessage" @apply="applyLessons" @save="saveLessons" @cancel="lessonEditorOpen = false" />
      <template v-else-if="editorOpen"><div class="task-editor-heading"><div><h3>{{ selectedSubject?.name }}</h3><span>{{ selectedHomeroom?.name }}</span></div><button class="secondary-button" :disabled="busy" @click="resetForm"><Plus :size="16" />新增授课老师</button></div><div class="task-switcher"><button v-for="task in selectedSubjectTasks" :key="task.id" class="task-switcher-item" :class="{active: editingId === task.id}" :disabled="busy" @click="edit(task)"><strong>{{ teacherName(task) }}</strong><span>{{ lessonCount(task.id) }} 个课次</span></button></div>
        <form class="detail-form" @submit.prevent="saveTask"><fieldset :disabled="busy">
          <label>教师<select v-model="taskForm.primary_teacher_id"><option value="">未指定教师，稍后配置</option><option v-for="item in teachers" :key="item.id" :value="item.id">{{ item.name }}{{ item.department ? ` · ${item.department}` : '' }}</option></select></label>
          <label>默认教室<select v-model="taskForm.fixed_room_id"><option value="">{{ selectedHomeroom?.default_room_id ? `沿用班级教室：${label(rooms, selectedHomeroom.default_room_id)}` : '不指定固定教室' }}</option><option v-for="item in rooms" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label>教室类型<select v-model="taskForm.required_room_type"><option value="">不限定教室类型</option><option v-for="item in roomTypes" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <section class="planning-import-card"><label>从其他课程导入课次设置<select v-model="importTaskId"><option value="">选择已配置课程</option><option v-for="task in tasks.filter(item => item.id !== editingId && item.term_id === taskForm.term_id)" :key="task.id" :value="task.id">{{ label(homerooms, task.homeroom_id) }} · {{ label(subjects, task.subject_id) }} · {{ teacherName(task) }}</option></select></label><button type="button" class="secondary-button" :disabled="!importTaskId" @click="importLessonSettings">导入课次设置</button></section>
          <div class="lesson-summary-card"><div class="frequency-title"><strong>课次</strong><span>{{ lessonDrafts.length }} 个课次 · {{ lessonDrafts.filter(item => item.enabled).length }} 个启用</span></div><p>期望时间、启用状态和课次教室在下方弹出栏中集中维护。</p><button type="button" class="secondary-button" @click="lessonEditorOpen = true">编辑课次</button></div>
          <p class="planning-help">每个课次可设置连续节数；具体上课时间以本班课表模板为准。</p><p v-if="notice" role="status" class="form-message">{{ notice }}</p><p v-if="errorMessage" role="alert" class="form-message error-copy">{{ errorMessage }}</p>
          <div class="planning-dialog-actions"><button class="primary-button" :disabled="busy">{{ busy ? '保存中…' : '保存授课任务' }}</button><button v-if="selectedTask" type="button" class="danger-button" @click="remove(selectedTask)">删除授课任务</button><button type="button" class="secondary-button" @click="closeDialog">取消</button></div>
        </fieldset></form>
      </template>
      <template v-else><input v-model="filterSearch" type="search" :placeholder="`搜索${filterKind ? filterLabels[filterKind] : ''}`" aria-label="搜索筛选项" /><div class="planning-filter-options"><label v-for="item in filterOptions" :key="item.id"><input v-model="filterSelection" type="checkbox" :value="item.id" /><span>{{ item.name }}</span></label><p v-if="!filterOptions.length">没有匹配项</p></div><div class="planning-dialog-actions"><span>已选 {{ filterSelection.length }} 项</span><button class="secondary-button" @click="filterSelection = []">清空选择</button><button class="primary-button" @click="confirmFilter">确定</button></div><p class="planning-help">确定后，点击过滤器中的“应用”更新班级列表。</p></template>
    </aside></div></Teleport>
  </section>
</template>

<style src="../web-workflows/web-planning.css"></style>
