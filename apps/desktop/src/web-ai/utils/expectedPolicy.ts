import type { ExpectedConfiguration } from './expectedTimes';

// Match semantic time cells, not JSON ordering or how a picker grouped weekdays.
export function sameExpectedTimes(left: ExpectedConfiguration, right: ExpectedConfiguration): boolean {
  function cells(config: ExpectedConfiguration): string[] {
    const values = new Set<string>();
    for (const rule of config.rules) {
      for (const period of rule.period_keys) {
        for (let week = 0; week < rule.week_bits.length; week++) {
          if (rule.week_bits[week] !== '1') continue;
          for (let day = 0; day < rule.day_bits.length; day++) {
            if (rule.day_bits[day] === '1') values.add(JSON.stringify([rule.template_id, period, week, day, rule.effect, rule.penalty, rule.required]));
          }
        }
      }
    }
    return [...values].sort();
  }
  return left.default_policy === right.default_policy && JSON.stringify(cells(left)) === JSON.stringify(cells(right));
}
