from __future__ import annotations

import json
import os
import secrets
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable, Sequence
from typing import Any, Mapping

from .schema import MIGRATIONS, SCHEMA_V1, SCHEMA_VERSION

FORMAT_VERSION = 1
APP_VERSION = "0.1.5"
ALGORITHM_PROTOCOL_VERSION = "1"


class ProjectError(RuntimeError):
    pass


class ProjectLockedError(ProjectError):
    pass


class ProjectSchemaTooNewError(ProjectError):
    pass


class ProjectMigrationError(ProjectError):
    pass


class RevisionConflictError(ProjectError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"项目版本冲突：期望 {expected}，当前 {actual}")
        self.expected = expected
        self.actual = actual


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def uuid7() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return str(uuid.UUID(int=value))


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_project_id(project_id: str) -> str:
    try:
        parsed = uuid.UUID(project_id)
    except (ValueError, AttributeError) as exc:
        raise ProjectError("项目 ID 不是有效 UUID") from exc
    normalized = str(parsed)
    if normalized != project_id.lower():
        raise ProjectError("项目 ID 必须使用规范 UUID 格式")
    return normalized


@dataclass(frozen=True)
class EntitySpec:
    table: str
    fields: frozenset[str]
    required: frozenset[str]
    order_by: str


ENTITY_SPECS: dict[str, EntitySpec] = {
    "academic_year": EntitySpec(
        "academic_years", frozenset({"name", "start_date", "end_date"}), frozenset({"name"}), "name"
    ),
    "term": EntitySpec(
        "terms",
        frozenset({"academic_year_id", "name", "start_date", "end_date", "week_count", "day_count", "active"}),
        frozenset({"name"}),
        "name",
    ),
    "bell_schedule": EntitySpec(
        "bell_schedules",
        frozenset({"term_id", "name", "day_count", "slot_duration_minutes", "is_default", "display_config"}),
        frozenset({"name"}),
        "name",
    ),
    "time_slot": EntitySpec(
        "time_slots",
        frozenset({"bell_schedule_id", "weekday", "period_index", "label", "start_slot", "length_slots", "start_time_minutes", "end_time_minutes", "active", "display_config"}),
        frozenset({"bell_schedule_id", "weekday", "period_index", "label", "start_time_minutes", "end_time_minutes"}),
        "weekday, period_index",
    ),
    "grade": EntitySpec(
        "grades", frozenset({"name", "code", "sort_order"}), frozenset({"name"}), "sort_order, name"
    ),
    "teacher": EntitySpec(
        "teachers", frozenset({"employee_no", "name", "department", "status"}), frozenset({"name"}), "name"
    ),
    "room_type": EntitySpec(
        "room_types", frozenset({"name", "code", "description"}), frozenset({"name"}), "name"
    ),
    "room": EntitySpec(
        "rooms", frozenset({"room_type_id", "name", "room_no", "capacity", "status"}), frozenset({"name"}), "name"
    ),
    "homeroom": EntitySpec(
        "homerooms",
        frozenset({"grade_id", "term_id", "head_teacher_id", "default_room_id", "name", "group_name", "student_count", "status"}),
        frozenset({"name"}),
        "name",
    ),
    "subject": EntitySpec(
        "subjects",
        frozenset({"name", "code", "category", "default_duration_slots", "requires_special_room"}),
        frozenset({"name"}),
        "name",
    ),
    "course_plan": EntitySpec(
        "course_plans",
        frozenset({"term_id", "homeroom_id", "subject_id", "weekly_slots", "duration_slots", "allow_double_period", "priority", "week_bits", "day_bits"}),
        frozenset({"homeroom_id", "subject_id", "weekly_slots"}),
        "homeroom_id, subject_id",
    ),
    "teaching_task": EntitySpec(
        "teaching_tasks",
        frozenset({"term_id", "course_plan_id", "homeroom_id", "subject_id", "primary_teacher_id", "weekly_slots", "duration_slots", "required_room_type", "fixed_room_id", "status", "week_bits", "day_bits"}),
        frozenset({"homeroom_id", "subject_id", "weekly_slots"}),
        "homeroom_id, subject_id",
    ),
    "task_lesson": EntitySpec(
        "task_lessons",
        frozenset({"teaching_task_id", "lesson_index", "duration_slots", "source_id", "week_bits", "day_bits", "label", "enabled"}),
        frozenset({"teaching_task_id", "lesson_index"}),
        "teaching_task_id, lesson_index",
    ),
    "availability_rule": EntitySpec(
        "availability_rules",
        frozenset({"entity_type", "entity_id", "bell_schedule_id", "time_slot_id", "week_bits", "day_bits", "required", "penalty", "reason"}),
        frozenset({"entity_type", "entity_id"}),
        "entity_type, entity_id",
    ),
    "constraint": EntitySpec(
        "constraints",
        frozenset({"type", "name", "severity", "enabled", "weight", "parameters"}),
        frozenset({"type", "name"}),
        "name",
    ),
    "timetable_template_assignment": EntitySpec(
        "timetable_template_assignments",
        frozenset({"entity_type", "entity_id", "bell_schedule_id"}),
        frozenset({"entity_type", "bell_schedule_id"}),
        "entity_type, entity_id",
    ),
}


class _ProjectLock:
    def __init__(self, project_directory: Path) -> None:
        self.path = project_directory / ".stt.lock"
        self.token = secrets.token_hex(16)
        payload = json.dumps({"pid": os.getpid(), "token": self.token, "created_at": utc_now()})
        self.descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR)
        try:
            if os.fstat(self.descriptor).st_size == 0:
                os.write(self.descriptor, b" ")
                os.fsync(self.descriptor)
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(self.descriptor, 0)
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            os.write(self.descriptor, payload.encode("utf-8"))
            os.fsync(self.descriptor)
        except OSError as exc:
            os.close(self.descriptor)
            self.descriptor = -1
            raise ProjectLockedError(
                f"项目已被另一个进程打开: {project_directory.name}"
            ) from exc

    def release(self) -> None:
        descriptor = getattr(self, "descriptor", -1)
        if descriptor < 0:
            return
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
            self.descriptor = -1


class ProjectRepository:
    def __init__(
        self,
        project_directory: Path,
        manifest: dict[str, Any],
        workspace: ProjectWorkspace | None = None,
    ) -> None:
        self.project_directory = project_directory
        self.workspace = workspace
        self.manifest_path = project_directory / "manifest.json"
        self.database_path = project_directory / "project.sqlite3"
        self.manifest = manifest
        self._lock = _ProjectLock(project_directory)
        try:
            self.connection = sqlite3.connect(self.database_path, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA busy_timeout = 5000")
            self._verify_database()
            actual_revision = self.revision
            if self.manifest.get("revision") != actual_revision:
                self.manifest["revision"] = actual_revision
                self.manifest["updated_at"] = utc_now()
                _atomic_write_json(self.manifest_path, self.manifest)
        except Exception:
            connection = getattr(self, "connection", None)
            if connection is not None:
                connection.close()
            self._lock.release()
            raise

    def _verify_database(self) -> None:
        integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ProjectError(f"项目数据库完整性检查失败: {integrity}")
        foreign_key_enabled = self.connection.execute("PRAGMA foreign_keys").fetchone()[0]
        if foreign_key_enabled != 1:
            raise ProjectError("SQLite 外键未启用")
        schema_version = int(
            self.connection.execute(
                "SELECT value FROM app_metadata WHERE key = 'schema_version'"
            ).fetchone()[0]
        )
        if schema_version > SCHEMA_VERSION:
            raise ProjectSchemaTooNewError(
                f"项目 schema {schema_version} 高于应用支持版本 {SCHEMA_VERSION}"
            )
        if schema_version < 1:
            raise ProjectMigrationError(f"不支持从 schema {schema_version} 迁移")
        if schema_version < SCHEMA_VERSION:
            self._migrate_database(schema_version)
            schema_version = self.schema_version
        if schema_version != SCHEMA_VERSION:
            raise ProjectMigrationError(
                f"项目 schema 迁移后仍为 {schema_version}，期望 {SCHEMA_VERSION}"
            )
        if self.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ProjectMigrationError("项目迁移后 SQLite 完整性检查失败")
        if self.connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ProjectMigrationError("项目迁移后存在外键错误")

    @property
    def schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise ProjectMigrationError("项目数据库缺少 schema_version")
        return int(row[0])

    def _migrate_database(self, source_version: int) -> None:
        workspace = self.workspace or ProjectWorkspace(self.project_directory.parents[1])
        project_size = sum(
            path.stat().st_size
            for path in self.project_directory.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        required_free = project_size * 2 + 500 * 1024 * 1024
        free_bytes = shutil.disk_usage(workspace.root).free
        if free_bytes < required_free:
            raise ProjectMigrationError(
                f"项目迁移至少需要 {required_free} 字节可用空间，当前仅 {free_bytes} 字节"
            )

        from stt_desktop.backups import BackupService

        backup = BackupService(self, workspace).create_backup(reason="pre-migration")
        if not backup.get("verified"):
            raise ProjectMigrationError("迁移前备份未通过校验")

        current = source_version
        try:
            while current < SCHEMA_VERSION:
                target = current + 1
                migration = MIGRATIONS.get(target)
                if not migration:
                    raise ProjectMigrationError(f"缺少 schema {current} 到 {target} 的迁移")
                script = (
                    "BEGIN IMMEDIATE;\n"
                    f"{migration}\n"
                    "UPDATE app_metadata SET value = "
                    f"'{target}' WHERE key = 'schema_version';\n"
                    "COMMIT;"
                )
                self.connection.executescript(script)
                current = target
        except Exception as exc:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            if isinstance(exc, ProjectMigrationError):
                raise
            raise ProjectMigrationError(
                f"项目从 schema {current} 迁移失败；已保留迁移前备份 {backup['fileName']}"
            ) from exc

        now = utc_now()
        self.manifest.update(
            {
                "schema_version": SCHEMA_VERSION,
                "app_version": APP_VERSION,
                "updated_at": now,
            }
        )
        _atomic_write_json(self.manifest_path, self.manifest)

    @property
    def revision(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'revision'"
        ).fetchone()
        return int(row[0])

    def project_info(self) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM project LIMIT 1").fetchone()
        return dict(row)

    def integrity_check(self) -> dict[str, Any]:
        integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [dict(row) for row in self.connection.execute("PRAGMA foreign_key_check")]
        return {"integrity": integrity, "foreign_key_issues": foreign_keys}

    def list_entities(self, entity_type: str) -> list[dict[str, Any]]:
        spec = self._entity_spec(entity_type)
        rows = self.connection.execute(
            f"SELECT * FROM {spec.table} ORDER BY {spec.order_by}"  # noqa: S608 - allowlisted
        ).fetchall()
        return [dict(row) for row in rows]

    def list_entities_page(
        self, entity_type: str, *, limit: int, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        if not 1 <= limit <= 500:
            raise ProjectError("分页大小必须在 1–500 之间")
        if offset < 0:
            raise ProjectError("分页偏移不能为负数")
        spec = self._entity_spec(entity_type)
        total = int(
            self.connection.execute(
                f"SELECT COUNT(*) FROM {spec.table}"  # noqa: S608 - allowlisted
            ).fetchone()[0]
        )
        rows = self.connection.execute(
            f"SELECT * FROM {spec.table} ORDER BY {spec.order_by} LIMIT ? OFFSET ?",  # noqa: S608 - allowlisted
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows], total

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        spec = self._entity_spec(entity_type)
        row = self.connection.execute(
            f"SELECT * FROM {spec.table} WHERE id = ?",  # noqa: S608 - allowlisted
            (entity_id,),
        ).fetchone()
        return dict(row) if row else None

    def save_entity(
        self,
        entity_type: str,
        payload: Mapping[str, Any],
        expected_revision: int,
    ) -> tuple[dict[str, Any], int]:
        spec = self._entity_spec(entity_type)
        unknown = sorted(set(payload) - spec.fields - {"id"})
        if unknown:
            raise ProjectError(f"{entity_type} 包含未知字段: {', '.join(unknown)}")
        entity_id = str(payload.get("id") or uuid7())
        existing = self.get_entity(entity_type, entity_id)
        missing = sorted(field for field in spec.required if field not in payload and existing is None)
        if missing:
            raise ProjectError(f"{entity_type} 缺少必要字段: {', '.join(missing)}")
        if not payload.keys() - {"id"}:
            raise ProjectError(f"{entity_type} 没有可保存字段")

        values = {key: payload[key] for key in payload if key in spec.fields}
        values = self._normalize_entity_values(entity_type, values)
        if entity_type == "timetable_template_assignment":
            effective_assignment = {**(existing or {}), **values}
            self._validate_timetable_template_assignment(effective_assignment)
            if effective_assignment.get("entity_type") == "all":
                values["entity_id"] = None
        now = utc_now()
        self._begin_write(expected_revision)
        try:
            if existing:
                assignments = ", ".join(f"{key} = ?" for key in values)
                parameters = [*values.values(), now, entity_id]
                self.connection.execute(
                    f"UPDATE {spec.table} SET {assignments}, updated_at = ? WHERE id = ?",  # noqa: S608
                    parameters,
                )
            else:
                columns = ["id", *values.keys(), "created_at", "updated_at"]
                placeholders = ", ".join("?" for _ in columns)
                parameters = [entity_id, *values.values(), now, now]
                self.connection.execute(
                    f"INSERT INTO {spec.table} ({', '.join(columns)}) VALUES ({placeholders})",  # noqa: S608
                    parameters,
                )
            revision = self._commit_write(now)
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        self._write_manifest_revision(revision, now)
        saved = self.get_entity(entity_type, entity_id)
        if saved is None:
            raise ProjectError("保存后无法读取实体")
        return saved, revision

    def save_teaching_task_bundle(
        self,
        payload: Mapping[str, Any],
        expected_revision: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        """Save one teaching task and regenerate its weekly lessons atomically."""
        spec = self._entity_spec("teaching_task")
        unknown = sorted(set(payload) - spec.fields - {"id"})
        if unknown:
            raise ProjectError(f"teaching_task 包含未知字段: {', '.join(unknown)}")
        task_id = str(payload.get("id") or uuid7())
        existing = self.get_entity("teaching_task", task_id)
        missing = sorted(
            field for field in spec.required if field not in payload and existing is None
        )
        if missing:
            raise ProjectError(f"teaching_task 缺少必要字段: {', '.join(missing)}")
        values = {key: payload[key] for key in payload if key in spec.fields}
        effective = {**(existing or {}), **values}
        weekly_slots = int(effective.get("weekly_slots", 0))
        duration_slots = int(effective.get("duration_slots", 1))
        if weekly_slots < 0 or duration_slots <= 0:
            raise ProjectError("教学任务课时必须为非负数，连续课时必须大于 0")
        week_bits = str(effective.get("week_bits", "11111111111111111111"))
        day_bits = str(effective.get("day_bits", "11111"))
        now = utc_now()
        self._begin_write(expected_revision)
        try:
            if existing:
                if not values:
                    raise ProjectError("teaching_task 没有可保存字段")
                assignments = ", ".join(f"{key} = ?" for key in values)
                self.connection.execute(
                    f"UPDATE {spec.table} SET {assignments}, updated_at = ? WHERE id = ?",  # noqa: S608
                    [*values.values(), now, task_id],
                )
            else:
                columns = ["id", *values.keys(), "created_at", "updated_at"]
                placeholders = ", ".join("?" for _ in columns)
                self.connection.execute(
                    f"INSERT INTO {spec.table} ({', '.join(columns)}) VALUES ({placeholders})",  # noqa: S608
                    [task_id, *values.values(), now, now],
                )
            self.connection.execute(
                "DELETE FROM task_lessons WHERE teaching_task_id = ?", (task_id,)
            )
            remaining = weekly_slots
            lesson_index = 0
            while remaining > 0:
                lesson_duration = min(duration_slots, remaining)
                self.connection.execute(
                    """
                    INSERT INTO task_lessons(
                        id, teaching_task_id, lesson_index, duration_slots, source_id,
                        week_bits, day_bits, label, enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        uuid7(),
                        task_id,
                        lesson_index,
                        lesson_duration,
                        f"generated:{task_id}:{lesson_index}",
                        week_bits,
                        day_bits,
                        f"第{lesson_index + 1}次课",
                        now,
                        now,
                    ),
                )
                remaining -= lesson_duration
                lesson_index += 1
            revision = self._commit_write(now)
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        self._write_manifest_revision(revision, now)
        task = self.get_entity("teaching_task", task_id)
        if task is None:
            raise ProjectError("保存后无法读取教学任务")
        lessons = [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM task_lessons WHERE teaching_task_id = ? ORDER BY lesson_index",
                (task_id,),
            )
        ]
        return task, lessons, revision

    def bulk_insert_entities(
        self,
        batches: Mapping[str, Sequence[Mapping[str, Any]]],
        expected_revision: int,
        *,
        after_insert: Callable[[sqlite3.Connection, str, int], Mapping[str, int] | None]
        | None = None,
    ) -> tuple[dict[str, int], int]:
        """Insert a dependency-ordered import as one revision and one transaction."""
        prepared: list[tuple[EntitySpec, str, dict[str, Any]]] = []
        counts: dict[str, int] = {}
        seen_ids: set[str] = set()
        for entity_type, payloads in batches.items():
            spec = self._entity_spec(entity_type)
            counts[entity_type] = len(payloads)
            for payload in payloads:
                unknown = sorted(set(payload) - spec.fields - {"id"})
                if unknown:
                    raise ProjectError(f"{entity_type} 包含未知字段: {', '.join(unknown)}")
                missing = sorted(field for field in spec.required if field not in payload)
                if missing:
                    raise ProjectError(f"{entity_type} 缺少必要字段: {', '.join(missing)}")
                entity_id = str(payload.get("id") or uuid7())
                if entity_id in seen_ids:
                    raise ProjectError(f"批量导入包含重复 ID: {entity_id}")
                seen_ids.add(entity_id)
                values = {key: payload[key] for key in payload if key in spec.fields}
                values = self._normalize_entity_values(entity_type, values)
                prepared.append((spec, entity_id, values))

        now = utc_now()
        self._begin_write(expected_revision)
        try:
            for spec, entity_id, values in prepared:
                columns = ["id", *values.keys(), "created_at", "updated_at"]
                placeholders = ", ".join("?" for _ in columns)
                parameters = [entity_id, *values.values(), now, now]
                self.connection.execute(
                    f"INSERT INTO {spec.table} ({', '.join(columns)}) VALUES ({placeholders})",  # noqa: S608
                    parameters,
                )
            if after_insert:
                extra_counts = after_insert(self.connection, now, expected_revision + 1)
                for key, value in (extra_counts or {}).items():
                    if key in counts:
                        raise ProjectError(f"批量导入统计键重复: {key}")
                    counts[key] = int(value)
            revision = self._commit_write(now)
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        self._write_manifest_revision(revision, now)
        return counts, revision

    def delete_entity(self, entity_type: str, entity_id: str, expected_revision: int) -> int:
        spec = self._entity_spec(entity_type)
        now = utc_now()
        self._begin_write(expected_revision)
        try:
            cursor = self.connection.execute(
                f"DELETE FROM {spec.table} WHERE id = ?",  # noqa: S608 - allowlisted
                (entity_id,),
            )
            if cursor.rowcount != 1:
                raise ProjectError(f"未找到要删除的 {entity_type}: {entity_id}")
            revision = self._commit_write(now)
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        self._write_manifest_revision(revision, now)
        return revision

    def _entity_spec(self, entity_type: str) -> EntitySpec:
        try:
            return ENTITY_SPECS[entity_type]
        except KeyError as exc:
            raise ProjectError(f"不支持的实体类型: {entity_type}") from exc

    def _normalize_entity_values(
        self, entity_type: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        json_fields: dict[str, tuple[str, ...]] = {
            "bell_schedule": ("display_config",),
            "time_slot": ("display_config",),
            "constraint": ("parameters",),
        }
        normalized = dict(values)
        for field in json_fields.get(entity_type, ()):
            if field not in normalized:
                continue
            raw = normalized[field]
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError as exc:
                raise ProjectError(f"{entity_type}.{field} 必须是有效 JSON") from exc
            if not isinstance(parsed, dict):
                raise ProjectError(f"{entity_type}.{field} 必须是 JSON 对象")
            normalized[field] = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        return normalized

    def _validate_timetable_template_assignment(self, values: dict[str, Any]) -> None:
        entity_type = str(values.get("entity_type") or "")
        entity_id = values.get("entity_id")
        if entity_type == "all":
            return
        target_tables = {
            "homeroom": "homerooms",
            "teacher": "teachers",
            "subject": "subjects",
            "room_type": "room_types",
            "room": "rooms",
        }
        table = target_tables.get(entity_type)
        if table is None:
            raise ProjectError("作息模板分配对象类型无效")
        if not entity_id:
            raise ProjectError("作息模板分配必须选择具体对象")
        if self.connection.execute(
            f"SELECT 1 FROM {table} WHERE id = ?",  # noqa: S608 - allowlisted table
            (str(entity_id),),
        ).fetchone() is None:
            raise ProjectError("作息模板分配对象不存在")

    def _begin_write(self, expected_revision: int) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        actual = self.revision
        if actual != expected_revision:
            self.connection.execute("ROLLBACK")
            raise RevisionConflictError(expected_revision, actual)

    def _commit_write(self, now: str) -> int:
        next_revision = self.revision + 1
        self.connection.execute(
            "UPDATE app_metadata SET value = ? WHERE key = 'revision'", (str(next_revision),)
        )
        self.connection.execute("UPDATE project SET updated_at = ?", (now,))
        self.connection.execute("COMMIT")
        return next_revision

    def _write_manifest_revision(self, revision: int, now: str) -> None:
        self.manifest["revision"] = revision
        self.manifest["updated_at"] = now
        _atomic_write_json(self.manifest_path, self.manifest)

    def close(self) -> None:
        connection = getattr(self, "connection", None)
        if connection is not None:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.close()
            self.connection = None  # type: ignore[assignment]
        self._lock.release()

    def __enter__(self) -> ProjectRepository:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class ProjectWorkspace:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.projects_directory = self.root / "projects"
        self.backups_directory = self.root / "backups"
        self.temp_directory = self.root / "temp"
        self.trash_projects_directory = self.root / "trash" / "projects"
        for directory in (
            self.projects_directory,
            self.backups_directory,
            self.temp_directory,
            self.trash_projects_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def create_project(self, name: str) -> ProjectRepository:
        normalized_name = name.strip()
        if not normalized_name:
            raise ProjectError("项目名称不能为空")
        project_id = uuid7()
        project_directory = self.projects_directory / project_id
        project_directory.mkdir()
        for relative in (
            "attachments",
            "artifacts/problem",
            "artifacts/solution",
            "artifacts/exports",
            "logs",
        ):
            (project_directory / relative).mkdir(parents=True)
        database_path = project_directory / "project.sqlite3"
        now = utc_now()
        try:
            connection = sqlite3.connect(database_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA_V1)
            for target in range(2, SCHEMA_VERSION + 1):
                migration = MIGRATIONS.get(target)
                if not migration:
                    raise ProjectMigrationError(f"缺少新项目 schema {target} 定义")
                connection.executescript(migration)
            connection.execute(
                "INSERT INTO app_metadata(key, value) VALUES ('schema_version', ?), ('revision', '0')",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO project(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project_id, normalized_name, now, now),
            )
            connection.commit()
            connection.close()
            manifest = {
                "kind": "project",
                "format_version": FORMAT_VERSION,
                "project_id": project_id,
                "name": normalized_name,
                "created_at": now,
                "updated_at": now,
                "app_version": APP_VERSION,
                "schema_version": SCHEMA_VERSION,
                "revision": 0,
                "algorithm_protocol_version": ALGORITHM_PROTOCOL_VERSION,
                "database": "project.sqlite3",
            }
            _atomic_write_json(project_directory / "manifest.json", manifest)
        except Exception:
            # The incomplete directory remains visible for diagnosis and is never treated as a project
            # because it lacks a valid manifest.
            raise
        return self.open_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for manifest_path in self.projects_directory.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                _safe_project_id(str(manifest["project_id"]))
                if manifest.get("kind") == "project":
                    projects.append(
                        {**manifest, "path": str(manifest_path.parent.resolve())}
                    )
            except (OSError, json.JSONDecodeError, KeyError, ProjectError):
                continue
        return sorted(projects, key=lambda item: item.get("updated_at", ""), reverse=True)

    def open_project(self, project_id: str) -> ProjectRepository:
        normalized = _safe_project_id(project_id)
        project_directory = (self.projects_directory / normalized).resolve()
        if project_directory.parent != self.projects_directory:
            raise ProjectError("项目路径越界")
        manifest_path = project_directory / "manifest.json"
        if (project_directory / ".stt.deleting.json").exists():
            raise ProjectError("项目正在移入回收区，不能打开")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProjectError(f"项目不存在: {normalized}") from exc
        except json.JSONDecodeError as exc:
            raise ProjectError("项目 manifest 无法解析") from exc
        if manifest.get("project_id") != normalized or manifest.get("kind") != "project":
            raise ProjectError("项目 manifest 与目录不匹配")
        manifest_schema = manifest.get("schema_version")
        if not isinstance(manifest_schema, int):
            raise ProjectError("项目 manifest 缺少有效 schema_version")
        if manifest_schema > SCHEMA_VERSION:
            raise ProjectSchemaTooNewError(
                f"项目 schema {manifest_schema} 高于应用支持版本 {SCHEMA_VERSION}"
            )
        return ProjectRepository(project_directory, manifest, self)

    def delete_project(self, project_id: str, expected_name: str) -> dict[str, Any]:
        normalized = _safe_project_id(project_id)
        project_directory = (self.projects_directory / normalized).resolve()
        if project_directory.parent != self.projects_directory:
            raise ProjectError("项目路径越界")
        manifest_path = project_directory / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProjectError(f"项目不存在: {normalized}") from exc
        except json.JSONDecodeError as exc:
            raise ProjectError("项目 manifest 无法解析") from exc
        if manifest.get("project_id") != normalized or manifest.get("kind") != "project":
            raise ProjectError("项目 manifest 与目录不匹配")
        if str(manifest.get("name") or "") != expected_name:
            raise ProjectError("项目名称已变化，请刷新列表后重新确认")

        deletion_marker = project_directory / ".stt.deleting.json"
        project_lock = _ProjectLock(project_directory)
        try:
            deleted_at = utc_now()
            target_name = (
                f"{normalized}-{deleted_at.replace(':', '').replace('-', '')}"
                f"-{secrets.token_hex(4)}"
            )
            target_directory = (self.trash_projects_directory / target_name).resolve()
            if target_directory.parent != self.trash_projects_directory:
                raise ProjectError("项目回收路径越界")
            _atomic_write_json(
                deletion_marker,
                {
                    "project_id": normalized,
                    "name": expected_name,
                    "deleted_at": deleted_at,
                    "original_path": str(project_directory),
                    "recoverable": True,
                },
            )
        finally:
            project_lock.release()

        try:
            project_directory.rename(target_directory)
        except Exception:
            deletion_marker.unlink(missing_ok=True)
            raise
        return {
            "projectId": normalized,
            "name": expected_name,
            "originalPath": str(project_directory),
            "trashPath": str(target_directory),
            "deletedAt": deleted_at,
            "recoverable": True,
        }
