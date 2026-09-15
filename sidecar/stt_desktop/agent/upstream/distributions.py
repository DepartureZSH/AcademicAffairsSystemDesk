"""ITC2019 distribution semantics shared by compilation, solving and validation."""
from dataclasses import dataclass
from itertools import combinations
from functools import lru_cache
import re

LABELS = {
    "SameStart": "相同开始时刻", "SameTime": "时段相同或包含", "DifferentTime": "每天时段错开",
    "SameDays": "上课星期相同或包含", "DifferentDays": "上课星期不重复",
    "SameWeeks": "教学周相同或包含", "DifferentWeeks": "教学周不重复",
    "SameRoom": "使用同一教室", "DifferentRoom": "使用不同教室", "Overlap": "必须有时间重叠",
    "NotOverlap": "上课时间不冲突", "SameAttendees": "共同师生可连续到课", "Precedence": "首次上课先后顺序",
    "WorkDay": "每日上课跨度上限", "MinGap": "两课最小间隔", "MaxDays": "上课星期数上限",
    "MaxDayLoad": "每日总课长上限", "MaxBreaks": "每日长课间次数上限", "MaxBlock": "连续上课块时长上限",
}
COMPOSITE_LABELS = {"ParallelLimit": "同一时段课程数量上限"}
PARAMETER_COUNTS = {"WorkDay": 1, "MinGap": 1, "MaxDays": 1, "MaxDayLoad": 1, "MaxBreaks": 2, "MaxBlock": 2, "ParallelLimit": 1}
GROUP_TYPES = {"MaxDays", "MaxDayLoad", "MaxBreaks", "MaxBlock", "ParallelLimit"}
EXTENSIONS = {"Consecutive", "DifferentWeekSameDaySameStart", *COMPOSITE_LABELS}


def semantic_lesson_ids(value: str, lesson_ids) -> list[str]:
    ids = list(dict.fromkeys(str(item) for item in lesson_ids if item))
    return ids if value in {"Precedence", "Consecutive"} else sorted(ids)


@lru_cache(maxsize=4096)
def parse_distribution(value: str) -> tuple[str, tuple[int, ...]]:
    match = re.fullmatch(r"([A-Za-z]+)(?:\((\d+(?:\s*,\s*\d+)*)\))?", str(value).strip())
    if not match or match[1] not in LABELS.keys() | EXTENSIONS:
        raise ValueError(f"不支持的约束类型：{value}")
    kind = match[1]
    args = tuple(int(part.strip()) for part in match[2].split(",")) if match[2] else ()
    if len(args) != PARAMETER_COUNTS.get(kind, 0):
        raise ValueError(f"{LABELS.get(kind, COMPOSITE_LABELS.get(kind, kind))}的参数数量不正确")
    if (any(arg > 100000 for arg in args) or (kind == "MaxDays" and not 1 <= args[0] <= 7)
            or (kind == "ParallelLimit" and not 1 <= args[0] <= 100)):
        raise ValueError("约束参数超出允许范围")
    return kind, args


@dataclass(frozen=True)
class Placement:
    start: int
    length: int
    days: str
    weeks: str
    room: str | None = None

    @property
    def end(self):
        return self.start + self.length


def bits(value: str) -> set[int]:
    return {i for i, bit in enumerate(value) if bit == "1"}


def pair_violates(kind: str, args: tuple[int, ...], a: Placement, b: Placement, travel: int = 0) -> bool:
    days_a, days_b, weeks_a, weeks_b = bits(a.days), bits(b.days), bits(a.weeks), bits(b.weeks)
    same_date = bool(days_a & days_b and weeks_a & weeks_b)
    time_overlap = a.start < b.end and b.start < a.end
    if kind == "SameStart": return a.start != b.start
    if kind == "SameTime": return not (a.start <= b.start <= b.end <= a.end or b.start <= a.start <= a.end <= b.end)
    if kind == "DifferentTime": return time_overlap
    if kind == "SameDays": return not (days_a <= days_b or days_b <= days_a)
    if kind == "DifferentDays": return bool(days_a & days_b)
    if kind == "SameWeeks": return not (weeks_a <= weeks_b or weeks_b <= weeks_a)
    if kind == "DifferentWeeks": return bool(weeks_a & weeks_b)
    if kind == "SameRoom": return a.room != b.room
    if kind == "DifferentRoom": return a.room == b.room
    if kind == "Overlap": return not (same_date and time_overlap)
    if kind == "NotOverlap": return same_date and time_overlap
    if kind == "SameAttendees": return same_date and not (a.end + travel <= b.start or b.end + travel <= a.start)
    if kind == "Precedence":
        first_a, first_b = (min(weeks_a, default=0), min(days_a, default=0)), (min(weeks_b, default=0), min(days_b, default=0))
        return first_a > first_b or (first_a == first_b and a.end > b.start)
    if kind == "WorkDay": return same_date and max(a.end, b.end) - min(a.start, b.start) > args[0]
    if kind == "MinGap": return same_date and not (a.end + args[0] <= b.start or b.end + args[0] <= a.start)
    return False


def group_excess(kind: str, args: tuple[int, ...], placements: list[Placement]) -> int:
    if kind == "MaxDays":
        return max(len(set().union(*(bits(p.days) for p in placements))) - args[0], 0)
    meetings: dict[tuple[int, int], list[Placement]] = {}
    for p in placements:
        for week in bits(p.weeks):
            for day in bits(p.days):
                meetings.setdefault((week, day), []).append(p)
    excess = 0
    for rows in meetings.values():
        if kind == "ParallelLimit":
            # Half-open intervals: a lesson ending now frees a slot immediately.
            events = sorted((point, delta) for p in rows for point, delta in ((p.start, 1), (p.end, -1)))
            active = peak = 0
            for _, delta in events:
                active += delta
                peak = max(peak, active)
            excess += max(peak - args[0], 0)
            continue
        if kind == "MaxDayLoad":
            excess += max(sum(p.length for p in rows) - args[0], 0)
            continue
        blocks = []
        for p in sorted(rows, key=lambda p: (p.start, p.end)):
            if blocks and p.start <= blocks[-1][1] + args[1]:
                blocks[-1][1] = max(blocks[-1][1], p.end)
                blocks[-1][2] += 1
            else:
                blocks.append([p.start, p.end, 1])
        if kind == "MaxBreaks": excess += max(len(blocks) - 1 - args[0], 0)
        if kind == "MaxBlock": excess += sum(count > 1 and end - start > args[0] for start, end, count in blocks)
    return excess


def distribution_cost(value: str, placements: list[Placement], penalty: int = 1, nr_weeks: int = 1,
                      travel: dict[tuple[str, str], int] | None = None, hard: bool = False) -> int:
    kind, args = parse_distribution(value)
    if kind in GROUP_TYPES:
        excess = group_excess(kind, args, placements)
        return excess if hard else penalty * excess // (max(nr_weeks, 1) if kind != "MaxDays" else 1)
    return penalty * sum(pair_violates(kind, args, a, b, (travel or {}).get((a.room, b.room), (travel or {}).get((b.room, a.room), 0)))
                         for a, b in combinations(placements, 2))
