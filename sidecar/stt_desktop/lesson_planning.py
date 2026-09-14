"""Atomic editing of a teaching task and its individually configured lessons."""

import json
import re

from stt_desktop.lesson_config import parse_lesson_config, parse_task_config
from stt_desktop.storage.project import ENTITY_SPECS, ProjectError, utc_now, uuid7


def save_course_arrangement(project, data, drafts, expected_revision, *, preallocated_ids=None):
    if not isinstance(drafts, list) or len(drafts) > 500:
        raise ProjectError("每条授课任务最多配置 500 个课次")
    task_id = str(data.get("id") or uuid7())
    existing = project.get_entity("teaching_task", task_id)
    spec = ENTITY_SPECS["teaching_task"]
    if set(data) - spec.fields - {"id"}:
        raise ProjectError("授课任务包含未知字段")
    effective = {**(existing or {}), **data}
    if not all(effective.get(key) for key in ("term_id", "homeroom_id", "subject_id")):
        raise ProjectError("请先选择学期、班级和科目")
    term = project.get_entity("term", effective["term_id"])
    homeroom = project.get_entity("homeroom", effective["homeroom_id"])
    if not term or not homeroom or homeroom.get("term_id") not in (None, "", term["id"]):
        raise ProjectError("班级与学期不匹配")
    if effective.get("course_plan_id"):
        plan = project.get_entity("course_plan", effective["course_plan_id"])
        if not plan or any(plan[key] != effective[key] for key in ("term_id", "homeroom_id", "subject_id")):
            raise ProjectError("课程计划不属于当前班级、学期或科目")
    old = {
        item["id"]: item
        for item in project.list_entities("task_lesson")
        if item["teaching_task_id"] == task_id
    }
    slots = {item["id"]: item for item in project.list_entities("time_slot") if item["active"]}
    schedules = {item["id"]: item for item in project.list_entities("bell_schedule")}
    rooms = {item["id"] for item in project.list_entities("room") if item["status"] == "active"}
    try:
        task_config = parse_task_config(effective.get("planning_config", {}))
    except (ValueError, TypeError) as exc:
        raise ProjectError(str(exc)) from exc
    if task_config:
        ids = task_config.get("room_ids", [])
        if type(task_config.get("uses_rooms")) is not bool or not isinstance(ids, list) or len(ids) > 200:
            raise ProjectError("默认教室设置格式无效")
        if any(not isinstance(room, str) or room not in rooms for room in ids) or len(set(ids)) != len(ids):
            raise ProjectError("默认教室不存在、已停用或重复")
    prepared, seen = [], set()
    for index, draft in enumerate(drafts):
        if not isinstance(draft, dict) or set(draft) - {
            "id",
            "label",
            "enabled",
            "duration_slots",
            "week_bits",
            "day_bits",
            "planning_config",
        }:
            raise ProjectError("课次包含未知字段")
        lesson_id = str(draft.get("id") or uuid7())
        new_reserved = lesson_id in (preallocated_ids or set()) and not project.get_entity('task_lesson', lesson_id)
        if lesson_id in seen or (draft.get("id") and lesson_id not in old and not new_reserved):
            raise ProjectError("课次 ID 重复或不属于当前授课任务")
        seen.add(lesson_id)
        duration = draft.get("duration_slots", 1)
        if type(duration) is not int or not 1 <= duration <= 1440:
            raise ProjectError("课长必须为 1–1440 之间的整数")
        weeks = draft.get("week_bits", "1" * term["week_count"])
        days = draft.get("day_bits", "1" * term["day_count"])
        if (
            not isinstance(weeks, str)
            or not re.fullmatch(r"[01]{1,60}", weeks)
            or "1" not in weeks
            or "1" in weeks[term["week_count"] :]
        ):
            raise ProjectError("课次周频率超出学期或未选择上课周")
        if not isinstance(days, str) or not re.fullmatch(r"[01]{1,7}", days) or "1" not in days:
            raise ProjectError("课次上课日无效")
        try:
            config = parse_lesson_config(draft.get("planning_config", {}))
        except (ValueError, TypeError) as exc:
            raise ProjectError(str(exc)) from exc
        if any(room not in rooms for room in config["room_ids"]):
            raise ProjectError("课次教室不存在或已停用，请重新选择")
        for rule in config["preferred_times"]:
            slot = slots.get(rule["time_slot_id"])
            if not slot or schedules[slot["bell_schedule_id"]].get("term_id") not in (
                None,
                "",
                term["id"],
            ):
                raise ProjectError("期望课节已失效或不属于当前学期，请重新选择")
            if any(
                bit == "1" and (i >= len(weeks) or weeks[i] != "1")
                for i, bit in enumerate(rule["week_bits"])
            ):
                raise ProjectError("期望时间周频率超出课次上课周")
        enabled = draft.get("enabled", 1)
        if enabled not in (0, 1, False, True):
            raise ProjectError("课次启用状态无效")
        prepared.append(
            dict(
                id=lesson_id,
                label=str(draft.get("label") or f"第{index + 1}课次")[:200],
                enabled=int(enabled),
                duration_slots=duration,
                week_bits=weeks,
                day_bits=days,
                planning_config=json.dumps(config, ensure_ascii=False),
            )
        )
    removed = set(old) - seen
    for constraint in project.list_entities("constraint"):
        if any(lesson_id in constraint["parameters"] for lesson_id in removed):
            raise ProjectError("待删除的课次仍被约束引用，请先在约束配置中移除引用")
    values = {key: value for key, value in data.items() if key in spec.fields}
    if "planning_config" in values:
        values["planning_config"] = json.dumps(task_config, ensure_ascii=False)
    values["weekly_slots"] = sum(item["duration_slots"] for item in prepared if item["enabled"])
    values["duration_slots"] = prepared[0]["duration_slots"] if prepared else 1
    now = utc_now()
    project._begin_write(expected_revision)
    try:
        plan = project.connection.execute(
            "SELECT id FROM course_plans WHERE term_id = ? AND homeroom_id = ? AND subject_id = ?",
            (effective["term_id"], effective["homeroom_id"], effective["subject_id"]),
        ).fetchone()
        plan_id = plan["id"] if plan else uuid7()
        if not plan:
            project.connection.execute(
                "INSERT INTO course_plans (id, term_id, homeroom_id, subject_id, weekly_slots, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (plan_id, effective["term_id"], effective["homeroom_id"], effective["subject_id"], values["weekly_slots"], now, now),
            )
        values["course_plan_id"] = plan_id
        if existing:
            assignments = ", ".join(f"{key} = ?" for key in values)
            project.connection.execute(
                f"UPDATE teaching_tasks SET {assignments}, updated_at = ? WHERE id = ?",  # noqa: S608
                [*values.values(), now, task_id],
            )
        else:
            columns = ["id", *values, "created_at", "updated_at"]
            project.connection.execute(
                f"INSERT INTO teaching_tasks ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",  # noqa: S608
                [task_id, *values.values(), now, now],
            )
        # Move indexes out of the final range before reordering, preserving IDs.
        project.connection.execute(
            "UPDATE task_lessons SET lesson_index = lesson_index + 1000000 WHERE teaching_task_id = ?",
            (task_id,),
        )
        for lesson_id in removed:
            project.connection.execute(
                "DELETE FROM availability_rules WHERE entity_type = 'lesson' AND entity_id = ?",
                (lesson_id,),
            )
            project.connection.execute("DELETE FROM task_lessons WHERE id = ?", (lesson_id,))
        for index, item in enumerate(prepared):
            fields = {**item, "lesson_index": index, "updated_at": now}
            lesson_id = fields.pop("id")
            if lesson_id in old:
                assignments = ", ".join(f"{key} = ?" for key in fields)
                project.connection.execute(
                    f"UPDATE task_lessons SET {assignments} WHERE id = ?",
                    [*fields.values(), lesson_id],
                )  # noqa: S608
            else:
                fields.update(
                    id=lesson_id, teaching_task_id=task_id, source_id=lesson_id, created_at=now
                )
                project.connection.execute(
                    f"INSERT INTO task_lessons ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                    list(fields.values()),
                )  # noqa: S608
        project.connection.execute(
            "UPDATE course_plans SET weekly_slots = (SELECT COALESCE(SUM(weekly_slots), 0) FROM teaching_tasks WHERE course_plan_id = ? AND status = 'active'), updated_at = ? WHERE id = ?",
            (plan_id, now, plan_id),
        )
        revision = project._commit_write(now)
    except Exception:
        project.connection.execute("ROLLBACK")
        raise
    project._write_manifest_revision(revision, now)
    return (
        project.get_entity("teaching_task", task_id),
        [project.get_entity("task_lesson", item["id"]) for item in prepared],
        revision,
    )


def set_course_scheduled(project, homeroom_id, subject_id, term_id, scheduled, expected_revision):
    homeroom = project.get_entity("homeroom", homeroom_id)
    if not homeroom or homeroom.get("term_id") not in (None, "", term_id) or not project.get_entity("subject", subject_id) or not project.get_entity("term", term_id):
        raise ProjectError("班级、科目或学期无效")
    tasks = [t for t in project.list_entities("teaching_task") if t["homeroom_id"] == homeroom_id and t["subject_id"] == subject_id and t["term_id"] == term_id]
    task_ids = {t["id"] for t in tasks}
    lessons = {lesson["id"] for lesson in project.list_entities("task_lesson") if lesson["teaching_task_id"] in task_ids}
    if not scheduled and any(any(i in c["parameters"] for i in task_ids | lessons) for c in project.list_entities("constraint")):
        raise ProjectError("授课任务或课次仍被约束引用，请先解除引用")
    now = utc_now()
    project._begin_write(expected_revision)
    try:
        if not scheduled:
            for lesson_id in lessons:
                project.connection.execute("DELETE FROM availability_rules WHERE entity_type = 'lesson' AND entity_id = ?", (lesson_id,))
            for task_id in task_ids:
                project.connection.execute("DELETE FROM teaching_tasks WHERE id = ?", (task_id,))
        plan = project.connection.execute("SELECT id FROM course_plans WHERE term_id = ? AND homeroom_id = ? AND subject_id = ?", (term_id, homeroom_id, subject_id)).fetchone()
        if plan:
            project.connection.execute("UPDATE course_plans SET weekly_slots = ?, updated_at = ? WHERE id = ?", (1 if scheduled else 0, now, plan["id"]))
        else:
            project.connection.execute("INSERT INTO course_plans (id, term_id, homeroom_id, subject_id, weekly_slots, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (uuid7(), term_id, homeroom_id, subject_id, 1 if scheduled else 0, now, now))
        revision = project._commit_write(now)
    except Exception:
        project.connection.execute("ROLLBACK")
        raise
    project._write_manifest_revision(revision, now)
    return revision
