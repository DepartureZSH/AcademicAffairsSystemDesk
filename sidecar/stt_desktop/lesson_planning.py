"""Atomic editing of a teaching task and its individually configured lessons."""

import json
import re

from stt_desktop.lesson_config import parse_lesson_config
from stt_desktop.storage.project import ENTITY_SPECS, ProjectError, utc_now, uuid7


def save_course_arrangement(project, data, drafts, expected_revision):
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
    old = {
        item["id"]: item
        for item in project.list_entities("task_lesson")
        if item["teaching_task_id"] == task_id
    }
    slots = {item["id"]: item for item in project.list_entities("time_slot") if item["active"]}
    schedules = {item["id"]: item for item in project.list_entities("bell_schedule")}
    rooms = {item["id"] for item in project.list_entities("room") if item["status"] == "active"}
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
        if lesson_id in seen or (draft.get("id") and lesson_id not in old):
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
    values["weekly_slots"] = sum(item["duration_slots"] for item in prepared if item["enabled"])
    values["duration_slots"] = prepared[0]["duration_slots"] if prepared else 1
    now = utc_now()
    project._begin_write(expected_revision)
    try:
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
