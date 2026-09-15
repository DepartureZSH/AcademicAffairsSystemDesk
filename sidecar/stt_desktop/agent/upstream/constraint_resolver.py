from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any
from stt_desktop.agent.upstream.distributions import GROUP_TYPES, parse_distribution


ALLOWED_SCOPE_KEYS = {
    "homeroom_ids",
    "homeroom_names",
    "subject_ids",
    "subject_names",
    "teacher_ids",
    "teacher_names",
    "lesson_ordinals",
    "enabled_only",
}
ALLOWED_GROUP_KEYS = {"teaching_task_id", "all"}
ALLOWED_SCOPE_KEYS.update("exclude_" + key for key in (
    "homeroom_ids", "homeroom_names", "subject_ids", "subject_names", "teacher_ids", "teacher_names"))
SOFT_PENALTIES = {10, 30, 60}

BUILTIN_COMPILERS = {
    "course_consecutive": {
        "compiler_key": "consecutive",
        "distribution_type": "Consecutive",
        "entity_scope": "lesson",
        "minimum_items": 2,
    },
    "course_non_consecutive": {
        "compiler_key": "different_days",
        "distribution_type": "DifferentDays",
        "entity_scope": "lesson",
        "minimum_items": 2,
    },
    "course_same_time_different_weeks": {
        "compiler_key": "different_week_same_day_same_start",
        "distribution_type": "DifferentWeekSameDaySameStart",
        "entity_scope": "lesson",
        "minimum_items": 2,
    },
    "spread_different_days": {
        "compiler_key": "different_days",
        "distribution_type": "DifferentDays",
        "entity_scope": "lesson",
        "minimum_items": 2,
    },
    "fixed_candidate_time": {
        "compiler_key": None,
        "distribution_type": None,
        "entity_scope": "lesson",
        "minimum_items": 1,
    },
    "teacher_unavailable": {
        "compiler_key": None,
        "distribution_type": None,
        "entity_scope": "teacher",
        "minimum_items": 1,
    },
}

CONSTRAINT_SCOPE_TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "resolve_constraint_scope",
            "description": "Interpret a Chinese scheduling constraint scope using only the allowed selector language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "constraint_key": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "scope_query": {
                        "type": "object",
                        "properties": {
                            "homeroom_ids": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "homeroom_names": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "subject_ids": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "subject_names": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "teacher_ids": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "teacher_names": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                            "lesson_ordinals": {"type": "array", "items": {"type": "integer", "minimum": 1}},
                            "enabled_only": {"type": "boolean"},
                        },
                        "additionalProperties": False,
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["teaching_task_id", "all"]},
                    },
                    "parameters": {"type": "object"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "unsupported_reason": {"type": "string", "description": "无法用选择器表达的条件，如已排时间筛选；可表达时为空。"},
                },
                "required": [
                    "constraint_key",
                    "interpretation",
                    "scope_query",
                    "group_by",
                    "parameters",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
    }
]

_scope_properties = CONSTRAINT_SCOPE_TOOL_SCHEMA[0]["function"]["parameters"]["properties"]["scope_query"]["properties"]
for _key in sorted(ALLOWED_SCOPE_KEYS):
    if _key.startswith("exclude_"):
        _scope_properties[_key] = {"type": "array", "items": {"type": "string"}}


def compact_constraint_context(
    planning: dict,
    school_data: dict,
    existing_constraints: list[dict],
    compile_schema: dict,
) -> dict:
    tasks = planning.get("teaching_tasks") or []
    lessons = planning.get("task_lessons") or []
    lessons_by_task: dict[str, list[dict]] = {}
    for lesson in lessons:
        lessons_by_task.setdefault(str(lesson.get("teaching_task_id") or ""), []).append(
            {
                "id": str(lesson.get("id") or ""),
                "xml_class_id": str(lesson.get("xml_class_id") or lesson.get("id") or ""),
                "lesson_index": int(lesson.get("lesson_index") or 0),
                "label": str(lesson.get("label") or ""),
                "enabled": lesson.get("enabled", True) is not False,
            }
        )
    compact_tasks = []
    for task in tasks:
        task_id = str(task.get("id") or "")
        compact_tasks.append(
            {
                "id": task_id,
                "homeroom_id": str(task.get("homeroom_id") or ""),
                "homeroom_name": str(task.get("homeroom_name") or ""),
                "subject_id": str(task.get("subject_id") or ""),
                "subject_name": str(task.get("subject_name") or ""),
                "teacher_id": str(task.get("primary_teacher_id") or task.get("teacher_id") or ""),
                "teacher_name": str(task.get("teacher_name") or ""),
                "lessons": sorted(lessons_by_task.get(task_id, []), key=lambda item: item["lesson_index"]),
            }
        )
    teacher_names = Counter(str(item.get("name") or "").strip() for item in school_data.get("teachers") or [])
    return {
        "compiler": compile_schema,
        "teaching_tasks": compact_tasks,
        "duplicate_teacher_names": sorted(name for name, count in teacher_names.items() if name and count > 1),
        "existing_constraints": [
            {
                "scenario_type": item.get("scenario_type"),
                "required": item.get("required", True),
                "penalty": item.get("penalty"),
                "lesson_ids": (item.get("parameters") or {}).get("lesson_ids") or [],
            }
            for item in existing_constraints
        ],
    }


def parse_scope_tool_response(response: dict) -> dict:
    message = (((response.get("choices") or [{}])[0]).get("message") or {})
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        if function.get("name") != "resolve_constraint_scope":
            continue
        raw = function.get("arguments") or "{}"
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    content = str(message.get("content") or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    return json.loads(content)


def normalize_scope_proposal(raw: dict, scenario_type: str) -> dict:
    scope_query = raw.get("scope_query") if isinstance(raw.get("scope_query"), dict) else {}
    normalized_scope = {
        key: _normalize_selector(value)
        for key, value in scope_query.items()
        if key in ALLOWED_SCOPE_KEYS
    }
    normalized_scope["enabled_only"] = bool(scope_query.get("enabled_only", True))
    group_by = [
        value
        for value in raw.get("group_by") or ["teaching_task_id"]
        if value in ALLOWED_GROUP_KEYS
    ]
    if scenario_type.startswith("common:ParallelLimit("):
        group_by = ["all"]
    return {
        "constraint_key": str(raw.get("constraint_key") or scenario_type),
        "interpretation": str(raw.get("interpretation") or "按授课任务分别匹配课次"),
        "scope_query": normalized_scope,
        "group_by": group_by or ["teaching_task_id"],
        "parameters": raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {},
        "confidence": max(0.0, min(float(raw.get("confidence") or 0), 1.0)),
    }


def deterministic_scope_fallback(scope_text: str, scenario_type: str, context: dict) -> dict:
    text = scope_text.strip()
    tasks = context.get("teaching_tasks") or []
    subject_names = sorted(
        {str(task.get("subject_name") or "") for task in tasks if str(task.get("subject_name") or "") in text}
    )
    homeroom_names = sorted(
        {str(task.get("homeroom_name") or "") for task in tasks if str(task.get("homeroom_name") or "") in text}
    )
    teacher_names = sorted(
        {str(task.get("teacher_name") or "") for task in tasks if str(task.get("teacher_name") or "") in text}
    )
    ordinal_count = _chinese_count(text)
    ordinals = list(range(1, ordinal_count + 1)) if ordinal_count else []
    has_selector = bool(subject_names or homeroom_names or teacher_names or "所有" in text or "全部" in text)
    return {
        "constraint_key": scenario_type,
        "interpretation": "每个授课任务分别建立约束",
        "scope_query": {
            "subject_names": subject_names or "*",
            "homeroom_names": homeroom_names or "*",
            "teacher_names": teacher_names or "*",
            "lesson_ordinals": ordinals,
            "enabled_only": True,
        },
        "group_by": ["teaching_task_id"],
        "parameters": {"consecutive_count": ordinal_count} if ordinal_count else {},
        "confidence": 0.9 if has_selector and (subject_names or homeroom_names or teacher_names) else 0.62,
    }


def resolve_scope_groups(
    proposal: dict,
    planning: dict,
    school_data: dict,
    compile_schema: dict,
    *,
    required: bool,
    penalty: int | None,
) -> dict:
    if proposal.get("unsupported_reason"):
        return {"status": "needs_clarification", "question": str(proposal["unsupported_reason"]), "candidates": []}
    unknown = set(proposal.get("scope_query") or {}) - ALLOWED_SCOPE_KEYS
    if unknown:
        return {"status": "needs_clarification", "question": "范围中存在暂不支持的条件，请改用班级、科目、教师和课次序号描述。", "candidates": []}
    proposal = normalize_scope_proposal(proposal, str(proposal.get("constraint_key") or ""))
    scope = proposal["scope_query"]
    for field, task_field in (("homeroom_names", "homeroom_name"), ("subject_names", "subject_name"),
                              ("teacher_names", "teacher_name"), ("homeroom_ids", "homeroom_id"),
                              ("subject_ids", "subject_id"), ("teacher_ids", "primary_teacher_id")):
        excluded = {str(value) for value in _selector_values(scope.get("exclude_" + field))}
        existing = {str(task.get(task_field) or "") for task in planning.get("teaching_tasks", [])}
        if excluded - existing:
            return {"status": "needs_clarification", "question": "未能在当前授课任务中确认要排除的对象："
                    + "、".join(sorted(excluded - existing)) + "。请使用具体班级、科目或教师名称重新搜索。", "candidates": []}
    duplicate_names = _duplicate_teacher_names(school_data.get("teachers") or [])
    requested_teacher_names = set(_selector_values(scope.get("teacher_names")))
    ambiguous_teachers = sorted(requested_teacher_names & duplicate_names)
    if ambiguous_teachers:
        candidates = _teacher_clarification_candidates(
            proposal,
            school_data.get("teachers") or [],
            ambiguous_teachers,
        )
        return {
            "status": "needs_clarification",
            "question": f"教师姓名“{'、'.join(ambiguous_teachers)}”存在重名，请选择具体教师后继续。",
            "candidates": _with_candidate_estimates(candidates, planning, compile_schema),
        }
    requested_ordinals = {
        int(value)
        for value in _selector_values(scope.get("lesson_ordinals"))
        if str(value).isdigit()
    }
    if (
        proposal["constraint_key"] == "course_consecutive"
        and not requested_ordinals
        and not int((proposal.get("parameters") or {}).get("consecutive_count") or 0)
    ):
        return {
            "status": "needs_clarification",
            "question": "需要明确每个授课任务中哪些课次应连续排课。",
            "candidates": _with_candidate_estimates(
                _clarification_candidates(proposal, reason="missing_lesson_range"),
                planning,
                compile_schema,
            ),
        }
    if proposal["confidence"] < 0.72:
        return {
            "status": "needs_clarification",
            "question": "这段范围描述仍有多种理解，请选择最接近的一种。",
            "candidates": _with_candidate_estimates(
                _clarification_candidates(proposal, reason="low_confidence"),
                planning,
                compile_schema,
            ),
        }

    tasks = planning.get("teaching_tasks") or []
    lessons = planning.get("task_lessons") or []
    lessons_by_task: dict[str, list[dict]] = {}
    for lesson in lessons:
        lessons_by_task.setdefault(str(lesson.get("teaching_task_id") or ""), []).append(lesson)

    matching_tasks = [task for task in tasks if _task_matches(task, scope)]
    minimum_items = max(int(compile_schema.get("minimum_items") or 1), 1)
    enabled_only = scope.get("enabled_only", True) is not False
    warnings: list[dict] = []
    groups: list[dict] = []
    combined_lessons: list[tuple[dict, dict]] = []
    for task in matching_tasks:
        task_lessons = sorted(
            lessons_by_task.get(str(task.get("id") or ""), []),
            key=lambda item: int(item.get("lesson_index") or 0),
        )
        disabled = [item for item in task_lessons if item.get("enabled", True) is False]
        if enabled_only:
            task_lessons = [item for item in task_lessons if item.get("enabled", True) is not False]
        if requested_ordinals:
            task_lessons = [
                item for item in task_lessons if int(item.get("lesson_index") or 0) in requested_ordinals
            ]
        if len(task_lessons) < minimum_items:
            warnings.append(
                {
                    "task_id": str(task.get("id") or ""),
                    "homeroom": task.get("homeroom_name") or "",
                    "subject": task.get("subject_name") or "",
                    "reason": f"仅匹配到 {len(task_lessons)} 个可用课次，至少需要 {minimum_items} 个",
                }
            )
            continue
        if disabled:
            warnings.append(
                {
                    "task_id": str(task.get("id") or ""),
                    "reason": f"已忽略 {len(disabled)} 个禁用课次",
                }
            )
        if "all" in proposal["group_by"]:
            combined_lessons.extend((task, lesson) for lesson in task_lessons)
        else:
            groups.append(_build_group(task, task_lessons, required, penalty, compile_schema))

    if combined_lessons:
        first_task = combined_lessons[0][0]
        groups.append(
            _build_group(
                {
                    **first_task,
                    "id": "all",
                    "homeroom_name": "多个班级",
                    "subject_name": "多个科目",
                    "teacher_name": "多位教师",
                },
                [lesson for _task, lesson in combined_lessons],
                required,
                penalty,
                compile_schema,
            )
        )
    if not groups:
        return {
            "status": "no_match",
            "interpretation": proposal["interpretation"],
            "message": "没有找到满足范围且课次数量足够的授课任务。",
            "warnings": warnings,
        }
    compiled_count = sum(1 for item in groups if item["compile_status"] == "compiled")
    draft_count = sum(1 for item in groups if item["compile_status"] != "compiled")
    return {
        "status": "resolved" if compiled_count else "unsupported_draft",
        "interpretation": proposal["interpretation"],
        "scope_query": scope,
        "group_by": proposal["group_by"],
        "parameters": proposal["parameters"],
        "groups": groups,
        "warnings": warnings,
        "compiled_count": compiled_count,
        "draft_count": draft_count,
        "message": (
            "当前排课算法尚未支持此规则。可以保存为禁用草稿，但不会参与排课。"
            if not compiled_count
            else None
        ),
    }


def validate_strength(required: bool, penalty: int | None) -> int | None:
    if required:
        return None
    if penalty not in SOFT_PENALTIES:
        raise ValueError("软约束惩罚值只能选择 10、30 或 60")
    return penalty


def semantic_dedupe_key(
    project_id: str,
    scenario_type: str,
    required: bool,
    penalty: int | None,
    groups: list[dict],
) -> str:
    canonical = {
        "project_id": project_id,
        "scenario_type": scenario_type,
        "required": required,
        "penalty": penalty,
        "groups": [list(group.get("lesson_ids") or []) if scenario_type in {"course_consecutive", "itc2019:Precedence", "itc2019:Consecutive"}
                   else sorted(group.get("lesson_ids") or []) for group in groups],
    }
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return "constraint-ai:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def compiler_for_scenario(scenario_type: str, template: dict | None = None) -> dict:
    schema = dict((template or {}).get("compile_schema") or {})
    if scenario_type.startswith(("itc2019:", "common:ParallelLimit(")):
        distribution_type = scenario_type.split(":", 1)[1]
        try:
            kind, _ = parse_distribution(distribution_type)
        except ValueError:
            return {}
        builtin = {
            "compiler_key": "itc_distribution",
            "distribution_type": distribution_type,
            "entity_scope": "lesson",
            "minimum_items": 1 if kind in GROUP_TYPES else 2,
        }
    else:
        builtin = BUILTIN_COMPILERS.get(scenario_type) or {}
    result = {**builtin, **schema}
    if result.get("distribution_type"):
        try:
            parse_distribution(str(result["distribution_type"]))
        except ValueError:
            return {}
    return result


def _build_group(
    task: dict,
    lessons: list[dict],
    required: bool,
    penalty: int | None,
    compile_schema: dict,
) -> dict:
    lesson_rows = [
        {
            "id": str(lesson.get("id") or ""),
            "xml_class_id": str(lesson.get("xml_class_id") or lesson.get("id") or ""),
            "ordinal": int(lesson.get("lesson_index") or 0),
            "label": str(lesson.get("label") or task.get("subject_name") or "课次"),
            "enabled": lesson.get("enabled", True) is not False,
        }
        for lesson in lessons
    ]
    lesson_ids = [item["xml_class_id"] for item in lesson_rows]
    group_seed = f"{task.get('id')}|{'|'.join(lesson_ids)}"
    compiled = bool(compile_schema.get("compiler_key") and compile_schema.get("distribution_type"))
    return {
        "id": hashlib.sha256(group_seed.encode("utf-8")).hexdigest()[:20],
        "teaching_task_id": str(task.get("id") or ""),
        "homeroom_id": str(task.get("homeroom_id") or ""),
        "homeroom_name": str(task.get("homeroom_name") or "未指定班级"),
        "subject_id": str(task.get("subject_id") or ""),
        "subject_name": str(task.get("subject_name") or "未指定科目"),
        "teacher_id": str(task.get("primary_teacher_id") or task.get("teacher_id") or ""),
        "teacher_name": str(task.get("teacher_name") or "未指定教师"),
        "lesson_ids": lesson_ids,
        "lessons": lesson_rows,
        "group_basis": "按授课任务分组" if task.get("id") != "all" else "合并为一个范围",
        "required": required,
        "penalty": penalty,
        "compile_status": "compiled" if compiled else "pending",
        "compile_label": "已编译" if compiled else "草稿，当前排课算法不会执行",
    }


def _task_matches(task: dict, scope: dict) -> bool:
    if task.get("enabled") is False or task.get("status", "active") != "active":
        return False
    checks = (
        ("homeroom_ids", "homeroom_id"),
        ("homeroom_names", "homeroom_name"),
        ("subject_ids", "subject_id"),
        ("subject_names", "subject_name"),
        ("teacher_ids", "primary_teacher_id"),
        ("teacher_names", "teacher_name"),
    )
    for selector_key, task_key in checks:
        task_value = str(task.get(task_key) or (task.get("teacher_id") if task_key == "primary_teacher_id" else ""))
        excluded = _selector_values(scope.get("exclude_" + selector_key))
        if task_value in {str(value) for value in excluded}:
            return False
        values = _selector_values(scope.get(selector_key))
        if not values:
            continue
        if task_value not in {str(value) for value in values}:
            return False
    return True


def _normalize_selector(value: Any) -> Any:
    if value in (None, "", "*"):
        return "*"
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


def _selector_values(value: Any) -> list[Any]:
    if value in (None, "", "*"):
        return []
    return value if isinstance(value, list) else [value]


def _duplicate_teacher_names(teachers: list[dict]) -> set[str]:
    counts = Counter(str(item.get("name") or "").strip() for item in teachers)
    return {name for name, count in counts.items() if name and count > 1}


def _clarification_candidates(proposal: dict, *, reason: str) -> list[dict]:
    base_scope = proposal.get("scope_query") or {}
    return [
        {
            "id": "per_task_first_two",
            "title": "每个授课任务分别选择前两课次",
            "interpretation": "每个班级、科目、教师组合分别创建一条约束，只使用第1和第2课次。",
            "scope_query": {**base_scope, "lesson_ordinals": [1, 2], "enabled_only": True},
            "group_by": ["teaching_task_id"],
            "suggested_prompt": "按每个授课任务分组，选择第1和第2课次。",
            "reason": reason,
        },
        {
            "id": "per_task_all_enabled",
            "title": "每个授课任务分别使用全部启用课次",
            "interpretation": "每个班级、科目、教师组合分别创建一条约束，包含其全部启用课次。",
            "scope_query": {**base_scope, "lesson_ordinals": [], "enabled_only": True},
            "group_by": ["teaching_task_id"],
            "suggested_prompt": "按每个授课任务分组，使用全部启用课次。",
            "reason": reason,
        },
    ]


def _teacher_clarification_candidates(
    proposal: dict,
    teachers: list[dict],
    ambiguous_names: list[str],
) -> list[dict]:
    base_scope = dict(proposal.get("scope_query") or {})
    base_scope.pop("teacher_names", None)
    candidates: list[dict] = []
    for teacher in teachers:
        name = str(teacher.get("name") or "").strip()
        if name not in ambiguous_names:
            continue
        teacher_id = str(teacher.get("id") or "")
        if not teacher_id:
            continue
        department = str(
            teacher.get("department")
            or teacher.get("group")
            or teacher.get("teacher_group")
            or "未分组"
        )
        candidates.append(
            {
                "id": f"teacher:{teacher_id}",
                "title": f"{name} · {department}",
                "interpretation": f"只匹配教师“{name}”（{department}）负责的授课任务。",
                "scope_query": {
                    **base_scope,
                    "teacher_ids": [teacher_id],
                    "enabled_only": True,
                },
                "group_by": proposal.get("group_by") or ["teaching_task_id"],
                "parameters": proposal.get("parameters") or {},
                "suggested_prompt": f"只选择 {department} 的{name}老师负责的课次。",
                "reason": "teacher_duplicate",
            }
        )
        if len(candidates) >= 4:
            break
    return candidates or _clarification_candidates(proposal, reason="teacher_duplicate")


def _with_candidate_estimates(
    candidates: list[dict],
    planning: dict,
    compile_schema: dict,
) -> list[dict]:
    tasks = planning.get("teaching_tasks") or []
    lessons = planning.get("task_lessons") or []
    lessons_by_task: dict[str, list[dict]] = {}
    for lesson in lessons:
        lessons_by_task.setdefault(str(lesson.get("teaching_task_id") or ""), []).append(lesson)
    minimum_items = max(int(compile_schema.get("minimum_items") or 1), 1)
    enriched: list[dict] = []
    for candidate in candidates:
        scope = candidate.get("scope_query") or {}
        ordinals = {
            int(value)
            for value in _selector_values(scope.get("lesson_ordinals"))
            if str(value).isdigit()
        }
        enabled_only = scope.get("enabled_only", True) is not False
        task_count = 0
        lesson_count = 0
        for task in tasks:
            if not _task_matches(task, scope):
                continue
            matched = [
                lesson
                for lesson in lessons_by_task.get(str(task.get("id") or ""), [])
                if (not enabled_only or lesson.get("enabled", True) is not False)
                and (not ordinals or int(lesson.get("lesson_index") or 0) in ordinals)
            ]
            if len(matched) < minimum_items:
                continue
            task_count += 1
            lesson_count += len(matched)
        enriched.append(
            {
                **candidate,
                "estimate": {
                    "task_count": task_count,
                    "lesson_count": lesson_count,
                },
            }
        )
    return enriched


def _chinese_count(text: str) -> int:
    match = re.search(r"([2-9])\s*(?:节|个)?课次", text)
    if match:
        return int(match.group(1))
    mapping = {"两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
    match = re.search(r"([两二三四五六])\s*(?:节|个)?课次", text)
    return mapping.get(match.group(1), 0) if match else 0
