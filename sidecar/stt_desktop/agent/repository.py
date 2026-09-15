"""Web repository protocol mapped to a single local SQLite transaction."""

from contextlib import contextmanager
from copy import deepcopy
import json

from stt_desktop.storage.project import ProjectRepository, ProjectError, utc_now, uuid7
from stt_desktop.timetable_settings import TimetableSettingsService, config


def build_preview_problem(*args, **kwargs):
    raise ProjectError("请在排课运行页面检查输入并发起排课")


create_scheduling_run = build_preview_problem


class BatchProject(ProjectRepository):
    """Reuse all normal validators without nested commits or manifest writes."""

    def _begin_write(self, expected_revision):
        if not self.connection.in_transaction or self.revision != expected_revision:
            raise ProjectError("AI 批量事务或项目版本已失效")

    def _commit_write(self, now):
        return self.revision

    def _write_manifest_revision(self, revision, now):
        pass


class LocalAgentRepository:
    def __init__(self, project, action=None, dry_run=False):
        self.project = project
        self.action = action
        self.dry_run = dry_run
        self.writer = BatchProject.__new__(BatchProject)
        self.writer.__dict__.update(project.__dict__)

    def list_school_data(self, organization_id):
        data = TimetableSettingsService(self.project).read()["schoolData"]
        for row in data["rooms"]:
            row["type_id"] = row.pop("room_type_id")
        for row in data["subjects"]:
            row["default_duration_slots"] = (row.get("default_duration_minutes") or 40) // 5
        return data

    def list_weekly_timetable_templates(self, *args):
        return TimetableSettingsService(self.project).read()["schoolData"]

    def list_constraint_templates(self, *args):
        return {"templates": []}

    def list_planning_data(self, *args):
        result = {}
        for key, entity in [
            ("course_plans", "course_plan"),
            ("teaching_tasks", "teaching_task"),
            ("task_lessons", "task_lesson"),
        ]:
            rows = self.project.list_entities(entity)
            for row in rows:
                settings = config(row.get("planning_config"))
                if "enabled" in row:
                    row["enabled"] = bool(row["enabled"])
                if settings.get("uses_rooms") is False:
                    row["required_room_type"] = "__no_room__"
                subject = (
                    self.project.get_entity("subject", row.get("subject_id", ""))
                    if row.get("subject_id")
                    else None
                )
                if entity == "task_lesson":
                    parent = self.project.get_entity("teaching_task", row["teaching_task_id"])
                    subject = (
                        self.project.get_entity("subject", parent["subject_id"]) if parent else None
                    )
                row["duration_slots"] = (
                    settings.get("duration_minutes")
                    or (subject or {}).get("default_duration_minutes")
                    or 40 * row["duration_slots"]
                ) // 5
                if entity == "task_lesson":
                    row["lesson_index"] += 1
                    row["time_preferences"] = settings.get("preferred_times", [])
                if entity in ("teaching_task", "task_lesson"):
                    room_settings = settings
                    if entity == "task_lesson" and settings.get("room_mode", "default") == "default":
                        room_settings = config((parent or {}).get("planning_config"))
                    if entity == "teaching_task" and room_settings.get("uses_rooms") is False:
                        row["required_room_type"] = "__no_room__"
                    row["room_ids"] = room_settings.get("room_ids", [])
                    row["room_options"] = [
                        {"room_id": identifier} for identifier in row["room_ids"]
                    ]
            result[key] = rows
        return result

    def list_constraints(self, *args):
        rows = self.project.list_entities("constraint")
        for row in rows:
            row.update(
                distribution_type=row["type"],
                required=row["severity"] == "hard",
                penalty=row["weight"],
                lesson_ids=config(row["parameters"]).get("lessonIds", []),
            )
        return {"constraints": rows}

    @contextmanager
    def agent_action_transaction(self):
        self.project._begin_write(self.action["base_revision"])
        try:
            yield
            if self.dry_run:
                self.project.connection.execute("ROLLBACK")
            else:
                now = utc_now()
                revision = self.project._commit_write(now)
                self.project._write_manifest_revision(revision, now)
        except Exception:
            if self.project.connection.in_transaction:
                self.project.connection.execute("ROLLBACK")
            raise

    def update_agent_action_item_results(self, action_id, results):
        self.results = results

    def update_agent_action_status(self, user_id, action_id, status, result, error):
        if self.dry_run:
            return
        updated = {**self.action, "status": status, "execution_result": result}
        by_id = {r["item_id"]: r for r in self.results}
        updated["items"] = [{**item, **by_id.get(item["id"], {})} for item in updated["items"]]
        self.project.connection.execute(
            "UPDATE ai_documents SET body = ? WHERE id = ? AND kind = ?",
            (json.dumps(updated, ensure_ascii=False), action_id, "action"),
        )

    def _save(self, entity, payload):
        values = deepcopy(payload)
        for key in [
            "created_at",
            "updated_at",
            "organization_id",
            "project_id",
            "subject_name",
            "homeroom_name",
            "teacher_name",
        ]:
            values.pop(key, None)
        if entity == "room" and "type_id" in values:
            values["room_type_id"] = values.pop("type_id")
        if entity == "subject":
            old = self.project.get_entity("subject", values.get("id", ""))
            values["default_duration_minutes"] = (
                int(values.pop("default_duration_slots")) * 5
                if "default_duration_slots" in values
                else values.get(
                    "default_duration_minutes", (old or {}).get("default_duration_minutes") or 40
                )
            )
            values["default_duration_slots"] = 1
            if old and old.get('default_duration_minutes') != values['default_duration_minutes']:
                # The upstream review explicitly warns that a subject-duration edit
                # propagates to its existing lessons. Keep that contract atomically.
                task_ids = {t['id'] for t in self.project.list_entities('teaching_task') if t['subject_id'] == old['id']}
                for lesson in self.project.list_entities('task_lesson'):
                    if lesson['teaching_task_id'] in task_ids:
                        self.writer.save_entity('task_lesson', {'id': lesson['id'], 'duration_slots': 1,
                            'planning_config': {**config(lesson.get('planning_config')), 'duration_minutes': values['default_duration_minutes']}}, self.project.revision)
        if entity == "course_plan":
            values["duration_slots"] = 1
            values.setdefault("term_id", self._term())
            if "weekly_slots" not in values:
                tasks = [
                    item["after_data"]
                    for item in (self.action or {}).get("items", [])
                    if item["target"] == "task"
                    and item.get("after_data")
                    and item["after_data"].get("course_plan_id") == values.get("id")
                ]
                if tasks and all(
                    isinstance(t.get("lessons"), list) or type(t.get("weekly_slots")) is int
                    for t in tasks
                ):
                    values["weekly_slots"] = sum(
                        len(t["lessons"])
                        if isinstance(t.get("lessons"), list)
                        else t["weekly_slots"]
                        for t in tasks
                    )
        return self.writer.save_entity(entity, values, self.project.revision)[0]

    def _term(self):
        active = [t for t in self.project.list_entities("term") if t["active"]]
        if len(active) != 1:
            raise ProjectError("请先配置唯一的当前学期")
        return active[0]["id"]

    def __getattr__(self, name):
        # Explicit entity allowlist; never expose arbitrary SQL or attribute dispatch to the model.
        for entity in ("teacher", "homeroom", "subject", "room_type", "room", "course_plan"):
            if name == "create_" + entity:
                return lambda *args, entity=entity: self._save(entity, args[-1])
            if name == "update_" + entity:
                return lambda *args, entity=entity: self._save(entity, {**args[-1], "id": args[-2]})
            if name == "delete_" + entity:
                return lambda *args, entity=entity: self.writer.delete_entity(
                    entity, args[-1], self.project.revision
                )
        raise AttributeError(name)

    def update_active_term(self, organization_id, payload):
        return self._save("term", {**payload, "id": self._term()})

    def create_weekly_timetable_template(self, organization_id, payload):
        planned = next(
            (
                i["after_data"]["id"]
                for i in (self.action or {}).get("items", [])
                if i["target"] == "timetable_template"
                and i["operation"] == "create"
                and i["after_data"].get("name") == payload.get("name")
            ),
            None,
        )
        return self._template({**payload, "id": payload.get("id") or planned or uuid7()}, [])

    def update_weekly_timetable_template(self, organization_id, template_id, payload):
        data = self.list_weekly_timetable_templates()
        old = next((t for t in data["weekly_timetable_templates"] if t["id"] == template_id), None)
        if old is None:
            raise ProjectError("课表模板不存在")
        return self._template(
            {**old, **payload, "id": template_id},
            [p for p in data["weekly_timetable_periods"] if p["template_id"] == template_id],
        )

    def _template(self, template, periods):
        allowed = {
            "id",
            "name",
            "term_id",
            "day_count",
            "slot_duration_minutes",
            "is_default",
            "display_config",
            "template_kind",
            "period_source_template_id",
            "periods_locked",
            "application_scope",
            "organization_id",
            "project_id",
            "created_at",
            "updated_at",
        }
        if set(template) - allowed or template.get("application_scope", "all") != "all":
            raise ProjectError("课表模板包含尚未支持的字段或应用范围，请在课表设置页配置")
        period_fields = {
            "id",
            "template_id",
            "bell_schedule_id",
            "weekday",
            "period_index",
            "label",
            "start_time_minutes",
            "end_time_minutes",
            "active",
            "display_config",
            "start_slot",
            "length_slots",
            "created_at",
            "updated_at",
        }
        if any(not isinstance(period, dict) or set(period) - period_fields for period in periods):
            raise ProjectError("课节包含尚不能安全转换的字段")
        result = TimetableSettingsService(self.writer).save(
            {"template": template, "periods": periods}, self.project.revision
        )
        return {"id": result["templateId"]}

    def replace_weekly_timetable_periods(self, organization_id, template_id, periods):
        template = next(
            t
            for t in self.list_weekly_timetable_templates()["weekly_timetable_templates"]
            if t["id"] == template_id
        )
        return self._template(template, periods)

    def delete_weekly_timetable_template(self, organization_id, template_id):
        return TimetableSettingsService(self.writer).delete(template_id, self.project.revision)

    def create_teaching_task(self, organization_id, project_id, payload):
        from stt_desktop.lesson_planning import save_course_arrangement

        values = deepcopy(payload)
        minutes = int(values.pop("duration_slots", 8)) * 5
        lessons = values.pop("lessons", None)
        room_ids = values.pop("room_ids", [])
        values.pop("room_options", None)
        for key in (
            "created_at",
            "updated_at",
            "organization_id",
            "project_id",
            "homeroom_name",
            "subject_name",
            "teacher_name",
        ):
            values.pop(key, None)
        values.setdefault("term_id", self._term())
        values["duration_slots"] = 1
        values["planning_config"] = {
            "uses_rooms": values.get("required_room_type") != "__no_room__",
            "room_ids": room_ids
            or ([values["fixed_room_id"]] if values.get("fixed_room_id") else []),
        }
        if lessons is None:
            count = int(values.get("weekly_slots", 1))
            if not 0 <= count <= 500:
                raise ProjectError("每条任务最多 500 个课次")
            lessons = [{} for _ in range(count)]
        drafts = []
        preallocated_ids = set()
        for lesson in lessons:
            allowed = {
                "id",
                "label",
                "name",
                "enabled",
                "week_bits",
                "day_bits",
                "planning_config",
                "duration_slots",
                "room_ids",
                "room_options",
                "time_preferences",
                "lesson_index",
                "teaching_task_id",
                "source_id",
                "created_at",
                "updated_at",
                "_agent_preallocated",
            }
            if set(lesson) - allowed:
                raise ProjectError("课次包含尚不能安全转换的字段，请核对变更内容")
            local = config(lesson.get("planning_config"))
            local["duration_minutes"] = int(lesson.get("duration_slots", minutes // 5)) * 5
            if lesson.get("room_ids"):
                local.update(room_mode="custom", room_ids=lesson["room_ids"])
            if "time_preferences" in lesson:
                prefs = lesson["time_preferences"]
                converted = []
                for preference in prefs:
                    if set(preference) == {"time_slot_id", "week_bits", "penalty"}:
                        converted.append(preference)
                        continue
                    if set(preference) - {
                        "period_id",
                        "week_bits",
                        "day_bits",
                        "required",
                        "penalty",
                    } or not preference.get("period_id"):
                        raise ProjectError("期望时间包含未知字段或缺少具体课节")
                    slot = self.project.get_entity("time_slot", preference["period_id"])
                    if not slot or not slot["active"]:
                        raise ProjectError("期望课节不存在或已停用")
                    days = preference.get("day_bits") or "".join(
                        "1" if d == slot["weekday"] else "0" for d in range(1, 8)
                    )
                    if len(days) > 7 or {i + 1 for i, bit in enumerate(days) if bit == "1"} != {
                        slot["weekday"]
                    }:
                        raise ProjectError("期望课节与星期不一致，请分别指定具体课节")
                    if preference.get("required", True) is not True:
                        raise ProjectError(
                            "请使用明确的候选期望时间与优先级，不要将必选范围设为可忽略"
                        )
                    converted.append(
                        {
                            "time_slot_id": slot["id"],
                            "week_bits": preference.get("week_bits")
                            or lesson.get("week_bits")
                            or "1"
                            * self.project.get_entity("term", values["term_id"])["week_count"],
                            "penalty": preference.get("penalty", 0),
                        }
                    )
                local["preferred_times"] = converted
            draft = {
                k: lesson[k]
                for k in ("id", "label", "enabled", "week_bits", "day_bits")
                if k in lesson
            }
            if lesson.get("_agent_preallocated") and not self.project.get_entity(
                "task_lesson", lesson.get("id", "")
            ):
                preallocated_ids.add(lesson["id"])
            draft.update(duration_slots=1, planning_config=local)
            drafts.append(draft)
        task, _, _ = save_course_arrangement(
            self.writer, values, drafts, self.project.revision, preallocated_ids=preallocated_ids
        )
        return task

    def update_teaching_task(self, organization_id, project_id, task_id, payload):
        return self.create_teaching_task(organization_id, project_id, {**payload, "id": task_id})

    def delete_teaching_task(self, organization_id, project_id, task_id):
        return self.writer.delete_entity("teaching_task", task_id, self.project.revision)

    def create_distribution_constraint(self, organization_id, project_id, payload):
        from stt_desktop.agent.upstream.distributions import parse_distribution, GROUP_TYPES

        kind = payload.get("distribution_type") or payload.get("type")
        parsed_kind, _ = parse_distribution(kind)
        ids = payload.get("lesson_ids", config(payload.get("parameters")).get("lessonIds", []))
        known = {lesson["id"] for lesson in self.project.list_entities("task_lesson")}
        if len(set(ids)) < (1 if parsed_kind in GROUP_TYPES else 2) or any(
            value not in known for value in ids
        ):
            raise ProjectError("约束必须引用至少两个当前项目中的课次")
        supported = {
            "id",
            "name",
            "type",
            "distribution_type",
            "required",
            "penalty",
            "lesson_ids",
            "parameters",
            "severity",
            "weight",
            "enabled",
            "created_at",
            "updated_at",
        }
        if set(payload) - supported:
            raise ProjectError("约束包含尚未支持的字段，请使用明确的课次分布约束")
        return self._save(
            "constraint",
            {
                "id": payload.get("id") or uuid7(),
                "name": payload.get("name") or kind,
                "type": kind,
                "severity": "hard"
                if payload.get("required", payload.get("severity") == "hard")
                else "soft",
                "weight": payload.get("penalty", payload.get("weight", 10)) or 0,
                "enabled": payload.get("enabled", True),
                "parameters": {"lessonIds": ids},
            },
        )

    def update_distribution_constraint(self, org, project, entity_id, payload):
        return self.create_distribution_constraint(org, project, {**payload, "id": entity_id})

    def delete_distribution_constraint(self, org, project, entity_id):
        return self.writer.delete_entity("constraint", entity_id, self.project.revision)

    def create_constraint_groups(self, user, org, project, payload):
        from stt_desktop.agent.upstream.constraint_resolver import compiler_for_scenario

        kind = payload.get("distribution_type") or compiler_for_scenario(
            str(payload.get("scenario_type") or "")
        ).get("distribution_type")
        if not kind:
            raise ProjectError("约束没有可执行的规则定义")
        return {
            "items": [
                self.create_distribution_constraint(
                    org,
                    project,
                    {
                        "distribution_type": kind,
                        "name": group.get("label") or group.get("name") or payload.get("name"),
                        "lesson_ids": group.get("lesson_ids"),
                        "required": payload.get("required", False),
                        "penalty": payload.get("penalty", 10),
                    },
                )
                for group in payload["groups"]
            ]
        }
