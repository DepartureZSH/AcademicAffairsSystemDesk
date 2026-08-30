from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from stt_desktop.storage.project import ProjectRepository, ProjectWorkspace, uuid7


class LegacyImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class LegacyProjectSummary:
    project_id: str
    name: str
    task_count: int
    lesson_count: int
    candidate_count: int


@dataclass(frozen=True)
class ImportResult:
    project_id: str
    revision: int
    counts: Mapping[str, int]


def _source_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise LegacyImportError("源项目 ID 不是有效 UUID") from exc


def _serializable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _new_id_map(rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    return {str(row["id"]): uuid7() for row in rows}


def _mapped(mapping: Mapping[str, str], value: Any) -> str | None:
    if value is None:
        return None
    return mapping.get(str(value))


class LegacySupabaseImporter:
    """Read a legacy Supabase Postgres snapshot and detach it into local SQLite."""

    def __init__(self, database_url: str, *, allow_remote_database: bool = False) -> None:
        parsed = urlparse(database_url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise LegacyImportError("旧版数据源必须是 PostgreSQL URL")
        if not allow_remote_database and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise LegacyImportError("默认只允许从本机 PostgreSQL 迁移；远程数据源需显式批准")
        self.database_url = database_url

    def discover_projects(self) -> list[LegacyProjectSummary]:
        query = """
            SELECT p.id::text AS project_id,
                   p.name,
                   count(DISTINCT t.id)::int AS task_count,
                   count(DISTINCT l.id)::int AS lesson_count,
                   count(DISTINCT s.id)::int AS candidate_count
              FROM public.scheduling_projects p
              LEFT JOIN public.teaching_tasks t ON t.project_id = p.id
              LEFT JOIN public.task_lessons l ON l.project_id = p.id
              LEFT JOIN public.solution_versions s ON s.project_id = p.id
             GROUP BY p.id, p.name
             ORDER BY p.created_at, p.id
        """
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                rows = connection.execute(query).fetchall()
        return [
            LegacyProjectSummary(
                project_id=row["project_id"],
                name=row["name"],
                task_count=row["task_count"],
                lesson_count=row["lesson_count"],
                candidate_count=row["candidate_count"],
            )
            for row in rows
        ]

    def import_project(
        self,
        source_project_id: str,
        workspace: ProjectWorkspace,
        *,
        target_name: str | None = None,
    ) -> tuple[ProjectRepository, ImportResult]:
        normalized_id = _source_uuid(source_project_id)
        snapshot = self._read_snapshot(normalized_id)
        batches = self._build_batches(snapshot)
        source_project = snapshot["project"][0]
        name = target_name.strip() if target_name and target_name.strip() else source_project["name"]
        repository = workspace.create_project(f"{name}（本地迁移）")
        try:
            counts, revision = repository.bulk_insert_entities(batches, expected_revision=0)
        except Exception:
            repository.close()
            raise
        return repository, ImportResult(
            project_id=repository.project_info()["id"], revision=revision, counts=counts
        )

    def _read_snapshot(self, project_id: str) -> dict[str, list[dict[str, Any]]]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                project = connection.execute(
                    """
                    SELECT id, organization_id, term_id, name
                      FROM public.scheduling_projects
                     WHERE id = %s
                    """,
                    (project_id,),
                ).fetchall()
                if not project:
                    raise LegacyImportError("源排课项目不存在")
                organization_id = project[0]["organization_id"]
                term_id = project[0]["term_id"]

                snapshot: dict[str, list[dict[str, Any]]] = {"project": project}
                for key, table in (
                    ("teachers", "teachers"),
                    ("room_types", "room_types"),
                    ("rooms", "rooms"),
                    ("homerooms", "homerooms"),
                    ("subjects", "subjects"),
                ):
                    snapshot[key] = self._fetch(
                        connection,
                        f"SELECT * FROM public.{table} WHERE organization_id = %s ORDER BY created_at, id",
                        (organization_id,),
                    )
                for key, table in (
                    ("course_plans", "course_plans"),
                    ("teaching_tasks", "teaching_tasks"),
                    ("task_lessons", "task_lessons"),
                ):
                    snapshot[key] = self._fetch(
                        connection,
                        f"SELECT * FROM public.{table} WHERE project_id = %s ORDER BY id",
                        (project_id,),
                    )

                assignments = self._fetch(
                    connection,
                    """
                    SELECT * FROM public.project_timetable_template_assignments
                     WHERE project_id = %s
                     ORDER BY created_at, id
                    """,
                    (project_id,),
                )
                assigned_template_ids = [row["template_id"] for row in assignments]
                snapshot["templates"] = self._fetch(
                    connection,
                    """
                    SELECT DISTINCT t.*
                      FROM public.weekly_timetable_templates t
                     WHERE t.organization_id = %s
                        OR t.id = ANY(%s::uuid[])
                     ORDER BY t.is_default DESC, t.created_at, t.id
                    """,
                    (organization_id, assigned_template_ids),
                )
                term_ids = {
                    str(value)
                    for value in [
                        term_id,
                        *(row.get("term_id") for row in snapshot["templates"]),
                        *(row.get("term_id") for row in snapshot["homerooms"]),
                        *(row.get("term_id") for row in snapshot["course_plans"]),
                        *(row.get("term_id") for row in snapshot["teaching_tasks"]),
                    ]
                    if value is not None
                }
                snapshot["terms"] = (
                    self._fetch(
                        connection,
                        "SELECT * FROM public.terms WHERE id = ANY(%s::uuid[]) ORDER BY created_at, id",
                        (list(term_ids),),
                    )
                    if term_ids
                    else []
                )
                template_ids = [row["id"] for row in snapshot["templates"]]
                snapshot["periods"] = (
                    self._fetch(
                        connection,
                        """
                        SELECT * FROM public.weekly_timetable_periods
                         WHERE template_id = ANY(%s::uuid[])
                         ORDER BY template_id, weekday, period_index
                        """,
                        (template_ids,),
                    )
                    if template_ids
                    else []
                )
                return snapshot

    @staticmethod
    def _fetch(
        connection: psycopg.Connection[dict[str, Any]],
        query: str,
        parameters: Sequence[Any],
    ) -> list[dict[str, Any]]:
        return list(connection.execute(query, parameters).fetchall())

    @staticmethod
    def _build_batches(
        snapshot: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> OrderedDict[str, list[dict[str, Any]]]:
        terms = snapshot.get("terms", [])
        templates = snapshot.get("templates", [])
        periods = snapshot.get("periods", [])
        teachers = snapshot.get("teachers", [])
        room_types = snapshot.get("room_types", [])
        rooms = snapshot.get("rooms", [])
        homerooms = snapshot.get("homerooms", [])
        subjects = snapshot.get("subjects", [])
        course_plans = snapshot.get("course_plans", [])
        teaching_tasks = snapshot.get("teaching_tasks", [])
        task_lessons = snapshot.get("task_lessons", [])

        ids = {
            "term": _new_id_map(terms),
            "bell_schedule": _new_id_map(templates),
            "time_slot": _new_id_map(periods),
            "teacher": _new_id_map(teachers),
            "room_type": _new_id_map(room_types),
            "room": _new_id_map(rooms),
            "homeroom": _new_id_map(homerooms),
            "subject": _new_id_map(subjects),
            "course_plan": _new_id_map(course_plans),
            "teaching_task": _new_id_map(teaching_tasks),
            "task_lesson": _new_id_map(task_lessons),
        }

        grade_names = sorted({str(row.get("group_name") or "未分组") for row in homerooms})
        grade_ids = {name: uuid7() for name in grade_names}
        batches: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        batches["term"] = [
            {
                "id": ids["term"][str(row["id"])],
                "name": row["name"],
                "start_date": _serializable(row.get("start_date")),
                "end_date": _serializable(row.get("end_date")),
                "week_count": row["week_count"],
                "day_count": row.get("day_count", 5),
                "active": row.get("active", True),
            }
            for row in terms
        ]
        batches["bell_schedule"] = [
            {
                "id": ids["bell_schedule"][str(row["id"])],
                "term_id": _mapped(ids["term"], row.get("term_id")),
                "name": row["name"],
                "day_count": row["day_count"],
                "slot_duration_minutes": row["slot_duration_minutes"],
                "is_default": row.get("is_default", False),
                "display_config": _serializable(row.get("display_config") or {}),
            }
            for row in templates
        ]
        batches["time_slot"] = [
            {
                "id": ids["time_slot"][str(row["id"])],
                "bell_schedule_id": ids["bell_schedule"][str(row["template_id"])],
                "weekday": row["weekday"],
                "period_index": row["period_index"],
                "label": row["label"],
                "start_slot": row["start_slot"],
                "length_slots": row["length_slots"],
                "start_time_minutes": row["start_time_minutes"],
                "end_time_minutes": row["end_time_minutes"],
                "active": row.get("active", True),
                "display_config": _serializable(row.get("display_config") or {}),
            }
            for row in periods
        ]
        batches["grade"] = [
            {"id": grade_ids[name], "name": name, "sort_order": index}
            for index, name in enumerate(grade_names)
        ]
        batches["teacher"] = [
            {
                "id": ids["teacher"][str(row["id"])],
                "employee_no": row.get("employee_no"),
                "name": row["name"],
                "department": row.get("department"),
                "status": row.get("status", "active"),
            }
            for row in teachers
        ]
        batches["room_type"] = [
            {
                "id": ids["room_type"][str(row["id"])],
                "name": row["name"],
                "code": row.get("code"),
                "description": row.get("description"),
            }
            for row in room_types
        ]
        batches["room"] = [
            {
                "id": ids["room"][str(row["id"])],
                "room_type_id": _mapped(ids["room_type"], row.get("type_id")),
                "name": row["name"],
                "room_no": row.get("room_no"),
                "capacity": row.get("capacity"),
                "status": row.get("status", "active"),
            }
            for row in rooms
        ]
        batches["homeroom"] = [
            {
                "id": ids["homeroom"][str(row["id"])],
                "grade_id": grade_ids[str(row.get("group_name") or "未分组")],
                "term_id": _mapped(ids["term"], row.get("term_id")),
                "head_teacher_id": _mapped(ids["teacher"], row.get("head_teacher_id")),
                "default_room_id": _mapped(ids["room"], row.get("default_room_id")),
                "name": row["name"],
                "group_name": row.get("group_name"),
                "student_count": row.get("student_count"),
                "status": row.get("status", "active"),
            }
            for row in homerooms
        ]
        batches["subject"] = [
            {
                "id": ids["subject"][str(row["id"])],
                "name": row["name"],
                "code": row.get("code"),
                "category": row.get("category", "general"),
                "default_duration_slots": row.get("default_duration_slots", 1),
                "requires_special_room": row.get("requires_special_room", False),
            }
            for row in subjects
        ]
        batches["course_plan"] = [
            {
                "id": ids["course_plan"][str(row["id"])],
                "term_id": _mapped(ids["term"], row.get("term_id")),
                "homeroom_id": ids["homeroom"][str(row["homeroom_id"])],
                "subject_id": ids["subject"][str(row["subject_id"])],
                "weekly_slots": row["weekly_slots"],
                "duration_slots": row["duration_slots"],
                "allow_double_period": row.get("allow_double_period", False),
                "priority": row.get("priority", 0),
                "week_bits": row["week_bits"],
                "day_bits": row["day_bits"],
            }
            for row in course_plans
        ]
        batches["teaching_task"] = [
            {
                "id": ids["teaching_task"][str(row["id"])],
                "term_id": _mapped(ids["term"], row.get("term_id")),
                "course_plan_id": _mapped(ids["course_plan"], row.get("course_plan_id")),
                "homeroom_id": ids["homeroom"][str(row["homeroom_id"])],
                "subject_id": ids["subject"][str(row["subject_id"])],
                "primary_teacher_id": _mapped(ids["teacher"], row.get("primary_teacher_id")),
                "weekly_slots": row["weekly_slots"],
                "duration_slots": row["duration_slots"],
                "required_room_type": row.get("required_room_type"),
                "fixed_room_id": _mapped(ids["room"], row.get("fixed_room_id")),
                "status": row.get("status", "active"),
                "week_bits": row["week_bits"],
                "day_bits": row["day_bits"],
            }
            for row in teaching_tasks
        ]
        batches["task_lesson"] = [
            {
                "id": ids["task_lesson"][str(row["id"])],
                "teaching_task_id": ids["teaching_task"][str(row["teaching_task_id"])],
                "lesson_index": row["lesson_index"],
                "duration_slots": row["duration_slots"],
                "source_id": row.get("xml_class_id"),
                "week_bits": row["week_bits"],
                "day_bits": row["day_bits"],
                "label": row.get("label"),
                "enabled": row.get("enabled", True),
            }
            for row in task_lessons
        ]
        return batches
