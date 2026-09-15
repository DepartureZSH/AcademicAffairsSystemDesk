from __future__ import annotations

import json
from copy import deepcopy

from fastapi import HTTPException, status

from typing import Any
SchedulingRepository = Any
from stt_desktop.agent.repository import build_preview_problem, create_scheduling_run
from stt_desktop.agent.upstream.compiler import ALLOWED_AGENT_ACTIONS


_ACTION_COMMON_PROPERTIES = {
    "scope": {"type": "string", "enum": ["organization", "project"]},
    "payload": {"type": "object"},
    "human_summary": {"type": "string"},
    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
    "preview": {"type": "object"},
    "dedupe_key": {"type": "string"},
}


def _action_schema_variant(target: str, operations: set[str]) -> dict:
    properties = dict(_ACTION_COMMON_PROPERTIES)
    if target in {"course_plan", "task"}:
        properties["payload"] = {
            "type": "object",
            "description": (
                "课程计划增改：homeroom_id、subject_id、weekly_slots、duration_slots；更新/删除可用查询得到的id。"
                "授课任务增改：id或homeroom_id+subject_id+primary_teacher_id，fixed_room_id、room_ids、weekly_slots、duration_slots、lessons。"
                "lessons包含id、label、duration_slots、room_ids；删除任务用id/ids。批量增改用非空items。"
                "course_plan mark_not_scheduled使用items班科配对，或scope_query由代码筛选全部真实记录，无需逐条输出。"
                "scope_query仅支持零课次/无任务条件，其他条件先查询再用items，禁止忽略条件。"
                "remove_existing_tasks=true会删除真实任务及课次，仅用户已明确授权该范围时使用，仍需最终审核。"
            ),
            "properties": {
                "items": {"type": "array", "minItems": 1, "items": {"type": "object"}},
                "id": {"type": "string"}, "ids": {"type": "array", "items": {"type": "string"}},
                "scope_query": {"type": "object", "properties": {
                    "condition": {"type": "string", "enum": ["zero_lessons", "no_tasks"]},
                    "all_homerooms": {"type": "boolean", "description": "用户明确全部班级时为true，否则传homeroom_ids。"},
                    "homeroom_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "subject_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "include_unconfigured": {"type": "boolean", "description": "是否包含尚无计划和任务的班级×科目；仅用户范围包含待配置课程时为true。"},
                }},
                "remove_existing_tasks": {"type": "boolean"},
            },
        }
    if target == "task":
        properties["payload"]["properties"]["scope_query"] = {"type": "object", "description": "批量设置本班教室时支持homeroom_ids、include_subject_names、exclude_subject_names、active_only。", "properties": {
            "homeroom_ids": {"type": "array", "items": {"type": "string"}},
            "include_subject_names": {"type": "array", "items": {"type": "string"}},
            "exclude_subject_names": {"type": "array", "items": {"type": "string"}},
            "active_only": {"type": "boolean"},
        }}
    if target == "subject":
        fields = {
            "id": {"type": "string", "description": "查询得到的科目 ID，仅用于定位，不编造。"},
            "name": {"type": "string", "description": "科目名称。"},
            "category": {"type": "string", "description": "科目类别，未要求修改时省略。"},
            "default_duration_slots": {
                "type": "integer", "minimum": 1,
                "description": "默认课长/默认时长，每格 5 分钟；40 分钟填 8，45 分钟填 9。不是分钟数。",
            },
            "source_ref": {"type": "object"},
        }
        properties["payload"] = {
            "type": "object",
            "description": "新增或修改使用科目属性；批量使用 items；删除使用 id/name 或 ids/names。禁止添加未知字段。",
            "properties": {
                **fields,
                "items": {"type": "array", "minItems": 1, "items": {"type": "object", "properties": fields, "additionalProperties": False}},
                "ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "names": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            },
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            **properties,
            "target": {"type": "string", "enum": [target]},
            "operation": {"type": "string", "enum": sorted(operations)},
        },
        "required": ["scope", "operation", "target", "payload", "human_summary", "risk_level"],
        "additionalProperties": False,
    }


ACTION_TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "propose_agent_action",
            "description": "提交支持的排课业务变更意图。服务端解析真实数据库明细，用户审核确认后才执行。human_summary使用简体中文。",
            "parameters": {
                "type": "object",
                "oneOf": [
                    _action_schema_variant(target, operations)
                    for target, operations in ALLOWED_AGENT_ACTIONS.items()
                ],
            },
        },
    }
]


PROJECT_QUERY_TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_project_data",
            "description": (
                "查询当前机构或项目的真实数据。这是服务端自动执行的只读查询，不需要用户确认。"
                "需要完整记录或真实ID时使用；使用offset和limit读取后续分页，不向用户输出内部查询分析。"
                "planning_courses查询全部班级×科目，含待配置项、lesson_count、task_count和arrangement；zero_lessons及arrangement筛选用于该数据集。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {
                        "type": "string",
                        "enum": [
                            "school_data",
                            "timetable_templates",
                            "course_plans",
                            "planning_courses",
                            "teaching_tasks",
                            "task_lessons",
                            "lesson_time_preferences",
                            "constraints",
                        ],
                    },
                    "filters": {
                        "type": "object",
                        "properties": {
                            "ids": {"type": "array", "items": {"type": "string"}},
                            "homeroom_ids": {"type": "array", "items": {"type": "string"}},
                            "subject_ids": {"type": "array", "items": {"type": "string"}},
                            "teacher_ids": {"type": "array", "items": {"type": "string"}},
                            "teaching_task_ids": {"type": "array", "items": {"type": "string"}},
                            "lesson_ids": {"type": "array", "items": {"type": "string"}},
                            "enabled_only": {"type": "boolean"},
                            "has_time_preferences": {"type": "boolean"},
                            "preference_penalties": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                            "query": {"type": "string"},
                            "zero_lessons": {"type": "boolean"},
                            "arrangement": {"type": "string", "enum": ["unconfigured", "not_scheduled", "scheduled"]},
                        },
                        "additionalProperties": False,
                    },
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                "required": ["dataset"],
                "additionalProperties": False,
            },
        },
    }
]


AGENT_TOOL_SCHEMA = [*PROJECT_QUERY_TOOL_SCHEMA, *ACTION_TOOL_SCHEMA]


AGENT_SCENE_POLICIES: dict[str, dict[str, object]] = {
    "timetable": {
        "title": "课表设置助手",
        "queries": {"timetable_templates", "school_data"},
        "targets": {"timetable_template"},
    },
    "rooms": {
        "title": "教室设置助手",
        "queries": {"school_data", "timetable_templates"},
        "targets": {"room_type", "room"},
    },
    "school": {
        "title": "学校数据助手",
        "queries": {"school_data", "timetable_templates"},
        "targets": {"term", "teacher", "homeroom", "subject"},
    },
    "planning": {
        "title": "课程计划助手",
        "queries": {
            "school_data", "timetable_templates", "course_plans", "planning_courses", "teaching_tasks",
            "task_lessons", "lesson_time_preferences", "constraints",
        },
        "targets": {"course_plan", "task"},
    },
    "constraints": {
        "title": "约束配置助手",
        "queries": {
            "school_data", "timetable_templates", "course_plans", "planning_courses", "teaching_tasks",
            "task_lessons", "lesson_time_preferences", "constraints",
        },
        "targets": {"constraint"},
    },
    "general": {
        "title": "排课配置对话",
        "queries": {
            "school_data", "timetable_templates", "course_plans", "planning_courses", "teaching_tasks",
            "task_lessons", "lesson_time_preferences", "constraints",
        },
        "targets": set(ALLOWED_AGENT_ACTIONS),
    },
}


def normalize_agent_scene(scene: str | None) -> str:
    value = str(scene or "").strip().lower()
    return value if value in AGENT_SCENE_POLICIES else "general"


def agent_scene_title(scene: str | None) -> str:
    policy = AGENT_SCENE_POLICIES[normalize_agent_scene(scene)]
    return str(policy["title"])


def agent_tools_for_scene(scene: str | None, *, readonly: bool = False) -> list[dict]:
    policy = AGENT_SCENE_POLICIES[normalize_agent_scene(scene)]
    datasets = sorted(str(item) for item in policy["queries"])
    query_tool = deepcopy(PROJECT_QUERY_TOOL_SCHEMA[0])
    query_tool["function"]["parameters"]["properties"]["dataset"]["enum"] = datasets
    if readonly:
        return [query_tool]
    allowed_targets = set(str(item) for item in policy["targets"])
    action_tool = {
        "type": "function",
        "function": {
            "name": "propose_agent_action",
            "description": "提交课程计划等业务的新增、修改、删除或不安排操作。服务端按真实数据库展开筛选并校验，生成完整明细供用户审核，不直接写入。",
            "parameters": {
                "type": "object",
                "oneOf": [
                    _action_schema_variant(target, operations)
                    for target, operations in ALLOWED_AGENT_ACTIONS.items()
                    if target in allowed_targets
                ],
            },
        },
    }
    return [query_tool, action_tool]


def execute_project_query(
    repo: SchedulingRepository,
    organization_id: str,
    project_id: str | None,
    arguments: dict,
) -> dict:
    dataset = str(arguments.get("dataset") or "").strip()
    filters = arguments.get("filters") if isinstance(arguments.get("filters"), dict) else {}
    offset = max(int(arguments.get("offset") or 0), 0)
    limit = min(max(int(arguments.get("limit") or 200), 1), 500)

    school_data = repo.list_school_data(organization_id)
    planning: dict = {}
    if dataset in {
        "course_plans",
        "planning_courses",
        "teaching_tasks",
        "task_lessons",
        "lesson_time_preferences",
        "constraints",
    }:
        if not project_id:
            raise ValueError("当前对话未关联项目，无法查询项目数据。")
        planning = repo.list_planning_data(organization_id, project_id)

    if dataset == "school_data":
        records = []
        for entity_type in ("teachers", "homerooms", "subjects", "rooms", "room_types"):
            records.extend(
                {"entity_type": entity_type, **dict(item)}
                for item in school_data.get(entity_type, [])
                if isinstance(item, dict)
            )
    elif dataset == "timetable_templates":
        template_data = repo.list_weekly_timetable_templates(organization_id, project_id)
        periods_by_template: dict[str, list[dict]] = {}
        for period in template_data.get("weekly_timetable_periods", []):
            if not isinstance(period, dict):
                continue
            periods_by_template.setdefault(str(period.get("template_id") or ""), []).append(dict(period))
        records = []
        for item in template_data.get("weekly_timetable_templates", []):
            if not isinstance(item, dict):
                continue
            records.append(
                {
                    **dict(item),
                    "periods": periods_by_template.get(str(item.get("id") or ""), []),
                }
            )
    elif dataset == "planning_courses":
        plans = {(str(p.get("homeroom_id")), str(p.get("subject_id"))): p for p in planning.get("course_plans", [])}
        tasks_by_pair = {}
        for task in planning.get("teaching_tasks", []):
            tasks_by_pair.setdefault((str(task.get("homeroom_id")), str(task.get("subject_id"))), []).append(task)
        lesson_counts = {}
        for lesson in planning.get("task_lessons", []):
            key = str(lesson.get("teaching_task_id"))
            lesson_counts[key] = lesson_counts.get(key, 0) + 1
        records = []
        for homeroom in school_data.get("homerooms", []):
            for subject in school_data.get("subjects", []):
                key = (str(homeroom["id"]), str(subject["id"]))
                plan, tasks = plans.get(key), tasks_by_pair.get(key, [])
                count = sum(max(lesson_counts.get(str(t.get("id")), 0), int(t.get("weekly_slots") or 0),
                                int(t.get("lesson_count") or 0), len(t.get("lessons") or [])) for t in tasks)
                records.append({"id": (plan or {}).get("id"), "homeroom_id": key[0], "subject_id": key[1],
                    "homeroom_name": homeroom.get("name"), "subject_name": subject.get("name"),
                    "lesson_count": count, "task_count": len(tasks),
                    "arrangement": "not_scheduled" if plan and plan.get("weekly_slots") == 0 and not tasks else "scheduled" if tasks else "unconfigured"})
    elif dataset == "course_plans":
        records = [dict(item) for item in planning.get("course_plans", []) if isinstance(item, dict)]
    elif dataset == "teaching_tasks":
        records = [{**dict(item), **_task_room_usage(item)} for item in planning.get("teaching_tasks", []) if isinstance(item, dict)]
    elif dataset in {"task_lessons", "lesson_time_preferences"}:
        tasks = {
            str(item.get("id")): item
            for item in planning.get("teaching_tasks", [])
            if isinstance(item, dict) and item.get("id")
        }
        records = []
        for item in planning.get("task_lessons", []):
            if not isinstance(item, dict):
                continue
            preferences = [dict(value) for value in item.get("time_preferences") or [] if isinstance(value, dict)]
            if dataset == "lesson_time_preferences" and not preferences:
                continue
            task = tasks.get(str(item.get("teaching_task_id") or ""), {})
            records.append(
                {
                    **dict(item),
                    "time_preferences": preferences,
                    "homeroom_id": task.get("homeroom_id"),
                    "homeroom_name": task.get("homeroom_name"),
                    "subject_id": task.get("subject_id"),
                    "subject_name": task.get("subject_name"),
                    "primary_teacher_id": task.get("primary_teacher_id"),
                    "teacher_name": task.get("teacher_name"),
                    "course_plan_id": task.get("course_plan_id"),
                    "task_required_room_type": task.get("required_room_type"),
                    "task_room_usage": _task_room_usage(task)["room_usage"],
                }
            )
    elif dataset == "constraints":
        records = [
            dict(item)
            for item in repo.list_constraints(organization_id, str(project_id)).get("constraints", [])
            if isinstance(item, dict)
        ]
    else:
        raise ValueError("不支持的数据查询类型。")

    filtered = [record for record in records if _project_query_matches(record, filters)]
    page = filtered[offset : offset + limit]
    context_truncated = False
    while page and len(json.dumps(page, ensure_ascii=False, default=str)) > 160_000:
        page.pop()
        context_truncated = True
    return {
        "ok": True,
        "dataset": dataset,
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "has_more": offset + len(page) < len(filtered),
        "context_truncated": context_truncated,
        "records": page,
    }


def _task_room_usage(task: dict) -> dict:
    if task.get("required_room_type") == "__no_room__":
        state, label = "not_used", "不使用教室"
    elif task.get("fixed_room_id") or task.get("room_ids") or task.get("room_options"):
        state, label = "assigned", "使用教室，已分配"
    else:
        state, label = "unassigned", "使用教室，尚未分配；不是不使用教室"
    return {"room_usage": state, "room_usage_label": label}


def _project_query_matches(record: dict, filters: dict) -> bool:
    if "zero_lessons" in filters and (record.get("lesson_count") is None or (record["lesson_count"] == 0) != filters["zero_lessons"]):
        return False
    if filters.get("arrangement") and record.get("arrangement") != filters["arrangement"]:
        return False
    id_filters = {
        "ids": ("id",),
        "homeroom_ids": ("homeroom_id",),
        "subject_ids": ("subject_id",),
        "teacher_ids": ("primary_teacher_id", "teacher_id"),
        "teaching_task_ids": ("teaching_task_id", "id"),
        "lesson_ids": ("id",),
    }
    for filter_name, record_fields in id_filters.items():
        requested = {str(value) for value in filters.get(filter_name) or [] if value}
        if requested and not any(str(record.get(field) or "") in requested for field in record_fields):
            return False
    if filters.get("enabled_only") and record.get("enabled") is False:
        return False
    preferences = record.get("time_preferences") or []
    if filters.get("has_time_preferences") is True and not preferences:
        return False
    if filters.get("has_time_preferences") is False and preferences:
        return False
    penalties = {int(value) for value in filters.get("preference_penalties") or []}
    if penalties and not any(int(item.get("penalty") or 0) in penalties for item in preferences if isinstance(item, dict)):
        return False
    query = str(filters.get("query") or "").strip().casefold()
    if query and query not in json.dumps(record, ensure_ascii=False, default=str).casefold():
        return False
    return True


def execute_agent_action(
    repo: SchedulingRepository,
    action: dict,
    enqueue=None,
    *,
    selected_item_ids: list[str] | None = None,
) -> dict:
    organization_id = str(action["organization_id"])
    project_id = str(action.get("project_id") or "")
    operation = str(action["operation"])
    target = str(action["target"])
    payload = _normalize_payload(action.get("payload"))

    if target == "term" and operation in {"update", "bulk_upsert"}:
        return repo.update_active_term(organization_id, payload)
    if target == "teacher" and operation == "create":
        return repo.create_teacher(organization_id, payload)
    if target == "teacher" and operation == "update":
        return repo.update_teacher(organization_id, _resource_id(repo, organization_id, payload, "teacher"), payload)
    if target == "teacher" and operation == "delete":
        items = _delete_items(payload, "teacher")
        if len(items) > 1:
            return _bulk_execute({"items": items}, lambda item: _delete_teacher(repo, organization_id, item))
        return _delete_teacher(repo, organization_id, items[0] if items else payload)
    if target == "teacher" and operation == "bulk_upsert":
        return _bulk_execute(payload, lambda item: _upsert_teacher(repo, organization_id, item))
    school_handlers = {
        "homeroom": (repo.create_homeroom, repo.update_homeroom, repo.delete_homeroom),
        "subject": (repo.create_subject, repo.update_subject, repo.delete_subject),
        "room_type": (repo.create_room_type, repo.update_room_type, repo.delete_room_type),
        "room": (repo.create_room, repo.update_room, repo.delete_room),
    }
    if target in school_handlers:
        creator, updater, deleter = school_handlers[target]
        if operation == "create":
            return creator(organization_id, payload)
        if operation == "update":
            return updater(organization_id, _resource_id(repo, organization_id, payload, target), payload)
        if operation == "delete":
            resource_id = _resource_id(repo, organization_id, payload, target)
            deleter(organization_id, resource_id)
            return {"status": "deleted", "target": target, "id": resource_id}
        if operation == "bulk_upsert":
            return _bulk_execute(payload, lambda item: creator(organization_id, item))
    if target == "timetable_template":
        _require_project(project_id)
        if operation == "delete":
            template_id = _resource_id(repo, organization_id, payload, target)
            repo.delete_weekly_timetable_template(organization_id, template_id)
            return {"status": "deleted", "target": target, "id": template_id}
        if operation == "bulk_upsert":
            return _bulk_execute(payload, lambda item: _upsert_timetable_template(repo, organization_id, project_id, item))
        return _upsert_timetable_template(repo, organization_id, project_id, payload, update=operation == "update")
    if target == "course_plan" and operation in {"create", "update", "delete", "bulk_upsert"}:
        _require_project(project_id)
        if operation == "delete":
            plan_id = _resource_id(repo, organization_id, payload, target)
            repo.delete_course_plan(organization_id, project_id, plan_id)
            return {"status": "deleted", "target": target, "id": plan_id}
        if operation == "bulk_upsert":
            return _bulk_execute(payload, lambda item: repo.create_course_plan(organization_id, project_id, item))
        return repo.create_course_plan(organization_id, project_id, payload)
    if target == "task" and operation in {"create", "update", "delete", "bulk_upsert"}:
        _require_project(project_id)
        if operation == "delete":
            task_id = _resource_id(repo, organization_id, payload, target)
            repo.delete_teaching_task(organization_id, project_id, task_id)
            return {"status": "deleted", "target": target, "id": task_id}
        if operation == "update":
            task_id = _resource_id(repo, organization_id, payload, target)
            return repo.update_teaching_task(organization_id, project_id, task_id, payload)
        if operation == "bulk_upsert":
            return _bulk_execute(payload, lambda item: repo.create_teaching_task(organization_id, project_id, item))
        return repo.create_teaching_task(organization_id, project_id, payload)
    if target == "constraint" and operation == "create":
        _require_project(project_id)
        return repo.create_distribution_constraint(organization_id, project_id, payload)
    if target == "constraint" and operation == "update":
        _require_project(project_id)
        constraint_id = _resource_id(repo, organization_id, payload, target)
        return repo.update_distribution_constraint(organization_id, project_id, constraint_id, payload)
    if target == "constraint" and operation == "delete":
        _require_project(project_id)
        constraint_id = _resource_id(repo, organization_id, payload, target)
        repo.delete_distribution_constraint(organization_id, project_id, constraint_id)
        return {"status": "deleted", "target": target, "id": constraint_id}
    if target == "constraint" and operation == "bulk_upsert":
        _require_project(project_id)
        groups = payload.get("groups")
        if not isinstance(groups, list) or not groups:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Constraint action requires at least one group",
            )
        selected = {str(value) for value in selected_item_ids or [] if value}
        if selected:
            payload["groups"] = [
                group for group in groups if str(group.get("id") or "") in selected
            ]
        if not payload["groups"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No constraint groups were selected",
            )
        return repo.create_constraint_groups(
            str(action["user_id"]),
            organization_id,
            project_id,
            payload,
        )
    if target == "problem_xml" and operation == "preview":
        _require_project(project_id)
        return build_preview_problem(project_id, organization_id, repo)
    if target == "run" and operation == "run":
        _require_project(project_id)
        repo.sync_auto_constraints(organization_id, project_id)
        run = create_scheduling_run(
            organization_id,
            project_id,
            str(action["user_id"]),
            payload.get("algorithm_config") or {"source": "ai_agent"},
            repository=repo,
        )
        if enqueue:
            enqueue(
                {
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "run_id": run["run_id"],
                    "algorithm_config": run.get("algorithm_config") or {},
                }
            )
        return run
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported agent action: {operation} {target}",
    )


def execute_agent_action_items(
    repo: SchedulingRepository,
    action: dict,
    items: list[dict],
    enqueue=None,
) -> dict:
    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="操作没有可执行的数据库明细。",
        )
    pending_jobs: list[dict] = []
    results: list[dict] = []
    transaction = getattr(repo, "agent_action_transaction", None)
    context = transaction() if callable(transaction) else _NoopTransaction()
    with context:
        for item in items:
            operation = str(item.get("operation") or "")
            if operation == "skip":
                results.append({"item_id": item.get("id"), "status": "skipped"})
                continue
            target = str(item.get("target") or "")
            if operation not in ALLOWED_AGENT_ACTIONS.get(target, set()) and not (
                operation in {"create", "update", "delete"}
                and target in ALLOWED_AGENT_ACTIONS
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的操作明细：{operation} {target}",
                )
            item_action = {
                **action,
                "target": target,
                "operation": operation,
                "payload": item.get("after_data") or item.get("identity") or {},
            }
            if operation == "create" and target == "timetable_template":
                # A compiled create has a planned ID, not an existing template to update.
                item_action["payload"] = {key: value for key, value in item_action["payload"].items() if key != "id"}
            if operation == "update" and target == "course_plan":
                item_action["operation"] = "create"
            if target == "constraint" and isinstance((item.get("after_data") or {}).get("groups"), list):
                item_action["operation"] = "bulk_upsert"
            if operation == "update" and target in {"homeroom", "subject", "room_type", "room"}:
                result = _execute_school_update(repo, action, item)
            elif operation == "update" and target == "task":
                result = repo.update_teaching_task(
                    str(action["organization_id"]),
                    str(action.get("project_id") or ""),
                    str(item.get("entity_id") or item.get("identity", {}).get("id") or ""),
                    dict(item.get("after_data") or {}),
                )
            else:
                result = execute_agent_action(
                    repo,
                    item_action,
                    pending_jobs.append if enqueue else None,
                )
            result_record = result if isinstance(result, dict) else {"result": result}
            results.append(
                {
                    "item_id": item.get("id"),
                    "status": "executed",
                    "entity_id": _result_entity_id(result_record),
                    "result": result_record,
                }
            )
        execution_result = {
            "created_or_updated": sum(1 for item in results if item["status"] == "executed"),
            "failed": 0,
            "skipped": sum(1 for item in results if item["status"] == "skipped"),
            "results": results,
        }
        if execution_result["created_or_updated"] == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="操作没有产生任何数据库写入。",
            )
        if len(results) == 1 and isinstance(results[0].get("result"), dict):
            execution_result.update(results[0]["result"])
        repo.update_agent_action_item_results(str(action["id"]), results)
        repo.update_agent_action_status(
            str(action["user_id"]), str(action["id"]), "executed", execution_result, None
        )
    if enqueue:
        for job in pending_jobs:
            try:
                enqueue(job)
            except Exception as exc:
                execution_result.setdefault("warnings", []).append(
                    f"排课运行已创建，但任务入队失败，需要重试：{exc}"
                )
        if execution_result.get("warnings"):
            repo.update_agent_action_status(
                str(action["user_id"]), str(action["id"]), "executed", execution_result, None
            )
    return execution_result


class _NoopTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _execute_school_update(repo: SchedulingRepository, action: dict, item: dict) -> dict:
    organization_id = str(action["organization_id"])
    entity_id = str(item.get("entity_id") or item.get("identity", {}).get("id") or "")
    payload = dict(item.get("after_data") or {})
    target = str(item["target"])
    updater = {
        "homeroom": repo.update_homeroom,
        "subject": repo.update_subject,
        "room_type": repo.update_room_type,
        "room": repo.update_room,
    }[target]
    return updater(organization_id, entity_id, payload)


def _result_entity_id(result: dict) -> str | None:
    for key in ("id", "run_id", "constraint_id"):
        if result.get(key):
            return str(result[key])
    nested = result.get("task")
    if isinstance(nested, dict) and nested.get("id"):
        return str(nested["id"])
    return None


def _require_project(project_id: str) -> None:
    if not project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project is required for this action")


def _normalize_payload(raw_payload) -> dict:
    if raw_payload is None:
        return {}
    if isinstance(raw_payload, dict):
        return dict(raw_payload)
    if isinstance(raw_payload, list):
        return {"items": raw_payload}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent action payload must be an object")


def _upsert_teacher(repo: SchedulingRepository, organization_id: str, payload: dict) -> dict:
    teacher_id = _optional_resource_id(repo, organization_id, payload, "teacher")
    if teacher_id:
        return repo.update_teacher(organization_id, teacher_id, payload)
    return repo.create_teacher(organization_id, payload)


def _upsert_timetable_template(
    repo: SchedulingRepository,
    organization_id: str,
    project_id: str,
    payload: dict,
    *,
    update: bool = False,
) -> dict:
    normalized = dict(payload)
    normalized["project_id"] = project_id
    template_id = str(normalized.get("id") or normalized.get("template_id") or "")
    periods = normalized.pop("periods", None)
    normalized.pop("template_id", None)
    if update or template_id:
        if not template_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="课表模板更新缺少模板 ID。")
        result = repo.update_weekly_timetable_template(organization_id, template_id, normalized)
    else:
        result = repo.create_weekly_timetable_template(organization_id, normalized)
        template_id = str(result.get("id") or "")
    if isinstance(periods, list) and template_id:
        repo.replace_weekly_timetable_periods(organization_id, template_id, periods)
    return result


def _delete_teacher(repo: SchedulingRepository, organization_id: str, payload: dict) -> dict:
    teacher_id = _resource_id(repo, organization_id, payload, "teacher")
    repo.delete_teacher(organization_id, teacher_id)
    return {"status": "deleted", "target": "teacher", "id": teacher_id}


def _delete_items(payload: dict, target: str) -> list[dict]:
    items = payload.get("items")
    if isinstance(items, list):
        return [_normalize_delete_item(item, target) for item in items]
    for key in ("ids", f"{target}_ids", "record_ids"):
        values = payload.get(key)
        if isinstance(values, list):
            return [{f"{target}_id": item} for item in values]
    names = payload.get("names")
    if isinstance(names, list):
        return [{"name": item} for item in names]
    for key in ("id", f"{target}_id", "record_id", "name"):
        value = payload.get(key)
        if isinstance(value, list):
            if key == "name":
                return [{"name": item} for item in value]
            return [{key: item} for item in value]
    return []


def _normalize_delete_item(item, target: str) -> dict:
    if isinstance(item, dict):
        return dict(item)
    if isinstance(item, str):
        return {f"{target}_id": item}
    return {"id": item}


def _optional_resource_id(repo: SchedulingRepository, organization_id: str, payload: dict, target: str) -> str:
    try:
        return _resource_id(repo, organization_id, payload, target)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return ""
        detail = str(exc.detail)
        if "required" in detail:
            return ""
        raise


def _resource_id(repo: SchedulingRepository, organization_id: str, payload: dict, target: str) -> str:
    for key in ("id", f"{target}_id", "record_id"):
        value = payload.get(key)
        if isinstance(value, list):
            continue
        if value:
            return str(value)
    name = str(payload.get("name") or "").strip()
    if target == "teacher" and name:
        matches = [
            item
            for item in repo.list_school_data(organization_id).get("teachers", [])
            if str(item.get("name") or "").strip() == name
        ]
        if len(matches) == 1:
            return str(matches[0]["id"])
        if len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Multiple teachers have this name; provide teacher id before deleting",
            )
        explicit_delete = any(payload.get(key) for key in ("id", f"{target}_id", "record_id"))
        if explicit_delete:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{target} not found",
            )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{target} id is required for this action",
    )


def _bulk_execute(payload: dict, executor) -> dict:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="批量操作必须提供非空 items 列表。")
    results = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"批量操作第 {index + 1} 项必须是结构化对象。",
            )
        results.append(executor(item))
    return {"created_or_updated": len(results), "failed": 0, "results": results, "errors": []}
