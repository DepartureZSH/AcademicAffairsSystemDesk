from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from stt_desktop.scheduling.service import (
    SNAPSHOT_TABLES,
    _canonical_json,
    _rows,
    _sha256_text,
    _write_text,
)
from stt_desktop.storage.project import (
    ProjectRepository,
    ProjectWorkspace,
    uuid7,
)


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
    warnings: tuple[Mapping[str, Any], ...] = ()


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


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _json_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    return []


def _timestamp(value: Any, fallback: str) -> str:
    serialized = _serializable(value)
    return str(serialized) if serialized else fallback


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
        warnings: list[dict[str, Any]] = []
        ids = self._build_id_maps(snapshot)
        batches = self._build_batches(snapshot, ids=ids, warnings=warnings)
        source_project = snapshot["project"][0]
        name = target_name.strip() if target_name and target_name.strip() else source_project["name"]
        repository = workspace.create_project(f"{name}（本地迁移）")
        created_files: list[Path] = []
        try:
            counts, revision = repository.bulk_insert_entities(
                batches,
                expected_revision=0,
                after_insert=lambda connection, now, target_revision: self._import_history(
                    repository,
                    snapshot,
                    ids,
                    warnings,
                    created_files,
                    now=now,
                    target_revision=target_revision,
                ),
            )
        except Exception:
            for path in created_files:
                path.unlink(missing_ok=True)
            repository.close()
            raise
        return repository, ImportResult(
            project_id=repository.project_info()["id"],
            revision=revision,
            counts=counts,
            warnings=tuple(warnings),
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
                snapshot["assignments"] = assignments
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
                snapshot["user_constraints"] = self._fetch(
                    connection,
                    """
                    SELECT * FROM public.user_constraint_templates
                     WHERE project_id = %s
                     ORDER BY id
                    """,
                    (project_id,),
                )
                snapshot["itc_constraints"] = self._fetch(
                    connection,
                    """
                    SELECT * FROM public.itc_distribution_constraints
                     WHERE project_id = %s
                     ORDER BY id
                    """,
                    (project_id,),
                )
                snapshot["runs"] = self._fetch(
                    connection,
                    """
                    SELECT * FROM public.scheduling_runs
                     WHERE project_id = %s
                     ORDER BY coalesce(queued_at, started_at, finished_at), id
                    """,
                    (project_id,),
                )
                snapshot["solutions"] = self._fetch(
                    connection,
                    """
                    SELECT * FROM public.solution_versions
                     WHERE project_id = %s
                     ORDER BY version_no, id
                    """,
                    (project_id,),
                )
                snapshot["timetable_entries"] = self._fetch(
                    connection,
                    """
                    SELECT * FROM public.timetable_entries
                     WHERE project_id = %s
                     ORDER BY solution_version_id, weekday, start_slot, id
                    """,
                    (project_id,),
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
    def _build_id_maps(
        snapshot: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> dict[str, dict[str, str]]:
        return {
            "term": _new_id_map(snapshot.get("terms", [])),
            "bell_schedule": _new_id_map(snapshot.get("templates", [])),
            "time_slot": _new_id_map(snapshot.get("periods", [])),
            "teacher": _new_id_map(snapshot.get("teachers", [])),
            "room_type": _new_id_map(snapshot.get("room_types", [])),
            "room": _new_id_map(snapshot.get("rooms", [])),
            "homeroom": _new_id_map(snapshot.get("homerooms", [])),
            "subject": _new_id_map(snapshot.get("subjects", [])),
            "course_plan": _new_id_map(snapshot.get("course_plans", [])),
            "teaching_task": _new_id_map(snapshot.get("teaching_tasks", [])),
            "task_lesson": _new_id_map(snapshot.get("task_lessons", [])),
            "assignment": _new_id_map(snapshot.get("assignments", [])),
            "constraint": _new_id_map(snapshot.get("user_constraints", [])),
            "run": _new_id_map(snapshot.get("runs", [])),
            "solution": _new_id_map(snapshot.get("solutions", [])),
        }

    @staticmethod
    def _build_batches(
        snapshot: Mapping[str, Sequence[Mapping[str, Any]]],
        *,
        ids: dict[str, dict[str, str]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> OrderedDict[str, list[dict[str, Any]]]:
        ids = ids or LegacySupabaseImporter._build_id_maps(snapshot)
        warnings = warnings if warnings is not None else []
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
        assignment_maps = {
            "homeroom": ids["homeroom"],
            "teacher": ids["teacher"],
            "subject": ids["subject"],
            "room_type": ids["room_type"],
            "room": ids["room"],
        }
        assignment_rows: list[dict[str, Any]] = []
        for row in snapshot.get("assignments", []):
            source_id = str(row["id"])
            entity_type = str(row.get("entity_type") or "")
            schedule_id = _mapped(ids["bell_schedule"], row.get("template_id"))
            entity_id = None
            if entity_type != "all":
                entity_id = _mapped(assignment_maps.get(entity_type, {}), row.get("entity_id"))
            if entity_type not in {*assignment_maps, "all"} or not schedule_id or (
                entity_type != "all" and not entity_id
            ):
                warnings.append(
                    {
                        "code": "LEGACY_ASSIGNMENT_SKIPPED",
                        "message": "旧版作息模板分配无法映射到桌面实体，已跳过",
                        "entityType": entity_type,
                    }
                )
                continue
            assignment_rows.append(
                {
                    "id": ids["assignment"][source_id],
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "bell_schedule_id": schedule_id,
                }
            )
        batches["timetable_template_assignment"] = assignment_rows

        lessons_by_source_id = {
            str(row.get("xml_class_id")): ids["task_lesson"][str(row["id"])]
            for row in task_lessons
            if row.get("xml_class_id")
        }
        linked_itc = {
            str(row["source_user_constraint_id"]): row
            for row in snapshot.get("itc_constraints", [])
            if row.get("source_user_constraint_id")
        }
        supported_types = {
            "NotOverlap",
            "SameRoom",
            "DifferentTime",
            "DifferentDays",
            "DifferentWeeks",
            "SameDays",
            "SameStart",
            "SameTime",
            "Precedence",
            "Consecutive",
        }
        constraint_rows: list[dict[str, Any]] = []
        for row in snapshot.get("user_constraints", []):
            source_id = str(row["id"])
            source_parameters = _json_object(row.get("parameters"))
            compiled = _json_array(row.get("compiled_constraints"))
            compiled_first = _json_object(compiled[0]) if compiled else {}
            linked = linked_itc.get(source_id, {})
            distribution_type = str(
                linked.get("distribution_type")
                or compiled_first.get("distribution_type")
                or source_parameters.get("distribution_type")
                or ""
            )
            compiled_parameters = _json_object(compiled_first.get("parameters"))
            source_lesson_ids = source_parameters.get("lesson_ids") or compiled_parameters.get(
                "lesson_ids", []
            )
            mapped_lessons: list[str] = []
            for value in source_lesson_ids if isinstance(source_lesson_ids, list) else []:
                source_lesson = str(value)
                mapped_lesson = ids["task_lesson"].get(source_lesson) or lessons_by_source_id.get(
                    source_lesson
                )
                if mapped_lesson and mapped_lesson not in mapped_lessons:
                    mapped_lessons.append(mapped_lesson)
            source_task = source_parameters.get("teaching_task_id")
            mapped_task = _mapped(ids["teaching_task"], source_task)
            parameters: dict[str, Any] = {"lessonIds": mapped_lessons}
            if mapped_task:
                parameters["teachingTaskIds"] = [mapped_task]
            if "ordered" in source_parameters:
                parameters["ordered"] = bool(source_parameters["ordered"])
            enabled = bool(row.get("enabled", True)) and distribution_type in supported_types
            if distribution_type not in supported_types:
                warnings.append(
                    {
                        "code": "LEGACY_CONSTRAINT_DISABLED",
                        "message": "旧版约束类型无法由桌面求解器编译，已保留但停用",
                        "constraintType": distribution_type or "unknown",
                    }
                )
            required = bool(linked.get("required", row.get("required", True)))
            penalty = linked.get("penalty", row.get("penalty"))
            constraint_rows.append(
                {
                    "id": ids["constraint"][source_id],
                    "type": distribution_type or "custom",
                    "name": row.get("name")
                    or row.get("human_summary")
                    or f"旧版 {distribution_type or '自定义'} 约束",
                    "severity": "hard" if required else "soft",
                    "enabled": enabled,
                    "weight": 0 if required else max(0, int(penalty or 100)),
                    "parameters": parameters,
                }
            )
        batches["constraint"] = constraint_rows
        return batches

    @staticmethod
    def _import_history(
        repository: ProjectRepository,
        snapshot: Mapping[str, Sequence[Mapping[str, Any]]],
        ids: Mapping[str, Mapping[str, str]],
        warnings: list[dict[str, Any]],
        created_files: list[Path],
        *,
        now: str,
        target_revision: int,
    ) -> Mapping[str, int]:
        runs = snapshot.get("runs", [])
        solutions = snapshot.get("solutions", [])
        entries = snapshot.get("timetable_entries", [])
        if not runs and not solutions and not entries:
            return LegacySupabaseImporter._record_import_warnings(
                repository, warnings, now
            )

        payload = {
            "project": repository.project_info(),
            "revision": target_revision,
            "tables": {table: _rows(repository, table) for table in SNAPSHOT_TABLES},
        }
        encoded = _canonical_json(payload)
        input_hash = _sha256_text(encoded)
        snapshot_id = uuid7()
        relative = "artifacts/problem/legacy-import-snapshot.json"
        snapshot_path = repository.project_directory / relative
        sha256, size = _write_text(snapshot_path, encoded + "\n")
        created_files.append(snapshot_path)
        repository.connection.execute(
            "INSERT INTO data_snapshots(id, revision, input_hash, payload_path, created_at) VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, target_revision, input_hash, relative, now),
        )
        repository.connection.execute(
            "INSERT INTO artifacts(id, kind, relative_path, sha256, size_bytes, created_at) VALUES (?, 'data_snapshot', ?, ?, ?, ?)",
            (uuid7(), relative, sha256, size, now),
        )

        session_id = uuid7()
        repository.connection.execute(
            "INSERT INTO optimization_sessions(id, name, status, created_at, updated_at) VALUES (?, ?, 'completed', ?, ?)",
            (session_id, "网页版历史候选（只读迁移）", now, now),
        )
        solutions_by_run: dict[str, int] = {}
        for solution in solutions:
            source_run_id = str(solution.get("run_id") or "")
            if source_run_id:
                solutions_by_run[source_run_id] = solutions_by_run.get(source_run_id, 0) + 1

        imported_run_ids: set[str] = set()
        for row in runs:
            source_id = str(row["id"])
            run_id = ids["run"][source_id]
            config = _json_object(row.get("config"))
            source_status = str(row.get("status") or "failed")
            if source_status == "succeeded" and solutions_by_run.get(source_id, 0):
                status = "succeeded"
            elif source_status == "cancelled":
                status = "cancelled"
            elif source_status in {"queued", "running", "preparing", "validating"}:
                status = "failed_recoverable"
            else:
                status = "failed"
            time_budget = max(10, min(1800, int(config.get("time_limit_seconds") or 60)))
            random_seed = max(0, min(2_147_483_647, int(config.get("seed") or 0)))
            created_at = _timestamp(
                row.get("queued_at") or row.get("started_at") or row.get("finished_at"),
                now,
            )
            started_at = _timestamp(row.get("started_at"), created_at) if row.get("started_at") else None
            finished_at = _timestamp(row.get("finished_at"), now) if row.get("finished_at") else None
            repository.connection.execute(
                """
                INSERT INTO scheduling_rounds(
                    id, session_id, snapshot_id, status, time_budget_seconds,
                    random_seed, algorithm, algorithm_config, input_hash,
                    started_at, finished_at, stop_reason, error_code, error_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    snapshot_id,
                    status,
                    time_budget,
                    random_seed,
                    str(row.get("algorithm") or "legacy_web"),
                    _canonical_json(config),
                    input_hash,
                    started_at,
                    finished_at,
                    "legacy_import",
                    str(row.get("error_code") or "") or None,
                    "网页版历史轮次失败（详细错误未迁移）" if status == "failed" else None,
                    created_at,
                    finished_at or started_at or created_at,
                ),
            )
            repository.connection.execute(
                "INSERT INTO round_events(id, round_id, sequence, event_type, payload, created_at) VALUES (?, ?, 1, 'legacy_history_imported', ?, ?)",
                (
                    uuid7(),
                    run_id,
                    _canonical_json({"source": "local_supabase", "readOnly": True}),
                    now,
                ),
            )
            imported_run_ids.add(source_id)

        imported_solution_ids: set[str] = set()
        invalid_candidate_count = 0
        for row in solutions:
            source_id = str(row["id"])
            source_run_id = str(row.get("run_id") or "")
            if source_run_id not in imported_run_ids:
                warnings.append(
                    {
                        "code": "LEGACY_CANDIDATE_SKIPPED",
                        "message": "旧版候选缺少可映射的排课轮次，已跳过",
                    }
                )
                continue
            hard_violations = max(0, int(row.get("hard_violations") or 0))
            source_status = str(row.get("status") or "candidate")
            if source_status == "superseded":
                status = "superseded"
            elif hard_violations == 0:
                status = "valid"
            else:
                status = "invalid"
                invalid_candidate_count += 1
            candidate_id = ids["solution"][source_id]
            candidate_created_at = _timestamp(row.get("published_at"), now)
            diagnostics = {
                "source": "local_supabase",
                "sourceStatus": source_status,
                "readOnlyImport": True,
                "scoreBreakdown": "legacy_total_as_distribution_penalty",
            }
            repository.connection.execute(
                """
                INSERT INTO candidates(
                    id, round_id, snapshot_id, name, status, hard_violations,
                    total_score, input_hash, solver_version, validator_version,
                    diagnostics, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'legacy-web-import', 'legacy-validator-import', ?, ?)
                """,
                (
                    candidate_id,
                    ids["run"][source_run_id],
                    snapshot_id,
                    row.get("name") or f"网页版候选 {row.get('version_no') or 1}",
                    status,
                    hard_violations,
                    int(row.get("total_score") or 0),
                    input_hash,
                    _canonical_json(diagnostics),
                    candidate_created_at,
                ),
            )
            for key, value in (
                ("time_penalty", 0),
                ("room_penalty", 0),
                ("distribution_penalty", int(row.get("total_score") or 0)),
                ("total_score", int(row.get("total_score") or 0)),
            ):
                repository.connection.execute(
                    "INSERT INTO candidate_metrics(id, candidate_id, metric_key, metric_value, details) VALUES (?, ?, ?, ?, ?)",
                    (uuid7(), candidate_id, key, value, _canonical_json({"source": "legacy"})),
                )
            imported_solution_ids.add(source_id)

        if invalid_candidate_count:
            warnings.append(
                {
                    "code": "LEGACY_INVALID_CANDIDATES_IMPORTED",
                    "message": f"{invalid_candidate_count} 个网页版候选含硬约束违例，已按只读无效候选保留",
                    "count": invalid_candidate_count,
                }
            )

        lesson_by_xml = {
            str(row.get("xml_class_id")): ids["task_lesson"][str(row["id"])]
            for row in snapshot.get("task_lessons", [])
            if row.get("xml_class_id")
        }
        imported_entry_count = 0
        missing_lesson_count = 0
        for row in entries:
            source_solution_id = str(row.get("solution_version_id") or "")
            if source_solution_id not in imported_solution_ids:
                continue
            source_lesson_id = str(row.get("lesson_id") or "")
            task_lesson_id = ids["task_lesson"].get(source_lesson_id) or lesson_by_xml.get(
                str(row.get("source_xml_class_id") or "")
            )
            if not task_lesson_id:
                missing_lesson_count += 1
            repository.connection.execute(
                """
                INSERT INTO timetable_entries(
                    id, candidate_id, task_lesson_id, teaching_task_id,
                    homeroom_id, subject_id, teacher_id, room_id, weekday,
                    start_slot, duration_slots, week_bits, source_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid7(),
                    ids["solution"][source_solution_id],
                    task_lesson_id,
                    _mapped(ids["teaching_task"], row.get("teaching_task_id")),
                    _mapped(ids["homeroom"], row.get("homeroom_id")),
                    _mapped(ids["subject"], row.get("subject_id")),
                    _mapped(ids["teacher"], row.get("teacher_id")),
                    _mapped(ids["room"], row.get("room_id")),
                    int(row["weekday"]),
                    int(row["start_slot"]),
                    max(1, int(row.get("length_slots") or row.get("duration_slots") or 1)),
                    str(row.get("week_bits") or "1"),
                    row.get("source_xml_class_id"),
                    now,
                ),
            )
            imported_entry_count += 1
        if missing_lesson_count:
            warnings.append(
                {
                    "code": "LEGACY_ENTRY_LESSON_UNRESOLVED",
                    "message": f"{missing_lesson_count} 条历史课表项无法关联现有课次，已保留为只读条目",
                    "count": missing_lesson_count,
                }
            )

        warning_counts = LegacySupabaseImporter._record_import_warnings(
            repository, warnings, now
        )
        return {
            "optimization_session": 1,
            "data_snapshot": 1,
            "scheduling_round": len(imported_run_ids),
            "candidate": len(imported_solution_ids),
            "timetable_entry": imported_entry_count,
            **warning_counts,
        }

    @staticmethod
    def _record_import_warnings(
        repository: ProjectRepository,
        warnings: Sequence[Mapping[str, Any]],
        now: str,
    ) -> Mapping[str, int]:
        for warning in warnings:
            repository.connection.execute(
                """
                INSERT INTO validation_issues(
                    id, scope_type, severity, code, message, details, created_at
                ) VALUES (?, 'legacy_import', 'warning', ?, ?, ?, ?)
                """,
                (
                    uuid7(),
                    str(warning["code"]),
                    str(warning["message"]),
                    _canonical_json(
                        {
                            key: value
                            for key, value in warning.items()
                            if key not in {"code", "message"}
                        }
                    ),
                    now,
                ),
            )
        return {"validation_issue": len(warnings)}
