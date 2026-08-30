from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
import os
import time
from xml.etree.ElementTree import fromstring

from ortools.sat.python import cp_model

from .cgcs import (
    Action,
    ClassAgent,
    Distribution,
    Problem,
    TimeOption,
    _actions,
    _build_solution_xml,
    _overlaps,
    _score,
    _violates,
    parse_problem,
    run_cgcs_greedy,
)


DEFAULT_TIME_LIMIT_SECONDS = 60.0
DEFAULT_NUM_WORKERS = min(8, max(1, os.cpu_count() or 1))


@dataclass(frozen=True)
class Candidate:
    ordinal: int
    class_id: str
    action_index: int
    action: Action
    literal: cp_model.IntVar


@dataclass(frozen=True)
class HardConflictSource:
    code: str
    constraint_id: str = ""
    constraint_type: str = ""
    constraint_name: str = ""
    constraint_scope: str = ""
    room_id: str = ""


def run_cp_sat_v1(
    problem_xml: str,
    run_id: str,
    algorithm_config: dict | None = None,
) -> dict:
    config = dict(algorithm_config or {})
    config["algorithm"] = "cp_sat_v1"
    problem = parse_problem(problem_xml)
    started_at = time.perf_counter()

    model = cp_model.CpModel()
    candidates_by_class, assigned_by_class = _create_candidates(model, problem)
    (
        hard_groups,
        hard_pairs,
        soft_pair_weights,
        hard_group_sources,
        hard_pair_sources,
    ) = _compile_constraints(
        problem, candidates_by_class
    )

    candidate_by_ordinal = {
        candidate.ordinal: candidate
        for candidates in candidates_by_class.values()
        for candidate in candidates
    }
    for group in hard_groups:
        model.add_at_most_one(
            candidate_by_ordinal[ordinal].literal for ordinal in group
        )
    for left_ordinal, right_ordinal in hard_pairs:
        left = candidate_by_ordinal[left_ordinal]
        right = candidate_by_ordinal[right_ordinal]
        model.add(left.literal + right.literal <= 1)

    hard_group_memberships: dict[int, set[tuple[int, ...]]] = {}
    for group in hard_groups:
        for ordinal in group:
            hard_group_memberships.setdefault(ordinal, set()).add(group)

    soft_violations: list[tuple[int, cp_model.IntVar]] = []
    for pair, weight in sorted(soft_pair_weights.items()):
        if _pair_is_hard(pair, hard_pairs, hard_group_memberships) or weight == 0:
            continue
        left = candidate_by_ordinal[pair[0]]
        right = candidate_by_ordinal[pair[1]]
        violation = model.new_bool_var(f"soft_{pair[0]}_{pair[1]}")
        model.add(violation <= left.literal)
        model.add(violation <= right.literal)
        model.add(violation >= left.literal + right.literal - 1)
        soft_violations.append((weight, violation))

    quality_objective, score_weight = _build_quality_objective(
        problem,
        candidates_by_class,
        assigned_by_class,
        soft_violations,
    )

    greedy_assignments = _greedy_assignments(
        problem_xml,
        problem,
        str(config.get("warm_start_solution_xml") or ""),
    )
    _add_greedy_hint(model, candidates_by_class, assigned_by_class, greedy_assignments)
    model_build_ms = round((time.perf_counter() - started_at) * 1000, 1)

    time_limit = _bounded_float(
        config.get("time_limit_seconds"), DEFAULT_TIME_LIMIT_SECONDS, 0.1, 1800.0
    )
    num_workers = _bounded_int(
        config.get("num_search_workers"), DEFAULT_NUM_WORKERS, 1, 32
    )
    assigned_count_expression = sum(assigned_by_class.values())
    model.maximize(assigned_count_expression)
    feasibility_solver = _new_solver(config, time_limit, num_workers)
    feasibility_started_at = time.perf_counter()
    feasibility_status = feasibility_solver.solve(model)
    feasibility_search_seconds = time.perf_counter() - feasibility_started_at
    feasibility_status_name = feasibility_solver.status_name(feasibility_status)
    if feasibility_status in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        assignments = _read_assignments(feasibility_solver, candidates_by_class)
        feasibility_objective_value = int(round(feasibility_solver.objective_value))
        feasibility_best_bound = int(round(feasibility_solver.best_objective_bound))
    else:
        assignments = greedy_assignments
        feasibility_objective_value = None
        feasibility_best_bound = None

    status = feasibility_status
    status_name = feasibility_status_name
    quality_status_name = None
    quality_search_ms = 0.0
    objective_value = None
    best_objective_bound = None
    remaining_time = max(0.0, time_limit - feasibility_search_seconds)
    can_optimize_quality = (
        feasibility_status in {cp_model.OPTIMAL, cp_model.FEASIBLE}
        and remaining_time >= 0.1
        and (
            feasibility_status == cp_model.OPTIMAL
            or len(assignments) == len(problem.agents)
        )
    )
    if can_optimize_quality:
        model.add(assigned_count_expression == len(assignments))
        model.clear_objective()
        model.minimize(quality_objective)
        model.clear_hints()
        _add_greedy_hint(model, candidates_by_class, assigned_by_class, assignments)
        quality_solver = _new_solver(config, remaining_time, num_workers, quality=True)
        quality_started_at = time.perf_counter()
        quality_status = quality_solver.solve(model)
        quality_search_ms = round(
            (time.perf_counter() - quality_started_at) * 1000, 1
        )
        quality_status_name = quality_solver.status_name(quality_status)
        if quality_status in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            assignments = _read_assignments(quality_solver, candidates_by_class)
            status = quality_status
            status_name = quality_status_name
            objective_value = int(round(quality_solver.objective_value))
            best_objective_bound = int(round(quality_solver.best_objective_bound))

    metrics = _score(assignments, problem.distributions)
    agents_by_id = {agent.class_id: agent for agent in problem.agents}
    unassigned_ids = [
        agent.class_id for agent in problem.agents if agent.class_id not in assignments
    ]
    unassigned_classes = [
        {"id": class_id, "label": agents_by_id[class_id].label}
        for class_id in unassigned_ids
    ]
    selected_ordinals = _selected_candidate_ordinals(candidates_by_class, assignments)
    unassigned_explanations = _build_unassigned_explanations(
        problem,
        candidates_by_class,
        candidate_by_ordinal,
        selected_ordinals,
        unassigned_ids,
        hard_group_memberships,
        hard_group_sources,
        hard_pair_sources,
        hard_feasibility_proven=feasibility_status == cp_model.OPTIMAL,
    )
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    hard_violations = len(unassigned_ids)
    if feasibility_status in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        if feasibility_status == cp_model.OPTIMAL and hard_violations:
            completion = "已证明当前硬约束下的最大可排结果"
        elif status == cp_model.OPTIMAL:
            completion = "最优解"
        else:
            completion = "当前最佳可行解"
        unassigned_detail = (
            "；未排课："
            + "、".join(
                f"{item['label']}（{item['id']}）" for item in unassigned_classes
            )
            if unassigned_classes
            else ""
        )
        log = (
            f"CP-SAT v1 {completion}：已安排 {len(assignments)}/{len(problem.agents)} 个课次，"
            f"未安排 {hard_violations} 个，软罚分 {metrics['total_score']}，"
            f"耗时 {elapsed_ms:.1f}ms，状态 {status_name}{unassigned_detail}"
        )
    else:
        log = (
            f"CP-SAT v1 在 {time_limit:.1f}s 预算内未返回可行解，已使用贪心初解："
            f"已安排 {len(assignments)}/{len(problem.agents)} 个课次，状态 {status_name}"
        )

    return {
        "run_id": run_id,
        "algorithm": "cp_sat_v1",
        "solution_xml": _build_solution_xml(run_id, assignments, config),
        "hard_violations": hard_violations,
        "assigned_count": len(assignments),
        "class_count": len(problem.agents),
        "unassigned_count": hard_violations,
        "unassigned_class_ids": unassigned_ids,
        "unassigned_classes": unassigned_classes,
        "unassigned_explanations": unassigned_explanations,
        "time_penalty": metrics["time_penalty"],
        "room_penalty": metrics["room_penalty"],
        "distribution_penalty": metrics["distribution_penalty"],
        "total_score": metrics["total_score"],
        "solver_status": status_name,
        "objective_value": objective_value,
        "best_objective_bound": best_objective_bound,
        "score_objective_weight": score_weight,
        "feasibility_status": feasibility_status_name,
        "feasibility_objective_value": feasibility_objective_value,
        "feasibility_best_bound": feasibility_best_bound,
        "hard_feasibility_proven": feasibility_status == cp_model.OPTIMAL,
        "complete_schedule_feasible": not unassigned_ids,
        "max_assignable_count": (
            feasibility_objective_value
            if feasibility_status == cp_model.OPTIMAL
            else None
        ),
        "quality_status": quality_status_name,
        "candidate_count": sum(len(items) for items in candidates_by_class.values()),
        "hard_conflict_count": len(hard_groups) + len(hard_pairs),
        "hard_group_count": len(hard_groups),
        "hard_pair_count": len(hard_pairs),
        "soft_conflict_count": len(soft_violations),
        "num_search_workers": num_workers,
        "model_build_ms": model_build_ms,
        "feasibility_search_ms": round(feasibility_search_seconds * 1000, 1),
        "quality_search_ms": quality_search_ms,
        "elapsed_ms": elapsed_ms,
        "log": log,
    }


def _create_candidates(
    model: cp_model.CpModel,
    problem: Problem,
) -> tuple[dict[str, tuple[Candidate, ...]], dict[str, cp_model.IntVar]]:
    candidates_by_class: dict[str, tuple[Candidate, ...]] = {}
    assigned_by_class: dict[str, cp_model.IntVar] = {}
    ordinal = 0
    for agent in problem.agents:
        candidates = []
        for action_index, action in enumerate(_actions(agent)):
            literal = model.new_bool_var(f"x_{ordinal}")
            candidates.append(
                Candidate(
                    ordinal=ordinal,
                    class_id=agent.class_id,
                    action_index=action_index,
                    action=action,
                    literal=literal,
                )
            )
            ordinal += 1
        assigned = model.new_bool_var(f"assigned_{len(assigned_by_class)}")
        if candidates:
            model.add(sum(candidate.literal for candidate in candidates) == assigned)
        else:
            model.add(assigned == 0)
        candidates_by_class[agent.class_id] = tuple(candidates)
        assigned_by_class[agent.class_id] = assigned
    return candidates_by_class, assigned_by_class


def _compile_constraints(
    problem: Problem,
    candidates_by_class: dict[str, tuple[Candidate, ...]],
) -> tuple[
    set[tuple[int, ...]],
    set[tuple[int, int]],
    dict[tuple[int, int], int],
    dict[tuple[int, ...], set[HardConflictSource]],
    dict[tuple[int, int], set[HardConflictSource]],
]:
    hard_groups: set[tuple[int, ...]] = set()
    hard_pairs: set[tuple[int, int]] = set()
    soft_pair_weights: dict[tuple[int, int], int] = {}
    hard_group_sources: dict[tuple[int, ...], set[HardConflictSource]] = {}
    hard_pair_sources: dict[tuple[int, int], set[HardConflictSource]] = {}

    candidates_by_room: dict[str, list[Candidate]] = {}
    for candidates in candidates_by_class.values():
        for candidate in candidates:
            if candidate.action.room_id:
                candidates_by_room.setdefault(candidate.action.room_id, []).append(candidate)
    for room_id, room_candidates in candidates_by_room.items():
        _compile_conflict_buckets(
            room_candidates,
            signature=lambda candidate: _time_signature(candidate.action.time),
            conflicts=lambda left, right: _cached_overlaps(
                left.action.time, right.action.time
            ),
            hard_groups=hard_groups,
            hard_pairs=hard_pairs,
            hard_group_sources=hard_group_sources,
            hard_pair_sources=hard_pair_sources,
            source=HardConflictSource(code="room_overlap", room_id=room_id),
        )

    for distribution in problem.distributions:
        class_ids = [
            class_id for class_id in distribution.class_ids if class_id in candidates_by_class
        ]
        distribution_candidates = [
            candidate
            for class_id in class_ids
            for candidate in candidates_by_class[class_id]
        ]
        if distribution.required and distribution.distribution_type in {
            "NotOverlap",
            "DifferentDays",
            "DifferentWeeks",
            "DifferentTime",
        }:
            _compile_conflict_buckets(
                distribution_candidates,
                signature=lambda candidate: _distribution_signature(
                    distribution.distribution_type, candidate
                ),
                conflicts=lambda left, right: _violates(
                    distribution, left.action, right.action
                ),
                hard_groups=hard_groups,
                hard_pairs=hard_pairs,
                hard_group_sources=hard_group_sources,
                hard_pair_sources=hard_pair_sources,
                source=_distribution_conflict_source(distribution),
            )
            continue
        for left_id, right_id in combinations(class_ids, 2):
            for left in candidates_by_class[left_id]:
                for right in candidates_by_class[right_id]:
                    if not _violates(distribution, left.action, right.action):
                        continue
                    pair = _candidate_pair(left, right)
                    if distribution.required:
                        hard_pairs.add(pair)
                        hard_pair_sources.setdefault(pair, set()).add(
                            _distribution_conflict_source(distribution)
                        )
                    else:
                        soft_pair_weights[pair] = (
                            soft_pair_weights.get(pair, 0) + distribution.penalty
                        )
    return (
        hard_groups,
        hard_pairs,
        soft_pair_weights,
        hard_group_sources,
        hard_pair_sources,
    )


def _compile_conflict_buckets(
    candidates: list[Candidate],
    *,
    signature,
    conflicts,
    hard_groups: set[tuple[int, ...]],
    hard_pairs: set[tuple[int, int]],
    hard_group_sources: dict[tuple[int, ...], set[HardConflictSource]],
    hard_pair_sources: dict[tuple[int, int], set[HardConflictSource]],
    source: HardConflictSource,
) -> None:
    buckets: dict[object, list[Candidate]] = {}
    for candidate in candidates:
        buckets.setdefault(signature(candidate), []).append(candidate)

    ordered_buckets = list(buckets.values())
    for bucket in ordered_buckets:
        if len({candidate.class_id for candidate in bucket}) >= 2:
            group = tuple(sorted(candidate.ordinal for candidate in bucket))
            hard_groups.add(group)
            hard_group_sources.setdefault(group, set()).add(source)

    for left_index, left_bucket in enumerate(ordered_buckets):
        left_representative = left_bucket[0]
        for right_bucket in ordered_buckets[left_index + 1 :]:
            right_representative = right_bucket[0]
            if not conflicts(left_representative, right_representative):
                continue
            for left in left_bucket:
                for right in right_bucket:
                    if left.class_id != right.class_id:
                        pair = _candidate_pair(left, right)
                        hard_pairs.add(pair)
                        hard_pair_sources.setdefault(pair, set()).add(source)


def _distribution_signature(distribution_type: str, candidate: Candidate) -> object:
    time_option = candidate.action.time
    if distribution_type == "NotOverlap":
        return _time_signature(time_option)
    if distribution_type == "DifferentDays":
        return time_option.weeks, time_option.days
    if distribution_type == "DifferentWeeks":
        return time_option.weeks
    return time_option.weeks, time_option.days, time_option.start


def _time_signature(time_option: TimeOption) -> tuple[str, str, int, int]:
    return (
        time_option.weeks,
        time_option.days,
        time_option.start,
        time_option.length,
    )


def _pair_is_hard(
    pair: tuple[int, int],
    hard_pairs: set[tuple[int, int]],
    hard_group_memberships: dict[int, set[tuple[int, ...]]],
) -> bool:
    if pair in hard_pairs:
        return True
    return bool(
        hard_group_memberships.get(pair[0], set())
        & hard_group_memberships.get(pair[1], set())
    )


def _distribution_conflict_source(distribution: Distribution) -> HardConflictSource:
    scope_codes = {
        "auto-homeroom": "homeroom_overlap",
        "auto-teacher": "teacher_overlap",
        "auto-room": "room_overlap",
    }
    type_codes = {
        "NotOverlap": "not_overlap",
        "DifferentTime": "different_time",
        "DifferentDays": "different_days",
        "DifferentWeeks": "different_weeks",
        "SameDays": "same_days",
        "SameStart": "same_start",
        "SameTime": "same_time",
        "SameRoom": "same_room",
        "Precedence": "precedence",
        "Consecutive": "consecutive",
        "DifferentWeekSameDaySameStart": "different_week_same_day_same_start",
    }
    return HardConflictSource(
        code=scope_codes.get(
            distribution.scope,
            type_codes.get(distribution.distribution_type, "hard_constraint"),
        ),
        constraint_id=distribution.distribution_id,
        constraint_type=distribution.distribution_type,
        constraint_name=distribution.name,
        constraint_scope=distribution.scope,
    )


def _selected_candidate_ordinals(
    candidates_by_class: dict[str, tuple[Candidate, ...]],
    assignments: dict[str, Action],
) -> set[int]:
    return {
        candidate.ordinal
        for class_id, candidates in candidates_by_class.items()
        for candidate in candidates
        if assignments.get(class_id) == candidate.action
    }


def _build_unassigned_explanations(
    problem: Problem,
    candidates_by_class: dict[str, tuple[Candidate, ...]],
    candidate_by_ordinal: dict[int, Candidate],
    selected_ordinals: set[int],
    unassigned_ids: list[str],
    hard_group_memberships: dict[int, set[tuple[int, ...]]],
    hard_group_sources: dict[tuple[int, ...], set[HardConflictSource]],
    hard_pair_sources: dict[tuple[int, int], set[HardConflictSource]],
    *,
    hard_feasibility_proven: bool,
) -> list[dict]:
    agents_by_id = {agent.class_id: agent for agent in problem.agents}
    room_names = {
        room.room_id: room.name
        for room in problem.rooms
        if room.name
    }
    pair_neighbors: dict[int, list[tuple[int, set[HardConflictSource]]]] = {}
    for (left_ordinal, right_ordinal), sources in hard_pair_sources.items():
        pair_neighbors.setdefault(left_ordinal, []).append((right_ordinal, sources))
        pair_neighbors.setdefault(right_ordinal, []).append((left_ordinal, sources))

    explanations: list[dict] = []
    for class_id in unassigned_ids:
        candidates = candidates_by_class.get(class_id, ())
        reason_states: dict[tuple[str, ...], dict] = {}
        candidate_details: list[dict] = []
        blocked_candidate_count = 0

        for candidate in candidates:
            blocker_map: dict[tuple[tuple[str, ...], int], dict] = {}
            for group in hard_group_memberships.get(candidate.ordinal, set()):
                selected_in_group = next(
                    (
                        ordinal
                        for ordinal in group
                        if ordinal != candidate.ordinal and ordinal in selected_ordinals
                    ),
                    None,
                )
                if selected_in_group is None:
                    continue
                for source in hard_group_sources.get(group, set()):
                    _add_candidate_blocker(
                        blocker_map,
                        source,
                        selected_in_group,
                        candidate_by_ordinal,
                        agents_by_id,
                    )

            for other_ordinal, sources in pair_neighbors.get(candidate.ordinal, []):
                if other_ordinal not in selected_ordinals:
                    continue
                for source in sources:
                    _add_candidate_blocker(
                        blocker_map,
                        source,
                        other_ordinal,
                        candidate_by_ordinal,
                        agents_by_id,
                    )

            blockers = sorted(
                blocker_map.values(),
                key=lambda item: (
                    str(item.get("code") or ""),
                    str(item.get("constraint_id") or ""),
                    str(item.get("conflicting_class_id") or ""),
                ),
            )
            if blockers:
                blocked_candidate_count += 1
            candidate_time = _action_time_payload(candidate.action)
            candidate_details.append(
                {
                    "candidate_ordinal": candidate.ordinal,
                    "time": candidate_time,
                    "room_id": candidate.action.room_id,
                    "blocked": bool(blockers),
                    "blockers": blockers,
                }
            )
            for blocker in blockers:
                source_key = _source_key_from_payload(blocker)
                state = reason_states.setdefault(
                    source_key,
                    {
                        "source": blocker,
                        "candidate_ordinals": set(),
                        "candidate_times": set(),
                        "conflicting_lessons": {},
                    },
                )
                state["candidate_ordinals"].add(candidate.ordinal)
                state["candidate_times"].add(str(candidate_time["label"]))
                conflicting_class_id = str(blocker.get("conflicting_class_id") or "")
                if conflicting_class_id:
                    conflicting_time = blocker.get("conflicting_time") or {}
                    state["conflicting_lessons"][conflicting_class_id] = {
                        "label": str(blocker.get("conflicting_label") or conflicting_class_id),
                        "time": str(conflicting_time.get("label") or ""),
                    }

        candidate_count = len(candidates)
        reason_groups = [
            _build_reason_group(state, candidate_count, room_names)
            for state in reason_states.values()
        ]
        reason_groups.sort(
            key=lambda item: (
                -int(item.get("blocked_candidate_count") or 0),
                str(item.get("title") or ""),
            )
        )
        label = agents_by_id.get(class_id).label if class_id in agents_by_id else class_id
        unblocked_count = candidate_count - blocked_candidate_count
        if candidate_count == 0:
            summary = (
                f"系统没有为 {label} 生成可尝试的上课时间和教室组合，"
                "请检查这节课的可用时间和教室设置"
            )
        elif unblocked_count == 0:
            summary = (
                f"系统为 {label} 尝试了 {candidate_count} 个可选的上课时间和教室组合，"
                "但每一个都会违反至少一条必须遵守的规则，所以暂时无法排入课表"
            )
        else:
            summary = (
                f"系统为 {label} 尝试了 {candidate_count} 个可选的上课时间和教室组合；"
                f"其中 {blocked_candidate_count} 个与已排课程直接冲突，剩余 {unblocked_count} 个"
                "虽然没有发现直接冲突，但在本次求解时间内仍未被选中"
            )

        explanations.append(
            {
                "class_id": class_id,
                "label": label,
                "candidate_count": candidate_count,
                "blocked_candidate_count": blocked_candidate_count,
                "unblocked_candidate_count": unblocked_count,
                "explanation_complete": candidate_count == 0 or unblocked_count == 0,
                "proof_status": (
                    "maximum_assignable_proven"
                    if hard_feasibility_proven
                    else "current_solution_only"
                ),
                "summary": summary,
                "reason_groups": reason_groups,
                "candidate_details": candidate_details,
            }
        )
    return explanations


def _add_candidate_blocker(
    blocker_map: dict[tuple[tuple[str, ...], int], dict],
    source: HardConflictSource,
    other_ordinal: int,
    candidate_by_ordinal: dict[int, Candidate],
    agents_by_id: dict[str, ClassAgent],
) -> None:
    other = candidate_by_ordinal.get(other_ordinal)
    if other is None:
        return
    source_payload = _source_payload(source)
    if source.code == "room_overlap" and not source_payload.get("room_id"):
        source_payload["room_id"] = other.action.room_id or ""
    key = (_source_key(source), other_ordinal)
    blocker_map[key] = {
        **source_payload,
        "conflicting_class_id": other.class_id,
        "conflicting_label": (
            agents_by_id[other.class_id].label
            if other.class_id in agents_by_id
            else other.class_id
        ),
        "conflicting_time": _action_time_payload(other.action),
        "conflicting_room_id": other.action.room_id,
    }


def _source_key(source: HardConflictSource) -> tuple[str, ...]:
    return (
        source.code,
        source.constraint_id,
        source.constraint_type,
        source.constraint_name,
        source.constraint_scope,
        source.room_id,
    )


def _source_key_from_payload(payload: dict) -> tuple[str, ...]:
    if payload.get("code") == "room_overlap":
        return (
            "room_overlap",
            "",
            "",
            "",
            "",
            str(payload.get("room_id") or ""),
        )
    return tuple(
        str(payload.get(key) or "")
        for key in (
            "code",
            "constraint_id",
            "constraint_type",
            "constraint_name",
            "constraint_scope",
            "room_id",
        )
    )


def _source_payload(source: HardConflictSource) -> dict:
    return {
        "code": source.code,
        "constraint_id": source.constraint_id,
        "constraint_type": source.constraint_type,
        "constraint_name": source.constraint_name,
        "constraint_scope": source.constraint_scope,
        "room_id": source.room_id,
    }


def _build_reason_group(
    state: dict,
    candidate_count: int,
    room_names: dict[str, str],
) -> dict:
    source = dict(state["source"])
    conflicting_lessons = [
        {"class_id": class_id, **lesson}
        for class_id, lesson in sorted(state["conflicting_lessons"].items())
    ]
    blocked_count = len(state["candidate_ordinals"])
    title = _reason_title(source, room_names)
    room_id = str(source.get("room_id") or "")
    room_name = room_names.get(room_id, "")
    lesson_names = "、".join(
        (
            f"{item['label']}（{item['time']}）"
            if item.get("time")
            else str(item["label"])
        )
        for item in conflicting_lessons[:4]
    )
    if len(conflicting_lessons) > 4:
        lesson_names += f" 等 {len(conflicting_lessons)} 个课次"
    type_name = str(source.get("constraint_type") or "")
    code = str(source.get("code") or "")
    if type_name == "DifferentDays":
        reason = f"这些选择与已经排好的 {lesson_names} 落在同一天"
    elif type_name == "Consecutive":
        reason = f"这些选择无法和已经排好的 {lesson_names} 连续安排"
    elif type_name == "Precedence":
        reason = f"这些选择无法和已经排好的 {lesson_names} 保持要求的先后顺序"
    elif code == "room_overlap" and lesson_names:
        reason = f"这些时间里，{room_name or '所选教室'} 已经安排了 {lesson_names}"
    elif lesson_names:
        reason = f"这些时间与已经排好的 {lesson_names} 重叠"
    else:
        reason = "这些选择会违反这条必须遵守的规则"
    return {
        "code": source.get("code"),
        "title": title,
        "detail": (
            f"尝试的 {candidate_count} 个上课时间和教室组合中，有 {blocked_count} 个"
            f"因为这条规则不可用；{reason}"
        ),
        "blocked_candidate_count": blocked_count,
        "candidate_count": candidate_count,
        "constraint_id": source.get("constraint_id"),
        "constraint_type": source.get("constraint_type"),
        "constraint_name": source.get("constraint_name"),
        "constraint_scope": source.get("constraint_scope"),
        "room_id": room_id,
        "room_name": room_name,
        "conflicting_lessons": conflicting_lessons,
        "candidate_times": sorted(state["candidate_times"]),
    }


def _reason_title(source: dict, room_names: dict[str, str]) -> str:
    room_id = str(source.get("room_id") or "")
    room_name = room_names.get(room_id, "")
    code_titles = {
        "homeroom_overlap": "班级在同一时间只能上一节课",
        "teacher_overlap": "教师在同一时间只能上一节课",
        "room_overlap": f"“{room_name or '所选教室'}”同一时间只能安排一节课",
        "different_days": "同一门课程需要分散到不同天",
        "different_weeks": "相关课次需要安排在不同教学周",
        "different_time": "相关课次不能安排在同一时间",
        "same_days": "相关课次需要安排在同一天",
        "same_start": "相关课次需要同时开始",
        "same_time": "相关课次需要安排在完全相同的时间",
        "same_room": "相关课次需要安排在同一间教室",
        "precedence": "相关课次需要按照指定先后顺序上课",
        "consecutive": "相关课次需要连续安排",
        "not_overlap": "相关课次不能安排在同一时间",
    }
    code = str(source.get("code") or "")
    if code in code_titles:
        return code_titles[code]
    if source.get("constraint_name"):
        return str(source["constraint_name"])
    return "必须遵守的排课规则"


def _action_time_payload(action: Action) -> dict:
    weekdays = [index + 1 for index, bit in enumerate(action.time.days) if bit == "1"]
    weekday_text = "、".join(f"周{weekday}" for weekday in weekdays) or "未指定日期"
    period_text = (
        f"第{action.time.period_index}节"
        if action.time.period_index is not None
        else f"时隙 {action.time.start}"
    )
    return {
        "weekdays": weekdays,
        "day_bits": action.time.days,
        "week_bits": action.time.weeks,
        "start_slot": action.time.start,
        "length_slots": action.time.length,
        "period_index": action.time.period_index,
        "label": f"{weekday_text}{period_text}",
    }


def _build_quality_objective(
    problem: Problem,
    candidates_by_class: dict[str, tuple[Candidate, ...]],
    assigned_by_class: dict[str, cp_model.IntVar],
    soft_violations: list[tuple[int, cp_model.IntVar]],
) -> tuple[cp_model.LinearExpr, int]:
    class_count = len(problem.agents)
    candidate_count = sum(len(items) for items in candidates_by_class.values())
    tie_bound = max(1, class_count * class_count + candidate_count)
    score_weight = tie_bound + 1
    terms = []
    for agent_index, agent in enumerate(problem.agents):
        assigned = assigned_by_class[agent.class_id]
        unassigned_tie = class_count - agent_index
        terms.append(unassigned_tie * (1 - assigned))
        for candidate in candidates_by_class[agent.class_id]:
            candidate_tie = candidate.action_index
            terms.append(
                (candidate.action.base_penalty * score_weight + candidate_tie)
                * candidate.literal
            )
    for weight, violation in soft_violations:
        terms.append(weight * score_weight * violation)
    return sum(terms), score_weight


def _new_solver(
    config: dict,
    time_limit: float,
    num_workers: int,
    *,
    quality: bool = False,
) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = num_workers
    solver.parameters.random_seed = _bounded_int(
        config.get("seed"), 0, 0, 2_147_483_647
    )
    solver.parameters.log_search_progress = bool(config.get("log_search_progress", False))
    if quality:
        relative_gap_limit = _bounded_float(
            config.get("relative_gap_limit"), 0.0, 0.0, 1.0
        )
        if relative_gap_limit > 0:
            solver.parameters.relative_gap_limit = relative_gap_limit
    return solver


@lru_cache(maxsize=None)
def _cached_overlaps(left: TimeOption, right: TimeOption) -> bool:
    return _overlaps(left, right)


def _greedy_assignments(
    problem_xml: str,
    problem: Problem,
    warm_start_solution_xml: str = "",
) -> dict[str, Action]:
    result = (
        {"solution_xml": warm_start_solution_xml}
        if warm_start_solution_xml
        else run_cgcs_greedy(
            problem_xml,
            "cp-sat-warm-start",
            {"algorithm": "cgcs_greedy"},
        )
    )
    selected = {}
    root = fromstring(str(result.get("solution_xml") or "<solution />"))
    for class_node in root.findall(".//class"):
        class_id = class_node.attrib.get("id")
        if not class_id:
            continue
        selected[class_id] = (
            class_node.attrib.get("days", ""),
            class_node.attrib.get("weeks", ""),
            int(class_node.attrib.get("start", "0")),
            int(class_node.attrib.get("length", "1")),
            (
                int(class_node.attrib["periodIndex"])
                if class_node.attrib.get("periodIndex") is not None
                else None
            ),
            class_node.attrib.get("room"),
        )

    assignments = {}
    agents_by_id: dict[str, ClassAgent] = {agent.class_id: agent for agent in problem.agents}
    for class_id, key in selected.items():
        agent = agents_by_id.get(class_id)
        if agent is None:
            continue
        action = next((item for item in _actions(agent) if _action_key(item) == key), None)
        if action is not None:
            assignments[class_id] = action
    return assignments


def _add_greedy_hint(
    model: cp_model.CpModel,
    candidates_by_class: dict[str, tuple[Candidate, ...]],
    assigned_by_class: dict[str, cp_model.IntVar],
    assignments: dict[str, Action],
) -> None:
    for class_id, candidates in candidates_by_class.items():
        selected = assignments.get(class_id)
        model.add_hint(assigned_by_class[class_id], int(selected is not None))
        for candidate in candidates:
            model.add_hint(candidate.literal, int(selected == candidate.action))


def _read_assignments(
    solver: cp_model.CpSolver,
    candidates_by_class: dict[str, tuple[Candidate, ...]],
) -> dict[str, Action]:
    assignments = {}
    for class_id, candidates in candidates_by_class.items():
        selected = next(
            (candidate.action for candidate in candidates if solver.value(candidate.literal)),
            None,
        )
        if selected is not None:
            assignments[class_id] = selected
    return assignments


def _candidate_pair(left: Candidate, right: Candidate) -> tuple[int, int]:
    return tuple(sorted((left.ordinal, right.ordinal)))


def _action_key(action: Action) -> tuple[str, str, int, int, int | None, str | None]:
    return (
        action.time.days,
        action.time.weeks,
        action.time.start,
        action.time.length,
        action.time.period_index,
        action.room_id,
    )


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bounded_float(value: object, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))
