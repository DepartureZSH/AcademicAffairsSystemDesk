import { computed, onMounted, ref, watch } from 'vue';
import { Channel, invoke } from '@tauri-apps/api/core';
import { aiAvailable, aiConnection } from '../lib/ai';
import { localApi, sidecarRequest, formatLocalError, type EntityRecord } from '../lib/sidecar';
import { save } from '@tauri-apps/plugin-dialog';
import { renderMarkdown } from './utils/markdown';
import * as actionPresentation from './utils/actionPresentation';
import { distributionLabel } from './utils/itcConstraints';

type Message = { id:string; role:'user'|'assistant'; content:string; pending?:boolean; error?:boolean; attachments?:Attachment[] };
type Attachment = { id:string; filename:string; text:string; localParsed?:boolean };
type Scene = 'timetable'|'rooms'|'school'|'planning'|'constraints';
const sceneOptions = [ {key:'timetable',label:'课表设置'}, {key:'rooms',label:'教室设置'}, {key:'school',label:'学校数据'}, {key:'planning',label:'课程计划'}, {key:'constraints',label:'约束配置'} ] as const;
const blankSchool = () => ({ teachers:[] as EntityRecord[], homerooms:[] as EntityRecord[], subjects:[] as EntityRecord[], rooms:[] as EntityRecord[], room_types:[] as EntityRecord[], weekly_timetable_templates:[] as EntityRecord[], weekly_timetable_periods:[] as EntityRecord[], default_weekly_timetable_template:null as EntityRecord|null });
export function useDesktopAgent(props: {projectId:string; projectName:string}, navigate:(section:string)=>void) {
  const activeAgentScene = ref<Scene>('planning');
  const activeSection = ref('agent');
  const projectId = computed(()=>props.projectId);
  const currentProjectName = computed(()=>props.projectName);
  const hasProject = computed(()=>!!props.projectId);
  const hasOrganization = hasProject; // Upstream concept maps to an opened local project.
  const organizationId = ref('local'), currentUserId = ref('local');
  // Page browsing is not a paid web entitlement; network calls enforce BYOK separately.
  const entitlement = ref({account_status:'member',membership_active:true,ai_enabled:true});
  const connection = ref({baseUrl:'',model:'',hasApiKey:false});
  const agentMessages = ref<Message[]>([]), agentAttachmentDrafts = ref<Attachment[]>([]);
  const agentInput = ref(''), agentError = ref('');
  const agentSessionLoading = ref(false), agentStreaming = ref(false), agentUploading = ref(false), loading=ref(false);
  const agentActions = ref<Record<string,any>[]>([]);
  const selectedAgentAction = ref<Record<string,any>|null>(null);
  const schoolData=ref(blankSchool());
  const planningData=ref({course_plans:[] as EntityRecord[],teaching_tasks:[] as EntityRecord[],task_lessons:[] as EntityRecord[]});
  const termWeekCount=ref(20), timetableTemplateSaveRevision=ref(0), showCoursePreferredPicker=ref(false);
  const expectedPickerContext=ref<Record<string,any>|null>(null);
  const aiTimetableDraft=ref<{result:any;options:any;targetId:string}|null>(null);
  const expansionRevisions=new Map<string,number>();
  function applyAiTimetableDraft(result:any, options:any, targetId='') {
    aiTimetableDraft.value={result,options:{...options},targetId};
  }
  const localSchoolRows=ref<any[]>([]);
  function parseConfig(value:any){try{return typeof value==='string'?JSON.parse(value):value||{};}catch{return {};}}
  const currentAgentConversationId=computed(()=>`${props.projectId}:${activeAgentScene.value}`);
  let generation=0;
  async function loadAgentProjectSession() {
    const scene=activeAgentScene.value, ticket=generation;
    if(!hasProject.value)return;
    agentSessionLoading.value=true;
    try {
      const pid=await actualProjectId();
      const session=await sidecarRequest<{messages:Message[];actions:Record<string,any>[]}>({method:'GET',path:`/v1/ai/session?project_id=${encodeURIComponent(pid)}&scene=${scene}`});
      if(ticket!==generation || scene!==activeAgentScene.value)return;
      agentMessages.value=session.messages;agentActions.value=session.actions;
    } catch(e) { agentError.value=formatLocalError(e); }
    finally {agentSessionLoading.value=false;}
    agentAttachmentDrafts.value=[]; agentInput.value='';
  }
  async function actualProjectId(){
    if(props.projectId!=='browser-preview')return props.projectId;
    const result=await sidecarRequest<{project:{id:string}}>({method:'GET',path:'/v1/projects/current'});
    return result.project.id;
  }
  async function selectAgentScene(scene:Scene) { if(agentStreaming.value)return; activeAgentScene.value=scene;selectedAgentAction.value=null;agentActions.value=[]; await loadAgentProjectSession(); }
  watch(projectId,()=>{generation++;aiTimetableDraft.value=null;expansionRevisions.clear();showCoursePreferredPicker.value=false;expectedPickerContext.value=null;agentMessages.value=[];agentActions.value=[];selectedAgentAction.value=null;void loadOverview().then(loadAgentProjectSession);});
  async function loadOverview() {
    if(!hasProject.value)return;
    const ticket=++generation;
    try {
      const types=['teacher','homeroom','subject','room','room_type','bell_schedule','time_slot','course_plan','teaching_task','task_lesson','term','timetable_template_assignment'];
      const rows=await Promise.all(types.map(type=>localApi.listEntities(type)));
      const settings=await sidecarRequest<any>({method:'GET',path:'/v1/timetable/settings'});
      if(ticket!==generation)return;
      localSchoolRows.value=rows;
      schoolData.value={...blankSchool(),...settings.schoolData};
      planningData.value={course_plans:rows[7].items,teaching_tasks:rows[8].items,task_lessons:rows[9].items.map(p=>({...p,lesson_index:Number(p.lesson_index)+1,time_preferences:parseConfig(p.planning_config).preferred_times||[]}))};
      termWeekCount.value=Number(rows[10].items[0]?.week_count || 20);
    }catch{ agentError.value='本地项目资料暂时无法读取，请检查本地服务。'; }
  }
  async function refreshConnection(){if(aiAvailable())connection.value=await aiConnection.status();}
  async function submitAgentDraft() {
    if(agentStreaming.value)return;
    if(!aiAvailable())throw new Error('浏览器仅预览页面，请在桌面应用中配置 AI 服务并发送。');
    await refreshConnection();
    if(!connection.value.hasApiKey)throw new Error('请先到 AI 设置填写 API 地址、密钥和模型。');
    const files=agentAttachmentDrafts.value.map(file=>({...file}));
    const text=agentInput.value.trim();
    if(!text && !files.length)return;
    if(!window.confirm(`将向 ${connection.value.baseUrl}\n模型：${connection.value.model}\n发送当前场景的历史对话、此前附件及本次消息${files.length ? '和新附件：'+files.map(f=>f.filename).join('、') : ''}。AI 可按需查询并发送本场景涉及的学校资料、课表、课程计划及约束。可能产生 API 费用。所有修改先展示审核，确认后才写入本地项目。\n是否继续？`))return;
    const ticket=generation;
    const user:Message={id:crypto.randomUUID(),role:'user',content:text,attachments:files};
    const history=[...agentMessages.value.filter(m=>!m.error&&!m.pending),user];
    const messages=history.map(m=>({role:m.role,content:m.content+(m.attachments?.map(f=>`\n\n附件 ${f.filename}（用户资料）：\n${f.text}`).join('')||'')}));
    if(new TextEncoder().encode(JSON.stringify(messages)).length>250000){agentError.value='对话与附件过大，请减少附件或清空对话。';return;}
    agentStreaming.value=true;agentError.value='';
    agentMessages.value.push(user,{id:crypto.randomUUID(),role:'assistant',content:'',pending:true});
    const pending=agentMessages.value[agentMessages.value.length-1];
    agentInput.value='';agentAttachmentDrafts.value=[];
    try {
      const pid=await actualProjectId(), scene=activeAgentScene.value;
      const target={expectedBaseUrl:connection.value.baseUrl,expectedModel:connection.value.model,confirmed:true};
      let response=await sidecarRequest<any>({method:'POST',path:'/v1/ai/turns',body:{project_id:pid,scene,content:text||'请读取附件，帮助我整理待审核的导入变更',attachment_ids:files.map(f=>f.id)}});
      for(let round=0;!response.done;round++){
        if(round>=13)throw new Error('本轮工具调用达到上限，请缩小操作范围。');
        if(ticket!==generation)throw new Error('项目已切换，本轮停止。');
        pending.content=`正在核对项目资料与整理变更（第 ${round+1} 轮）…`;
        let partial='';
        const onProgress=new Channel<string>();
        onProgress.onmessage=(text)=>{if(ticket===generation){partial+=text;pending.content=partial;}};
        const message=await invoke<any>('ai_stream_complete',{...response.providerRequest,...target,onProgress});
        if(ticket!==generation)throw new Error('项目已切换，本轮停止。');
        response=await sidecarRequest<any>({method:'POST',path:`/v1/ai/turns/${response.turnId}/step`,body:{project_id:pid,step:response.step,message}});
      }
      if(ticket===generation){agentMessages.value=response.messages;agentActions.value=response.actions;}
    }catch(e){if(ticket===generation){pending.pending=false;pending.error=true;pending.content='请求未完成，请检查连接后重试。';agentError.value=typeof e==='string'?e:'发送失败';}}
    finally{agentStreaming.value=false;}
  }
  async function uploadAgentAttachments(event:Event) {
    const input=event.target as HTMLInputElement;
    const files=Array.from(input.files||[]);input.value='';agentUploading.value=true;agentError.value='';
    try {
      if(files.length+agentAttachmentDrafts.value.length>5)throw new Error('每次最多添加 5 个附件。');
      for(const file of files){
        if(file.size>2*1024*1024)throw new Error('单个附件请控制在 2 MB 以内。');
        const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
        for(let offset=0;offset<bytes.length;offset+=8192)binary+=String.fromCharCode(...bytes.subarray(offset,offset+8192));
        const attachment=await sidecarRequest<Attachment>({method:'POST',path:'/v1/ai/attachments',body:{project_id:await actualProjectId(),scene:activeAgentScene.value,filename:file.name,file:btoa(binary)}});
        agentAttachmentDrafts.value.push(attachment);
      }
    }catch(e){agentError.value=e instanceof Error?e.message:'附件读取失败';}finally{agentUploading.value=false;}
  }
  async function clearCurrentAgentConversation(){
    if(agentStreaming.value || !window.confirm('清空本场景的对话和 AI 记忆？变更审核记录仍保留。'))return false;
    try {await sidecarRequest({method:'POST',path:'/v1/ai/clear',body:{project_id:await actualProjectId(),scene:activeAgentScene.value}});agentMessages.value=[];return true;}
    catch(e){agentError.value=formatLocalError(e);return false;}
  }
  async function specialist(flow:string,payload:any):Promise<any>{
    const ticket=generation, project_id=await actualProjectId();
    let state=await sidecarRequest<any>({method:'POST',path:'/v1/ai/workflows',body:{project_id,flow,payload}});
    if(state.done)return state.result;
    if(!aiAvailable())throw new Error('请在桌面应用中配置 AI 服务后使用识别功能。浏览器预览不会发送资料。');
    await refreshConnection();
    if(!connection.value.hasApiKey)throw new Error('请先在 AI 设置中保存服务地址、模型和密钥');
    const target={expectedBaseUrl:connection.value.baseUrl,expectedModel:connection.value.model,confirmed:true};
    if(!window.confirm(`将向 ${target.expectedBaseUrl}\n模型：${target.expectedModel}\n发送本次填写的描述、附件内容及完成此专项所需的项目资料。识别不会自动保存修改，可能产生费用。是否继续？`))throw new Error('已取消识别，未修改项目');
    for(let i=0;i<7;i++){
      if(ticket!==generation)throw new Error('项目已变化，请重新预览');
      const response=await invoke<any>('ai_specialist_complete',{...state.providerRequest,...target});
      if(ticket!==generation)throw new Error('项目已变化，请重新预览');
      state=await sidecarRequest<any>({method:'POST',path:`/v1/ai/workflows/${state.turnId}`,body:{project_id,step:state.step,response}});
      if(state.done)return state.result;
    }
    throw new Error('识别重试次数已达上限，请缩小范围');
  }
  async function request(path:string,options?:{body?:FormData|unknown;method?:string}):Promise<any>{
    if(path.endsWith('/planning/ai/expected-policy')){
      const body=typeof options?.body==='string'?JSON.parse(options.body):options?.body;
      const result=await specialist('planning/expected-policy',body);
      if(!window.confirm(`补充要求解释为：${result.interpretation}\n是否按此策略继续？`))throw new Error('已取消，未修改项目');
      return result;
    }
    if(path.includes('/timetable/ai/') || path.includes('/constraints/')){
      const body:any=options?.body;
      let payload:any=typeof body==='string'?JSON.parse(body):body||{};
      if(body instanceof FormData){
        payload={};
        for(const [key,value] of body.entries()){
          if(value instanceof File){
            if(value.size>5*1024*1024)throw new Error('文件不能超过5 MB');
            const bytes=new Uint8Array(await value.arrayBuffer());let binary='';
            for(let offset=0;offset<bytes.length;offset+=8192)binary+=String.fromCharCode(...bytes.subarray(offset,offset+8192));
            payload.file=btoa(binary);payload.filename=value.name;
          }else payload[key]=['options','zoning'].includes(key)?JSON.parse(value):value;
        }
      }
      let flow=path.includes('/timetable/ai/')?'timetable/'+path.split('/timetable/ai/')[1]:'constraints/'+path.split('/constraints/')[1];
      if(flow.startsWith('constraints/ai/')&&!flow.includes('/expansion/'))flow=flow.replace('constraints/ai/','constraints/');
      if(flow==='constraints/resolve')flow='constraints/resolve-scope';
      const download=flow.match(/^constraints\/workbooks\/(blank|parallel|consecutive|spread)$/);
      if(download){const result=await specialist('constraints/workbooks/download',{id:download[1]});return new Blob([Uint8Array.from(atob(result.data),c=>c.charCodeAt(0))],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});}
      const sourceKey=JSON.stringify(payload.source);
      if(flow.endsWith('/expansion/commit'))payload.base_revision=expansionRevisions.get(sourceKey);
      const result=await specialist(flow,payload);
      if(flow.endsWith('/expansion/preview'))expansionRevisions.set(sourceKey,result.base_revision);
      if(result.actionId){
        if(!window.confirm(`确认创建 ${result.created_count} 条约束？重复的 ${result.skipped_count} 条将跳过。保存前会自动备份。`))throw new Error('已取消，未保存约束');
        await sidecarRequest({method:'POST',path:`/v1/ai/actions/${result.actionId}/confirm`,body:{project_id:await actualProjectId()}});
      }
      return result;
    }
    if(path.endsWith('/lesson-expected-times')){
      const project_id=await actualProjectId();
      if(options?.method==='PATCH'){
        const body=typeof options.body==='string'?JSON.parse(options.body):options.body;
        if(!window.confirm(`确认修改 ${body.items.length} 个课次的期望时间？系统会先备份，再整批保存。`))throw new Error('已取消，未修改项目');
        const result=await sidecarRequest({method:'POST',path:'/v1/ai/expected-times',body:{project_id,items:body.items}});
        void loadAgentProjectSession();return result;
      }
      return sidecarRequest({method:'GET',path:`/v1/ai/expected-times?project_id=${encodeURIComponent(project_id)}`});
    }
    if(path.endsWith('/planning/ai/search-lessons')){
      const body=typeof options?.body==='string'?JSON.parse(options.body):options?.body;
      if(aiAvailable()){
        await refreshConnection();
        if(connection.value.hasApiKey){
          const ticket=generation,project_id=await actualProjectId();
          const target={expectedBaseUrl:connection.value.baseUrl,expectedModel:connection.value.model,confirmed:true};
          if(!window.confirm(`将向 ${target.expectedBaseUrl}\n模型：${target.expectedModel}\n发送筛选描述及当前项目的班级、科目、任课教师和课次摘要。只搜索，不修改项目；可能产生费用。是否继续？`))throw new Error('已取消 AI 搜索');
          const prepared=await sidecarRequest<any>({method:'POST',path:'/v1/ai/scope-search',body:{project_id,text:body.scope_text}});
          const message=await invoke<any>('ai_complete',{...prepared.providerRequest,...target});
          if(ticket!==generation)throw new Error('项目资料已变化，请重新搜索');
          return sidecarRequest({method:'POST',path:`/v1/ai/scope-search/${prepared.searchId}`,body:{project_id,message}});
        }
      }
      const words=String(body.scope_text||'').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      const rows=planningData.value.task_lessons.map(lesson=>{
        const task=planningData.value.teaching_tasks.find(t=>t.id===lesson.teaching_task_id);
        const name=(list:EntityRecord[],id:unknown)=>list.find(row=>row.id===id)?.name||'';
        return {...lesson,label:lesson.label,ordinal:lesson.lesson_index,subject_name:name(schoolData.value.subjects,task?.subject_id),homeroom_name:name(schoolData.value.homerooms,task?.homeroom_id),teacher_name:name(schoolData.value.teachers,task?.primary_teacher_id),time_preferences_count:(lesson.time_preferences as any[])?.length||0};
      }).filter(row=>words.every(word=>[row.label,row.subject_name,row.homeroom_name,row.teacher_name].join(' ').toLocaleLowerCase().includes(word)));
      return {rows,interpretation:'按本地关键词匹配；未调用 AI，请核对并勾选目标课次。'};
    }
    throw new Error('无法识别该操作，请刷新页面后重试；未修改项目。');
  }
  function coursePlanningPeriodsForHomeroom(id:unknown){
    const rows=localSchoolRows.value;
    if(!rows.length)return [];
    const assignment=rows[11].items.find((a:any)=>a.entity_type==='homeroom'&&a.entity_id===id)||rows[11].items.find((a:any)=>a.entity_type==='all');
    const schedule=rows[5].items.find((s:any)=>s.id===assignment?.bell_schedule_id)||rows[5].items.find((s:any)=>s.is_default);
    if(!schedule)return [];
    const days=parseConfig(schedule.display_config).enabled_weekdays;
    return schoolData.value.weekly_timetable_periods.filter(p=>p.template_id===schedule.id&&p.active&&(!Array.isArray(days)||days.includes(Number(p.weekday))));
  }
  function openCoursePreferredPickerForDraft(draft:any){
    const rows=localSchoolRows.value,term=rows[10]?.items.find((t:any)=>t.active);
    if(!term||!rows[1]?.items.length||!rows[2]?.items.length)throw new Error('请先配置学期、班级和科目');
    expectedPickerContext.value={pickerDraft:draft,term,homeroom:rows[1].items[0],subject:rows[2].items[0],taskId:'',slots:rows[6].items,allSlots:rows[6].items,schedules:rows[5].items,assignments:rows[11].items,revision:rows[0].revision};
    showCoursePreferredPicker.value=true;
  }
  async function downloadOfficialWorkbook(scene:string,template_id='blank'){
    const result=await sidecarRequest<{data:string;filename:string}>({method:'POST',path:'/v1/ai/workbook',body:{scene,template_id}});
    if(aiAvailable()){
      const destination=await save({defaultPath:result.filename,filters:[{name:'Excel 工作簿',extensions:['xlsx']}]});
      if(destination)await sidecarRequest({method:'POST',path:'/v1/ai/workbook',body:{scene,template_id,destination}});
    }else{
      const bytes=Uint8Array.from(atob(result.data),c=>c.charCodeAt(0));
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
      const link=document.createElement('a');link.href=url;link.download=result.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
  }
  const selectedAgentActionItems=ref<any[]>([]),selectedAgentActionContextItems=ref<any[]>([]),selectedAgentActionItemTotal=ref(0);
  const agentActionItemQuery=ref(''),agentActionItemTarget=ref(''),agentActionItemOperation=ref('');
  function loadSelectedAgentActionItems(){
    const all=selectedAgentAction.value?.items||[];
    selectedAgentActionContextItems.value=all;
    selectedAgentActionItems.value=all.filter((item:any)=>(!agentActionItemTarget.value||item.target===agentActionItemTarget.value)&&(!agentActionItemOperation.value||item.operation===agentActionItemOperation.value)&&(!agentActionItemQuery.value||JSON.stringify(item).includes(agentActionItemQuery.value)));
    selectedAgentActionItemTotal.value=selectedAgentActionItems.value.length;
  }
  function openAgentActionDetail(action:any){selectedAgentAction.value=action;agentActionItemQuery.value='';agentActionItemTarget.value='';agentActionItemOperation.value='';loadSelectedAgentActionItems();}
  async function handleAction(id:string,operation:'confirm'|'reject'){
    if(loading.value)return;
    if(operation==='confirm'&&!window.confirm('确认执行清单中的全部变更？系统将先备份项目，再一次性保存。'))return;
    loading.value=true;agentError.value='';
    try{
      const updated=await sidecarRequest<any>({method:'POST',path:`/v1/ai/actions/${id}/${operation}`,body:{project_id:await actualProjectId()}});
      agentActions.value=agentActions.value.map(a=>a.id===id?updated:a);
      if(selectedAgentAction.value?.id===id)openAgentActionDetail(updated);
      await loadOverview();
    }catch(e){agentError.value=formatLocalError(e);}finally{loading.value=false;}
  }
  const planningHomerooms=computed(()=>schoolData.value.homerooms);
  function classConfigurationStatus(id:string){
    const tasks=planningData.value.teaching_tasks.filter(t=>t.homeroom_id===id&&t.status!=='inactive');
    const periods=coursePlanningPeriodsForHomeroom(id);
    let missingTimeCount=0, totalProgress=0, completeSubjects=0;
    for(const s of schoolData.value.subjects){
      const rows=tasks.filter(t=>t.subject_id===s.id);
      if(planningData.value.course_plans.some(p=>p.homeroom_id===id&&p.subject_id===s.id&&p.weekly_slots===0)){
        totalProgress++;completeSubjects++;continue;
      }
      if(!rows.length)continue;
      let issues=0, lessonCount=0;
      for(const task of rows){
        const lessons=planningData.value.task_lessons.filter(l=>l.teaching_task_id===task.id);
        const enabled=lessons.filter(l=>l.enabled!==0&&l.enabled!==false);
        lessonCount+=lessons.length;
        const taskRooms=parseConfig(task.planning_config);
        if(task.required_room_type!=='__no_room__'&&taskRooms.uses_rooms!==false&&!task.fixed_room_id&&!taskRooms.room_ids?.length
          &&!(enabled.length&&enabled.every(l=>parseConfig(l.planning_config).room_ids?.length)))issues++;
        if(!lessons.length)issues++;
        for(const lesson of enabled){
          const rules=parseConfig(lesson.planning_config).preferred_times||[];
          if(!rules.some((rule:any)=>rule.penalty>=0&&periods.some(p=>p.id===rule.time_slot_id))){missingTimeCount++;issues++;}
        }
      }
      if(!issues)completeSubjects++;
      const checks=Math.max(1+rows.length*3+lessonCount,1);
      totalProgress+=Math.max(0,(checks-issues)/checks);
    }
    return {complete:schoolData.value.subjects.length>0&&completeSubjects===schoolData.value.subjects.length,
      progress:schoolData.value.subjects.length?Math.round(100*totalProgress/schoolData.value.subjects.length):0,
      missingTimeCount};
  }
  onMounted(()=>{void loadOverview().then(loadAgentProjectSession);void refreshConnection().catch(()=>{agentError.value='AI 设置暂时无法读取';});});
  return { activeAgentScene,activeSection,agentSceneOptions:sceneOptions,currentProjectName,hasProject,hasOrganization,organizationId,currentUserId,projectId,entitlement,connection,
    agentMessages,agentAttachmentDrafts,agentInput,agentError,agentSessionLoading,agentStreaming,agentUploading,currentAgentConversationId,loading,agentActions,selectedAgentAction,
    selectAgentScene,showSection:navigate,loadAgentProjectSession,submitAgentDraft,uploadAgentAttachments,clearCurrentAgentConversation,renderMarkdown,
    agentMessageAttachments:(m:Message)=>m.attachments||[],removeAgentAttachmentDraft:(id:string)=>{agentAttachmentDrafts.value=agentAttachmentDrafts.value.filter(f=>f.id!==id);},
    schoolData,planningData,planningHomerooms,termWeekCount,timetableTemplateSaveRevision,showCoursePreferredPicker,classConfigurationStatus,
    coursePlanningPeriodsForHomeroom,openCoursePreferredPickerForDraft,expectedPickerContext,
    request,loadOverview,loadPlanningData:loadOverview,loadConstraints:loadOverview,loadAgentUsage:refreshConnection,downloadOfficialWorkbook,applyAiTimetableDraft,aiTimetableDraft,
    agentUsage:ref(null), ...actionPresentation,
    openAgentActionDetail,closeAgentActionDetail:()=>{selectedAgentAction.value=null;},
    rejectAgentAction:(id:string)=>handleAction(id,'reject'),confirmAgentAction:(id:string)=>handleAction(id,'confirm'),
    selectedAgentActionItems,selectedAgentActionContextItems,selectedAgentActionItemTotal,agentActionItemsLoading:ref(false),agentActionItemQuery,agentActionItemTarget,agentActionItemOperation,loadSelectedAgentActionItems,
    durationText:(n:number)=>`${n*5}分钟`,constraintTypeLabel:distributionLabel,
  };
}
