// Generated from the web controller; see scripts/extract-course-editor.cjs.
import {computed, ref, nextTick, watch, onMounted, onBeforeUnmount} from 'vue';
import {localApi, formatLocalError} from '../lib/sidecar';
import {localGuideSteps} from './guideSteps';
export function useCourseEditor(props: any, emit: any) {
const schoolData = ref<{teachers:Record<string,unknown>[];rooms:Record<string,unknown>[];subjects:Record<string,unknown>[];homerooms:Record<string,unknown>[];[key:string]:any}>({teachers:[], rooms:[], room_types:[], subjects:[], homerooms:[], weekly_timetable_templates:[], weekly_timetable_periods:[], timetable_template_assignments:[], active_term:null});
const planningData = ref<any>({course_plans:[], teaching_tasks:[], task_lessons:[]});
const selectedSubject = computed(() => props.context.subject);
const selectedPlanningHomeroom = computed(() => props.context.homeroom);
const selectedCoursePlan = computed(() => planningData.value.course_plans.find((p: any) => p.term_id === props.context.term.id && p.homeroom_id === props.context.homeroom.id && p.subject_id === props.context.subject.id));
const selectedCoursePlanTasks = computed<any[]>(() => planningData.value.teaching_tasks.filter((t: any) => t.status === 'active' && t.term_id === props.context.term.id && t.homeroom_id === props.context.homeroom.id && t.subject_id === props.context.subject.id));
const selectedCourseNotScheduled = computed(() => !!selectedCoursePlan.value && Number(selectedCoursePlan.value.weekly_slots) === 0 && !selectedCoursePlanTasks.value.length);
const planningViewMode = ref<PlanningViewMode>('class');
const selectedTemplatePeriods = computed<any[]>(() => {
  const all = props.context.allSlots || props.context.slots;
  const schedules = (props.context.schedules || []).filter((s:any)=>!s.term_id || s.term_id === props.context.term.id);
  let selected;
  for(const [kind,id] of [['homeroom',props.context.homeroom.id],['teacher',teachingTaskForm.value.primary_teacher_id],['subject',props.context.subject.id],['all',null]]) {
    const assignment=(props.context.assignments||[]).find((a:any)=>a.entity_type===kind && (a.entity_id||null)===id);
    selected=schedules.find((s:any)=>s.id===assignment?.bell_schedule_id && all.some((p:any)=>p.bell_schedule_id===s.id&&p.active));
    if(selected)break;
  }
  selected ||= schedules.find((s:any)=>s.is_default && all.some((p:any)=>p.bell_schedule_id===s.id&&p.active)) || schedules.find((s:any)=>all.some((p:any)=>p.bell_schedule_id===s.id&&p.active));
  const metadata = localConfig(selected?.display_config);
  const template = metadata._web_template || metadata;
  const visibleDays = metadata.enabled_weekdays || template.display_config?.enabled_weekdays || template.enabled_weekdays;
  return (selected?all.filter((p:any)=>p.bell_schedule_id===selected.id&&p.active):props.context.slots)
    .filter((s:any)=>!Array.isArray(visibleDays)||visibleDays.includes(Number(s.weekday)))
    .map((s:any)=>({...s,period_index:Number(s.period_index)+1}));
});
const enabledWeekdays = computed<number[]>(() => [...new Set<number>(selectedTemplatePeriods.value.map(p=>Number(p.weekday)))].sort());
const lessonImportTaskOptions = computed<any[]>(() => planningData.value.teaching_tasks.filter((t: any) => t.id !== selectedTeachingTaskId.value && t.term_id === props.context.term.id && lessonsForTask(t.id).length));
const subjectEditorOpen = ref(false);
const subjectEditorPanel = ref<HTMLElement|null>(null);
const courseCandidateScale = ref(100);
const courseCandidateScaleWasAdjusted = ref(false);
const localRevision = ref(props.context.revision);
const localOriginalOverflow = document.body.style.overflow;
const localReturnFocus = document.activeElement as HTMLElement|null;
function markCourseCandidateScaleAdjusted() { courseCandidateScaleWasAdjusted.value = true; }
function syncCourseCandidateScale() { if(!courseCandidateScaleWasAdjusted.value) courseCandidateScale.value = window.innerWidth<=560?65:window.innerWidth<=820?75:window.innerWidth<=1100?85:100; }
function coursePlanningPeriodsForHomeroom(_id?: unknown) { return selectedTemplatePeriods.value; }
function lessonsForTask(id: unknown): any[] { return planningData.value.task_lessons.filter((l: any)=>l.teaching_task_id===id).sort((a:any,b:any)=>a.lesson_index-b.lesson_index); }
function taskLessonCount(id: unknown) { return lessonsForTask(id).filter(l=>l.enabled!==false && l.enabled!==0).length; }
function isTeachingTaskActive(id: unknown) {return selectedTeachingTaskId.value===String(id);}
function legacyDurationMinutes(slots: unknown) { return selectedTemplatePeriods.value.filter(p=>Number(p.weekday)===enabledWeekdays.value[0]).slice(0,Number(slots)||1).reduce((n,p)=>n+Number(p.end_time_minutes)-Number(p.start_time_minutes),0) || 40; }
function selectedSubjectDurationSlots() { return Number(selectedSubject.value.default_duration_minutes || legacyDurationMinutes(selectedSubject.value.default_duration_slots)) / 5; }
function unitsToMinutes(units: unknown) { return Number(units || 0) * 5; }
function isCoursePreferredPeriodDisabled(index: number, period?: any): boolean {
  const duration = unitsToMinutes(activeCoursePreferredLesson()?.duration_slots);
  const fits = (p:any) => Number(p.end_time_minutes)-Number(p.start_time_minutes)>=duration;
  return period ? !fits(period) : !selectedTemplatePeriods.value.filter(p=>p.period_index===index).some(fits);
}
function closeSubjectEditor() { if(!courseArrangementSaving.value) emit('close'); }
function handleSubjectEditorKeydown(event: KeyboardEvent) {
  if (Array.from(document.querySelectorAll('[role="dialog"], .bottom-sheet-mask')).some(el => el !== subjectEditorPanel.value && el.getClientRects().length && !subjectEditorPanel.value?.contains(el))) return;
  if (event.key === 'Escape') { event.stopPropagation(); closeSubjectEditor(); }
  if (event.key === 'Tab') {
    const controls = Array.from(subjectEditorPanel.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]') || []).filter(el => el.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
}
function localConfig(raw: any) { try {return typeof raw==='string'?JSON.parse(raw):raw||{};} catch {return {};} }
function localRules(lesson: any): CoursePreferredRuleDraft[] {
  return (localConfig(lesson.planning_config).preferred_times||[]).map((r:any)=>{const p=selectedTemplatePeriods.value.find(p=>p.id===r.time_slot_id);const original=(props.context.allSlots||[]).find((p:any)=>p.id===r.time_slot_id);return {key:coursePreferredRuleKey(),week_bits:r.week_bits,day_bits:p||original?bitsFromNumbers([Number((p||original).weekday)],termDayCount.value):'0000000',period_index:p?.period_index??(original?Number(original.period_index)+1:-1),penalty:r.penalty,forbidden:r.penalty<0};});
}
function localDraft(lesson:any): CourseLessonDraft {const cfg=localConfig(lesson.planning_config), rules=localRules(lesson), slots=coursePreferredSlotsFromRules(rules);return {id:lesson.id,key:lesson.id||crypto.randomUUID(),label:lesson.label||recordName(selectedSubject.value),duration_slots:Number(cfg.duration_minutes || legacyDurationMinutes(lesson.duration_slots))/5,enabled:lesson.enabled!==0 && lesson.enabled!==false,room_mode:cfg.room_mode||'default',room_ids:cfg.room_ids||[],preferred_rules:rules,preferred_slots:slots,preferred_period_ids:[...new Set(slots.map(s=>s.period_id))]};}
function selectTeachingTask(task: any) {
  selectedTeachingTaskId.value=task.id||'';
  const cfg=localConfig(task.planning_config), fallback=task.fixed_room_id||props.context.homeroom.default_room_id;
  teachingTaskForm.value={homeroom_id:props.context.homeroom.id,subject_id:props.context.subject.id,primary_teacher_id:task.primary_teacher_id||'',fixed_room_id:task.fixed_room_id||'',uses_rooms:cfg.uses_rooms??true,room_ids:cfg.room_ids??(fallback?[fallback]:[]),course_plan_id:task.course_plan_id||'',week_bits:task.week_bits||'1'.repeat(termWeekCount.value),day_bits:task.day_bits||defaultDayBits()};
  coursePlanForm.value.homeroom_id=props.context.homeroom.id; coursePlanForm.value.subject_id=props.context.subject.id;coursePlanForm.value.week_bits=teachingTaskForm.value.week_bits;coursePlanForm.value.day_bits=teachingTaskForm.value.day_bits;
  courseLessonDrafts.value=task.id?lessonsForTask(task.id).map(localDraft):[newCourseLessonDraft()];
  defaultRoomSearch.value='';showDefaultRoomOptions.value=false;lessonRoomSearch.value={};showLessonRoomOptions.value={};courseLessonPreferencesDirty.value=false;syncTeacherSearchFromSelection();
}
function startNewTeachingTask() { selectTeachingTask({}); }
function sourceLessonDraftsFromTask(task:any, _name?:string) {return lessonsForTask(task.id).map(l=>{const d=localDraft(l);delete d.id;d.key=crypto.randomUUID();return d;});}
function taskRoomOptionIds(task:any) {const cfg=localConfig(task.planning_config);return cfg.uses_rooms===false?[]:cfg.room_ids??(task.fixed_room_id?[task.fixed_room_id]:[]);}
function importLessonSettingsFromSelectedTask() {
  const task=planningData.value.teaching_tasks.find((t:any)=>t.id===selectedLessonImportTaskId.value); if(!task)return;
  const cfg=localConfig(task.planning_config);teachingTaskForm.value.uses_rooms=cfg.uses_rooms??true;teachingTaskForm.value.room_ids=taskRoomOptionIds(task);teachingTaskForm.value.fixed_room_id=teachingTaskForm.value.room_ids[0]||'';
  courseLessonDrafts.value=sourceLessonDraftsFromTask(task);selectedLessonImportTaskId.value='';defaultRoomSearch.value='';lessonRoomSearch.value={};error.value='';
}
async function loadSchoolData() {
  const types=['teacher','homeroom','subject','room','room_type','course_plan','teaching_task','task_lesson'];
  const results=await Promise.all(types.map(type=>localApi.listEntities(type)));
  const [teachers,homerooms,subjects,rooms,roomTypes,plans,tasks,lessons]=results.map(r=>r.items);
  schoolData.value={...schoolData.value,teachers,homerooms,subjects,rooms:rooms.map(r=>({...r,room_type_name:roomTypes.find(t=>t.id===r.room_type_id)?.name})),room_types:roomTypes,active_term:props.context.term};
  planningData.value={course_plans:plans,teaching_tasks:tasks,task_lessons:lessons};localRevision.value=Math.max(...results.map(r=>r.revision));
}
async function saveCourseArrangement() {
  const teacher=resolveTeacherIdForSave();if(teacher===null){error.value='请从教师下拉列表中选择教师，或清空教师后再保存';return;}
  courseArrangementSaving.value=true;error.value='';
  try {
    const serialized=courseLessonDrafts.value.map(lesson=>{
      if(lesson.preferred_rules.some(rule=>rule.period_index<1 || !selectedTemplatePeriods.value.some(p=>Number(p.period_index)===rule.period_index && rule.day_bits[Number(p.weekday)-1]==='1'))) throw new Error('部分期望时间已不在当前课表中，请在课次编辑中清空该课次的时间后重新选择。');
      const preferred_times=lesson.preferred_rules.flatMap(rule=>selectedTemplatePeriods.value.filter(p=>Number(p.period_index)===Number(rule.period_index)&&rule.day_bits[Number(p.weekday)-1]==='1').map(p=>({time_slot_id:p.id,week_bits:rule.week_bits,penalty:rule.forbidden?-1:rule.penalty})));
      const original=lessonsForTask(selectedTeachingTaskId.value).find(l=>l.id===lesson.id);
      const keepLegacy=original && !localConfig(original.planning_config).duration_minutes && unitsToMinutes(lesson.duration_slots)===legacyDurationMinutes(original.duration_slots);
      return {id:lesson.id,label:lesson.label,enabled:lesson.enabled,duration_slots:keepLegacy?original.duration_slots:1,week_bits:teachingTaskForm.value.week_bits,day_bits:teachingTaskForm.value.day_bits,planning_config:{...(!keepLegacy?{duration_minutes:unitsToMinutes(lesson.duration_slots)}:{}),room_mode:lesson.room_mode,room_ids:lesson.room_ids,preferred_times}};
    });
    const result=await localApi.saveCourseArrangement({...(selectedTeachingTaskId.value?{id:selectedTeachingTaskId.value}:{}),term_id:props.context.term.id,homeroom_id:props.context.homeroom.id,subject_id:props.context.subject.id,primary_teacher_id:teacher||null,fixed_room_id:null,required_room_type:null,status:'active',week_bits:teachingTaskForm.value.week_bits,day_bits:teachingTaskForm.value.day_bits,planning_config:{uses_rooms:teachingTaskForm.value.uses_rooms,room_ids:teachingTaskForm.value.room_ids}},serialized,localRevision.value);
    await loadSchoolData();selectTeachingTask(result.task);lessonEditorSessionSnapshot.value=cloneLessonEditorDrafts(courseLessonDrafts.value);showLessonEditorSheet.value=false;courseArrangementNotice.value='授课任务已保存';emit('saved',localRevision.value);
  }catch(e){error.value=formatLocalError(e);}finally{courseArrangementSaving.value=false;}
}
async function deleteCourseArrangement(task:any) {
  if(!window.confirm('确认删除该授课任务及其课次？'))return;courseArrangementSaving.value=true;
  try{const result=await localApi.deleteEntity('teaching_task',task.id,localRevision.value);localRevision.value=result.revision;await loadSchoolData();selectTeachingTask(selectedCoursePlanTasks.value[0]||{});emit('saved',localRevision.value);}catch(e){error.value=formatLocalError(e);}finally{courseArrangementSaving.value=false;}
}
async function markSelectedCourseNotScheduled() { await localSetScheduled(false); }
async function resumeSelectedCourseScheduling() { await localSetScheduled(true); }
async function localSetScheduled(scheduled:boolean) {
  if(!scheduled&&selectedCoursePlanTasks.value.length&&!window.confirm(`将“${selectedSubject.value.name}”设为不安排？现有 ${selectedCoursePlanTasks.value.length} 个授课任务及其课次会被删除。`))return;
  courseArrangementSaving.value=true;
  try{const result=await localApi.setCourseScheduled(props.context.homeroom.id,props.context.subject.id,props.context.term.id,scheduled,localRevision.value);localRevision.value=result.revision;await loadSchoolData();startNewTeachingTask();courseArrangementNotice.value=scheduled?'已恢复安排，请新增授课任务；教师可以暂时保持未指定':'已设为不安排；该班级不会生成这门课程的课次，也不会参与排课';emit('saved',localRevision.value);}catch(e){error.value=formatLocalError(e);}finally{courseArrangementSaving.value=false;}
}
function startGuide(page: string, _force?:boolean) { localGuidePage.value=page;activeGuideStepIndex.value=0;showGuide.value=true;void updateGuideTarget(true); }
const localGuidePage = ref('');
const activeGuideSteps = computed(()=>localGuideSteps[localGuidePage.value]||[]);
function skipGuide() {showGuide.value=false;guideTargetRect.value=null;}
function nextGuideStep() {if(activeGuideStepIndex.value>=activeGuideSteps.value.length-1)skipGuide();else{activeGuideStepIndex.value++;void updateGuideTarget(true);}}
function previousGuideStep() {activeGuideStepIndex.value=Math.max(0,activeGuideStepIndex.value-1);void updateGuideTarget(true);}
function restartGuide() {activeGuideStepIndex.value=0;void updateGuideTarget(true);}
function localGuidePosition() {if(showGuide.value)void updateGuideTarget();}
onMounted(()=>watch(error, message=>{if(message)window.alert(message);}));
onMounted(async()=>{document.body.style.overflow='hidden';syncCourseCandidateScale();window.addEventListener('resize',syncCourseCandidateScale);window.addEventListener('resize',localGuidePosition);window.addEventListener('scroll',localGuidePosition,true);try{await loadSchoolData();selectTeachingTask(planningData.value.teaching_tasks.find((t:any)=>t.id===props.context.taskId)||selectedCoursePlanTasks.value[0]||{});if(props.context.pickerDraft){externalCoursePreferredDraft.value=props.context.pickerDraft;coursePreferredPickerTitle.value='专项期望时间设置';prepareCoursePreferredPicker();watch(showCoursePreferredPicker,open=>{if(!open)emit('close');});return;}subjectEditorOpen.value=true;await nextTick();subjectEditorPanel.value?.querySelector<HTMLElement>('button')?.focus();}catch(e){window.alert(formatLocalError(e));emit('close');}});
onBeforeUnmount(()=>{document.body.style.overflow=localOriginalOverflow;window.removeEventListener('resize',syncCourseCandidateScale);window.removeEventListener('resize',localGuidePosition);window.removeEventListener('scroll',localGuidePosition,true);localReturnFocus?.focus();});

type PlanningViewMode = "class" | "subject" | "teacher";

type CourseCellExportLayout = "single_line" | "two_line" | "split_rows";

type CourseCellExportField = "subject" | "teacher" | "room" | "time" | "homeroom";

type PeriodCellMode = "scheduled" | "custom" | "disabled";

type PeriodCellExportStyle = "default" | "custom";

type GuideTargetRect = {
    top: number;
    left: number;
    width: number;
    height: number;
  } | null;

type PeriodDraft = {
    id?: string;
    weekday: number;
    period_index: number;
    label: string;
    start_time: string;
    end_time: string;
    active: boolean;
    align: "left" | "center";
    colspan: number;
    cell_mode?: PeriodCellMode;
    custom_content?: string;
    sample_subject?: string;
    sample_teacher?: string;
    sample_room?: string;
    sample_homeroom?: string;
    export_style?: PeriodCellExportStyle;
    export_layout?: CourseCellExportLayout;
    export_top_field?: CourseCellExportField;
    export_bottom_field?: CourseCellExportField;
  };

type RoomUnavailableRuleDraft = {
    key: string;
    week_bits: string;
    day_bits: string;
    period_index: number;
  };

type RoomUnavailableRule = {
    key: string;
    week_bits: string;
    day_bits: string;
    period_index: number;
    time_range: string;
    timeText: string;
    dayText: string;
    weekText: string;
    label: string;
    compactLabel: string;
  };

type CoursePreferredSlot = {
    week: number;
    period_id: string;
  };

type CoursePreferredRuleDraft = RoomUnavailableRuleDraft & {
    penalty: number;
    forbidden?: boolean;
  };

type CoursePreferredRule = RoomUnavailableRule & {
    penalty: number;
    forbidden?: boolean;
    priorityText: string;
    priorityClass: string;
  };

type CourseLessonDraft = {
    id?: string;
    key: string;
    label: string;
    duration_slots: number;
    enabled: boolean;
    room_mode: "default" | "custom";
    room_ids: string[];
    preferred_period_ids: string[];
    preferred_slots: CoursePreferredSlot[];
    preferred_rules: CoursePreferredRuleDraft[];
    draft_origin?: "new" | "copy";
  };

type LessonEditorChange = {
    key: string;
    tone: "add" | "update" | "delete";
    title: string;
    detail: string;
  };

const showGuide = ref(false);

const activeGuideStepIndex = ref(0);

const guideTargetRect = ref<GuideTargetRect>(null);

const guideMissingTarget = ref(false);

const termForm = ref({ name: "默认学期", week_count: 14, day_count: 7 });

const coursePlanForm = ref({
    homeroom_id: "",
    subject_id: "",
    week_bits: "11111111111111",
    day_bits: "1111100",
    preferred_period_ids: [] as string[],
    preferred_slots: [] as CoursePreferredSlot[],
    preferred_rules: [] as CoursePreferredRuleDraft[],
  });

const teachingTaskForm = ref({
    homeroom_id: "",
    subject_id: "",
    primary_teacher_id: "",
    fixed_room_id: "",
    uses_rooms: true,
    room_ids: [] as string[],
    course_plan_id: "",
    week_bits: "11111111111111",
    day_bits: "1111100",
  });

const courseLessonDrafts = ref<CourseLessonDraft[]>([]);

const subjectDefaultLessonDrafts = ref<CourseLessonDraft[]>([]);

const selectedCoursePreferredLessonKey = ref("");

const courseLessonPreferencesDirty = ref(false);

const lessonEditorSessionSnapshot = ref<CourseLessonDraft[]>([]);

const lessonEditorSessionMode = ref<PlanningViewMode>("class");

const coursePreferredRuleSnapshot = ref<CoursePreferredRuleDraft[]>([]);

const defaultRoomSearch = ref("");

const showDefaultRoomOptions = ref(false);

const lessonRoomSearch = ref<Record<string, string>>({});

const showLessonRoomOptions = ref<Record<string, boolean>>({});

const loading = ref(false);

const courseArrangementSaving = ref(false);

const courseArrangementNotice = ref("");

const error = ref("");

const selectedTeachingTaskId = ref("");

const selectedLessonImportTaskId = ref("");

const teacherSearch = ref("");

const teacherSearchInput = ref<HTMLInputElement | null>(null);

const showTeacherOptions = ref(false);

const showCoursePreferredPicker = ref(false);

const externalCoursePreferredDraft = ref<CourseLessonDraft | null>(null);

const coursePreferredPickerTitle = ref("");

const showLessonEditorSheet = ref(false);

const courseWeekFrequencyCollapsed = ref(false);

const editingCoursePreferredRuleKey = ref("");

const coursePreferredBatchMode = ref(false);

const coursePreferredBatchPeriodIndexes = ref<number[]>([]);

const roomUnavailableRuleForm = ref({
    week_bits: "",
    day_bits: "",
    period_index: 1,
  });

const coursePreferredRuleForm = ref({
    week_bits: "",
    day_bits: "",
    period_index: 1,
    penalty: 0,
    forbidden: false,
  });

const coursePreferredPriorityOptions = [
    { penalty: 0, label: "最高优先", hint: "优先安排", className: "priority-0" },
    { penalty: 10, label: "普通优先", hint: "可接受", className: "priority-10" },
    { penalty: 30, label: "较低优先", hint: "尽量少用", className: "priority-30" },
    { penalty: 60, label: "兜底可排", hint: "最后选择", className: "priority-60" },
    { penalty: -1, label: "绝对不排", hint: "禁止安排", className: "priority-forbidden", forbidden: true },
  ];

const weekdayOptions = [
    { index: 0, label: "周一" },
    { index: 1, label: "周二" },
    { index: 2, label: "周三" },
    { index: 3, label: "周四" },
    { index: 4, label: "周五" },
    { index: 5, label: "周六" },
    { index: 6, label: "周日" },
  ];

const fixedWeeklyDayCount = 7;

const termWeekCount = computed(() => Number(schoolData.value.active_term?.week_count || termForm.value.week_count || 14));

const termDayCount = computed(() => fixedWeeklyDayCount);

const termWeekOptions = computed(() =>
    Array.from({ length: termWeekCount.value }, (_, index) => ({
      index,
      label: `${index + 1}`,
    })),
  );

const activeGuideStep = computed(() => activeGuideSteps.value[activeGuideStepIndex.value] || null);

const guideProgressLabel = computed(() => {
    const total = activeGuideSteps.value.length;
    if (!total) return "新手指引";
    return `${activeGuideStepIndex.value + 1} / ${total}`;
  });

const guideHighlightStyle = computed<Record<string, string>>(() => {
    if (!guideTargetRect.value) return {} as Record<string, string>;
    return {
      top: `${guideTargetRect.value.top}px`,
      left: `${guideTargetRect.value.left}px`,
      width: `${guideTargetRect.value.width}px`,
      height: `${guideTargetRect.value.height}px`,
    };
  });

const guideCardStyle = computed<Record<string, string>>(() => {
    const rect = guideTargetRect.value;
    if (!rect || window.innerWidth <= 720) return {} as Record<string, string>;
    const cardWidth = 320;
    const left = Math.min(Math.max(rect.left, 16), window.innerWidth - cardWidth - 16);
    const preferredTop = rect.top - 136;
    const top = preferredTop > 16 ? preferredTop : Math.min(rect.top + rect.height + 16, window.innerHeight - 220);
    return {
      top: `${Math.max(top, 16)}px`,
      left: `${left}px`,
      width: `${cardWidth}px`,
    };
  });

function guideTargetElement(target: string) {
    return document.querySelector(`[data-guide-id="${target}"]`) as HTMLElement | null;
  }

async function updateGuideTarget(scrollTarget = false) {
    const step = activeGuideStep.value;
    if (!step) {
      guideTargetRect.value = null;
      guideMissingTarget.value = true;
      return;
    }
    const element = guideTargetElement(step.target);
    if (!element) {
      guideTargetRect.value = null;
      guideMissingTarget.value = true;
      return;
    }
    if (scrollTarget) {
      element.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
      await new Promise((resolve) => window.setTimeout(resolve, 180));
    }
    const rect = element.getBoundingClientRect();
    const padding = 8;
    guideTargetRect.value = {
      top: Math.max(rect.top - padding, 8),
      left: Math.max(rect.left - padding, 8),
      width: Math.min(rect.width + padding * 2, window.innerWidth - Math.max(rect.left - padding, 8) - 8),
      height: Math.min(rect.height + padding * 2, window.innerHeight - Math.max(rect.top - padding, 8) - 8),
    };
    guideMissingTarget.value = false;
  }

function normalizeEnabledWeekdays(days: unknown) {
    const values = Array.isArray(days)
      ? days.map((day) => Number(day)).filter((day) => day >= 1 && day <= fixedWeeklyDayCount)
      : [1, 2, 3, 4, 5];
    const normalized = Array.from(new Set(values)).sort((left, right) => left - right);
    return normalized.length ? normalized : [1, 2, 3, 4, 5];
  }

function isTemplateWeekdayEnabled(weekday: number) {
    return enabledWeekdays.value.includes(weekday);
  }

function timeSlotKey(week: number, periodId: unknown) {
    return `${Number(week || 0)}:${String(periodId)}`;
  }

function coursePreferredRuleKey() {
    return `course-rule-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

function activeRoomUnavailableWeeks(bits = roomUnavailableRuleForm.value.week_bits) {
    const normalized = normalizeBits(bits, termWeekCount.value);
    return normalized
      .split("")
      .map((value, index) => (value === "1" ? index + 1 : null))
      .filter((value): value is number => value !== null);
  }

function timeRuleIdentity(rule: RoomUnavailableRuleDraft) {
    const penalty = (rule as { penalty?: unknown }).penalty;
    const penaltyPart = penalty === undefined ? "" : `:${Number(penalty || 0)}`;
    return `${normalizeBits(rule.week_bits, termWeekCount.value)}:${sanitizeDayBitsForEnabledWeekdays(rule.day_bits, false)}:${Number(rule.period_index || 0)}${penaltyPart}`;
  }

function mergeTimeRuleDrafts<T extends RoomUnavailableRuleDraft>(rules: T[]) {
    const merged = new Map<string, T>();
    for (const rule of rules) {
      if (!rule.week_bits.includes("1") || !rule.day_bits.includes("1") || Number(rule.period_index || 0) <= 0) {
        continue;
      }
      const key = timeRuleIdentity(rule);
      if (!merged.has(key)) {
        merged.set(key, rule);
      }
    }
    return Array.from(merged.values());
  }

function timetablePeriodOptions(periods: Array<Record<string, unknown>>) {
    const grouped = new Map<
      number,
      { period_index: number; label: string; time_ranges: Set<string>; length_slots: number }
    >();
    for (const period of periods) {
      const periodIndex = Number(period.period_index || 0);
      if (!periodIndex) continue;
      const option = grouped.get(periodIndex) || {
        period_index: periodIndex,
        label: `第${periodIndex}节`,
        time_ranges: new Set<string>(),
        length_slots: 0,
      };
      option.time_ranges.add(periodTimeRange(period));
      option.length_slots = Math.max(option.length_slots, Number(period.length_slots || 1));
      grouped.set(periodIndex, option);
    }
    return Array.from(grouped.values())
      .map((option) => {
        const timeRanges = Array.from(option.time_ranges).sort(
          (left, right) => timeRangeStartMinutes(left) - timeRangeStartMinutes(right),
        );
        return {
          period_index: option.period_index,
          label: option.label,
          time_range: timeRanges.length === 1 ? timeRanges[0] : "各日时间不同",
          time_ranges: timeRanges,
          has_variable_times: timeRanges.length > 1,
          length_slots: option.length_slots,
          start_minutes: Math.min(...timeRanges.map(timeRangeStartMinutes)),
        };
      })
      .sort((left, right) => left.period_index - right.period_index);
  }

function roomUnavailablePeriodOptions() {
    return timetablePeriodOptions(
      selectedTemplatePeriods.value.filter((period) => isTemplateWeekdayEnabled(Number(period.weekday || 0))),
    );
  }

function coursePreferredPeriodOptions() {
    return timetablePeriodOptions(selectedTemplatePeriods.value);
  }

function weekFrequencyPresets() {
    const weeks = Array.from({ length: termWeekCount.value }, (_, index) => index + 1);
    return [
      { key: "all", label: "全学期", weeks },
      { key: "odd", label: "单周", weeks: weeks.filter((week) => week % 2 === 1) },
      { key: "even", label: "双周", weeks: weeks.filter((week) => week % 2 === 0) },
      { key: "first-half", label: "前半学期", weeks: weeks.filter((week) => week <= Math.ceil(termWeekCount.value / 2)) },
      { key: "second-half", label: "后半学期", weeks: weeks.filter((week) => week > Math.ceil(termWeekCount.value / 2)) },
    ].filter((preset) => preset.weeks.length);
  }

function applyCoursePreferredWeekPreset(weeks: number[]) {
    coursePreferredRuleForm.value.week_bits = bitsFromNumbers(weeks, termWeekCount.value);
  }

function timeRangeStartMinutes(range: string) {
    const start = String(range || "").split("-")[0]?.trim();
    return start ? clockToMinutes(start) : 0;
  }

function normalizeBatchPeriodIndexes(indexes: number[]) {
    const available = new Set(roomUnavailablePeriodOptions().map((period) => period.period_index));
    return Array.from(new Set(indexes.map((index) => Number(index || 0)).filter((index) => available.has(index))))
      .sort((left, right) => left - right);
  }

function setCoursePreferredBatchMode(active: boolean) {
    coursePreferredBatchMode.value = active;
    coursePreferredBatchPeriodIndexes.value = active
      ? normalizeBatchPeriodIndexes([coursePreferredRuleForm.value.period_index])
      : [];
  }

function closeCoursePreferredPicker() {
    setCoursePreferredBatchMode(false);
    const target = activeCoursePreferredLesson();
    const restored = coursePreferredRuleSnapshot.value.map((rule) => ({ ...rule }));
    if (target) {
      target.preferred_rules = restored;
    } else {
      coursePlanForm.value.preferred_rules = restored;
    }
    syncCoursePreferredSlotsFromRules();
    courseLessonPreferencesDirty.value = lessonEditorHasChanges.value;
    coursePreferredRuleSnapshot.value = [];
    showCoursePreferredPicker.value = false;
    externalCoursePreferredDraft.value = null;
    coursePreferredPickerTitle.value = "";
  }

function openLessonEditorSheet() {
    ensureCourseLessons();
    lessonEditorSessionMode.value = planningViewMode.value;
    lessonEditorSessionSnapshot.value = cloneLessonEditorDrafts(activeLessonDraftList());
    showLessonEditorSheet.value = true;
  }

function closeLessonEditorSheet() {
    if (lessonEditorHasChanges.value) {
      const confirmed = window.confirm("当前课次有尚未保存的修改。确认关闭并放弃这些修改吗？");
      if (!confirmed) return;
      replaceActiveLessonDrafts(cloneLessonEditorDrafts(lessonEditorSessionSnapshot.value));
      courseLessonPreferencesDirty.value = false;
    }
    lessonEditorSessionSnapshot.value = [];
    selectedCoursePreferredLessonKey.value = "";
    showLessonEditorSheet.value = false;
  }

function syncCoursePreferredPeriodIds() {
    const target = activeCoursePreferredLesson();
    if (target) {
      target.preferred_period_ids = Array.from(new Set(target.preferred_slots.map((slot) => slot.period_id)));
      return;
    }
    coursePlanForm.value.preferred_period_ids = Array.from(new Set(coursePlanForm.value.preferred_slots.map((slot) => slot.period_id)));
  }

function toggleCoursePreferredRuleWeek(index: number) {
    coursePreferredRuleForm.value.week_bits = toggleBit(
      coursePreferredRuleForm.value.week_bits,
      index,
      termWeekCount.value,
    );
  }

function expandCoursePreferredRuleSlotsForPeriods(
    rule: CoursePreferredRuleDraft,
    periods: Array<Record<string, unknown>>,
  ) {
    const activeWeeks = activeRoomUnavailableWeeks(rule.week_bits);
    const dayBits = normalizeCoursePlanningDayBits(rule.day_bits, periods, false);
    const selectedDays = dayBits
      .split("")
      .map((value, index) => (value === "1" ? index + 1 : null))
      .filter((value): value is number => value !== null);
    return periods
      .filter(
        (period) =>
          Number(period.period_index || 0) === Number(rule.period_index || 0) &&
          selectedDays.includes(Number(period.weekday || 0)),
      )
      .flatMap((period) =>
        activeWeeks.map((week) => ({ week, period_id: String(period.id || "") })).filter((slot) => slot.period_id),
      );
  }

function expandCoursePreferredRuleSlots(rule: CoursePreferredRuleDraft) {
    return expandCoursePreferredRuleSlotsForPeriods(rule, selectedTemplatePeriods.value);
  }

function syncCoursePreferredSlotsFromRules() {
    const next = new Map<string, CoursePreferredSlot>();
    const target = activeCoursePreferredLesson();
    const rules = target ? target.preferred_rules : coursePlanForm.value.preferred_rules;
    for (const rule of rules) {
      for (const slot of expandCoursePreferredRuleSlots(rule)) {
        next.set(timeSlotKey(slot.week, slot.period_id), slot);
      }
    }
    const slots = Array.from(next.values()).sort((left, right) => {
      return left.week - right.week || left.period_id.localeCompare(right.period_id);
    });
    if (target) {
      target.preferred_slots = slots;
      target.preferred_period_ids = Array.from(new Set(slots.map((slot) => slot.period_id)));
      courseLessonPreferencesDirty.value = true;
      return;
    }
    coursePlanForm.value.preferred_slots = slots;
    syncCoursePreferredPeriodIds();
  }

function coursePreferredPriorityOption(penalty: unknown) {
    const value = Number(penalty || 0);
    return (
      coursePreferredPriorityOptions.find((option) => option.penalty === value) ||
      coursePreferredPriorityOptions[coursePreferredPriorityOptions.length - 1]
    );
  }

function coursePreferredRuleDayIndexes(rule: CoursePreferredRuleDraft) {
    return normalizeCoursePlanningDayBits(rule.day_bits, selectedTemplatePeriods.value, false)
      .split("")
      .map((value, index) => (value === "1" ? index + 1 : null))
      .filter((value): value is number => value !== null);
  }

function splitCoursePreferredRuleToCells(rule: CoursePreferredRuleDraft): CoursePreferredRuleDraft[] {
    return coursePreferredRuleDayIndexes(rule).map((weekday) => ({
      ...rule,
      key: `${rule.key || coursePreferredRuleKey()}-d${weekday}`,
      day_bits: bitsFromNumbers([weekday], termDayCount.value),
         penalty: Number(rule.penalty || 0),
         forbidden: Boolean(rule.forbidden || Number(rule.penalty) < 0),
    }));
  }

function normalizeCoursePreferredCellRules(rules: CoursePreferredRuleDraft[]) {
    return mergeTimeRuleDrafts(
      rules.flatMap((rule) => splitCoursePreferredRuleToCells({
        ...rule,
        week_bits: normalizeBits(rule.week_bits, termWeekCount.value),
        day_bits: normalizeCoursePlanningDayBits(rule.day_bits, selectedTemplatePeriods.value, false),
         penalty: Number(rule.penalty || 0),
         forbidden: Boolean(rule.forbidden || Number(rule.penalty) < 0),
      })),
    );
  }

function activeCoursePreferredRuleList() {
    const target = activeCoursePreferredLesson();
    return target ? target.preferred_rules : coursePlanForm.value.preferred_rules;
  }

function setActiveCoursePreferredRules(rules: CoursePreferredRuleDraft[]) {
    const normalized = normalizeCoursePreferredCellRules(rules);
    const target = activeCoursePreferredLesson();
    if (target) {
      target.preferred_rules = normalized;
      courseLessonPreferencesDirty.value = true;
    } else {
      coursePlanForm.value.preferred_rules = normalized;
    }
    syncCoursePreferredSlotsFromRules();
  }

function cloneLessonEditorDrafts(lessons: CourseLessonDraft[]) {
    return lessons.map((lesson) => ({
      ...lesson,
      room_ids: [...lesson.room_ids],
      preferred_period_ids: [...lesson.preferred_period_ids],
      preferred_slots: lesson.preferred_slots.map((slot) => ({ ...slot })),
      preferred_rules: lesson.preferred_rules.map((rule) => ({ ...rule })),
    }));
  }

function lessonDraftComparable(lesson: CourseLessonDraft) {
    return {
      id: String(lesson.id || ""),
      label: lesson.label.trim(),
      duration_slots: Number(lesson.duration_slots || 0),
      enabled: lesson.enabled !== false,
      room_mode: lesson.room_mode,
      room_ids: [...lesson.room_ids].map(String).sort(),
      preferred_rules: lesson.preferred_rules
        .map((rule) => ({
          week_bits: normalizeBits(rule.week_bits, termWeekCount.value),
          day_bits: normalizeCoursePlanningDayBits(rule.day_bits, selectedTemplatePeriods.value, false),
          period_index: Number(rule.period_index || 0),
          penalty: Number(rule.penalty || 0),
        }))
        .sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right))),
    };
  }

function lessonDraftFieldChanges(before: CourseLessonDraft, after: CourseLessonDraft) {
    const fields: string[] = [];
    if (before.label.trim() !== after.label.trim()) fields.push("课次名称");
    if (Number(before.duration_slots || 0) !== Number(after.duration_slots || 0)) fields.push("时长");
    if (before.enabled !== after.enabled) fields.push("启用状态");
    if (
      before.room_mode !== after.room_mode
      || JSON.stringify([...before.room_ids].sort()) !== JSON.stringify([...after.room_ids].sort())
    ) fields.push("课次教室");
    if (
      JSON.stringify(lessonDraftComparable(before).preferred_rules)
      !== JSON.stringify(lessonDraftComparable(after).preferred_rules)
    ) fields.push("期望时间");
    return fields;
  }

const lessonEditorChanges = computed<LessonEditorChange[]>(() => {
    if (!showLessonEditorSheet.value || lessonEditorSessionMode.value !== planningViewMode.value) return [];
    const before = lessonEditorSessionSnapshot.value;
    const after = activeLessonDraftList();
    const beforeByKey = new Map(before.map((lesson) => [lesson.key, lesson]));
    const afterByKey = new Map(after.map((lesson) => [lesson.key, lesson]));
    const changes: LessonEditorChange[] = [];
    before.forEach((lesson, index) => {
      if (!afterByKey.has(lesson.key)) {
        changes.push({
          key: `delete-${lesson.key}`,
          tone: "delete",
          title: `删除第 ${index + 1} 课次`,
          detail: lesson.label || `第 ${index + 1} 课次`,
        });
      }
    });
    after.forEach((lesson, index) => {
      const previous = beforeByKey.get(lesson.key);
      if (!previous) {
        changes.push({
          key: `add-${lesson.key}`,
          tone: "add",
          title: lesson.draft_origin === "copy" ? `复制为第 ${index + 1} 课次` : `新增第 ${index + 1} 课次`,
          detail: lesson.label || `第 ${index + 1} 课次`,
        });
        return;
      }
      const fields = lessonDraftFieldChanges(previous, lesson);
      if (fields.length) {
        changes.push({
          key: `update-${lesson.key}`,
          tone: "update",
          title: `修改第 ${index + 1} 课次`,
          detail: fields.join("、"),
        });
      }
    });
    return changes;
  });

const lessonEditorHasChanges = computed(() => lessonEditorChanges.value.length > 0);

function normalizeActiveCoursePreferredRules() {
    setActiveCoursePreferredRules(activeCoursePreferredRuleList());
  }

function coursePreferredGridCellRule(weekday: unknown, periodIndex: unknown) {
    const dayBits = bitsFromNumbers([Number(weekday || 0)], termDayCount.value);
    const weekBits = normalizeBits(coursePreferredRuleForm.value.week_bits, termWeekCount.value);
    return activeCoursePreferredRuleList().find(
      (rule) =>
        normalizeBits(rule.week_bits, termWeekCount.value) === weekBits &&
        normalizeCoursePlanningDayBits(rule.day_bits, selectedTemplatePeriods.value, false) === dayBits &&
        Number(rule.period_index || 0) === Number(periodIndex || 0),
    );
  }

function toggleCoursePreferredGridCell(period: Record<string, unknown>) {
    const weekday = Number(period.weekday || 0);
    const periodIndex = Number(period.period_index || 0);
    if (!weekday || !periodIndex || isCoursePreferredPeriodDisabled(periodIndex, period)) {
      return;
    }
    const weekBits = normalizeBits(coursePreferredRuleForm.value.week_bits, termWeekCount.value);
    const dayBits = bitsFromNumbers([weekday], termDayCount.value);
    const selectedPenalty = Number(coursePreferredRuleForm.value.penalty || 0);
    const existing = coursePreferredGridCellRule(weekday, periodIndex);
    const rules = activeCoursePreferredRuleList().filter(
      (rule) =>
        !(
          normalizeBits(rule.week_bits, termWeekCount.value) === weekBits &&
          normalizeCoursePlanningDayBits(rule.day_bits, selectedTemplatePeriods.value, false) === dayBits &&
          Number(rule.period_index || 0) === periodIndex
        ),
    );
    if (existing && Number(existing.penalty || 0) === selectedPenalty) {
      setActiveCoursePreferredRules(rules);
      return;
    }
    setActiveCoursePreferredRules([
      ...rules,
      {
        key: coursePreferredRuleKey(),
        week_bits: weekBits,
        day_bits: dayBits,
        period_index: periodIndex,
        penalty: selectedPenalty,
      },
    ]);
  }

function toggleCoursePreferredGridRow(periodIndex: unknown) {
    const targetPeriodIndex = Number(periodIndex || 0);
    if (!targetPeriodIndex) return;
    const weekBits = normalizeBits(coursePreferredRuleForm.value.week_bits, termWeekCount.value);
    const selectedPenalty = Number(coursePreferredRuleForm.value.penalty || 0);
    const rowPeriods = coursePreferredPickerGrid.value
      .flatMap((day) => day.periods)
      .filter((period) =>
        Number(period.period_index || 0) === targetPeriodIndex &&
        !isCoursePreferredPeriodDisabled(targetPeriodIndex, period),
      );
    if (!rowPeriods.length) return;
    const selectedCells = new Set(
      rowPeriods
        .map((period) => coursePreferredGridCellRule(Number(period.weekday || 0), targetPeriodIndex))
        .filter(Boolean)
        .map((rule) => `${String(rule?.day_bits)}:${targetPeriodIndex}`),
    );
    const allSelected = selectedCells.size === rowPeriods.length;
    const rowCellKeys = new Set(
      rowPeriods.map((period) => `${bitsFromNumbers([Number(period.weekday || 0)], termDayCount.value)}:${targetPeriodIndex}`),
    );
    const nextRules = activeCoursePreferredRuleList().filter((rule) => {
      const dayIndex = coursePreferredRuleDayIndexes(rule)[0] || 0;
      return !(
        normalizeBits(rule.week_bits, termWeekCount.value) === weekBits &&
        rowCellKeys.has(`${bitsFromNumbers([dayIndex], termDayCount.value)}:${Number(rule.period_index || 0)}`)
      );
    });
    if (allSelected) {
      setActiveCoursePreferredRules(nextRules);
      return;
    }
    setActiveCoursePreferredRules([
      ...nextRules,
      ...rowPeriods.map((period) => ({
        key: coursePreferredRuleKey(),
        week_bits: weekBits,
        day_bits: bitsFromNumbers([Number(period.weekday || 0)], termDayCount.value),
        period_index: targetPeriodIndex,
        penalty: selectedPenalty,
      })),
    ]);
  }

function clearActiveCoursePreferredRules() {
    setActiveCoursePreferredRules([]);
  }

function clearCourseLessonPreferredTimes(lesson: CourseLessonDraft) {
    lesson.preferred_rules = [];
    lesson.preferred_slots = [];
    lesson.preferred_period_ids = [];
    courseLessonPreferencesDirty.value = true;
  }

function coursePreferredCandidatePresetOptions() {
    const options = coursePreferredPeriodOptions();
    const morning = options.filter((period) => period.start_minutes < 12 * 60);
    const afternoon = options.filter((period) => period.start_minutes >= 12 * 60);
    return [
      { key: "all", label: "全选", hint: `${options.length} 个节次`, periodIndexes: options.map((period) => period.period_index) },
      { key: "morning", label: "上午", hint: `${morning.length} 个节次`, periodIndexes: morning.map((period) => period.period_index) },
      { key: "afternoon", label: "下午", hint: `${afternoon.length} 个节次`, periodIndexes: afternoon.map((period) => period.period_index) },
    ].filter((preset) => preset.periodIndexes.length);
  }

function applyCoursePreferredCandidatePreset(periodIndexes: number[]) {
    const weekBits = normalizeBits(coursePreferredRuleForm.value.week_bits, termWeekCount.value);
    const selectedPenalty = Number(coursePreferredRuleForm.value.penalty || 0);
    const wantedPeriods = new Set(periodIndexes.map((index) => Number(index || 0)));
    const nextRules = [...activeCoursePreferredRuleList()];
    const ruleCellKey = (ruleWeekBits: string, weekday: number, periodIndex: number) =>
      `${ruleWeekBits}:${bitsFromNumbers([weekday], termDayCount.value)}:${periodIndex}`;
    const replacementKeys = new Set<string>();
    const additions: CoursePreferredRuleDraft[] = [];
  
    for (const day of coursePreferredPickerGrid.value) {
      for (const period of day.periods) {
        const periodIndex = Number(period.period_index || 0);
        const weekday = Number(period.weekday || 0);
        if (!wantedPeriods.has(periodIndex) || !weekday || isCoursePreferredPeriodDisabled(periodIndex, period)) {
          continue;
        }
        replacementKeys.add(ruleCellKey(weekBits, weekday, periodIndex));
        additions.push({
          key: coursePreferredRuleKey(),
          week_bits: weekBits,
          day_bits: bitsFromNumbers([weekday], termDayCount.value),
          period_index: periodIndex,
          penalty: selectedPenalty,
        });
      }
    }
  
    setActiveCoursePreferredRules([
      ...nextRules.filter((rule) => {
        const weekday = coursePreferredRuleDayIndexes(rule)[0] || 0;
        return !replacementKeys.has(ruleCellKey(
          normalizeBits(rule.week_bits, termWeekCount.value),
          weekday,
          Number(rule.period_index || 0),
        ));
      }),
      ...additions,
    ]);
  }

function prepareCoursePreferredPicker() {
    editingCoursePreferredRuleKey.value = "";
    setCoursePreferredBatchMode(false);
    const target = activeCoursePreferredLesson();
    if (target && !target.preferred_rules.length && target.preferred_slots.length) {
      target.preferred_rules = deriveCoursePreferredRulesFromSlots(target.preferred_slots);
    } else if (!target && !coursePlanForm.value.preferred_rules.length && coursePlanForm.value.preferred_slots.length) {
      coursePlanForm.value.preferred_rules = deriveCoursePreferredRulesFromSlots(coursePlanForm.value.preferred_slots);
    }
    normalizeActiveCoursePreferredRules();
    coursePreferredRuleSnapshot.value = activeCoursePreferredRuleList().map((rule) => ({ ...rule }));
    if (!activeCoursePreferredRuleList().length && !activeCoursePreferredLesson()?.preferred_slots.length) {
      const defaultDayBits = defaultCoursePlanningDayBits();
      const defaultRules = selectedTemplatePeriods.value
        .filter(period => !isCoursePreferredPeriodDisabled(Number(period.period_index), period))
        .map(period => ({
          key: coursePreferredRuleKey(),
          week_bits: "1".repeat(termWeekCount.value),
          day_bits: bitsFromNumbers([Number(period.weekday)], termDayCount.value),
          period_index: Number(period.period_index), penalty: 0, forbidden: false,
        }));
      setActiveCoursePreferredRules(defaultRules);
    }
    const existingRule = activeCoursePreferredRuleList()[0];
    const allOptions = coursePreferredPeriodOptions();
    const firstAvailable = allOptions.find(
      (period) => !isCoursePreferredPeriodDisabled(period.period_index),
    );
    coursePreferredRuleForm.value = {
      week_bits: existingRule?.week_bits || "1".repeat(termWeekCount.value),
      day_bits: defaultCoursePlanningDayBits(),
      period_index: firstAvailable?.period_index || allOptions[0]?.period_index || 1,
      penalty: existingRule?.penalty ?? 0,
      forbidden: Number(existingRule?.penalty) < 0 || Boolean(existingRule?.forbidden),
    };
    showCoursePreferredPicker.value = true;
  }

function openCoursePreferredPicker(lessonKey = "") {
    externalCoursePreferredDraft.value = null;
    coursePreferredPickerTitle.value = "";
    selectedCoursePreferredLessonKey.value = lessonKey;
    prepareCoursePreferredPicker();
  }

function saveCoursePreferredRule() {
    const weekBits = normalizeBits(coursePreferredRuleForm.value.week_bits, termWeekCount.value);
    setActiveCoursePreferredRules(activeCoursePreferredRuleList().map((rule) => ({
      ...rule,
      week_bits: weekBits,
    })));
    syncCoursePreferredSlotsFromRules();
    coursePreferredRuleSnapshot.value = [];
    editingCoursePreferredRuleKey.value = "";
    showCoursePreferredPicker.value = false;
    externalCoursePreferredDraft.value = null;
    coursePreferredPickerTitle.value = "";
  }

const editableCourseLessonDrafts = computed(() =>
    planningViewMode.value === "subject" ? subjectDefaultLessonDrafts.value : courseLessonDrafts.value,
  );

function currentCoursePlanningPeriods() {
    return coursePlanningPeriodsForHomeroom(coursePlanForm.value.homeroom_id);
  }

function normalizeCoursePlanningDayBits(
    bits: unknown,
    periods = currentCoursePlanningPeriods(),
    fallbackToEnabled = true,
  ) {
    const enabledDays = Array.from(new Set(
      periods.map((period) => Number(period.weekday || 0)).filter((weekday) => weekday >= 1 && weekday <= termDayCount.value),
    )).sort((left, right) => left - right);
    const normalized = normalizeBits(bits, termDayCount.value, "0");
    if (!enabledDays.length) {
      if (normalized.includes("1") || !fallbackToEnabled) return normalized;
      return bitsFromNumbers(
        Array.from({ length: Math.min(termDayCount.value, 5) }, (_, index) => index + 1),
        termDayCount.value,
      );
    }
    const enabledSet = new Set(enabledDays);
    const filtered = normalized
      .split("")
      .map((value, index) => value === "1" && enabledSet.has(index + 1) ? "1" : "0")
      .join("");
    return filtered.includes("1") || !fallbackToEnabled
      ? filtered
      : bitsFromNumbers(enabledDays, termDayCount.value);
  }

function defaultCoursePlanningDayBits(homeroomId: unknown = coursePlanForm.value.homeroom_id) {
    return normalizeCoursePlanningDayBits(
      "",
      coursePlanningPeriodsForHomeroom(homeroomId),
      true,
    );
  }

function durationText(value: unknown) {
    const minutes = unitsToMinutes(value);
    if (!minutes) {
      return "未设置";
    }
    return `${minutes} 分钟`;
  }

function minutesToClock(value: unknown) {
    const minutes = Number(value || 0);
    const hours = Math.floor(minutes / 60);
    const minute = minutes % 60;
    return `${String(hours).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  }

function clockToMinutes(value: string) {
    const [hours, minutes] = value.split(":").map((part) => Number(part || 0));
    return Math.min(Math.max(hours * 60 + minutes, 0), 1440);
  }

function periodTimeRange(period: Record<string, unknown> | PeriodDraft) {
    const start =
      "start_time" in period
        ? period.start_time
        : minutesToClock((period as Record<string, unknown>).start_time_minutes);
    const end =
      "end_time" in period
        ? period.end_time
        : minutesToClock((period as Record<string, unknown>).end_time_minutes);
    return `${start}-${end}`;
  }

function bitsFromNumbers(values: number[], length: number) {
    const set = new Set(values.filter((value) => value >= 1 && value <= length));
    return Array.from({ length }, (_, index) => (set.has(index + 1) ? "1" : "0")).join("");
  }

function selectedCoursePreferredSummary(lesson?: CourseLessonDraft) {
    const slots = lesson ? lesson.preferred_slots : coursePlanForm.value.preferred_slots;
    if (!slots.length) {
      return "默认全部可行时间";
    }
    const rules = coursePreferredRules(lesson);
    if (rules.length === 1) {
      return "已选择一个时间段";
    }
    return `已选择 ${rules.length} 个时间段`;
  }

function weekListLabel(weeks: number[]) {
    const uniqueWeeks = Array.from(new Set(weeks.filter((week) => week > 0))).sort((left, right) => left - right);
    if (!uniqueWeeks.length || uniqueWeeks.length === termWeekCount.value) {
      return "全学期";
    }
    const ranges: string[] = [];
    let start = uniqueWeeks[0];
    let previous = uniqueWeeks[0];
    for (const week of uniqueWeeks.slice(1)) {
      if (week === previous + 1) {
        previous = week;
        continue;
      }
      ranges.push(start === previous ? `${start}` : `${start}-${previous}`);
      start = week;
      previous = week;
    }
    ranges.push(start === previous ? `${start}` : `${start}-${previous}`);
    return `第${ranges.join("、")}周`;
  }

function compactWeekListLabel(weeks: number[]) {
    const uniqueWeeks = Array.from(new Set(weeks.filter((week) => week > 0))).sort((left, right) => left - right);
    if (!uniqueWeeks.length || uniqueWeeks.length === termWeekCount.value) {
      return "全学期";
    }
    if (uniqueWeeks.length <= 3) {
      return weekListLabel(uniqueWeeks);
    }
    return `${uniqueWeeks.length}周`;
  }

function deriveCoursePreferredRulesFromSlots(
    slots: CoursePreferredSlot[],
    fallbackWeekBits = coursePlanForm.value.week_bits,
  ): CoursePreferredRuleDraft[] {
    const records = new Map<string, { weeks: Set<number>; days: Set<number>; period_index: number; time_range: string }>();
    for (const slot of slots) {
      const period = selectedTemplatePeriods.value.find((item) => String(item.id) === String(slot.period_id || ""));
      if (!period) {
        continue;
      }
      const periodIndex = Number(period.period_index || 0);
      if (!periodIndex) {
        continue;
      }
      const timeRange = periodTimeRange(period);
      const key = `${periodIndex}:${timeRange}`;
      if (!records.has(key)) {
        records.set(key, {
          weeks: new Set<number>(),
          days: new Set<number>(),
          period_index: periodIndex,
          time_range: timeRange,
        });
      }
      const record = records.get(key)!;
      if (Number(slot.week || 0) > 0) {
        record.weeks.add(Number(slot.week));
      }
      record.days.add(Number(period.weekday || 1));
    }
    return Array.from(records.values()).map((record, index) => {
      const weeks = record.weeks.size ? Array.from(record.weeks) : activeRoomUnavailableWeeks(fallbackWeekBits);
      return {
        key: `course-derived-${record.period_index}-${index}`,
        week_bits: bitsFromNumbers(weeks, termWeekCount.value),
        day_bits: bitsFromNumbers(Array.from(record.days), termDayCount.value),
        period_index: record.period_index,
        penalty: 0,
      };
    }).sort((left, right) => left.period_index - right.period_index || left.key.localeCompare(right.key, "zh-Hans-CN"));
  }

function displayCoursePreferredRule(rule: CoursePreferredRuleDraft): CoursePreferredRule {
    const period = coursePreferredPeriodOptions().find((item) => item.period_index === rule.period_index);
    const weekBits = normalizeBits(rule.week_bits, termWeekCount.value);
    const dayBits = normalizeCoursePlanningDayBits(rule.day_bits, selectedTemplatePeriods.value, false);
    const weeks = activeRoomUnavailableWeeks(weekBits);
    const timeRange = period?.time_range || "";
    const timeText = `第${rule.period_index}节${timeRange ? ` ${timeRange}` : ""}`;
    const dayText = bitsToDayLabel(dayBits);
    const weekText = compactWeekListLabel(weeks);
    const priority = coursePreferredPriorityOption(rule.penalty);
    return {
      key: rule.key,
      week_bits: weekBits,
      day_bits: dayBits,
      period_index: rule.period_index,
      time_range: timeRange,
      timeText,
      dayText,
      weekText,
      label: `${weekListLabel(weeks)} · ${dayText} · ${timeText}`,
      compactLabel: `${timeText} · ${dayText} · ${weekText}`,
      penalty: Number(rule.penalty || 0),
      forbidden: Number(rule.penalty) < 0 || Boolean(rule.forbidden),
      priorityText: priority.label,
      priorityClass: priority.className,
    };
  }

function coursePreferredSlotsFromRules(rules: CoursePreferredRuleDraft[]) {
    const slots = new Map<string, CoursePreferredSlot>();
    for (const rule of rules) {
      for (const slot of expandCoursePreferredRuleSlots(rule)) {
        slots.set(timeSlotKey(slot.week, slot.period_id), slot);
      }
    }
    return Array.from(slots.values()).sort((left, right) => left.week - right.week || left.period_id.localeCompare(right.period_id));
  }

function coursePreferredRules(lesson?: CourseLessonDraft): CoursePreferredRule[] {
    const rulesSource = lesson ? lesson.preferred_rules : coursePlanForm.value.preferred_rules;
    const slots = lesson ? lesson.preferred_slots : coursePlanForm.value.preferred_slots;
    const rules =
      rulesSource.length > 0
        ? rulesSource
        : deriveCoursePreferredRulesFromSlots(slots);
    return rules
      .map(displayCoursePreferredRule)
      .filter((rule) => rule.week_bits.includes("1") && rule.day_bits.includes("1"))
      .sort((left, right) => left.period_index - right.period_index || left.label.localeCompare(right.label, "zh-Hans-CN"));
  }

const coursePreferredPickerGrid = computed(() => {
    const enabledDays = new Set(selectedTemplatePeriods.value.map((period) => Number(period.weekday || 0)));
    return weekdayOptions.filter((day) => enabledDays.has(day.index + 1)).map((day) => ({
      ...day,
      periods: selectedTemplatePeriods.value.filter((period) => Number(period.weekday || 0) === day.index + 1),
    }));
  });

const coursePreferredPickerRows = computed(() =>
    coursePreferredPeriodOptions().map((periodOption) => ({
      ...periodOption,
      cells: coursePreferredPickerGrid.value.map((day) => {
        const period = day.periods.find(
          (item) => Number(item.period_index || 0) === Number(periodOption.period_index || 0),
        );
        const rule = period ? coursePreferredGridCellRule(Number(period.weekday || 0), periodOption.period_index) : undefined;
        const priority = rule ? coursePreferredPriorityOption(rule.penalty) : undefined;
        return {
          day,
          period,
          rule,
          priority,
          time_range: period ? periodTimeRange(period) : "",
          show_time: periodOption.has_variable_times,
          disabled: !period || isCoursePreferredPeriodDisabled(periodOption.period_index, period),
        };
      }),
    })),
  );

function selectedCoursePreferredRuleCount() {
    return activeCoursePreferredRuleList().length;
  }

function coursePreferredCellButtonLabel(rule?: CoursePreferredRuleDraft) {
    return rule ? coursePreferredPriorityOption(rule.penalty).label : "可选";
  }

function coursePreferredPickerHint() {
    const count = selectedCoursePreferredRuleCount();
    const weekText = bitsToWeekLabel(coursePreferredRuleForm.value.week_bits);
    const priority = coursePreferredPriorityOption(coursePreferredRuleForm.value.penalty);
    if (!count) {
      return `不设置候选时间时，默认允许全学期所有可行上课时间。需要限制时，选择周频率并点击下方周课表格子。`;
    }
    return `已选择 ${count} 个候选时间，适用于${weekText}。本课次只能排入这些候选时间；继续点击格子可新增、取消或按「${priority.label}」调整优先级。`;
  }

function coursePreferredPickerSummary() {
    const count = selectedCoursePreferredRuleCount();
    return count ? `硬限制 · 已选 ${count} 个候选时间` : "默认全部可行时间";
  }

function activeLessonDraftList() {
    return planningViewMode.value === "subject" ? subjectDefaultLessonDrafts.value : courseLessonDrafts.value;
  }

function replaceActiveLessonDrafts(lessons: CourseLessonDraft[]) {
    if (planningViewMode.value === "subject") {
      subjectDefaultLessonDrafts.value = lessons;
      return;
    }
    courseLessonDrafts.value = lessons;
  }

function newCourseLessonDraft(index = activeLessonDraftList().length + 1): CourseLessonDraft {
    return {
      id: undefined,
      key: `lesson-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      label: `${recordName(selectedSubject.value || {}) || "课程"}`,
      duration_slots: selectedSubjectDurationSlots(),
      enabled: true,
      room_mode: "default",
      room_ids: [],
      preferred_period_ids: [],
      preferred_slots: [],
      preferred_rules: [],
      draft_origin: "new",
    };
  }

function ensureCourseLessons() {
    if (!activeLessonDraftList().length) {
      replaceActiveLessonDrafts([newCourseLessonDraft(1)]);
    }
  }

function addCourseLesson() {
    const lessons = activeLessonDraftList();
    replaceActiveLessonDrafts([...lessons, newCourseLessonDraft(lessons.length + 1)]);
  }

function copyCourseLesson(key: string) {
    const lessons = activeLessonDraftList();
    const source = lessons.find((lesson) => lesson.key === key);
    if (!source) return;
    const copy: CourseLessonDraft = {
      key: `lesson-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      label: source.label,
      duration_slots: source.duration_slots,
      enabled: source.enabled,
      room_mode: source.room_mode,
      room_ids: [...source.room_ids],
      preferred_period_ids: [...source.preferred_period_ids],
      preferred_slots: source.preferred_slots.map((s) => ({ ...s })),
      preferred_rules: source.preferred_rules.map((r) => ({ ...r })),
      draft_origin: "copy",
    };
    const index = lessons.findIndex((lesson) => lesson.key === key);
    replaceActiveLessonDrafts([
      ...lessons.slice(0, index + 1),
      copy,
      ...lessons.slice(index + 1),
    ]);
  }

function deleteCourseLesson(key: string) {
    const lessons = activeLessonDraftList();
    if (lessons.length <= 1) {
      error.value = "至少保留一个课次";
      return;
    }
    replaceActiveLessonDrafts(lessons.filter((lesson) => lesson.key !== key));
  }

function activeCoursePreferredLesson() {
    if (externalCoursePreferredDraft.value) return externalCoursePreferredDraft.value;
    return activeLessonDraftList().find((lesson) => lesson.key === selectedCoursePreferredLessonKey.value);
  }

const coursePreferredAllPeriodsDisabled = computed(() => {
    const options = coursePreferredPeriodOptions();
    return options.length > 0 && options.every((period) => isCoursePreferredPeriodDisabled(period.period_index));
  });

function roomOptionText(room: Record<string, unknown>) {
    return [
      recordName(room),
      room.room_type_name,
      room.type,
      room.capacity,
    ]
      .map((value) => String(value || "").toLowerCase())
      .join(" ");
  }

function filterRoomOptions(query: string, excludedIds: string[] = []) {
    const lowerQuery = query.trim().toLowerCase();
    const excluded = new Set(excludedIds.map(String));
    return schoolData.value.rooms.filter((room) => {
      const id = String(room.id || "");
      if (!id || excluded.has(id)) {
        return false;
      }
      return !lowerQuery || roomOptionText(room).includes(lowerQuery);
    });
  }

const selectedDefaultRooms = computed(() =>
    teachingTaskForm.value.room_ids
      .map((roomId) => schoolData.value.rooms.find((room) => String(room.id || "") === String(roomId)))
      .filter((room): room is Record<string, unknown> => Boolean(room)),
  );

const filteredDefaultRoomOptions = computed(() =>
    filterRoomOptions(defaultRoomSearch.value, teachingTaskForm.value.room_ids),
  );

function selectedLessonRooms(lesson: CourseLessonDraft) {
    return lesson.room_ids
      .map((roomId) => schoolData.value.rooms.find((room) => String(room.id || "") === String(roomId)))
      .filter((room): room is Record<string, unknown> => Boolean(room));
  }

function filteredLessonRoomOptions(lesson: CourseLessonDraft) {
    return filterRoomOptions(lessonRoomSearch.value[lesson.key] || "", lesson.room_ids);
  }

function lessonRoomSearchValue(lesson: CourseLessonDraft) {
    return lessonRoomSearch.value[lesson.key] || "";
  }

function setLessonRoomSearch(lesson: CourseLessonDraft, event: Event) {
    lessonRoomSearch.value = {
      ...lessonRoomSearch.value,
      [lesson.key]: (event.target as HTMLInputElement).value,
    };
    showLessonRoomOptions.value = {
      ...showLessonRoomOptions.value,
      [lesson.key]: true,
    };
  }

function hideDefaultRoomOptionsSoon() {
    window.setTimeout(() => {
      showDefaultRoomOptions.value = false;
    }, 120);
  }

function hideLessonRoomOptionsSoon(lesson: CourseLessonDraft) {
    window.setTimeout(() => {
      showLessonRoomOptions.value = {
        ...showLessonRoomOptions.value,
        [lesson.key]: false,
      };
    }, 120);
  }

function addDefaultRoom(room: Record<string, unknown>) {
    if (!teachingTaskForm.value.uses_rooms) {
      return;
    }
    const id = String(room.id || "");
    if (!id || teachingTaskForm.value.room_ids.includes(id)) {
      return;
    }
    teachingTaskForm.value.room_ids = [...teachingTaskForm.value.room_ids, id];
    teachingTaskForm.value.fixed_room_id = teachingTaskForm.value.room_ids[0] || "";
    defaultRoomSearch.value = "";
    showDefaultRoomOptions.value = false;
  }

function removeDefaultRoom(roomId: unknown) {
    const id = String(roomId || "");
    teachingTaskForm.value.room_ids = teachingTaskForm.value.room_ids.filter((item) => item !== id);
    teachingTaskForm.value.fixed_room_id = teachingTaskForm.value.room_ids[0] || "";
  }

function addLessonRoom(lesson: CourseLessonDraft, room: Record<string, unknown>) {
    if (!teachingTaskForm.value.uses_rooms) {
      return;
    }
    lesson.room_mode = "custom";
    const id = String(room.id || "");
    if (!id || lesson.room_ids.includes(id)) {
      return;
    }
    lesson.room_ids = [...lesson.room_ids, id];
    lessonRoomSearch.value = {
      ...lessonRoomSearch.value,
      [lesson.key]: "",
    };
    showLessonRoomOptions.value = {
      ...showLessonRoomOptions.value,
      [lesson.key]: false,
    };
  }

function removeLessonRoom(lesson: CourseLessonDraft, roomId: unknown) {
    const id = String(roomId || "");
    lesson.room_ids = lesson.room_ids.filter((item) => item !== id);
  }

function setUsesRooms(value: boolean) {
    teachingTaskForm.value.uses_rooms = value;
    if (value) {
      return;
    }
    teachingTaskForm.value.fixed_room_id = "";
    teachingTaskForm.value.room_ids = [];
    defaultRoomSearch.value = "";
    showDefaultRoomOptions.value = false;
    for (const lesson of courseLessonDrafts.value) {
      lesson.room_ids = [];
    }
    lessonRoomSearch.value = {};
    showLessonRoomOptions.value = {};
  }

function setLessonRoomMode(lesson: CourseLessonDraft, mode: "default" | "custom") {
    lesson.room_mode = mode;
    if (mode === "default") {
      lesson.room_ids = [];
    }
  }

function defaultRoomSelectionSummary() {
    if (!teachingTaskForm.value.uses_rooms) {
      return "不使用教室";
    }
    return teachingTaskForm.value.room_ids.length
      ? `已选择 ${teachingTaskForm.value.room_ids.length} 间教室`
      : "默认无教室";
  }

function lessonRoomSelectionSummary(lesson: CourseLessonDraft) {
    if (!teachingTaskForm.value.uses_rooms) {
      return "不使用教室";
    }
    if (lesson.room_mode === "custom") {
      return lesson.room_ids.length ? `已选择 ${lesson.room_ids.length} 间教室` : "自定义：未选择教室";
    }
    return teachingTaskForm.value.room_ids.length ? `继承 ${teachingTaskForm.value.room_ids.length} 间默认教室` : "默认无教室";
  }

function hasRecordId(records: Array<Record<string, unknown>>, id: unknown) {
    const value = String(id || "");
    return Boolean(value) && records.some((record) => String(record.id || "") === value);
  }

function recordNameById(records: Array<Record<string, unknown>>, id: unknown, fallback = "") {
    const record = records.find((item) => String(item.id || "") === String(id || ""));
    return record ? recordName(record, fallback) : fallback;
  }

function taskHomeroomName(task: Record<string, unknown>) {
    return String(task.homeroom_name || recordNameById(schoolData.value.homerooms, task.homeroom_id, "未选择班级"));
  }

function taskSubjectName(task: Record<string, unknown>) {
    return String(task.subject_name || recordNameById(schoolData.value.subjects, task.subject_id, "未选择科目"));
  }

function taskTeacherName(task: Record<string, unknown>) {
    return String(task.teacher_name || recordNameById(schoolData.value.teachers, task.primary_teacher_id, ""));
  }

const selectedTeacherName = computed(() => {
    const teacher = schoolData.value.teachers.find((item) => String(item.id || "") === teachingTaskForm.value.primary_teacher_id);
    return teacher ? recordName(teacher) : "";
  });

const filteredTeacherOptions = computed(() => {
    const query = teacherSearch.value.trim().toLowerCase();
    const rows = schoolData.value.teachers;
    if (!query) {
      return rows;
    }
    return rows.filter((teacher) => {
      return [teacher.name, teacher.department]
        .map((value) => String(value || "").toLowerCase())
        .some((value) => value.includes(query));
    });
  });

function syncTeacherSearchFromSelection() {
    teacherSearch.value = selectedTeacherName.value;
  }

function onTeacherSearchInput() {
    showTeacherOptions.value = true;
    if (!teacherSearch.value.trim()) {
      teachingTaskForm.value.primary_teacher_id = "";
    }
  }

function selectTeacherOption(teacher: Record<string, unknown>) {
    teachingTaskForm.value.primary_teacher_id = String(teacher.id || "");
    teacherSearch.value = recordName(teacher);
    showTeacherOptions.value = false;
  }

function clearTeacherSelection() {
    teachingTaskForm.value.primary_teacher_id = "";
    teacherSearch.value = "";
    showTeacherOptions.value = true;
  }

function hideTeacherOptionsSoon() {
    window.setTimeout(() => {
      showTeacherOptions.value = false;
    }, 120);
  }

function resolveTeacherIdForSave() {
    const currentId = String(teachingTaskForm.value.primary_teacher_id || "");
    if (hasRecordId(schoolData.value.teachers, currentId)) {
      return currentId;
    }
    const query = teacherSearch.value.trim();
    if (!query) {
      return "";
    }
    const matched = schoolData.value.teachers.filter((teacher) => recordName(teacher).trim() === query);
    if (matched.length === 1) {
      return String(matched[0].id || "");
    }
    return null;
  }

function defaultDayBits() {
    return bitsFromNumbers(enabledDayNumbers(), termDayCount.value);
  }

function normalizeBits(bits: unknown, length: number, fallback = "1") {
    const raw = String(bits || "");
    const normalized = Array.from({ length }, (_, index) => (raw[index] === "1" ? "1" : "0")).join("");
    return normalized.includes("1") ? normalized : fallback.repeat(length);
  }

function toggleBit(bits: string, index: number, length: number) {
    const chars = normalizeBits(bits, length).split("");
    chars[index] = chars[index] === "1" ? "0" : "1";
    if (!chars.includes("1")) {
      chars[index] = "1";
    }
    return chars.join("");
  }

function enabledDayNumbers() {
    return normalizeEnabledWeekdays(enabledWeekdays.value).filter((day) => day <= termDayCount.value);
  }

function sanitizeDayBitsForEnabledWeekdays(bits: unknown, fallbackToEnabled = true) {
    const enabledDays = enabledDayNumbers();
    const enabledSet = new Set(enabledDays);
    const normalized = normalizeBits(bits, termDayCount.value, "0")
      .split("")
      .map((value, index) => (value === "1" && enabledSet.has(index + 1) ? "1" : "0"))
      .join("");
    if (!normalized.includes("1") && fallbackToEnabled) {
      return bitsFromNumbers(enabledDays, termDayCount.value);
    }
    return normalized;
  }

function bitsToWeekLabel(bits: unknown) {
    const active = String(bits || "")
      .split("")
      .map((value, index) => (value === "1" ? index + 1 : null))
      .filter((value): value is number => value !== null);
    if (!active.length) {
      return "未选择周";
    }
    if (active.length === termWeekCount.value) {
      return "全学期";
    }
    return active.length <= 5 ? `第 ${active.join("、")} 周` : `已选 ${active.length} 周`;
  }

function bitsToDayLabel(bits: unknown) {
    const active = sanitizeDayBitsForEnabledWeekdays(bits, false)
      .split("")
      .slice(0, termDayCount.value)
      .map((value, index) => (value === "1" ? weekdayOptions[index]?.label : null))
      .filter((value): value is string => Boolean(value));
    if (!active.length) {
      return "未选择日";
    }
    return active.join("、");
  }

function taskImportLabel(task: Record<string, unknown>) {
    return `${taskHomeroomName(task)} · ${taskSubjectName(task)} · ${taskTeacherName(task) || "未指定教师"} · ${taskLessonCount(task.id)} 课次`;
  }

function recordName(record: Record<string, unknown>, fallback = "-") {
    return String(record.name || record.homeroom_name || record.subject_name || fallback);
  }
return {showGuide,activeGuideStepIndex,guideTargetRect,guideMissingTarget,teachingTaskForm,courseLessonDrafts,defaultRoomSearch,showDefaultRoomOptions,showLessonRoomOptions,loading,courseArrangementSaving,courseArrangementNotice,selectedTeachingTaskId,planningViewMode,selectedLessonImportTaskId,teacherSearch,teacherSearchInput,showTeacherOptions,showCoursePreferredPicker,coursePreferredPickerTitle,showLessonEditorSheet,courseWeekFrequencyCollapsed,coursePreferredRuleForm,coursePreferredPriorityOptions,termWeekOptions,activeGuideSteps,activeGuideStep,guideProgressLabel,guideHighlightStyle,guideCardStyle,startGuide,nextGuideStep,previousGuideStep,restartGuide,skipGuide,weekFrequencyPresets,applyCoursePreferredWeekPreset,closeCoursePreferredPicker,openLessonEditorSheet,closeLessonEditorSheet,toggleCoursePreferredRuleWeek,lessonEditorChanges,lessonEditorHasChanges,toggleCoursePreferredGridCell,toggleCoursePreferredGridRow,clearActiveCoursePreferredRules,clearCourseLessonPreferredTimes,coursePreferredCandidatePresetOptions,applyCoursePreferredCandidatePreset,openCoursePreferredPicker,saveCoursePreferredRule,selectedCourseNotScheduled,selectedSubject,editableCourseLessonDrafts,selectedPlanningHomeroom,selectedCoursePlanTasks,lessonImportTaskOptions,unitsToMinutes,durationText,selectedCoursePreferredSummary,coursePreferredPickerGrid,coursePreferredPickerRows,selectedCoursePreferredRuleCount,coursePreferredCellButtonLabel,coursePreferredPickerHint,coursePreferredPickerSummary,selectedSubjectDurationSlots,addCourseLesson,copyCourseLesson,deleteCourseLesson,activeCoursePreferredLesson,coursePreferredAllPeriodsDisabled,selectedDefaultRooms,filteredDefaultRoomOptions,selectedLessonRooms,filteredLessonRoomOptions,lessonRoomSearchValue,setLessonRoomSearch,hideDefaultRoomOptionsSoon,hideLessonRoomOptionsSoon,addDefaultRoom,removeDefaultRoom,addLessonRoom,removeLessonRoom,setUsesRooms,setLessonRoomMode,defaultRoomSelectionSummary,lessonRoomSelectionSummary,taskTeacherName,filteredTeacherOptions,syncTeacherSearchFromSelection,onTeacherSearchInput,selectTeacherOption,clearTeacherSelection,hideTeacherOptionsSoon,bitsToWeekLabel,taskImportLabel,isTeachingTaskActive,selectTeachingTask,startNewTeachingTask,importLessonSettingsFromSelectedTask,taskLessonCount,markSelectedCourseNotScheduled,resumeSelectedCourseScheduling,saveCourseArrangement,deleteCourseArrangement,recordName,subjectEditorOpen,subjectEditorPanel,courseCandidateScale,markCourseCandidateScaleAdjusted,closeSubjectEditor,handleSubjectEditorKeydown,error};
}
