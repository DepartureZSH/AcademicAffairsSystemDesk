"""Lossless adapter between the web expected-time contract and local lesson slots."""

from stt_desktop.storage import ProjectError
from stt_desktop.timetable_settings import config
from stt_desktop.agent.service import AgentService


def read_expected(project):
    periods = {row["id"]: row for row in project.list_entities("time_slot")}
    items = []
    for lesson in project.list_entities("task_lesson"):
        rules = []
        for preference in config(lesson["planning_config"]).get("preferred_times", []):
            period = periods.get(preference["time_slot_id"])
            if not period:
                raise ProjectError("已有期望时间引用失效课节，请先修复项目")
            rules.append(
                {
                    "template_id": period["bell_schedule_id"],
                    "period_keys": [period["period_index"] + 1],
                    "week_bits": preference["week_bits"],
                    "day_bits": "".join(
                        "1" if day == period["weekday"] else "0" for day in range(1, 8)
                    ),
                    "effect": "forbidden" if preference["penalty"] < 0 else "preferred",
                    "penalty": max(0, preference["penalty"]),
                    "required": True,
                }
            )
        items.append(
            {
                "lesson_id": lesson["id"],
                "revision": project.revision,
                "configuration": {
                    "schema_version": 2,
                    "default_policy": "restricted" if rules else "inherit",
                    "rules": rules,
                },
            }
        )
    return {"items": items, "revision": project.revision}


def convert_configuration(project, configuration):
    if (
        not isinstance(configuration, dict)
        or set(configuration) != {"schema_version", "default_policy", "rules"}
        or configuration["schema_version"] != 2
    ):
        raise ProjectError("期望时间配置版本或字段无效")
    rules = configuration["rules"]
    if (
        not isinstance(rules, list)
        or len(rules) > 5000
        or configuration["default_policy"] != ("restricted" if rules else "inherit")
    ):
        raise ProjectError("期望时间配置与默认策略不一致")
    schedules = {row["id"]: row for row in project.list_entities("bell_schedule")}
    slots = project.list_entities("time_slot")
    result = {}
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {
            "template_id",
            "period_keys",
            "week_bits",
            "day_bits",
            "effect",
            "penalty",
            "required",
        }:
            raise ProjectError("期望时间规则包含未知字段")
        schedule = schedules.get(rule["template_id"])
        if (
            not schedule
            or rule["required"] is not True
            or rule["effect"] not in ("preferred", "forbidden")
            or type(rule["penalty"]) is not int
            or rule["penalty"] not in (0, 10, 30, 60)
        ):
            raise ProjectError("期望时间模板、优先级或规则无效")
        days, weeks = rule["day_bits"], rule["week_bits"]
        if (
            not isinstance(days, str)
            or not 1 <= len(days) <= 7
            or set(days) - {"0", "1"}
            or "1" not in days
        ):
            raise ProjectError("请选择有效的星期")
        if (
            not isinstance(weeks, str)
            or not 1 <= len(weeks) <= 60
            or set(weeks) - {"0", "1"}
            or "1" not in weeks
        ):
            raise ProjectError("请选择有效的教学周")
        keys = rule["period_keys"]
        if (
            not isinstance(keys, list)
            or not keys
            or len(keys) > 200
            or any(type(key) is not int or key < 1 for key in keys)
        ):
            raise ProjectError("请选择有效课节")
        visible = config(schedule["display_config"]).get("enabled_weekdays", list(range(1, 8)))
        for day, bit in enumerate(days, 1):
            if bit != "1":
                continue
            if day not in visible:
                raise ProjectError("所选星期已在课表中隐藏，请重新选择")
            for key in keys:
                matches = [
                    slot
                    for slot in slots
                    if slot["bell_schedule_id"] == schedule["id"]
                    and slot["weekday"] == day
                    and slot["period_index"] == key - 1
                    and slot["active"]
                ]
                if len(matches) != 1:
                    raise ProjectError("目标模板中课节缺失、停用或不唯一")
                identity = (matches[0]["id"], weeks)
                penalty = -1 if rule["effect"] == "forbidden" else rule["penalty"]
                if identity in result and result[identity]["penalty"] != penalty:
                    raise ProjectError("同一课节和教学周存在不同优先级，请先消除冲突")
                result[identity] = {
                    "time_slot_id": matches[0]["id"],
                    "week_bits": weeks,
                    "penalty": penalty,
                }
    return list(result.values())


def apply_expected(project, workspace, items):
    if not isinstance(items, list) or not 1 <= len(items) <= 5000:
        raise ProjectError("请选择 1–5000 个课次")
    lessons = {row["id"]: row for row in project.list_entities("task_lesson")}
    tasks = {row["id"]: row for row in project.list_entities("teaching_task")}
    grouped = {}
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"lesson_id", "revision", "configuration"}:
            raise ProjectError("课次期望时间请求格式无效")
        identifier = item["lesson_id"]
        if (
            identifier not in lessons
            or identifier in seen
            or type(item["revision"]) is not int
            or item["revision"] != project.revision
        ):
            raise ProjectError("所选课次已变化、重复或不存在，请刷新后重试")
        seen.add(identifier)
        lesson = lessons[identifier]
        grouped.setdefault(lesson["teaching_task_id"], []).append(
            {
                "id": identifier,
                "lesson_index": lesson["lesson_index"] + 1,
                "time_preferences": convert_configuration(project, item["configuration"]),
            }
        )
    proposals = []
    for identifier, drafts in grouped.items():
        task = tasks[identifier]
        proposals.append(
            {
                "target": "task",
                "operation": "update",
                "human_summary": "专项设置课次期望时间",
                "payload": {
                    "id": identifier,
                    "homeroom_id": task["homeroom_id"],
                    "subject_id": task["subject_id"],
                    "course_plan_id": task["course_plan_id"],
                    "lessons": drafts,
                },
            }
        )
    service = AgentService(project, workspace)
    action = service.compile("planning", proposals)
    service.confirm(action["id"])
    return {"revision": project.revision, "action_id": action["id"], "updated": len(items)}
