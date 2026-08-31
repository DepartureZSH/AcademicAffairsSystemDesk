from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from xml.etree.ElementTree import Element, SubElement, fromstring, tostring


SUPPORTED_DISTRIBUTIONS = {
    "NotOverlap",
    "SameRoom",
    "DifferentTime",
    "DifferentDays",
    "DifferentWeeks",
    "SameDays",
    "SameStart",
    "SameTime",
    "Precedence",
    "Consecutive",
    "DifferentWeekSameDaySameStart",
}


@dataclass(frozen=True)
class TimeOption:
    days: str
    weeks: str
    start: int
    length: int
    penalty: int
    period_index: int | None = None


@dataclass(frozen=True)
class RoomOption:
    room_id: str
    penalty: int
    unavailable_times: tuple[tuple[str, str, int], ...] = ()
    timed_penalties: tuple[tuple[str, str, int, int], ...] = ()


@dataclass(frozen=True)
class Room:
    room_id: str
    name: str


@dataclass(frozen=True)
class ClassAgent:
    class_id: str
    label: str
    time_options: tuple[TimeOption, ...]
    room_options: tuple[RoomOption, ...]


@dataclass(frozen=True)
class Action:
    class_id: str
    time: TimeOption
    room_id: str | None
    time_penalty: int
    room_penalty: int

    @property
    def base_penalty(self) -> int:
        return self.time_penalty + self.room_penalty


@dataclass(frozen=True)
class Distribution:
    distribution_id: str
    distribution_type: str
    required: bool
    penalty: int
    class_ids: tuple[str, ...]
    name: str = ""
    scope: str = ""


@dataclass(frozen=True)
class ResourceLimit:
    constraint_id: str
    limit_type: str
    required: bool
    penalty: int
    limit: int
    class_ids: tuple[str, ...]
    name: str = ""
    scope: str = ""


@dataclass(frozen=True)
class Problem:
    name: str
    rooms: tuple[Room, ...]
    agents: tuple[ClassAgent, ...]
    distributions: tuple[Distribution, ...]
    resource_limits: tuple[ResourceLimit, ...]


def run_cgcs_greedy(problem_xml: str, run_id: str, algorithm_config: dict | None = None) -> dict:
    problem = parse_problem(problem_xml)
    assignments: dict[str, Action] = {}
    failed_agents: list[ClassAgent] = []
    ordered_agents = sorted(
        problem.agents,
        key=lambda agent: _agent_order_key(agent, problem.distributions),
    )

    for agent in ordered_agents:
        if agent.class_id in assignments:
            continue
        best_action: Action | None = None
        best_penalty: int | None = None
        for action in _actions(agent):
            if not _is_feasible(action, assignments, problem.distributions):
                continue
            penalty = action.base_penalty + _incremental_soft_penalty(
                action, assignments, problem.distributions
            )
            if best_penalty is None or penalty < best_penalty:
                best_action = action
                best_penalty = penalty
        if best_action is None:
            failed_agents.append(agent)
            continue
        assignments[agent.class_id] = best_action

    failed_agents = _repair_failed_agents(
        failed_agents,
        assignments,
        problem.distributions,
        {agent.class_id: agent for agent in problem.agents},
    )

    metrics = _score(assignments, problem.distributions)
    solution_xml = _build_solution_xml(run_id, assignments, algorithm_config or {})
    failed_labels = [agent.label for agent in failed_agents]
    hard_violations = len(failed_agents)
    if hard_violations:
        log = (
            f"无法为下列课次找到可行安排：{'；'.join(failed_labels)}"
            f"（已成功安排 {len(assignments)}/{len(problem.agents)} 个课次）"
        )
    else:
        log = (
            "CGCS greedy completed: "
            f"{len(assignments)}/{len(problem.agents)} classes assigned, "
            f"{len(problem.distributions)} distributions checked"
        )
    return {
        "run_id": run_id,
        "solution_xml": solution_xml,
        "hard_violations": hard_violations,
        "time_penalty": metrics["time_penalty"],
        "room_penalty": metrics["room_penalty"],
        "distribution_penalty": metrics["distribution_penalty"],
        "total_score": metrics["total_score"],
        "log": log,
    }


def _repair_failed_agents(
    failed_agents: list[ClassAgent],
    assignments: dict[str, Action],
    distributions: tuple[Distribution, ...],
    agents_by_id: dict[str, ClassAgent],
) -> list[ClassAgent]:
    pending = list(failed_agents)
    while pending:
        remaining = []
        repaired_count = 0
        for agent in pending:
            direct_action = _best_feasible_action(agent, assignments, distributions)
            if direct_action is not None:
                assignments[agent.class_id] = direct_action
                repaired_count += 1
                continue
            if _repair_by_relocating_one(
                agent,
                assignments,
                distributions,
                agents_by_id,
            ):
                repaired_count += 1
                continue
            remaining.append(agent)
        pending = remaining
        if repaired_count == 0:
            return pending
    return []


def _best_feasible_action(
    agent: ClassAgent,
    assignments: dict[str, Action],
    distributions: tuple[Distribution, ...],
) -> Action | None:
    candidates = [
        action
        for action in _actions(agent)
        if _is_feasible(action, assignments, distributions)
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda action: (
            action.base_penalty + _incremental_soft_penalty(action, assignments, distributions),
            action.time.start,
            action.room_id or "",
        ),
    )


def _repair_by_relocating_one(
    failed_agent: ClassAgent,
    assignments: dict[str, Action],
    distributions: tuple[Distribution, ...],
    agents_by_id: dict[str, ClassAgent],
) -> bool:
    best_plan: tuple[int, Action, str, Action] | None = None
    for candidate in _actions(failed_agent):
        blocker_ids = _blocking_class_ids(candidate, assignments, distributions)
        if len(blocker_ids) != 1:
            continue
        blocker_id = next(iter(blocker_ids))
        blocker_action = assignments.pop(blocker_id)
        try:
            if not _is_feasible(candidate, assignments, distributions):
                continue
            candidate_penalty = candidate.base_penalty + _incremental_soft_penalty(
                candidate,
                assignments,
                distributions,
            )
            assignments[failed_agent.class_id] = candidate
            blocker_agent = agents_by_id[blocker_id]
            replacement = _best_feasible_action(blocker_agent, assignments, distributions)
            if replacement is None or replacement == blocker_action:
                continue
            penalty = (
                candidate_penalty
                + replacement.base_penalty
                + _incremental_soft_penalty(replacement, assignments, distributions)
            )
            plan = (penalty, candidate, blocker_id, replacement)
            if best_plan is None or plan[0] < best_plan[0]:
                best_plan = plan
        finally:
            assignments.pop(failed_agent.class_id, None)
            assignments[blocker_id] = blocker_action

    if best_plan is None:
        return False
    _, candidate, blocker_id, replacement = best_plan
    assignments[failed_agent.class_id] = candidate
    assignments[blocker_id] = replacement
    return True


def _blocking_class_ids(
    candidate: Action,
    assignments: dict[str, Action],
    distributions: tuple[Distribution, ...],
) -> set[str]:
    blocker_ids = {
        class_id
        for class_id, assigned in assignments.items()
        if candidate.room_id
        and candidate.room_id == assigned.room_id
        and _overlaps(candidate.time, assigned.time)
    }
    for distribution in distributions:
        if not distribution.required or candidate.class_id not in distribution.class_ids:
            continue
        for class_id in distribution.class_ids:
            other = assignments.get(class_id)
            if other and _violates(distribution, candidate, other):
                blocker_ids.add(class_id)
    return blocker_ids


def parse_problem(problem_xml: str) -> Problem:
    root = fromstring(problem_xml)
    rooms = tuple(
        Room(
            room_id=room_node.attrib["id"],
            name=room_node.attrib.get("name", "").strip(),
        )
        for room_node in root.findall("./rooms/room")
        if room_node.attrib.get("id")
    )
    agents = []
    for class_node in root.findall(".//class"):
        class_id = class_node.attrib.get("id")
        if not class_id or class_node.find("time") is None:
            continue
        time_options = tuple(
            TimeOption(
                days=time_node.attrib.get("days", ""),
                weeks=time_node.attrib.get("weeks", ""),
                start=int(time_node.attrib.get("start", "0")),
                length=int(time_node.attrib.get("length", "1")),
                penalty=int(time_node.attrib.get("penalty", "0")),
                period_index=(
                    int(time_node.attrib["periodIndex"])
                    if time_node.attrib.get("periodIndex") is not None
                    else None
                ),
            )
            for time_node in class_node.findall("time")
        )
        room_options = tuple(
            RoomOption(
                room_id=room_node.attrib["id"],
                penalty=int(room_node.attrib.get("penalty", "0")),
                unavailable_times=tuple(
                    (
                        item.attrib.get("days", ""),
                        item.attrib.get("weeks", ""),
                        int(item.attrib.get("start", "0")),
                    )
                    for item in room_node.findall("unavailable")
                ),
                timed_penalties=tuple(
                    (
                        item.attrib.get("days", ""),
                        item.attrib.get("weeks", ""),
                        int(item.attrib.get("start", "0")),
                        int(item.attrib.get("penalty", "0")),
                    )
                    for item in room_node.findall("preference")
                ),
            )
            for room_node in class_node.findall("room")
            if room_node.attrib.get("id")
        )
        agents.append(
            ClassAgent(
                class_id=class_id,
                label=class_node.attrib.get("label", "") or class_node.attrib.get("subject", "") or class_id,
                time_options=time_options,
                room_options=room_options,
            )
        )

    distributions = []
    for distribution_node in root.findall(".//distribution"):
        distribution_type = distribution_node.attrib.get("type", "")
        class_ids = tuple(
            class_node.attrib["id"]
            for class_node in distribution_node.findall("class")
            if class_node.attrib.get("id")
        )
        if distribution_type not in SUPPORTED_DISTRIBUTIONS or len(class_ids) < 2:
            continue
        required = distribution_node.attrib.get("required", "false").lower() == "true"
        distributions.append(
            Distribution(
                distribution_id=distribution_node.attrib.get("id", ""),
                distribution_type=distribution_type,
                required=required,
                penalty=int(distribution_node.attrib.get("penalty", "0")),
                class_ids=class_ids,
                name=distribution_node.attrib.get("name", ""),
                scope=distribution_node.attrib.get("scope", ""),
            )
        )

    resource_limits = []
    for limit_node in root.findall("./limits/limit"):
        limit_type = limit_node.attrib.get("type", "")
        class_ids = tuple(
            class_node.attrib["id"]
            for class_node in limit_node.findall("class")
            if class_node.attrib.get("id")
        )
        if limit_type not in {"max_daily_lessons", "consecutive_limit"} or not class_ids:
            continue
        resource_limits.append(
            ResourceLimit(
                constraint_id=limit_node.attrib.get("id", ""),
                limit_type=limit_type,
                required=limit_node.attrib.get("required", "false").lower() == "true",
                penalty=int(limit_node.attrib.get("penalty", "0")),
                limit=max(1, int(limit_node.attrib.get("limit", "1"))),
                class_ids=class_ids,
                name=limit_node.attrib.get("name", ""),
                scope=limit_node.attrib.get("scope", ""),
            )
        )

    return Problem(
        name=root.attrib.get("name", "stt-problem"),
        rooms=rooms,
        agents=tuple(agents),
        distributions=tuple(distributions),
        resource_limits=tuple(resource_limits),
    )


def _actions(agent: ClassAgent) -> list[Action]:
    actions = []
    if agent.room_options:
        for room in agent.room_options:
            for time in agent.time_options:
                time_key = (time.days, time.weeks, time.start)
                if time_key in room.unavailable_times:
                    continue
                timed_penalty = sum(
                    penalty
                    for days, weeks, start, penalty in room.timed_penalties
                    if (days, weeks, start) == time_key
                )
                actions.append(
                    Action(
                        class_id=agent.class_id,
                        time=time,
                        room_id=room.room_id,
                        time_penalty=time.penalty,
                        room_penalty=room.penalty + timed_penalty,
                    )
                )
    else:
        for time in agent.time_options:
            actions.append(
                Action(
                    class_id=agent.class_id,
                    time=time,
                    room_id=None,
                    time_penalty=time.penalty,
                    room_penalty=0,
                )
            )
    return sorted(actions, key=lambda action: (action.base_penalty, action.time.start, action.room_id or ""))


def _agent_order_key(
    agent: ClassAgent,
    distributions: tuple[Distribution, ...],
) -> tuple[int, int, int, int, str]:
    consecutive_positions = [
        (distribution_index, distribution.class_ids.index(agent.class_id))
        for distribution_index, distribution in enumerate(distributions)
        if distribution.distribution_type == "Consecutive"
        and agent.class_id in distribution.class_ids
    ]
    if consecutive_positions:
        distribution_index, class_index = min(consecutive_positions)
        return 0, distribution_index, class_index, len(_actions(agent)), agent.class_id
    return 1, len(distributions), 0, len(_actions(agent)), agent.class_id


def _is_feasible(
    candidate: Action,
    assignments: dict[str, Action],
    distributions: tuple[Distribution, ...],
) -> bool:
    if candidate.room_id:
        for assigned in assignments.values():
            if candidate.room_id == assigned.room_id and _overlaps(candidate.time, assigned.time):
                return False

    for distribution in distributions:
        if not distribution.required or candidate.class_id not in distribution.class_ids:
            continue
        for other_class_id in distribution.class_ids:
            other = assignments.get(other_class_id)
            if other and _violates(distribution, candidate, other):
                return False
    return True


def _incremental_soft_penalty(
    candidate: Action,
    assignments: dict[str, Action],
    distributions: tuple[Distribution, ...],
) -> int:
    penalty = 0
    for distribution in distributions:
        if distribution.required or candidate.class_id not in distribution.class_ids:
            continue
        for other_class_id in distribution.class_ids:
            other = assignments.get(other_class_id)
            if other and _violates(distribution, candidate, other):
                penalty += distribution.penalty
    return penalty


def _score(assignments: dict[str, Action], distributions: tuple[Distribution, ...]) -> dict:
    time_penalty = sum(action.time_penalty for action in assignments.values())
    room_penalty = sum(action.room_penalty for action in assignments.values())
    distribution_penalty = 0
    for distribution in distributions:
        if distribution.required:
            continue
        for left_id, right_id in combinations(distribution.class_ids, 2):
            left = assignments.get(left_id)
            right = assignments.get(right_id)
            if left and right and _violates(distribution, left, right):
                distribution_penalty += distribution.penalty
    return {
        "time_penalty": time_penalty,
        "room_penalty": room_penalty,
        "distribution_penalty": distribution_penalty,
        "total_score": time_penalty + room_penalty + distribution_penalty,
    }


def _violates(distribution: Distribution, left: Action, right: Action) -> bool:
    distribution_type = distribution.distribution_type
    if distribution_type == "NotOverlap":
        return _overlaps(left.time, right.time)
    if distribution_type == "SameRoom":
        return left.room_id != right.room_id
    if distribution_type == "DifferentTime":
        return _shares_week(left.time, right.time) and _shares_day(left.time, right.time) and left.time.start == right.time.start
    if distribution_type == "DifferentDays":
        return _shares_week(left.time, right.time) and _shares_day(left.time, right.time)
    if distribution_type == "DifferentWeeks":
        return _shares_week(left.time, right.time)
    if distribution_type == "SameDays":
        return left.time.days != right.time.days
    if distribution_type == "SameStart":
        return left.time.start != right.time.start
    if distribution_type == "SameTime":
        return (
            left.time.days != right.time.days
            or left.time.weeks != right.time.weeks
            or left.time.start != right.time.start
            or left.time.length != right.time.length
        )
    if distribution_type == "Precedence":
        return _violates_precedence(distribution, left, right)
    if distribution_type == "Consecutive":
        return _violates_consecutive(distribution, left, right)
    if distribution_type == "DifferentWeekSameDaySameStart":
        return (
            _shares_week(left.time, right.time)
            or left.time.days != right.time.days
            or left.time.start != right.time.start
        )
    return False


def _violates_precedence(distribution: Distribution, left: Action, right: Action) -> bool:
    left_index = distribution.class_ids.index(left.class_id)
    right_index = distribution.class_ids.index(right.class_id)
    if left_index == right_index or not _shares_week(left.time, right.time) or not _shares_day(left.time, right.time):
        return False
    if left_index < right_index:
        return left.time.start + left.time.length > right.time.start
    return right.time.start + right.time.length > left.time.start


def _violates_consecutive(distribution: Distribution, left: Action, right: Action) -> bool:
    left_index = distribution.class_ids.index(left.class_id)
    right_index = distribution.class_ids.index(right.class_id)
    if abs(left_index - right_index) != 1:
        return False
    if left_index < right_index:
        earlier, later = left, right
    else:
        earlier, later = right, left
    return (
        earlier.time.weeks != later.time.weeks
        or earlier.time.days != later.time.days
        or (
            later.time.period_index != earlier.time.period_index + 1
            if earlier.time.period_index is not None and later.time.period_index is not None
            else earlier.time.start + earlier.time.length != later.time.start
        )
    )


def _overlaps(left: TimeOption, right: TimeOption) -> bool:
    return (
        _shares_week(left, right)
        and _shares_day(left, right)
        and left.start < right.start + right.length
        and right.start < left.start + left.length
    )


def _shares_week(left: TimeOption, right: TimeOption) -> bool:
    return _shares_bit(left.weeks, right.weeks)


def _shares_day(left: TimeOption, right: TimeOption) -> bool:
    return _shares_bit(left.days, right.days)


def _shares_bit(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return any(left_bit == "1" and right_bit == "1" for left_bit, right_bit in zip(left, right))


def _build_solution_xml(run_id: str, assignments: dict[str, Action], algorithm_config: dict) -> str:
    solution = Element(
        "solution",
        {
            "run": run_id,
            "algorithm": str(algorithm_config.get("algorithm", "cgcs_greedy")),
        },
    )
    for class_id in sorted(assignments):
        action = assignments[class_id]
        attrs = {
            "id": action.class_id,
            "days": action.time.days,
            "weeks": action.time.weeks,
            "start": str(action.time.start),
            "length": str(action.time.length),
        }
        if action.time.period_index is not None:
            attrs["periodIndex"] = str(action.time.period_index)
        if action.room_id:
            attrs["room"] = action.room_id
        SubElement(solution, "class", attrs)
    return tostring(solution, encoding="unicode")


def _failed_result(run_id: str, message: str, assigned_count: int = 0, class_count: int = 0) -> dict:
    return {
        "run_id": run_id,
        "solution_xml": '<solution status="failed" />',
        "hard_violations": 1,
        "assigned_count": assigned_count,
        "class_count": class_count,
        "time_penalty": 0,
        "room_penalty": 0,
        "distribution_penalty": 0,
        "total_score": 0,
        "log": f"{message}（已成功安排 {assigned_count}/{class_count} 个课次）",
    }
