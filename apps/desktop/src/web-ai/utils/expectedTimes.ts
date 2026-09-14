// @ts-nocheck -- upstream source
export type ExpectedRule = {
  template_id: string; period_keys: number[]; week_bits: string; day_bits: string;
  effect: "preferred" | "forbidden"; penalty: number; required: boolean;
};
export type ExpectedConfiguration = { schema_version: 2; default_policy: "inherit" | "restricted"; rules: ExpectedRule[] };
const mask = (left: string, right: string, remove = false) => Array.from(left).map((bit, i) => bit === "1" && (remove ? right[i] !== "1" : right[i] === "1") ? "1" : "0").join("");

export function configurationFromPicker(rules: Record<string, any>[], periods: Record<string, any>[]): ExpectedConfiguration {
  const result: ExpectedRule[] = [];
  for (const rule of rules) {
    const days = String(rule.day_bits || "");
    const matches = periods.filter(p => Number(p.period_index) === Number(rule.period_index) && p.active !== false && days[Number(p.weekday) - 1] === "1");
    for (let day = 1; day <= days.length; day++) {
      if (days[day - 1] === "1" && !matches.some(p => Number(p.weekday) === day)) throw new Error(`目标模板缺少星期${day}第${rule.period_index}课次，请先核对模板`);
    }
    for (const template of new Set(matches.map(p => String(p.template_id)))) {
      result.push({ template_id: template, period_keys: [Number(rule.period_index)], week_bits: String(rule.week_bits),
        day_bits: Array.from(days).map((bit, i) => bit === "1" && matches.some(p => String(p.template_id) === template && Number(p.weekday) === i + 1) ? "1" : "0").join(""),
        effect: Number(rule.penalty) < 0 || rule.forbidden ? "forbidden" : "preferred", penalty: Math.max(0, Number(rule.penalty || 0)), required: true });
    }
  }
  return pack(result);
}

function pack(rules: ExpectedRule[]): ExpectedConfiguration {
  const groups = new Map<string, ExpectedRule>();
  rules.forEach(rule => {
    const key = JSON.stringify([rule.template_id, rule.week_bits, rule.day_bits, rule.effect, rule.penalty, rule.required]);
    const previous = groups.get(key);
    groups.set(key, { ...rule, period_keys: [...new Set([...(previous?.period_keys || []), ...rule.period_keys])].sort((a,b) => a-b) });
  });
  return { schema_version: 2, default_policy: groups.size ? "restricted" : "inherit", rules: [...groups.values()] };
}

export function editExpectedConfiguration(current: ExpectedConfiguration, selected: ExpectedConfiguration, operation: "add" | "modify" | "delete"): ExpectedConfiguration {
  if (operation === "modify") return pack(selected.rules);
  if (operation === "add") return pack([...current.rules, ...selected.rules]);
  let rules = current.rules;
  for (const removal of selected.rules) {
    rules = rules.flatMap(rule => {
      if (rule.template_id !== removal.template_id) return [rule];
      const intersection = rule.period_keys.filter(key => removal.period_keys.includes(key));
      const weeks = mask(rule.week_bits, removal.week_bits), days = mask(rule.day_bits, removal.day_bits);
      if (!intersection.length || !weeks.includes("1") || !days.includes("1")) return [rule];
      const remaining: ExpectedRule[] = [];
      const keys = rule.period_keys.filter(key => !intersection.includes(key));
      const otherWeeks = mask(rule.week_bits, removal.week_bits, true), otherDays = mask(rule.day_bits, removal.day_bits, true);
      if (keys.length) remaining.push({ ...rule, period_keys: keys });
      if (otherWeeks.includes("1")) remaining.push({ ...rule, period_keys: intersection, week_bits: otherWeeks });
      if (otherDays.includes("1")) remaining.push({ ...rule, period_keys: intersection, week_bits: weeks, day_bits: otherDays });
      return remaining;
    });
  }
  return pack(rules);
}
