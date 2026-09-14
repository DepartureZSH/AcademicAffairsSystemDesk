// @ts-nocheck -- upstream source
export type ConstraintParameter = { label: string; unit: string; value: number; min: number; max: number; step: number };
const minutes = (label: string, value: number): ConstraintParameter => ({ label, value, unit: "分钟", min: 0, max: 1440, step: 5 });
const count = (label: string, value: number, unit: string, min = 0, max = 100): ConstraintParameter => ({ label, value, unit, min, max, step: 1 });
export const itcConstraints = [
  { type: "SameStart", label: "相同开始时刻", category: "时段", description: "开始时刻相同，不要求在同一星期或教学周。" },
  { type: "SameTime", label: "时段相同或包含", category: "时段", description: "两课的时段相同，或较短的一课完全包含在较长的一课内；不比较星期和教学周。" },
  { type: "DifferentTime", label: "每天时段错开", category: "时段", description: "即使不在同一天，所选课次的钟点时段也不能重叠。" },
  { type: "Overlap", label: "必须有时间重叠", category: "时段", description: "每两课都须有共同的教学周、星期和重叠时段。" },
  { type: "NotOverlap", label: "上课时间不冲突", category: "时段", description: "同一教学周、同一星期内的两课不能重叠，前一课结束即可开始下一课。" },
  { type: "SameDays", label: "上课星期相同或包含", category: "星期", description: "每两课的上课星期集合相同，或一方包含另一方，例如周一与周一、周三。" },
  { type: "DifferentDays", label: "上课星期不重复", category: "星期", description: "所选课次不占用相同星期，即使安排在不同教学周也要错开。" },
  { type: "SameWeeks", label: "教学周相同或包含", category: "教学周", description: "每两课的教学周集合相同，或一方包含另一方。" },
  { type: "DifferentWeeks", label: "教学周不重复", category: "教学周", description: "所选课次的教学周不能有交集，适合轮换周课程。" },
  { type: "SameRoom", label: "使用同一教室", category: "教室", description: "所选课次使用同一间教室。" },
  { type: "DifferentRoom", label: "使用不同教室", category: "教室", description: "每两课使用不同教室，即使上课时间不同。" },
  { type: "SameAttendees", label: "共同师生可连续到课", category: "衔接", description: "课次不能冲突，且须预留教室间的通行时间；未配置通行时间时按零计算。" },
  { type: "Precedence", label: "首次上课先后顺序", category: "衔接", description: "按关联课次的选择顺序比较首次上课：先看教学周，再看星期，最后要求前课结束后再开始后课。" },
  { type: "WorkDay", label: "每日上课跨度上限", category: "每日负荷", description: "同一天每两课从最早开始到最晚结束的跨度不超过上限，包含课间。", parameters: [minutes("每日跨度上限", 360)] },
  { type: "MinGap", label: "两课最小间隔", category: "衔接", description: "同一天两课之间至少留出指定时间。", parameters: [minutes("最小课间", 10)] },
  { type: "MaxDays", label: "上课星期数上限", category: "每日负荷", description: "所选课次合计最多占用几个星期，不按教学周分别计算。", parameters: [count("最多上课星期数", 5, "天", 1, 7)] },
  { type: "MaxDayLoad", label: "每日总课长上限", category: "每日负荷", description: "每个教学周的每一天，所选课次的课长总和不超过上限，不计课间。", parameters: [minutes("每日总课长", 240)] },
  { type: "MaxBreaks", label: "每日长课间次数上限", category: "每日负荷", description: "每日超过课间阈值的空档次数不超过上限；等于阈值不算长课间。", parameters: [count("最多长课间", 1, "次"), minutes("课间阈值", 30)] },
  { type: "MaxBlock", label: "连续上课块时长上限", category: "每日负荷", description: "课间不超过阈值的课程视为一组，含课间的总跨度不超过上限。单独一课超过上限不计违规。", parameters: [minutes("连续上课块上限", 120), minutes("课间阈值", 15)] },
].map(item => ({ ...item, parameters: (item.parameters || []) as ConstraintParameter[], pairBased: !["MaxDays", "MaxDayLoad", "MaxBreaks", "MaxBlock"].includes(item.type) }));

export function constraintDefinition(value: unknown) {
  const type = String(value || "").split("(")[0];
  if (type === "ParallelLimit") return {
    type, label: "同一时段课程数量上限", category: "常见约束", pairBased: false,
    description: "所选课次合计的同时开课数量不超过上限；按实际教学周、星期和时间判断。原有教师、班级和教室冲突规则仍生效。",
    parameters: [count("同时最多上课", 4, "节", 1, 100)],
  };
  if (type === "Consecutive") return {
    type, label: "课程连续排课", category: "衔接", pairBased: true,
    description: "按已选课次的顺序，在相同教学周、同一星期的相邻节次连排，保留课表已有的课间；未设置节次时，两课首尾相接。",
    parameters: [] as ConstraintParameter[],
  };
  if (type === "DifferentWeekSameDaySameStart") return {
    type, label: "不同周保持同一时间", category: "教学周", pairBased: true,
    description: "所选课次安排在互不重复的教学周，但上课星期和开始时刻相同。",
    parameters: [] as ConstraintParameter[],
  };
  return itcConstraints.find(item => item.type === type);
}
export function constraintValues(value: string) {
  const definition = constraintDefinition(value);
  const args = value.match(/\(([^)]+)\)/)?.[1].split(",").map(Number);
  return definition?.parameters.map((p, i) => args?.[i] === undefined ? p.value : args[i] * (p.unit === "分钟" ? 5 : 1)) || [];
}
export function encodeConstraint(type: string, values?: number[]) {
  const definition = constraintDefinition(type);
  if (!definition?.parameters.length) return type;
  const args = definition.parameters.map((p, i) => {
    const value = values?.[i] ?? p.value;
    if (!Number.isInteger(value) || value < p.min || value > p.max || value % p.step) throw new Error(`${p.label}应为 ${p.min}–${p.max} 之间的 ${p.step} 的整数倍`);
    return value / (p.unit === "分钟" ? 5 : 1);
  });
  return `${definition.type}(${args.join(",")})`;
}
export function distributionLabel(value: unknown) {
  const text = String(value || "");
  const definition = constraintDefinition(text);
  if (!definition) return ({ Consecutive: "课程连续排课", DifferentWeekSameDaySameStart: "不同周保持同一时间" } as Record<string, string>)[text] || text || "-";
  const values = constraintValues(text);
  return definition.label + (values.length ? `（${definition.parameters.map((p, i) => `${p.label} ${values[i]} ${p.unit}`).join("，")}）` : "");
}

export const commonConstraintCategories = [
  { id: "time", label: "上课时间", description: "同时上课、错开时段或避免冲突" },
  { id: "sequence", label: "连排与间隔", description: "连续上课、先后顺序与课间衔接" },
  { id: "days", label: "每周安排", description: "安排在哪些星期、分散或集中上课" },
  { id: "weeks", label: "教学周安排", description: "同周上课、错周轮换与单双周安排" },
  { id: "rooms", label: "教室与场地", description: "教室选择与同时开课数量" },
  { id: "load", label: "课量与休息", description: "每天课量、在校跨度与长课间" },
];

// A single entry per executable rule; common wording and basic rules share the same parameters.
export const commonConstraintScenarios = [
  { type: "NotOverlap", category: "time", title: "这些课不能同时上", example: "两门选修课有共同学生，安排在互不冲突的时间。" },
  { type: "SameStart", category: "time", title: "这些课在同一钟点开始", example: "两次课都从 8:00 开始，可以安排在不同的星期。" },
  { type: "SameTime", category: "time", title: "这些课的钟点时段相同或包含", example: "一课 8:00–8:40，另一课 8:00–9:20；也可以在不同天。" },
  { type: "DifferentTime", category: "time", title: "这些课的钟点时段要错开", example: "一课占用 8:00–8:40，另一课即使在不同天，也避开这个时段。" },
  { type: "Overlap", category: "time", title: "这些课必须有同时上课的时间", example: "两项活动需要同期开展，至少有共同的教学周、星期和重叠时段。" },
  { type: "Consecutive", key: "course_consecutive", category: "sequence", title: "这些课连续上", example: "两节作文课前后紧接着上；先选第一节，再选第二节。" },
  { type: "Precedence", category: "sequence", title: "这些课按先后顺序开始", example: "首次理论课先于首次实验课；课次顺序就是要求的先后顺序。" },
  { type: "MinGap", category: "sequence", title: "两课之间至少休息一段时间", example: "同一天的两节实验课之间，至少空出 20 分钟。" },
  { type: "SameAttendees", category: "sequence", title: "师生能按时赶到下一堂课", example: "师生需要从教学楼走到实验楼，两课之间预留已配置的通行时间。" },
  { type: "DifferentDays", key: "spread_different_days", category: "days", title: "这些课分散到不同星期", example: "三次体育课分别放在周一、周三、周五，不能都挤在周一。" },
  { type: "SameDays", category: "days", title: "这些课安排在相同星期或其中几天", example: "一课在周一，另一课在周一、周三，符合要求；周一与周二则不符合。" },
  { type: "MaxDays", category: "days", title: "这些课每周最多占几天", example: "选中一位教师的全部课次，合计最多占用周一至周四这 4 天；不同教学周也一起计算。" },
  { type: "SameWeeks", category: "weeks", title: "这些课在相同教学周或其中几周上", example: "一课在第 1–8 周，另一课在第 1–4 周，符合要求。" },
  { type: "DifferentWeeks", category: "weeks", title: "这些课安排在不同教学周", example: "一门活动课安排单周，另一门安排双周，教学周不重复。" },
  { type: "DifferentWeekSameDaySameStart", key: "course_same_time_different_weeks", category: "weeks", title: "不同周轮换，同星期同钟点上课", example: "单周美术、双周音乐，都安排在周三 14:00 开始。" },
  { type: "ParallelLimit", key: "parallel_limit", category: "rooms", title: "同一时段课程数量上限", example: "全校体育课同一时间最多上 4 节，也可以合并多个科目一起限制。" },
  { type: "SameRoom", category: "rooms", title: "这些课使用同一间教室", example: "几次实验课固定使用同一间实验室，上课时间仍需错开。" },
  { type: "DifferentRoom", category: "rooms", title: "这些课分别使用不同教室", example: "两项活动分配到不同教室，即使它们不是同时开始。" },
  { type: "WorkDay", category: "load", title: "每天从上课到结束不要跨太久", example: "选中某教师的课次，每天最早开始到最晚结束不超过 6 小时，包含课间。" },
  { type: "MaxDayLoad", category: "load", title: "每天上课总时长不要太多", example: "选中某班课次，每天累计上课不超过 240 分钟，不计课间。" },
  { type: "MaxBreaks", category: "load", title: "每天不要出现太多长课间", example: "一天中超过 30 分钟的空档最多 1 次，正好 30 分钟不计入。" },
  { type: "MaxBlock", category: "load", title: "连续上课不要太久", example: "课间不超过 15 分钟的课算连续一段，整段含课间不超过 120 分钟。" },
].map(item => {
  const definition = constraintDefinition(item.type)!;
  return {
    ...item,
    key: item.key || item.type,
    defaultName: item.title,
    distributionType: encodeConstraint(item.type),
    description: definition.description,
    minimumItems: definition.pairBased ? 2 : 1,
    ordered: ["Consecutive", "Precedence"].includes(item.type),
  };
});
