from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from typing import Any
SchedulingRepository = Any
from stt_desktop.agent.upstream.distributions import parse_distribution


ALLOWED_AGENT_ACTIONS: dict[str, set[str]] = {
    "term": {"update", "bulk_upsert"},
    "teacher": {"create", "update", "delete", "bulk_upsert"},
    "homeroom": {"create", "update", "delete", "bulk_upsert"},
    "subject": {"create", "update", "delete", "bulk_upsert"},
    "room_type": {"create", "update", "delete", "bulk_upsert"},
    "room": {"create", "update", "delete", "bulk_upsert"},
    "timetable_template": {"create", "update", "delete", "bulk_upsert"},
    "course_plan": {"create", "update", "delete", "bulk_upsert", "mark_not_scheduled"},
    "task": {"create", "update", "delete", "bulk_upsert"},
    "constraint": {"create", "update", "delete", "bulk_upsert"},
    "run": {"run"},
}

TARGET_LABELS = {
    "term": "学期",
    "teacher": "教师",
    "homeroom": "班级",
    "subject": "科目",
    "room_type": "教室类型",
    "room": "教室",
    "timetable_template": "课表模板",
    "course_plan": "课程计划",
    "task": "授课任务",
    "constraint": "约束",
    "run": "排课运行",
}

PLACEHOLDER_VALUES = {"待确认", "待补充", "未知", "unknown", "tbd", "todo", "待定"}


@dataclass
class ActionCompilationError(ValueError):
    issues: list[dict]

    def __str__(self) -> str:
        return "；".join(str(item.get("message") or "操作信息不完整") for item in self.issues)


def compile_agent_actions(
    repository: SchedulingRepository,
    organization_id: str,
    project_id: str | None,
    proposals: list[dict],
    *,
    source_summary: dict | None = None,
) -> dict:
    if not proposals:
        raise ActionCompilationError([{"code": "no_action", "message": "没有可执行的操作。"}])
    school_data = repository.list_school_data(organization_id)
    planning = repository.list_planning_data(organization_id, project_id) if project_id else {}
    if project_id:
        planning = {
            **planning,
            "constraints": repository.list_constraints(organization_id, project_id).get("constraints", []),
        }
    template_data = repository.list_weekly_timetable_templates(organization_id, project_id)
    state = _CompilerState(organization_id, project_id, school_data, planning, template_data)
    items: list[dict] = []
    issues: list[dict] = []
    summaries: list[str] = []
    dependency_order = {
        "term": 0,
        "teacher": 1,
        "homeroom": 1,
        "subject": 1,
        "room_type": 1,
        "room": 2,
        "timetable_template": 2,
        "course_plan": 3,
        "task": 4,
        "constraint": 5,
        "run": 6,
    }
    ordered_proposals = sorted(
        enumerate(proposals),
        key=lambda entry: (dependency_order.get(_text(entry[1].get("target")), 99), entry[0]),
    )
    for proposal_index, proposal in ordered_proposals:
        try:
            compiled = _compile_proposal(
                state,
                proposal,
                organization_id=organization_id,
                project_id=project_id,
                proposal_index=proposal_index,
            )
            items.extend(compiled)
            summary = str(proposal.get("human_summary") or "").strip()
            if summary:
                summaries.append(summary)
        except ActionCompilationError as exc:
            issues.extend(exc.issues)
    if issues:
        raise ActionCompilationError(issues)
    actionable = [item for item in items if item["operation"] != "skip"]
    if not actionable:
        raise ActionCompilationError(
            [{"code": "no_changes", "message": "当前数据库已经符合要求，没有需要确认的变更。"}]
        )
    for index, item in enumerate(items):
        item["item_index"] = index
        item["item_key"] = item.get("item_key") or f"{item['target']}:{index}:{item['snapshot_hash'][:12]}"
    snapshot_hash = _hash_json([item["snapshot_hash"] for item in items])
    counts = _counts(items)
    target_names = [TARGET_LABELS.get(target, target) for target in dict.fromkeys(item["target"] for item in items)]
    summary = "；".join(dict.fromkeys(summaries)) or f"更新{'、'.join(target_names)}"
    risk = "high" if any(item["operation"] in {"delete", "run"} for item in items) else "medium"
    return {
        "scope": "project" if project_id else "organization",
        "operation": "change_set",
        "target": "change_set",
        "payload": {"compiler": "agent_actions_v2", "original_proposals": proposals},
        "human_summary": summary,
        "risk_level": risk,
        "schema_version": 2,
        "revision": 1,
        "item_count": len(items),
        "snapshot_hash": snapshot_hash,
        "source_summary": source_summary or {},
        "preview": {
            "can_execute": True,
            "summary": summary,
            "target_label": "、".join(target_names),
            "operation_label": summary,
            "counts": counts,
            "warnings": ["修改科目默认课长会同步该科目已有课程计划、授课任务和课次的课长。"] if any(
                item["target"] == "subject" and item["operation"] == "update"
                and (item["before_data"] or {}).get("default_duration_slots") != (item["after_data"] or {}).get("default_duration_slots")
                for item in items
            ) else [],
            "sample_names": [str(item["display_data"].get("name") or item["item_key"]) for item in items[:5]],
        },
        "dedupe_key": _hash_json(
            [
                {
                    "target": item["target"],
                    "operation": item["operation"],
                    "identity": item["identity"],
                    "after": item["after_data"],
                }
                for item in items
            ]
        )[:32],
        "items": items,
        "original_proposals": proposals,
    }


class _CompilerState:
    def __init__(
        self,
        organization_id: str,
        project_id: str | None,
        school_data: dict,
        planning: dict,
        template_data: dict,
    ) -> None:
        self.organization_id = organization_id
        self.project_id = project_id
        self.school_data = school_data
        self.planning = planning
        self.by_id: dict[str, dict[str, dict]] = {}
        self.by_name: dict[str, dict[str, list[dict]]] = {}
        source_keys = {
            "teacher": "teachers",
            "homeroom": "homerooms",
            "subject": "subjects",
            "room_type": "room_types",
            "room": "rooms",
        }
        for target, key in source_keys.items():
            records = [dict(item) for item in school_data.get(key, []) if isinstance(item, dict)]
            self.by_id[target] = {str(item.get("id")): item for item in records if item.get("id")}
            names: dict[str, list[dict]] = {}
            for item in records:
                name = _text(item.get("name"))
                if name:
                    names.setdefault(name, []).append(item)
            self.by_name[target] = names
        self.course_plans = [dict(item) for item in planning.get("course_plans", []) if isinstance(item, dict)]
        self.tasks = [dict(item) for item in planning.get("teaching_tasks", []) if isinstance(item, dict)]
        lessons = [dict(item) for item in planning.get("task_lessons", []) if isinstance(item, dict)]
        self.lessons = lessons
        self.lesson_ids = {str(item.get("id")) for item in lessons if item.get("id")}
        self.timetable_templates = [
            dict(item)
            for item in template_data.get("weekly_timetable_templates", [])
            if isinstance(item, dict)
        ]
        self.constraints = [dict(item) for item in planning.get("constraints", []) if isinstance(item, dict)]

    def planned_id(self, target: str, identity: dict) -> str:
        seed = _hash_json(
            {
                "organization_id": self.organization_id,
                "project_id": self.project_id,
                "target": target,
                "identity": identity,
            }
        )
        return str(uuid5(NAMESPACE_URL, f"stt-agent-action:{seed}"))

    def register_school(self, target: str, record: dict) -> None:
        record_id = _text(record.get("id"))
        name = _text(record.get("name"))
        if record_id:
            self.by_id[target][record_id] = record
            for existing_name, records in self.by_name[target].items():
                self.by_name[target][existing_name] = [
                    item for item in records if _text(item.get("id")) != record_id
                ]
        if name:
            self.by_name[target][name] = [*self.by_name[target].get(name, []), record]

    def remove_school(self, target: str, record: dict) -> None:
        record_id = _text(record.get("id"))
        name = _text(record.get("name"))
        self.by_id[target].pop(record_id, None)
        if name:
            self.by_name[target][name] = [
                item for item in self.by_name[target].get(name, []) if _text(item.get("id")) != record_id
            ]


def _compile_proposal(
    state: _CompilerState,
    proposal: dict,
    *,
    organization_id: str,
    project_id: str | None,
    proposal_index: int,
) -> list[dict]:
    target = _text(proposal.get("target"))
    operation = _text(proposal.get("operation"))
    if operation not in ALLOWED_AGENT_ACTIONS.get(target, set()):
        raise ActionCompilationError(
            [{"code": "unsupported_action", "message": f"AI 当前不支持执行 {operation or '未知操作'} {target or '未知对象'}。"}]
        )
    if target in {"timetable_template", "course_plan", "task", "constraint", "run"} and not project_id:
        raise ActionCompilationError([{"code": "project_required", "message": f"{TARGET_LABELS[target]}操作必须先选择项目。"}])
    payload = proposal.get("payload")
    if not isinstance(payload, dict):
        raise ActionCompilationError([{"code": "invalid_payload", "message": "操作数据必须是结构化对象。"}])
    if _contains_placeholder(payload):
        raise ActionCompilationError([{"code": "placeholder_value", "message": "操作中仍有“待确认”或未知值，请补充信息后重试。"}])
    if target == "course_plan" and operation == "mark_not_scheduled":
        return _compile_not_scheduled(state, payload, proposal_index)
    if target == "constraint" and operation == "bulk_upsert":
        return _compile_constraint_groups(state, payload, proposal_index)
    if target == "task" and operation == "bulk_upsert" and isinstance(payload.get("scope_query"), dict):
        raw_items = _expand_task_scope_items(state, payload)
    elif operation == "delete" and isinstance(payload.get("ids"), list):
        raw_items = [{"id": value} for value in payload["ids"]]
    elif operation == "delete" and isinstance(payload.get("names"), list):
        raw_items = [{"name": value} for value in payload["names"]]
    else:
        raw_items = payload.get("items") if operation == "bulk_upsert" else [payload]
    if operation == "bulk_upsert" and (not isinstance(raw_items, list) or not raw_items):
        raise ActionCompilationError([{"code": "missing_items", "message": "批量操作缺少非空 items 列表，请重新描述具体记录。"}])
    if not isinstance(raw_items, list):
        raise ActionCompilationError([{"code": "invalid_items", "message": "items 必须是数组。"}])
    if target == "task":
        raw_items = _merge_task_items(raw_items)
    compiled: list[dict] = []
    for item_index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ActionCompilationError(
                [{"code": "invalid_item", "message": f"第 {item_index + 1} 项不是结构化记录。"}]
            )
        source_ref = _source_ref(raw, proposal_index, item_index)
        if target in state.by_id:
            compiled.append(_compile_school_item(state, target, operation, raw, source_ref))
        elif target == "term":
            compiled.append(_compile_term(state, raw, source_ref))
        elif target == "timetable_template":
            compiled.append(_compile_timetable_template(state, raw, operation, source_ref))
        elif target == "course_plan":
            compiled.append(_compile_course_plan(state, raw, operation, source_ref))
        elif target == "task":
            if operation != "delete" and not raw.get("course_plan_id"):
                homeroom_id = _resolve_reference(state, "homeroom", raw, required=True)
                subject_id = _resolve_reference(state, "subject", raw, required=True)
                if not any(item.get("homeroom_id") == homeroom_id and item.get("subject_id") == subject_id for item in state.course_plans):
                    compiled.append(_compile_course_plan(state, {"homeroom_id": homeroom_id, "subject_id": subject_id}, "create", source_ref))
            compiled.append(
                _compile_task(
                    state,
                    raw,
                    source_ref,
                    requested_operation=operation,
                )
            )
        elif target == "constraint":
            compiled.append(_compile_constraint(state, raw, operation, source_ref))
        elif target == "run":
            compiled.append(_new_item("run", "run", {"project_id": project_id}, None, raw, source_ref, "发起排课"))
    return compiled


def _compile_not_scheduled(state: _CompilerState, payload: dict, proposal_index: int) -> list[dict]:
    pairs = _expand_not_scheduled_scope(state, payload) if "scope_query" in payload else payload.get("items")
    if "scope_query" in payload and not pairs:
        raise ActionCompilationError([{"code": "no_changes", "message": "没有符合条件且需要设为不安排的课程。"}])
    if not isinstance(pairs, list) or not pairs:
        raise ActionCompilationError([{"code": "missing_items", "message": "批量不安排必须列出具体班级和科目。"}])
    compiled = []
    seen = set()
    for index, raw in enumerate(pairs):
        if not isinstance(raw, dict):
            raise ActionCompilationError([{"code": "invalid_item", "message": "不安排明细必须包含班级和科目。"}])
        homeroom_id = _resolve_reference(state, "homeroom", raw, required=True)
        subject_id = _resolve_reference(state, "subject", raw, required=True)
        if (homeroom_id, subject_id) in seen:
            continue
        seen.add((homeroom_id, subject_id))
        source_ref = _source_ref(raw, proposal_index, index)
        tasks = [task for task in state.tasks if task.get("homeroom_id") == homeroom_id and task.get("subject_id") == subject_id]
        if tasks and payload.get("remove_existing_tasks") is not True:
            raise ActionCompilationError([{"code": "existing_tasks_require_confirmation", "message": "部分科目已有授课任务。设为不安排会删除任务及课次，请先征求用户确认；不删除要求下不能执行。"}])
        for task in tasks:
            compiled.append(_compile_task(state, {"id": task["id"]}, source_ref, requested_operation="delete"))
        plan = _compile_course_plan(state, {
            "homeroom_id": homeroom_id, "subject_id": subject_id, "weekly_slots": 0,
            "duration_slots": state.by_id["subject"][subject_id].get("default_duration_slots") or 1,
        }, "bulk_upsert", source_ref)
        plan["display_data"]["arrangement"] = "不安排"
        compiled.append(plan)
        removed_ids = {task["id"] for task in tasks}
        state.tasks = [task for task in state.tasks if task["id"] not in removed_ids]
    return compiled


def _expand_not_scheduled_scope(state: _CompilerState, payload: dict) -> list[dict]:
    query = payload.get("scope_query")
    allowed = {"condition", "all_homerooms", "homeroom_ids", "subject_ids", "include_unconfigured"}
    if set(payload) - {"scope_query", "remove_existing_tasks"} or not isinstance(query, dict) or set(query) - allowed:
        raise ActionCompilationError([{"code": "invalid_scope", "message": "不安排筛选包含未知字段或混用了items，不允许忽略筛选条件。"}])
    if query.get("condition") not in {"zero_lessons", "no_tasks"}:
        raise ActionCompilationError([{"code": "invalid_scope", "message": "不安排筛选必须明确选择zero_lessons（零课次）或no_tasks（无授课任务）。"}])
    for key in ("all_homerooms", "include_unconfigured"):
        if key in query and not isinstance(query[key], bool):
            raise ActionCompilationError([{"code": "invalid_scope", "message": f"{key}必须为布尔值。"}])
    homerooms = _string_set(query.get("homeroom_ids"), "班级ID")
    subjects = _string_set(query.get("subject_ids"), "科目ID")
    if bool(homerooms) == (query.get("all_homerooms") is True):
        raise ActionCompilationError([{"code": "invalid_scope", "message": "必须选择明确班级ID或全部班级，不能同时选择。"}])
    if ("subject_ids" in query and not subjects) or ("homeroom_ids" in query and not homerooms):
        raise ActionCompilationError([{"code": "invalid_scope", "message": "范围ID列表不能为空，不能将空范围扩大为全部。"}])
    if homerooms - state.by_id["homeroom"].keys() or subjects - state.by_id["subject"].keys():
        raise ActionCompilationError([{"code": "invalid_scope", "message": "筛选包含不存在或无权限访问的班级、科目ID。"}])
    homerooms = homerooms or set(state.by_id["homeroom"])
    subjects = subjects or set(state.by_id["subject"])
    plans = {(str(p.get("homeroom_id")), str(p.get("subject_id"))): p for p in state.course_plans}
    tasks_by_pair = {}
    for task in state.tasks:
        tasks_by_pair.setdefault((str(task.get("homeroom_id")), str(task.get("subject_id"))), []).append(task)
    lesson_counts = {}
    for lesson in state.lessons:
        key = str(lesson.get("teaching_task_id"))
        lesson_counts[key] = lesson_counts.get(key, 0) + 1
    pairs = []
    for h in sorted(homerooms):
        for s in sorted(subjects):
            plan, tasks = plans.get((h, s)), tasks_by_pair.get((h, s), [])
            if not plan and not tasks and query.get("include_unconfigured") is not True:
                continue
            if plan and plan.get("weekly_slots") == 0 and not tasks:
                continue
            if query["condition"] == "no_tasks" and tasks:
                continue
            if query["condition"] == "zero_lessons" and any(max(
                lesson_counts.get(str(t.get("id")), 0), int(t.get("lesson_count") or 0),
                int(t.get("weekly_slots") or 0), len(t.get("lessons") or [])) > 0 for t in tasks):
                continue
            pairs.append({"homeroom_id": h, "subject_id": s,
                          "source_ref": {"condition": query["condition"], "source": "当前项目数据库筛选"}})
    return pairs


def _expand_task_scope_items(state: _CompilerState, payload: dict) -> list[dict]:
    allowed_payload_keys = {"scope_query", "set_fields"}
    unexpected_payload_keys = sorted(set(payload) - allowed_payload_keys)
    if unexpected_payload_keys:
        raise ActionCompilationError(
            [{
                "code": "invalid_task_scope_payload",
                "message": f"授课任务范围操作包含不支持的字段：{', '.join(unexpected_payload_keys)}。",
            }]
        )
    scope_query = payload.get("scope_query")
    set_fields = payload.get("set_fields")
    if not isinstance(scope_query, dict) or not isinstance(set_fields, dict):
        raise ActionCompilationError(
            [{"code": "invalid_task_scope", "message": "授课任务范围和更新字段必须是结构化对象。"}]
        )
    allowed_scope_keys = {"exclude_subject_names", "include_subject_names", "homeroom_ids", "active_only"}
    unexpected_scope_keys = sorted(set(scope_query) - allowed_scope_keys)
    if unexpected_scope_keys:
        raise ActionCompilationError(
            [{
                "code": "invalid_task_scope_query",
                "message": f"授课任务范围包含不支持的筛选字段：{', '.join(unexpected_scope_keys)}。",
            }]
        )
    room_source = set_fields.get("fixed_room_source")
    no_room = set_fields == {"required_room_type": "__no_room__"}
    if not no_room and (set(set_fields) != {"fixed_room_source"} or room_source not in {
        "homeroom_classroom", "homeroom_default_room"
    }):
        raise ActionCompilationError(
            [{
                "code": "invalid_task_scope_update",
                "message": "范围操作支持本班默认教室，或required_room_type=__no_room__明确不使用教室。",
            }]
        )

    excluded_subject_names = _string_set(scope_query.get("exclude_subject_names"), "排除科目")
    included_subject_names = _string_set(scope_query.get("include_subject_names"), "包含科目")
    homeroom_ids = _string_set(scope_query.get("homeroom_ids"), "班级 ID")
    unknown_homeroom_ids = sorted(homeroom_ids - set(state.by_id["homeroom"]))
    if unknown_homeroom_ids:
        raise ActionCompilationError(
            [{"code": "homeroom_not_found", "message": "筛选条件包含不属于当前机构的班级。"}]
        )
    if included_subject_names:
        unknown_subject_names = sorted(included_subject_names - set(state.by_name["subject"]))
        if unknown_subject_names:
            raise ActionCompilationError(
                [{
                    "code": "subject_not_found",
                    "message": f"找不到科目：{'、'.join(unknown_subject_names)}。",
                }]
            )

    raw_items: list[dict] = []
    missing_default_rooms: list[str] = []
    active_only = scope_query.get("active_only") is not False
    for task in state.tasks:
        if active_only and _text(task.get("status")) not in {"", "active"}:
            continue
        homeroom_id = _text(task.get("homeroom_id"))
        subject_id = _text(task.get("subject_id"))
        homeroom = state.by_id["homeroom"].get(homeroom_id)
        subject = state.by_id["subject"].get(subject_id)
        if not homeroom or not subject:
            continue
        subject_name = _text(subject.get("name"))
        if homeroom_ids and homeroom_id not in homeroom_ids:
            continue
        if included_subject_names and subject_name not in included_subject_names:
            continue
        if subject_name in excluded_subject_names:
            continue
        if no_room:
            raw_items.append({"id": _text(task.get("id")), "homeroom_id": homeroom_id,
                "subject_id": subject_id, "required_room_type": "__no_room__",
                "fixed_room_id": None, "room_ids": [],
                "lessons": [{**lesson, "room_ids": [], "room_options": []} for lesson in state.lessons
                            if _text(lesson.get("teaching_task_id")) == _text(task.get("id"))],
                "source_ref": {"scope": "no_room"}})
            continue
        default_room_id = _text(homeroom.get("default_room_id"))
        if not default_room_id:
            classroom_name = f"{_text(homeroom.get('name'))}教室"
            room_matches = list(state.by_name["room"].get(classroom_name, []))
            if len(room_matches) > 1:
                raise ActionCompilationError(
                    [{
                        "code": "ambiguous_homeroom_classroom",
                        "message": f"班级“{homeroom.get('name') or homeroom_id}”匹配到多个同名本班教室。",
                    }]
                )
            if len(room_matches) == 1:
                default_room_id = _text(room_matches[0].get("id"))
            else:
                missing_default_rooms.append(_text(homeroom.get("name")) or homeroom_id)
                continue
        if default_room_id not in state.by_id["room"]:
            raise ActionCompilationError(
                [{
                    "code": "default_room_not_found",
                    "message": f"班级“{homeroom.get('name') or homeroom_id}”的默认教室不属于当前机构。",
                }]
            )
        raw_items.append(
            {
                "id": _text(task.get("id")),
                "homeroom_id": homeroom_id,
                "subject_id": subject_id,
                "fixed_room_id": default_room_id,
                "source_ref": {"scope": "homeroom_classroom"},
            }
        )
    if missing_default_rooms:
        unique_names = list(dict.fromkeys(missing_default_rooms))
        suffix = "等" if len(unique_names) > 5 else ""
        raise ActionCompilationError(
            [{
                "code": "homeroom_default_room_required",
                "message": (
                    f"以下班级既未设置默认教室，也没有唯一的“班级名+教室”："
                    f"{'、'.join(unique_names[:5])}{suffix}。请先完善班级教室。"
                ),
            }]
        )
    if not raw_items:
        raise ActionCompilationError(
            [{"code": "task_scope_no_match", "message": "当前项目没有匹配该范围的授课任务。"}]
        )
    return raw_items


def _string_set(value: Any, label: str) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ActionCompilationError(
            [{"code": "invalid_scope_filter", "message": f"{label}必须是字符串数组。"}]
        )
    return {_text(item) for item in value if _text(item)}


def _merge_task_items(raw_items: list) -> list:
    merged: list = []
    indexes: dict[str, int] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            merged.append(raw)
            continue
        task_id = _text(raw.get("id") or raw.get("task_id"))
        if not task_id or task_id not in indexes:
            if task_id:
                indexes[task_id] = len(merged)
            merged.append(dict(raw))
            continue
        position = indexes[task_id]
        previous = merged[position]
        combined = {**previous, **raw}
        lesson_by_key: dict[str, dict] = {}
        lesson_order: list[str] = []
        for lesson in [*(previous.get("lessons") or []), *(raw.get("lessons") or [])]:
            if not isinstance(lesson, dict):
                continue
            key = _text(lesson.get("id")) or f"ordinal:{int(lesson.get('lesson_index') or len(lesson_order) + 1)}"
            if key not in lesson_by_key:
                lesson_order.append(key)
                lesson_by_key[key] = {}
            lesson_by_key[key] = {**lesson_by_key[key], **lesson}
        if lesson_order:
            combined["lessons"] = [lesson_by_key[key] for key in lesson_order]
        merged[position] = combined
    return merged


def _compile_school_item(
    state: _CompilerState,
    target: str,
    requested_operation: str,
    raw: dict,
    source_ref: dict,
) -> dict:
    name = _text(raw.get("name"))
    entity_id = _text(raw.get("id") or raw.get(f"{target}_id") or raw.get("record_id"))
    matches: list[dict] = []
    if entity_id:
        existing = state.by_id[target].get(entity_id)
        matches = [existing] if existing else []
    elif name:
        matches = list(state.by_name[target].get(name, []))
        if target == "teacher" and len(matches) > 1 and raw.get("department") is not None:
            matches = [item for item in matches if _text(item.get("department")) == _text(raw.get("department"))]
    if requested_operation in {"update", "delete"} and not matches:
        raise ActionCompilationError([{"code": "entity_not_found", "message": f"找不到要操作的{TARGET_LABELS[target]}：{name or entity_id or '未命名'}。"}])
    if len(matches) > 1:
        raise ActionCompilationError([{"code": "ambiguous_entity", "message": f"{TARGET_LABELS[target]}“{name}”存在多条记录，请提供更明确的信息。"}])
    before = matches[0] if matches else None
    if requested_operation == "delete":
        state.remove_school(target, before)
        return _new_item(target, "delete", {"id": before["id"], "name": before.get("name")}, before, None, source_ref, name)
    if target == "subject":
        raw = _normalize_subject_payload(raw, before)
        name = _text(raw.get("name") or (before or {}).get("name"))
        raw["name"] = name
    if not name and requested_operation in {"update", "bulk_upsert"} and before:
        name = _text(before.get("name"))
    if not name:
        raise ActionCompilationError([{"code": "name_required", "message": f"{TARGET_LABELS[target]}缺少名称。"}])
    normalized = _without_meta(raw)
    if target == "homeroom":
        for entity, field in (("teacher", "head_teacher_id"), ("room", "default_room_id")):
            if raw.get(f"{entity}_name"):
                normalized[field] = _resolve_reference(state, entity, raw, required=True, field=field)
    if target == "room":
        room_type_id = _resolve_reference(state, "room_type", raw, required=False, field="type_id")
        if room_type_id:
            normalized["type_id"] = room_type_id
    planned_id = (before or {}).get("id") or state.planned_id(
        target,
        {"name": name, "department": raw.get("department") if target == "teacher" else None},
    )
    after = {**(before or {}), **normalized, "id": planned_id}
    if before and _same_requested_fields(before, normalized):
        operation = "skip"
    else:
        operation = "update" if before else "create"
    identity = {"id": planned_id, "name": name}
    state.register_school(target, after)
    return _new_item(target, operation, identity, before, after, source_ref, name)


def _normalize_subject_payload(raw: dict, before: dict | None) -> dict:
    normalized = _without_meta(raw)
    normalized.pop("subject_id", None)
    # A model may echo read-only query fields, but must not invent writable columns.
    for key in ("code", "organization_id", "created_at", "updated_at", "status"):
        if key not in normalized:
            continue
        if before is None or normalized[key] != before.get(key):
            raise ActionCompilationError([{"code": "readonly_subject_field", "message": f"科目字段 {key} 由系统维护，不能修改。"}])
        normalized.pop(key)
    unexpected = set(normalized) - {"id", "name", "category", "default_duration_slots", "default_duration_minutes"}
    if unexpected:
        raise ActionCompilationError([{"code": "unknown_subject_field", "message": f"科目包含不支持的字段：{', '.join(sorted(unexpected))}。默认课长应使用 default_duration_slots（每格 5 分钟）。"}])
    if "default_duration_minutes" in normalized:
        minutes = normalized.pop("default_duration_minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes <= 0 or minutes % 5 != 0:
            raise ActionCompilationError([{"code": "invalid_subject_duration", "message": "科目默认课长必须是正数且为 5 分钟的整数倍。"}])
        slots = int(minutes / 5)
        if "default_duration_slots" in normalized and normalized["default_duration_slots"] != slots:
            raise ActionCompilationError([{"code": "conflicting_subject_duration", "message": "科目默认课长的分钟数与时间格数不一致，请重新生成操作。"}])
        normalized["default_duration_slots"] = slots
    if "default_duration_slots" in normalized:
        slots = normalized["default_duration_slots"]
        if isinstance(slots, bool) or not isinstance(slots, int) or slots <= 0:
            raise ActionCompilationError([{"code": "invalid_subject_duration", "message": "科目默认课长的时间格数必须是正整数，每格 5 分钟。"}])
    if before is None:
        normalized.setdefault("category", "academic")
        normalized.setdefault("default_duration_slots", 1)
    return normalized


def _compile_term(state: _CompilerState, raw: dict, source_ref: dict) -> dict:
    before = state.school_data.get("active_term") or None
    if not raw:
        raise ActionCompilationError([{"code": "term_payload_required", "message": "学期更新缺少具体字段。"}])
    after = {**(before or {}), **_without_meta(raw)}
    operation = "skip" if before and _same_requested_fields(before, raw) else "update"
    return _new_item("term", operation, {"id": (before or {}).get("id")}, before, after, source_ref, after.get("name") or "当前学期")


def _compile_timetable_template(
    state: _CompilerState,
    raw: dict,
    requested_operation: str,
    source_ref: dict,
) -> dict:
    template_id = _text(raw.get("id") or raw.get("template_id"))
    name = _text(raw.get("name"))
    matches = [item for item in state.timetable_templates if _text(item.get("id")) == template_id] if template_id else [
        item for item in state.timetable_templates if _text(item.get("name")) == name
    ]
    if requested_operation in {"update", "delete"} and not matches:
        raise ActionCompilationError([{"code": "template_not_found", "message": f"找不到课表模板：{name or template_id or '未命名'}。"}])
    if len(matches) > 1:
        raise ActionCompilationError([{"code": "ambiguous_template", "message": f"存在多个同名课表模板“{name}”，请提供模板 ID。"}])
    before = matches[0] if matches else None
    display_name = name or _text((before or {}).get("name"))
    if requested_operation == "delete":
        return _new_item(
            "timetable_template", "delete",
            {"id": before["id"], "name": before.get("name")}, before, None,
            source_ref, display_name,
        )
    if not display_name:
        raise ActionCompilationError([{"code": "template_name_required", "message": "课表模板缺少名称。"}])
    normalized = _without_meta(raw)
    normalized.pop("template_id", None)
    normalized["name"] = display_name
    normalized["project_id"] = state.project_id
    normalized.setdefault("day_count", int((before or {}).get("day_count") or 7))
    normalized.setdefault("slot_duration_minutes", int((before or {}).get("slot_duration_minutes") or 5))
    normalized.setdefault("template_kind", str((before or {}).get("template_kind") or "normal"))
    normalized.setdefault("application_scope", str((before or {}).get("application_scope") or "all"))
    normalized.setdefault("is_default", bool((before or {}).get("is_default")))
    planned_id = _text((before or {}).get("id")) or state.planned_id("timetable_template", {"name": display_name})
    after = {**(before or {}), **normalized, "id": planned_id}
    operation = "skip" if before and _same_requested_fields(before, normalized) else ("update" if before else "create")
    state.timetable_templates = [item for item in state.timetable_templates if _text(item.get("id")) != planned_id] + [after]
    return _new_item(
        "timetable_template", operation, {"id": planned_id, "name": display_name},
        before, after, source_ref, display_name,
    )


def _compile_course_plan(
    state: _CompilerState,
    raw: dict,
    requested_operation: str,
    source_ref: dict,
) -> dict:
    plan_id = _text(raw.get("id") or raw.get("course_plan_id"))
    if plan_id:
        id_matches = [item for item in state.course_plans if _text(item.get("id")) == plan_id]
        if not id_matches:
            raise ActionCompilationError([{"code": "course_plan_not_found", "message": "课程计划不存在或不属于当前项目。"}])
        before = id_matches[0]
        if requested_operation == "delete":
            return _new_item(
                "course_plan", "delete", {"id": plan_id}, before, None, source_ref,
                str(before.get("subject_name") or before.get("subject_id") or "课程计划"),
            )
    else:
        before = None
    normalized = dict(_without_meta(raw))
    normalized.pop("course_plan_id", None)
    normalized["subject_id"] = _resolve_reference(state, "subject", raw, required=True)
    normalized["homeroom_id"] = _resolve_reference(state, "homeroom", raw, required=False)
    if before is None:
        matches = [
            item for item in state.course_plans
            if str(item.get("subject_id") or "") == normalized["subject_id"]
            and str(item.get("homeroom_id") or "") == str(normalized.get("homeroom_id") or "")
        ]
        if len(matches) > 1:
            raise ActionCompilationError([{"code": "ambiguous_course_plan", "message": "同一班级和科目存在多条课程计划，无法安全更新。"}])
        before = matches[0] if matches else None
    if requested_operation == "delete":
        if not before:
            raise ActionCompilationError([{"code": "course_plan_not_found", "message": "找不到要删除的课程计划。"}])
        return _new_item(
            "course_plan", "delete", {"id": before["id"]}, before, None, source_ref,
            str(before.get("subject_name") or normalized["subject_id"]),
        )
    planned_id = (before or {}).get("id") or state.planned_id(
        "course_plan",
        {"homeroom_id": normalized.get("homeroom_id"), "subject_id": normalized["subject_id"]},
    )
    after = {**(before or {}), **normalized, "id": planned_id}
    operation = "skip" if before and _same_requested_fields(before, normalized) else ("update" if before else "create")
    subject = state.by_id["subject"].get(normalized["subject_id"], {})
    homeroom = state.by_id["homeroom"].get(normalized.get("homeroom_id", ""), {})
    name = f"{homeroom.get('name') or '全校'} · {subject.get('name') or normalized['subject_id']}"
    identity = {"id": planned_id, "homeroom_id": normalized.get("homeroom_id"), "subject_id": normalized["subject_id"]}
    state.course_plans = [item for item in state.course_plans if _text(item.get("id")) != planned_id] + [after]
    return _new_item("course_plan", operation, identity, before, after, source_ref, name)


def _compile_task(
    state: _CompilerState,
    raw: dict,
    source_ref: dict,
    *,
    requested_operation: str,
) -> dict:
    task_id = _text(raw.get("id") or raw.get("task_id"))
    if requested_operation == "delete" and task_id:
        matches = [item for item in state.tasks if _text(item.get("id")) == task_id]
        if not matches:
            raise ActionCompilationError(
                [{"code": "task_not_found", "message": "授课任务不存在或不属于当前项目。"}]
            )
        before = matches[0]
        state.tasks = [item for item in state.tasks if _text(item.get("id")) != task_id]
        return _new_item(
            "task", "delete", {"id": task_id}, before, None, source_ref,
            str(before.get("subject_name") or before.get("subject_id") or "授课任务"),
        )
    normalized = dict(_without_meta(raw))
    normalized["homeroom_id"] = _resolve_reference(state, "homeroom", raw, required=True)
    normalized["subject_id"] = _resolve_reference(state, "subject", raw, required=True)
    teacher_id = _resolve_reference(state, "teacher", raw, required=False, field="primary_teacher_id")
    if teacher_id:
        normalized["primary_teacher_id"] = teacher_id
    fixed_room_id = _resolve_reference(state, "room", raw, required=False, field="fixed_room_id")
    if fixed_room_id:
        normalized["fixed_room_id"] = fixed_room_id
    if "fixed_room_source" in normalized:
        source = normalized.pop("fixed_room_source")
        if source != "homeroom_classroom":
            raise ActionCompilationError([{"code": "invalid_room_source", "message": "无法识别默认教室来源，请指定真实教室。"}])
        room_id = state.by_id["homeroom"].get(normalized["homeroom_id"], {}).get("default_room_id")
        if not room_id or room_id not in state.by_id["room"]:
            raise ActionCompilationError([{"code": "missing_default_room", "message": "班级未设置有效的默认教室，请先确认教室。"}])
        normalized["fixed_room_id"] = room_id
        normalized["room_ids"] = [room_id]
    course_plan_id = _text(raw.get("course_plan_id"))
    if course_plan_id:
        if not any(_text(item.get("id")) == course_plan_id for item in state.course_plans):
            raise ActionCompilationError([{"code": "course_plan_not_found", "message": "授课任务引用的课程计划不属于当前项目。"}])
        normalized["course_plan_id"] = course_plan_id
    else:
        plan_matches = [
            item for item in state.course_plans
            if _text(item.get("homeroom_id")) == normalized["homeroom_id"]
            and _text(item.get("subject_id")) == normalized["subject_id"]
        ]
        if len(plan_matches) == 1:
            normalized["course_plan_id"] = _text(plan_matches[0].get("id"))
        else:
            raise ActionCompilationError([{"code": "ambiguous_course_plan", "message": "授课任务必须关联唯一的课程计划，请先确认班级和科目。"}])
    requested_fields = dict(normalized)
    if task_id:
        matches = [item for item in state.tasks if str(item.get("id")) == task_id]
        if not matches:
            raise ActionCompilationError(
                [{"code": "task_not_found", "message": "授课任务不存在或不属于当前项目。"}]
            )
    elif requested_operation == "create":
        matches = []
    else:
        task_scope = [
            item for item in state.tasks
            if str(item.get("homeroom_id") or "") == normalized["homeroom_id"]
            and str(item.get("subject_id") or "") == normalized["subject_id"]
            and (
                not normalized.get("course_plan_id")
                or str(item.get("course_plan_id") or "") == normalized["course_plan_id"]
            )
        ]
        exact_teacher_matches = [
            item
            for item in task_scope
            if str(item.get("primary_teacher_id") or "")
            == str(normalized.get("primary_teacher_id") or "")
        ]
        if exact_teacher_matches:
            matches = exact_teacher_matches
        else:
            # bulk_upsert is also used to fill teachers into an existing course plan.
            # Reuse its unassigned task instead of creating a duplicate task and lessons.
            matches = [item for item in task_scope if not item.get("primary_teacher_id")]
    if len(matches) > 1:
        raise ActionCompilationError(
            [{
                "code": "ambiguous_task",
                "message": "同一课程匹配到多条可更新授课任务，请提供授课任务 ID 后重试。",
            }]
        )
    before = matches[0] if matches else None
    if normalized.get("duration_slots") is None:
        normalized["duration_slots"] = (before or {}).get("duration_slots") or state.by_id["subject"][normalized["subject_id"]].get("default_duration_slots") or 1
    planned_id = (before or {}).get("id") or state.planned_id(
        "task",
        {
            "homeroom_id": normalized["homeroom_id"],
            "subject_id": normalized["subject_id"],
            "primary_teacher_id": normalized.get("primary_teacher_id"),
        },
    )
    if "room_ids" not in normalized:
        normalized["room_ids"] = [
            str(option.get("room_id"))
            for option in (before or {}).get("room_options") or []
            if isinstance(option, dict) and option.get("room_id")
        ]
    if isinstance(raw.get("lessons"), list):
        existing_lesson_records = [
            item
            for item in state.lessons
            if _text(item.get("teaching_task_id")) == planned_id
        ]
        existing_lessons = {
            int(item.get("lesson_index") or 0): item
            for item in existing_lesson_records
        }
        normalized_lessons_by_ordinal = {
            int(item.get("lesson_index") or 0): dict(item)
            for item in existing_lesson_records
        }
        existing_task_lesson_ids = {
            _text(item.get("id")) for item in existing_lesson_records if item.get("id")
        }
        for lesson_index, lesson in enumerate(raw["lessons"]):
            if not isinstance(lesson, dict):
                raise ActionCompilationError([{"code": "invalid_lesson", "message": f"第 {lesson_index + 1} 个课次不是结构化记录。"}])
            ordinal = int(lesson.get("lesson_index") or lesson_index + 1)
            existing_lesson = existing_lessons.get(ordinal)
            lesson_id = _text(lesson.get("id"))
            if lesson_id and lesson_id not in existing_task_lesson_ids:
                raise ActionCompilationError([{"code": "lesson_not_found", "message": f"第 {ordinal} 课次不属于当前授课任务。"}])
            if not lesson_id:
                lesson_id = _text((existing_lesson or {}).get("id")) or state.planned_id(
                    "task_lesson", {"teaching_task_id": planned_id, "lesson_index": ordinal}
                )
            normalized_lesson = {**(existing_lesson or {}), **lesson, "id": lesson_id, "lesson_index": ordinal}
            if not normalized_lesson.get("label") and normalized_lesson.get("name"):
                normalized_lesson["label"] = normalized_lesson.pop("name")
            if normalized_lesson.get("duration_slots") is None:
                normalized_lesson["duration_slots"] = normalized["duration_slots"]
            if "room_ids" not in normalized_lesson:
                normalized_lesson["room_ids"] = [
                    str(option.get("room_id"))
                    for option in (existing_lesson or {}).get("room_options") or []
                    if isinstance(option, dict) and option.get("room_id")
                ]
            if not existing_lesson:
                normalized_lesson["_agent_preallocated"] = True
            normalized_lessons_by_ordinal[ordinal] = normalized_lesson
            state.lesson_ids.add(lesson_id)
        normalized["lessons"] = [
            normalized_lessons_by_ordinal[ordinal]
            for ordinal in sorted(normalized_lessons_by_ordinal)
        ]
    elif before:
        # Updating a teacher or room must preserve every existing lesson and its
        # time preferences. The task repository treats an omitted lesson list as
        # a request to regenerate lessons from weekly_slots.
        existing_lesson_records = [
            dict(item)
            for item in state.lessons
            if _text(item.get("teaching_task_id")) == planned_id
        ]
        if existing_lesson_records:
            normalized["lessons"] = sorted(
                existing_lesson_records,
                key=lambda item: int(item.get("lesson_index") or 0),
            )
    after = {**(before or {}), **normalized, "id": planned_id}
    operation = "skip" if before and _same_requested_fields(before, requested_fields) else ("update" if before else "create")
    subject = state.by_id["subject"].get(normalized["subject_id"], {})
    homeroom = state.by_id["homeroom"].get(normalized["homeroom_id"], {})
    teacher = state.by_id["teacher"].get(normalized.get("primary_teacher_id", ""), {})
    name = " · ".join(filter(None, [str(homeroom.get("name") or ""), str(subject.get("name") or ""), str(teacher.get("name") or "未指定教师")]))
    identity = {"id": planned_id, "homeroom_id": normalized["homeroom_id"], "subject_id": normalized["subject_id"], "primary_teacher_id": normalized.get("primary_teacher_id")}
    state.tasks = [item for item in state.tasks if _text(item.get("id")) != planned_id] + [after]
    return _new_item("task", operation, identity, before, after, source_ref, name)


def _compile_constraint_groups(state: _CompilerState, payload: dict, proposal_index: int) -> list[dict]:
    _validate_constraint_type(payload)
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ActionCompilationError([{"code": "missing_constraint_groups", "message": "约束操作缺少可执行分组。"}])
    compiled = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ActionCompilationError([{"code": "invalid_constraint_group", "message": f"第 {index + 1} 个约束分组格式错误。"}])
        lesson_ids = [str(value) for value in group.get("lesson_ids") or [] if value]
        missing = [lesson_id for lesson_id in lesson_ids if lesson_id not in state.lesson_ids]
        if missing:
            raise ActionCompilationError([{"code": "lesson_not_found", "message": f"约束分组引用了当前项目不存在的课次：{', '.join(missing[:3])}。"}])
        after = {key: value for key, value in payload.items() if key != "groups"}
        after["groups"] = [group]
        compiled.append(_new_item("constraint", "create", {"group_id": group.get("id"), "lesson_ids": lesson_ids}, None, after, _source_ref(group, proposal_index, index), group.get("label") or group.get("name") or f"约束分组 {index + 1}"))
    return compiled


def _compile_constraint(
    state: _CompilerState,
    raw: dict,
    requested_operation: str,
    source_ref: dict,
) -> dict:
    if requested_operation != "delete":
        _validate_constraint_type(raw)
    constraint_id = _text(raw.get("id") or raw.get("constraint_id") or raw.get("record_id"))
    name = _text(raw.get("name"))
    matches = [item for item in state.constraints if (
        (constraint_id and _text(item.get("id")) == constraint_id)
        or (not constraint_id and name and _text(item.get("name")) == name)
    )]
    if requested_operation in {"update", "delete"}:
        if len(matches) != 1:
            raise ActionCompilationError([{
                "code": "constraint_not_found",
                "message": "请先查询并提供唯一的约束 ID。",
            }])
        before = matches[0]
        identity = {"id": str(before["id"])}
        if requested_operation == "delete":
            return _new_item("constraint", "delete", identity, before, None, source_ref, before.get("name"))
        requested = _without_meta(raw)
        requested.pop("id", None)
        requested.pop("constraint_id", None)
        after = {**before, **requested}
        operation = "skip" if _same_requested_fields(before, requested) else "update"
        return _new_item("constraint", operation, identity, before, after, source_ref, after.get("name"))
    return _new_item("constraint", "create", {}, None, _without_meta(raw), source_ref, name or "约束")


def _validate_constraint_type(payload: dict) -> None:
    value = payload.get("distribution_type")
    scenario = str(payload.get("scenario_type") or "")
    if not value and scenario.startswith(("itc2019:", "common:ParallelLimit(")):
        value = scenario.split(":", 1)[1]
    if value:
        try:
            parse_distribution(str(value))
        except ValueError as exc:
            raise ActionCompilationError([{"code": "invalid_distribution", "message": str(exc)}]) from exc


def _resolve_reference(
    state: _CompilerState,
    target: str,
    raw: dict,
    *,
    required: bool,
    field: str | None = None,
) -> str | None:
    id_field = field or f"{target}_id"
    value = _text(raw.get(id_field) or raw.get(f"{target}_id"))
    if value:
        if value not in state.by_id[target]:
            raise ActionCompilationError([{"code": "foreign_entity_not_found", "message": f"所选{TARGET_LABELS[target]}不属于当前机构。"}])
        return value
    name_fields = [f"{target}_name"]
    if target == "homeroom":
        name_fields.extend(["class_name", "homeroom"])
    if target == "subject":
        name_fields.extend(["subject"])
    if target == "teacher":
        name_fields.extend(["teacher_name", "teacher"])
    if target == "room":
        name_fields.extend(["room_name", "room"])
    if target == "room_type":
        name_fields.extend(["room_type_name", "room_type"])
    name = next((_text(raw.get(key)) for key in name_fields if _text(raw.get(key))), "")
    if not name:
        if required:
            raise ActionCompilationError([{"code": "foreign_entity_required", "message": f"缺少{TARGET_LABELS[target]} ID 或名称。"}])
        return None
    matches = list(state.by_name[target].get(name, []))
    if len(matches) != 1:
        reason = "不存在" if not matches else "存在重名"
        raise ActionCompilationError([{"code": "ambiguous_reference", "message": f"{TARGET_LABELS[target]}“{name}”{reason}，请重新选择。"}])
    return str(matches[0]["id"])


def _new_item(target: str, operation: str, identity: dict, before: dict | None, after: dict | None, source_ref: dict, name: Any) -> dict:
    before_copy = _json_value(before)
    after_copy = _json_value(after)
    snapshot_hash = _hash_json({"target": target, "identity": identity, "before": before_copy})
    return {
        "target": target,
        "operation": operation,
        "entity_id": str((before or {}).get("id")) if (before or {}).get("id") else None,
        "identity": _json_value(identity) or {},
        "before_data": before_copy,
        "after_data": after_copy,
        "display_data": {"name": str(name or TARGET_LABELS.get(target, target)), "target_label": TARGET_LABELS.get(target, target)},
        "source_ref": source_ref,
        "snapshot_hash": snapshot_hash,
        "status": "pending" if operation != "skip" else "skipped",
    }


def _source_ref(raw: dict, proposal_index: int, item_index: int) -> dict:
    explicit = raw.get("source_ref") if isinstance(raw.get("source_ref"), dict) else {}
    return {"proposal_index": proposal_index, "item_index": item_index, **explicit}


def _without_meta(raw: dict) -> dict:
    aliases = {
        "source_ref",
        "teacher_name",
        "homeroom_name",
        "subject_name",
        "room_name",
        "room_type_name",
        "class_name",
        "teacher",
        "homeroom",
        "subject",
        "room",
        "room_type",
        "record_id",
        "constraint_id",
        "task_id",
    }
    return {key: value for key, value in raw.items() if key not in aliases}


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDER_VALUES
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    return False


def _same_requested_fields(before: dict, requested: dict) -> bool:
    ignored = {"id", "created_at", "updated_at", "status"}
    return all(_json_value(before.get(key)) == _json_value(value) for key, value in requested.items() if key not in ignored)


def _counts(items: list[dict]) -> dict:
    counts = {"create": 0, "update": 0, "delete": 0, "skip": 0, "run": 0, "failed": 0}
    for item in items:
        counts[item["operation"]] = counts.get(item["operation"], 0) + 1
    return counts


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str)) if value is not None else None


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
