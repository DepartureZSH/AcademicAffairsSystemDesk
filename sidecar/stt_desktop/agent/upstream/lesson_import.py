"""Deterministic six-column lesson imports; models decide policy, never rewrite rows."""
from collections import defaultdict
import hashlib
import json

from stt_desktop.agent.upstream.compiler import ActionCompilationError

HEADERS = ("班级", "科目", "教师", "默认教室", "课次名", "课次教室")
NO_ROOM = {"不使用教室", "无需教室", "无教室"}
POLICY_TOOL = {"type": "function", "function": {
    "name": "resolve_import_policy",
    "description": "仅解释用户对已上传课程表的处理策略。不得输出课程、任务、课次或逐行数据。",
    "parameters": {"type": "object", "additionalProperties": False, "properties": {
        "intent": {"type": "string", "enum": ["import", "other"]},
        "existing": {"type": "string", "enum": ["preserve", "update"]},
        "missing_subjects": {"type": "string", "enum": ["leave", "not_scheduled"]},
        "teacher_aliases": {"type": "object", "additionalProperties": {"type": ["string", "null"]}},
        "questions": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
    }, "required": ["intent", "existing", "missing_subjects", "teacher_aliases", "questions"]},
}}


def read_lesson_rows(attachments):
    rows = []
    recognized = False
    for attachment in attachments:
        for sheet in (attachment.get("extracted_data") or {}).get("sheets", []):
            header = None
            for row in sheet.get("rows") or []:
                values = [str(value if value is not None else "").strip() for value in row.get("values", [])]
                if header is None:
                    if all(key in values for key in HEADERS):
                        if sheet.get("truncated") or any(values.count(key) != 1 for key in HEADERS):
                            raise ActionCompilationError([{"code": "incomplete_import_source", "message": f"{sheet.get('name')}被截断或含重复表头，不能完整导入。"}])
                        header = {key: values.index(key) for key in HEADERS}
                        recognized = True
                    continue
                record = {key: values[index] if index < len(values) else "" for key, index in header.items()}
                if not record["课次名"]:
                    continue
                record["source_ref"] = {"attachment_id": attachment.get("id"), "sheet": sheet.get("name"), "row": row.get("row")}
                rows.append(record)
    return rows if recognized else None


def source_key(attachments):
    return hashlib.sha256(json.dumps([
        {"id": item.get("id"), "data": item.get("extracted_data")} for item in attachments
    ], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def name_indexes(school):
    indexes = {}
    for key in ("homerooms", "subjects", "teachers", "rooms"):
        index = defaultdict(list)
        for record in school.get(key, []):
            index[str(record.get("name") or "").strip()].append(record)
        indexes[key] = index
    return indexes


def policy_context(rows, school, planning):
    names = name_indexes(school)
    teacher_names = sorted({row["教师"] for row in rows})
    source_names = defaultdict(set)
    for row in rows:
        source_names[(row["班级"], row["科目"])].add(row["课次名"])
    class_names = {str(item["id"]): item["name"] for item in school.get("homerooms", [])}
    subject_names = {str(item["id"]): item["name"] for item in school.get("subjects", [])}
    tasks = {str(item["id"]): item for item in planning.get("teaching_tasks", [])}
    different_labels = 0
    for lesson in planning.get("task_lessons", []):
        task = tasks.get(str(lesson.get("teaching_task_id")), {})
        expected = source_names.get((class_names.get(str(task.get("homeroom_id"))), subject_names.get(str(task.get("subject_id")))))
        if expected and lesson.get("label") not in expected:
            different_labels += 1
    return {
        "classes": len({row["班级"] for row in rows}), "lessons": len(rows),
        "unmatched_teachers": [name for name in teacher_names if name and len(names["teachers"].get(name, [])) != 1],
        "blank_teacher_rows": sum(not row["教师"] for row in rows),
        "existing_tasks": len(planning.get("teaching_tasks", [])),
        "existing_lesson_names_different_from_source": different_labels,
        "contract": "每个有效行一课次；同班同科同教师合并任务；课长沿用真实科目；默认教室和课次教室逐行读取。",
    }


def validate_policy(raw):
    if not isinstance(raw, dict) or raw.get("intent") not in {"import", "other"} or raw.get("existing") not in {"preserve", "update"} or raw.get("missing_subjects") not in {"leave", "not_scheduled"}:
        raise ValueError("导入策略格式无效")
    aliases = raw.get("teacher_aliases")
    questions = raw.get("questions")
    if not isinstance(aliases, dict) or any(not isinstance(key, str) or (value is not None and not isinstance(value, str)) for key, value in aliases.items()):
        raise ValueError("教师处理策略无效")
    if not isinstance(questions, list) or len(questions) > 6 or any(not isinstance(q, str) or not q.strip() for q in questions):
        raise ValueError("补充问题格式无效")
    return {key: raw[key] for key in ("intent", "existing", "missing_subjects", "teacher_aliases", "questions")}


def import_diagnostics(rows, school, planning, issues):
    """Give AI concrete discrepancies, not the entire workbook or only an error count."""
    indexes = name_indexes(school)
    missing = {name for issue in issues for name in (issue.get("coverage") or {}).get("missing_classes", [])}
    references = {(ref.get("attachment_id"), ref.get("sheet"), ref.get("row")) for issue in issues if (ref := issue.get("source_ref"))}
    relevant = [row for row in rows if (row["source_ref"].get("attachment_id"), row["source_ref"].get("sheet"), row["source_ref"].get("row")) in references]
    selected = (relevant or [row for row in rows if not missing or row["班级"] in missing])[:12]
    examples = []
    for row in selected:
        class_ids = {str(item["id"]) for item in indexes["homerooms"].get(row["班级"], [])}
        subject_ids = {str(item["id"]) for item in indexes["subjects"].get(row["科目"], [])}
        existing = []
        for task in planning.get("teaching_tasks", []):
            if str(task.get("homeroom_id")) not in class_ids or str(task.get("subject_id")) not in subject_ids:
                continue
            lessons = task.get("lessons")
            if not isinstance(lessons, list):
                lessons = [lesson for lesson in planning.get("task_lessons", []) if str(lesson.get("teaching_task_id")) == str(task["id"])]
            existing.append({"teacher": task.get("teacher_name"), "duration_slots": task.get("duration_slots"),
                "room": task.get("room_name"), "lesson_count": len(lessons),
                "lesson_names": [lesson.get("label") for lesson in lessons[:6]]})
        examples.append({"source": row, "existing_tasks": existing[:4]})
    return {"issue_count": len(issues), "issues": issues[:12], "examples": examples,
            "examples_truncated": len(rows) > len(selected), "summary": policy_context(rows, school, planning)}


def build_lesson_proposals(rows, school, planning, policy):
    indexes = name_indexes(school)
    issues, groups, pairs = [], {}, set()
    aliases = policy["teacher_aliases"]

    def resolve(kind, name, row, optional=False):
        if optional and not name:
            return None
        matches = indexes[kind].get(name, [])
        if len(matches) != 1:
            ref = row["source_ref"]
            label = {"homerooms": "班级", "subjects": "科目", "teachers": "教师", "rooms": "教室"}[kind]
            question = f"{label}“{name or '空白名称'}”无法唯一匹配，请核对系统名称。"
            if kind == "teachers":
                question += "也可明确是否将该教师名称对应的课程暂留为未指定教师。"
            issues.append({"code": "import_reference", "message": f"{ref['sheet']}第{ref['row']}行：{name or '空白名称'}无法唯一匹配{label}。", "question": question, "source_ref": ref})
            return None
        return matches[0]

    for row in rows:
        homeroom = resolve("homerooms", row["班级"], row)
        subject = resolve("subjects", row["科目"], row)
        teacher_name = aliases.get(row["教师"], row["教师"])
        if teacher_name is None:
            teacher = None
        elif not teacher_name:
            issues.append({"code": "import_teacher", "message": f"{row['source_ref']['sheet']}第{row['source_ref']['row']}行教师为空。", "question": "附件中教师确实为空的行是否保留为未指定教师？"})
            teacher = None
        else:
            teacher = resolve("teachers", teacher_name, row)
        default_name = row["默认教室"]
        default_room = None if default_name in NO_ROOM else resolve("rooms", default_name, row)
        lesson_name = row["课次教室"]
        if lesson_name == "默认":
            lesson_rooms = []
        elif lesson_name in NO_ROOM:
            lesson_rooms = []
            if default_room:
                issues.append({"code": "unsupported_room_override", "message": f"{row['source_ref']['sheet']}第{row['source_ref']['row']}行要求有默认教室但单课次不使用教室，当前数据模型无法无损表达，请单独配置该任务。"})
        else:
            room = resolve("rooms", lesson_name, row)
            lesson_rooms = [str(room["id"])] if room else []
        if not homeroom or not subject:
            continue
        pair = (str(homeroom["id"]), str(subject["id"]))
        pairs.add(pair)
        key = (*pair, str(teacher["id"]) if teacher else None)
        duration = subject.get("default_duration_slots")
        if not isinstance(duration, int) or duration <= 0:
            issues.append({"code": "missing_duration", "message": f"科目{subject['name']}没有有效默认课长。"})
            continue
        room_id = str(default_room["id"]) if default_room else None
        required_room_type = "__no_room__" if default_name in NO_ROOM else None
        if required_room_type == "__no_room__" and lesson_rooms:
            issues.append({"code": "unsupported_room_override", "message": f"{row['班级']}、{row['科目']}明确不使用教室，但课次又指定了教室，请确认教室设置。"})
        if key not in groups:
            groups[key] = {"homeroom_id": pair[0], "subject_id": pair[1], "primary_teacher_id": key[2],
                "fixed_room_id": room_id, "room_ids": [room_id] if room_id else [], "duration_slots": duration,
                "required_room_type": required_room_type,
                "lessons": [], "source_ref": {**row["source_ref"], "rows": []}}
        group = groups[key]
        if group["fixed_room_id"] != room_id or group["required_room_type"] != required_room_type:
            issues.append({"code": "inconsistent_default_room", "message": f"{row['班级']}、{row['科目']}同一教师的默认教室不一致，请统一默认教室或使用课次教室。"})
        group["lessons"].append({"label": row["课次名"], "duration_slots": duration, "room_ids": lesson_rooms})
        group["source_ref"]["rows"].append(row["source_ref"])
    if issues:
        raise ActionCompilationError(issues)
    existing = defaultdict(list)
    for task in planning.get("teaching_tasks", []):
        existing[(str(task.get("homeroom_id")), str(task.get("subject_id")), str(task["primary_teacher_id"]) if task.get("primary_teacher_id") else None)].append(task)
    tasks, preserved = [], 0
    plan_totals = defaultdict(int)
    for key, group in groups.items():
        matches = existing.get(key, [])
        if len(matches) > 1:
            issues.append({"code": "ambiguous_task", "message": f"班级{key[0]}科目{key[1]}存在多条相同教师任务，请先消除歧义。"})
            continue
        group["weekly_slots"] = len(group["lessons"])
        if matches:
            if policy["existing"] == "preserve":
                plan_totals[key[:2]] += int(matches[0].get("lesson_count") or matches[0].get("weekly_slots") or len(group["lessons"]))
                preserved += 1
                continue
            group["id"] = str(matches[0]["id"])
            existing_count = int(matches[0].get("lesson_count") or matches[0].get("weekly_slots") or 0)
            # The compiler preserves extra existing lessons rather than deleting them.
            group["weekly_slots"] = max(group["weekly_slots"], existing_count)
        plan_totals[key[:2]] += group["weekly_slots"]
        tasks.append(group)
    for key, records in existing.items():
        if key not in groups:
            plan_totals[key[:2]] += sum(int(task.get("lesson_count") or task.get("weekly_slots") or 0) for task in records)
    proposals = []
    if tasks:
        proposals.append({"scope": "project", "target": "task", "operation": "bulk_upsert", "payload": {"items": tasks}, "human_summary": f"按原始附件整理{len(tasks)}个授课任务及完整课次", "risk_level": "medium"})
        changed_pairs = {(task["homeroom_id"], task["subject_id"]) for task in tasks}
        plans = [{"homeroom_id": h, "subject_id": s, "weekly_slots": plan_totals[(h, s)]} for h, s in sorted(changed_pairs)]
        proposals.append({"scope": "project", "target": "course_plan", "operation": "bulk_upsert", "payload": {"items": plans}, "human_summary": "同步课程计划与所有授课任务的课次数", "risk_level": "medium"})
    not_scheduled = already_not_scheduled = 0
    if policy["missing_subjects"] == "not_scheduled":
        missing = [{"homeroom_id": h, "subject_id": str(s["id"])} for h in sorted({pair[0] for pair in pairs}) for s in school.get("subjects", []) if (h, str(s["id"])) not in pairs]
        affected = {(item["homeroom_id"], item["subject_id"]) for item in missing}
        conflicts = [task for task in planning.get("teaching_tasks", []) if (str(task.get("homeroom_id")), str(task.get("subject_id"))) in affected]
        if conflicts:
            issues.append({"code": "destructive_import_conflict", "message": f"附件未列科目中存在{len(conflicts)}条已有授课任务。本导入流程不会删除已有任务，请先单独审核这些任务的删除，或改为保留附件未列科目。"})
        else:
            zero_pairs = {(str(plan.get("homeroom_id")), str(plan.get("subject_id")))
                for plan in planning.get("course_plans", []) if plan.get("weekly_slots") == 0}
            already_not_scheduled = len(affected & zero_pairs)
            missing = [item for item in missing if (item["homeroom_id"], item["subject_id"]) not in zero_pairs]
            not_scheduled = len(missing)
            if missing:
                proposals.append({"scope": "project", "target": "course_plan", "operation": "mark_not_scheduled", "payload": {"items": missing}, "human_summary": f"将附件涉及班级的{len(missing)}个未列科目设为不安排", "risk_level": "medium"})
    if issues:
        raise ActionCompilationError(issues)
    return proposals, {"classes": len({row["班级"] for row in rows}), "lessons": len(rows), "tasks": len(groups), "preserved_tasks": preserved,
        "not_scheduled": not_scheduled, "already_not_scheduled": already_not_scheduled}
