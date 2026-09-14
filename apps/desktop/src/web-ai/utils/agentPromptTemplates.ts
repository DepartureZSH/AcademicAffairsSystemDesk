// @ts-nocheck -- upstream source
export const agentPromptCategories = [
  { key: "task", label: "让 AI 做什么" },
  { key: "avoid", label: "不要做什么" },
  { key: "scope", label: "限制修改范围" },
] as const;

export type AgentPromptCategory = typeof agentPromptCategories[number]["key"];
export type AgentPromptScene = "timetable" | "rooms" | "school" | "planning" | "constraints";
export type AgentPromptTemplate = { id: string; category: AgentPromptCategory; title: string; text: string };

export const agentPromptTemplates: Record<AgentPromptScene, AgentPromptTemplate[]> = {
  timetable: [
    { id: "timetable-create", category: "task", title: "建立每周课表", text: "请新增课表模板【模板名称】：每周【周一到周五】上课，上午【4】节、下午【3】节，每节【40】分钟，课间【10】分钟，上午【08:00】开始、下午【14:00】开始。先检查时间是否冲突，再生成待确认变更。" },
    { id: "timetable-file", category: "task", title: "根据作息表建模板", text: "请读取附件中的作息时间表，整理上课日、课次、开始和结束时间，生成本项目课表模板的待确认变更；无法识别的时间请单独列出并询问我。" },
    { id: "timetable-check", category: "task", title: "检查现有模板", text: "请查询本项目课表模板，检查课次时间重叠、结束早于开始和缺失时间，仅列出问题与建议，不生成修改操作。" },
    { id: "timetable-no-guess", category: "avoid", title: "不猜测作息时间", text: "不要自行补充文件中没有写明的作息时间、课次数或上课日；缺失信息先询问我。" },
    { id: "timetable-no-delete", category: "avoid", title: "保留已有模板", text: "不要删除或覆盖任何已有课表模板；发现同名模板时，先列出差异让我选择。" },
    { id: "timetable-no-other", category: "avoid", title: "不调整其他数据", text: "不要修改教师、班级、科目、教室、课程计划或排课约束。" },
    { id: "timetable-one", category: "scope", title: "只修改一个模板", text: "本次只允许修改本项目中名为【模板名称】的课表模板，其余模板保持不变；有多个同名结果时先让我确认。" },
    { id: "timetable-period", category: "scope", title: "只改指定时段", text: "只修改【模板名称】中【周一下午】的课次时间，其他日期、时段、课次数及自定义内容均保持原样。" },
    { id: "timetable-readonly", category: "scope", title: "本次仅查看", text: "本次仅查询和解释课表模板，不生成新增、修改或删除操作。" },
  ],
  rooms: [
    { id: "rooms-official", category: "task", title: "录入官方教室 Excel", text: "请按官方模板 v1 严格录入教室设置。仅处理本附件填写的数据，空白可选项不覆盖原值，不删除已有数据；缺项、重名或引用不存在时停止并指出工作表和行号。生成待审批变更，不直接执行。" },
    { id: "rooms-file", category: "task", title: "从清单整理教室", text: "请读取附件中的教室清单，整理教室名称、教室类型和容量，先与已有教室对照去重，再生成待确认变更。缺失的容量不要猜测。" },
    { id: "rooms-create", category: "task", title: "新增一间教室", text: "请新增教室【教室名称】，类型为【教室类型】，容量为【40】人。先查询是否已有同名教室及对应类型，再生成待确认变更。" },
    { id: "rooms-template", category: "task", title: "为教室设置模板", text: "请查询本项目的课表模板和已有教室，将【教室名称】关联到【模板名称】；先确认对象唯一且模板可用，再生成待确认变更。" },
    { id: "rooms-no-guess", category: "avoid", title: "不猜测容量和类型", text: "不要根据教室名称推测容量或类型；无法确定的信息列出来问我。" },
    { id: "rooms-no-delete", category: "avoid", title: "不删除或合并教室", text: "不要删除、合并或重命名已有教室；名称相似的教室先列为待核对项。" },
    { id: "rooms-no-other", category: "avoid", title: "不改模板和课程计划", text: "可以查询课表模板，但不要修改模板内容，也不要修改教师、班级、科目、课程计划或约束。" },
    { id: "rooms-listed", category: "scope", title: "只处理指定教室", text: "只处理这些教室：【教室名称列表】。其他教室及教室类型保持原样。" },
    { id: "rooms-capacity", category: "scope", title: "只更新容量", text: "只更新【教室名称】的容量为【人数】人，不改名称、类型、关联模板和其他字段。" },
    { id: "rooms-add-only", category: "scope", title: "只新增缺少的教室", text: "仅新增附件中尚不存在的教室。已有同名教室全部跳过并说明原因，不更新已有记录。" },
  ],
  school: [
    { id: "school-official", category: "task", title: "录入官方学校数据 Excel", text: "请按官方模板 v1 严格录入学校数据。仅处理本附件填写的数据，空白可选项不覆盖原值，不删除已有数据；缺项、重名或引用不存在时停止并指出工作表和行号。生成待审批变更，不直接执行。" },
    { id: "school-file", category: "task", title: "从任课表提取基础数据", text: "请从附件中提取明确出现的教师、班级和科目，与已有学校数据对照去重，并生成待确认的新增操作。即使缺少周课时或教室信息，也先处理可确定的基础数据，不生成课程计划。" },
    { id: "school-teachers", category: "task", title: "录入教师名单", text: "请整理以下教师名单并与已有教师去重，生成待确认的新增操作：【教师名单】。姓名相同但无法确定是否同一人的记录先询问我。" },
    { id: "school-check", category: "task", title: "核对班级与科目", text: "请对照附件和已有学校数据，列出缺少、重复或名称不一致的班级与科目。先给出核对清单，不生成修改操作。" },
    { id: "school-no-plan", category: "avoid", title: "不生成课程计划", text: "本次只整理学校基础数据，不生成任课安排、周课时、课程计划或排课约束，也不要为这些信息不完整而停止基础数据整理。" },
    { id: "school-no-guess", category: "avoid", title: "不猜测人员和班级", text: "不要推测教师全名、科目归属、班级人数或缺失班级；模糊、缺失和同名项请列出来问我。" },
    { id: "school-no-delete", category: "avoid", title: "保留已有学校数据", text: "不要删除、重命名或合并已有教师、班级和科目；名称不一致时先给出差异。" },
    { id: "school-teachers-only", category: "scope", title: "只处理教师", text: "本次仅处理教师数据，班级、科目、学期及其他数据全部保持不变。" },
    { id: "school-grade", category: "scope", title: "只处理指定年级班级", text: "本次仅处理【年级名称】的班级数据，其他年级、教师、科目和学期不做修改。" },
    { id: "school-add-only", category: "scope", title: "只新增缺失记录", text: "只新增附件中明确存在且系统中缺少的教师、班级和科目。已有记录保持不变，疑似重复项不自动合并。" },
  ],
  planning: [
    { id: "planning-not-scheduled", category: "task", title: "不安排课次", text: "请在当前项目【处理范围：填写班级、年级或全部班级】中，将满足【不安排条件：例如课次数为0，包含尚未配置的课程】的课程设为“不安排”。这是独立的业务请求，先查询系统实际数据；只有条件明确依赖附件时才读取相关附件，不重新导入历史文件。只处理符合条件的对象，列出班级、科目、命中条件及受影响的授课任务和课次，生成待审核操作，不直接执行。不符合条件及范围外的数据保持原样，已设为不安排的跳过。若我只指定某个课次，不得扩大为整门科目不安排；条件未填写、含义不清或存在尚未授权的删除影响时，只询问这些缺失信息。" },
    { id: "planning-file", category: "task", title: "从教师任课表生成计划", text: "请读取附件中的任课表，匹配已有教师、班级和科目，整理谁教哪个班、什么科目及每周课次数，生成课程计划的待确认变更。缺少匹配对象或周课时的行单独列出，先处理信息完整的行。" },
    { id: "planning-collection", category: "task", title: "按课程计划模板录入", text: "请读取附件的课程计划工作表，按班级、科目、教师、默认教室、课次名、课次教室六列整理课程计划。合并单元格表示其覆盖课次共用的信息；每个已填写课次名的行表示一节课，空白课次行不计数。课次教室填写“默认”时使用该课程的默认教室，“不使用教室”表示无需教室，其他名称须匹配已有教室。课长沿用系统中对应科目的默认课长；缺失或重名无法确定的信息请列出让我确认，不要猜测，不修改期望时间。只生成待确认操作，不删除已有课程或基础数据。" },
    { id: "planning-create", category: "task", title: "增加一项任课安排", text: "请为【班级名称】新增【科目名称】课程计划，由【教师姓名】任教，每周【课次数】次。先检查是否已有相同安排，再生成待确认变更。" },
    { id: "planning-check", category: "task", title: "核对任课与周课时", text: "请对照附件与当前项目课程计划，检查任课教师、班级、科目和每周课次数，列出缺漏、重复及不一致项。本次仅查询，不生成修改操作。" },
    { id: "planning-no-hours", category: "avoid", title: "不推测周课时", text: "不要根据常见教学安排猜测每周课次数，也不要把总课时直接当成周课时。含义不清时先询问我。" },
    { id: "planning-no-foundation", category: "avoid", title: "不补建基础数据", text: "不要新增或修改教师、班级、科目和教室；找不到对应基础数据时，列出缺失项，待我在学校数据或教室设置中补齐。" },
    { id: "planning-no-extra", category: "avoid", title: "不增加额外排课规则", text: "不要自行设置连堂、固定时间、教室或额外约束；保留已有设置，未说明的要求先询问我。" },
    { id: "planning-class", category: "scope", title: "只处理指定班级", text: "只处理当前项目【班级名称】的课程计划，其他班级的任课安排和课次数保持原样。" },
    { id: "planning-teacher", category: "scope", title: "只替换任课教师", text: "仅把当前项目【班级名称】的【科目名称】任课教师由【原教师】改为【新教师】，不改课次数、教室和时间设置。" },
    { id: "planning-add-only", category: "scope", title: "只补缺少的计划", text: "仅新增附件中尚未录入的课程计划，不覆盖、删除或调整已有计划；发现冲突时列出差异让我确认。" },
  ],
  constraints: [
    { id: "constraints-unavailable", category: "task", title: "教师指定时间不排课", text: "请为【教师姓名】设置【周三下午】不排课的规则。先查询本项目模板和该教师的授课任务，确认对应时段后生成待确认约束。" },
    { id: "constraints-spread", category: "task", title: "课程分散到不同天", text: "请让【班级名称】的【科目名称】尽量分散到不同天，优先保证每天不超过【1】次。先核对课次数与可用天数，不可满足时说明原因，再生成待确认约束。" },
    { id: "constraints-check", category: "task", title: "检查规则是否重复或矛盾", text: "请查询当前项目已有约束及相关课程计划，找出重复或可能矛盾的规则，说明涉及对象与理由。仅提供建议，不生成修改操作。" },
    { id: "constraints-no-weaken", category: "avoid", title: "不擅自放宽规则", text: "不要删除或放宽现有硬性约束，也不要擅自把硬性要求改成偏好；如果要求冲突，先说明并让我决定。" },
    { id: "constraints-no-data", category: "avoid", title: "不调整任课和课时", text: "不要为满足约束而修改任课教师、课程计划、每周课次数、教室或课表模板。" },
    { id: "constraints-no-extra", category: "avoid", title: "不添加未提出的规则", text: "不要自动添加我未提出的连堂、分散、午休或固定时间规则，也不要启动排课。" },
    { id: "constraints-teacher", category: "scope", title: "只处理指定教师", text: "本次只新增或调整【教师姓名】相关的约束，其他教师、班级和全校通用规则保持原样。" },
    { id: "constraints-one", category: "scope", title: "只改一条约束", text: "仅修改约束【约束名称或编号】，具体要求为【修改内容】；先确认对象唯一，其余约束一律不动。" },
    { id: "constraints-readonly", category: "scope", title: "只分析不修改", text: "本次只查询和分析排课约束，不生成新增、修改、删除或运行排课操作。" },
  ],
};

export function appendAgentPrompt(draft: string, text: string): string {
  if (draft.includes(text)) return draft;
  return draft.trim() ? `${draft.trimEnd()}\n\n${text}` : text;
}
