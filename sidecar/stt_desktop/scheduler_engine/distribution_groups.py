"""CP-SAT encodings for whole-group ITC rules and NotOverlap compositions."""
from stt_desktop.agent.upstream.distributions import GROUP_TYPES, bits, parse_distribution


def _any(model, values, name):
    result = model.new_bool_var(name)
    model.add_max_equality(result, list(values) or [0])
    return result


def _and(model, values, name):
    result = model.new_bool_var(name)
    for value in values:
        model.add(result <= value)
    model.add(result >= sum(values) - len(values) + 1)
    return result


def _block_metrics(model, candidates, gap, limit, name):
    # Only interval boundaries matter. Extending ends by S merges exactly gaps <= S.
    points = sorted({v for c in candidates for v in (c.action.time.start, c.action.time.start + c.action.time.length + gap)})
    previous_active, previous_origin, previous_count = 0, 0, 0
    starts, oversized = [], []
    for index, point in enumerate(points):
        prefix = f"{name}_{index}"
        active = _any(model, (c.literal for c in candidates
                              if c.action.time.start <= point < c.action.time.start + c.action.time.length + gap), prefix + "_active")
        start = _and(model, [active, 1 - previous_active], prefix + "_start")
        starts.append(start)
        if limit is not None:
            end = _and(model, [previous_active, 1 - active], prefix + "_end")
            origin = model.new_int_var(0, max(points), prefix + "_origin")
            model.add(origin == point).only_enforce_if(start)
            model.add(origin == previous_origin).only_enforce_if(start.Not())
            count = model.new_int_var(0, len(candidates), prefix + "_count")
            new_classes = sum(c.literal for c in candidates if c.action.time.start == point)
            model.add(count == 0).only_enforce_if(active.Not())
            model.add(count == new_classes).only_enforce_if(start)
            model.add(count == previous_count + new_classes).only_enforce_if([active, start.Not()])
            multiple = model.new_bool_var(prefix + "_multiple")
            model.add(previous_count >= 2).only_enforce_if(multiple)
            model.add(previous_count < 2).only_enforce_if(multiple.Not())
            too_long = model.new_bool_var(prefix + "_long")
            model.add(point - gap - previous_origin > limit).only_enforce_if(too_long)
            model.add(point - gap - previous_origin <= limit).only_enforce_if(too_long.Not())
            oversized.append(_and(model, [end, multiple, too_long], prefix + "_bad"))
            previous_origin, previous_count = origin, count
        previous_active = active
    return sum(starts), sum(oversized)


def compile_group_constraints(model, problem, candidates_by_class):
    costs = []
    for index, distribution in enumerate(problem.distributions):
        kind, args = parse_distribution(distribution.distribution_type)
        if kind not in GROUP_TYPES:
            continue
        candidates = [c for class_id in distribution.class_ids for c in candidates_by_class.get(class_id, ())]
        if not candidates:
            continue
        prefix = f"distribution_{index}"
        excesses = []
        bound = max(1, sum(c.action.time.length + 1 for c in candidates) * max(distribution.nr_weeks, 1) * 7)
        if kind == "MaxDays":
            days = sorted(set().union(*(bits(c.action.time.days) for c in candidates)))
            active_days = [_any(model, (c.literal for c in candidates if day in bits(c.action.time.days)), f"{prefix}_day_{day}") for day in days]
            excess = model.new_int_var(0, len(days), prefix + "_excess")
            model.add_max_equality(excess, [sum(active_days) - args[0], 0])
            excesses.append(excess)
        else:
            meetings = {}
            for c in candidates:
                for week in bits(c.action.time.weeks):
                    for day in bits(c.action.time.days):
                        meetings.setdefault((week, day), []).append(c)
            encoded_parallel_dates = set()
            for (week, day), rows in meetings.items():
                name = f"{prefix}_{week}_{day}"
                if kind == "ParallelLimit" and distribution.required:
                    date_key = tuple(c.ordinal for c in rows)
                    if date_key in encoded_parallel_dates or len({c.class_id for c in rows}) <= args[0]:
                        continue
                    encoded_parallel_dates.add(date_key)
                    # Existential partition into K NotOverlap lanes, independently per date.
                    # Fixed class groups (or a global lane per recurring class) overconstrain it.
                    lanes = [[] for _ in range(min(args[0], len({c.class_id for c in rows})))]
                    for ordinal, c in enumerate(rows):
                        choices = []
                        for lane, intervals in enumerate(lanes):
                            presence = model.new_bool_var(f"{name}_{ordinal}_lane_{lane}")
                            choices.append(presence)
                            intervals.append(model.new_optional_fixed_size_interval_var(
                                c.action.time.start, c.action.time.length, presence,
                                f"{name}_{ordinal}_interval_{lane}"))
                        model.add(sum(choices) == c.literal)
                    for intervals in lanes:
                        model.add_no_overlap(intervals)
                    continue
                excess = model.new_int_var(0, bound, name + "_excess")
                if kind == "ParallelLimit":
                    peaks = [sum(c.literal for c in rows
                                 if c.action.time.start <= point < c.action.time.start + c.action.time.length)
                             for point in sorted({c.action.time.start for c in rows})]
                    model.add_max_equality(excess, [0, *(peak - args[0] for peak in peaks)])
                elif kind == "MaxDayLoad":
                    model.add_max_equality(excess, [sum(c.action.time.length * c.literal for c in rows) - args[0], 0])
                else:
                    blocks, oversized = _block_metrics(model, rows, args[1], args[0] if kind == "MaxBlock" else None, name)
                    if kind == "MaxBreaks":
                        model.add_max_equality(excess, [blocks - 1 - args[0], 0])
                    else:
                        model.add(excess == oversized)
                excesses.append(excess)
        if distribution.required:
            model.add(sum(excesses) == 0)
        elif distribution.penalty:
            cost = model.new_int_var(0, bound * distribution.penalty, prefix + "_cost")
            divisor = max(distribution.nr_weeks, 1) if kind != "MaxDays" else 1
            model.add_division_equality(cost, distribution.penalty * sum(excesses), divisor)
            costs.append((1, cost))
    return costs
