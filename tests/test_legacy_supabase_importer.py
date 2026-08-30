from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from stt_desktop.importers.legacy_supabase import LegacyImportError, LegacySupabaseImporter
from stt_desktop.scheduling.timetable import TimetableService
from stt_desktop.storage.project import ProjectError
from stt_desktop.storage import ProjectWorkspace


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


def minimal_snapshot() -> dict[str, list[dict[str, object]]]:
    return {
        "terms": [
            {
                "id": uid(1),
                "name": "第一学期",
                "start_date": None,
                "end_date": None,
                "week_count": 20,
                "day_count": 5,
                "active": True,
            }
        ],
        "templates": [
            {
                "id": uid(2),
                "term_id": uid(1),
                "name": "默认作息",
                "day_count": 5,
                "slot_duration_minutes": 40,
                "is_default": True,
                "display_config": {},
            }
        ],
        "periods": [
            {
                "id": uid(3),
                "template_id": uid(2),
                "weekday": 1,
                "period_index": 0,
                "label": "第一节",
                "start_slot": 0,
                "length_slots": 1,
                "start_time_minutes": 480,
                "end_time_minutes": 520,
                "active": True,
                "display_config": {},
            }
        ],
        "teachers": [
            {
                "id": uid(4),
                "employee_no": "T001",
                "name": "测试教师",
                "department": "数学组",
                "status": "active",
            }
        ],
        "room_types": [
            {"id": uid(5), "name": "普通教室", "code": "NORMAL", "description": None}
        ],
        "rooms": [
            {
                "id": uid(6),
                "type_id": uid(5),
                "name": "101",
                "room_no": "101",
                "capacity": 45,
                "status": "active",
            }
        ],
        "homerooms": [
            {
                "id": uid(7),
                "term_id": uid(1),
                "head_teacher_id": uid(4),
                "default_room_id": uid(6),
                "name": "一班",
                "group_name": "一年级",
                "student_count": 40,
                "status": "active",
            }
        ],
        "subjects": [
            {
                "id": uid(8),
                "name": "数学",
                "code": "MATH",
                "category": "general",
                "default_duration_slots": 1,
                "requires_special_room": False,
            }
        ],
        "course_plans": [
            {
                "id": uid(9),
                "term_id": uid(1),
                "homeroom_id": uid(7),
                "subject_id": uid(8),
                "weekly_slots": 5,
                "duration_slots": 1,
                "allow_double_period": False,
                "priority": 0,
                "week_bits": "1" * 20,
                "day_bits": "11111",
            }
        ],
        "teaching_tasks": [
            {
                "id": uid(10),
                "term_id": uid(1),
                "course_plan_id": uid(9),
                "homeroom_id": uid(7),
                "subject_id": uid(8),
                "primary_teacher_id": uid(4),
                "weekly_slots": 5,
                "duration_slots": 1,
                "required_room_type": None,
                "fixed_room_id": uid(6),
                "status": "active",
                "week_bits": "1" * 20,
                "day_bits": "11111",
            }
        ],
        "task_lessons": [
            {
                "id": uid(11),
                "teaching_task_id": uid(10),
                "lesson_index": 0,
                "duration_slots": 1,
                "xml_class_id": "legacy-class-1",
                "week_bits": "1" * 20,
                "day_bits": "11111",
                "label": None,
                "enabled": True,
            }
        ],
    }


def complete_snapshot() -> dict[str, list[dict[str, object]]]:
    snapshot = minimal_snapshot()
    snapshot.update(
        {
            "project": [{"id": uid(100), "name": "源项目"}],
            "assignments": [
                {
                    "id": uid(12),
                    "template_id": uid(2),
                    "entity_type": "teacher",
                    "entity_id": uid(4),
                }
            ],
            "user_constraints": [
                {
                    "id": uid(13),
                    "name": "两课次不同天",
                    "parameters": {"lesson_ids": ["legacy-class-1"]},
                    "compiled_constraints": [],
                    "required": True,
                    "enabled": True,
                }
            ],
            "itc_constraints": [
                {
                    "id": uid(14),
                    "source_user_constraint_id": uid(13),
                    "distribution_type": "DifferentDays",
                    "required": True,
                    "penalty": 0,
                }
            ],
            "runs": [
                {
                    "id": uid(15),
                    "status": "succeeded",
                    "algorithm": "cgcs",
                    "config": {"time_limit_seconds": 60, "seed": 7},
                    "queued_at": "2026-01-01T00:00:00+00:00",
                    "started_at": "2026-01-01T00:00:01+00:00",
                    "finished_at": "2026-01-01T00:00:02+00:00",
                }
            ],
            "solutions": [
                {
                    "id": uid(16),
                    "run_id": uid(15),
                    "name": "含冲突的网页版候选",
                    "version_no": 1,
                    "status": "candidate",
                    "hard_violations": 2,
                    "total_score": 42,
                    "published_at": "2026-01-01T00:00:03+00:00",
                }
            ],
            "timetable_entries": [
                {
                    "id": uid(17),
                    "solution_version_id": uid(16),
                    "lesson_id": None,
                    "source_xml_class_id": "legacy-class-1",
                    "teaching_task_id": uid(10),
                    "homeroom_id": uid(7),
                    "subject_id": uid(8),
                    "teacher_id": uid(4),
                    "room_id": uid(6),
                    "weekday": 1,
                    "start_slot": 0,
                    "length_slots": 1,
                    "week_bits": "1" * 20,
                }
            ],
        }
    )
    return snapshot


def test_importer_rejects_remote_database_by_default() -> None:
    with pytest.raises(LegacyImportError, match="只允许从本机"):
        LegacySupabaseImporter("postgresql://user@example.com/database")


def test_snapshot_is_remapped_and_writes_as_one_revision(tmp_path: Path) -> None:
    batches = LegacySupabaseImporter._build_batches(minimal_snapshot())
    workspace = ProjectWorkspace(tmp_path / "workspace")
    with workspace.create_project("迁移测试") as project:
        counts, revision = project.bulk_insert_entities(batches, expected_revision=0)

        assert revision == 1
        assert counts["teacher"] == 1
        assert counts["task_lesson"] == 1
        teacher = project.list_entities("teacher")[0]
        homeroom = project.list_entities("homeroom")[0]
        task = project.list_entities("teaching_task")[0]
        lesson = project.list_entities("task_lesson")[0]
        assert teacher["id"] != uid(4)
        assert homeroom["head_teacher_id"] == teacher["id"]
        assert task["primary_teacher_id"] == teacher["id"]
        assert lesson["teaching_task_id"] == task["id"]
        assert project.integrity_check() == {"integrity": "ok", "foreign_key_issues": []}


def test_complete_history_is_imported_atomically_and_invalid_candidate_is_read_only(
    tmp_path: Path,
) -> None:
    snapshot = complete_snapshot()
    ids = LegacySupabaseImporter._build_id_maps(snapshot)
    warnings: list[dict[str, object]] = []
    batches = LegacySupabaseImporter._build_batches(snapshot, ids=ids, warnings=warnings)
    workspace = ProjectWorkspace(tmp_path / "workspace")
    with workspace.create_project("完整迁移测试") as project:
        counts, revision = project.bulk_insert_entities(
            batches,
            expected_revision=0,
            after_insert=lambda connection, now, target_revision: LegacySupabaseImporter._import_history(
                project,
                snapshot,
                ids,
                warnings,
                [],
                now=now,
                target_revision=target_revision,
            ),
        )

        assert revision == 1
        assert counts["timetable_template_assignment"] == 1
        assert counts["constraint"] == 1
        assert counts["scheduling_round"] == 1
        assert counts["candidate"] == 1
        assert counts["timetable_entry"] == 1
        assert counts["validation_issue"] == 1
        assignment = project.list_entities("timetable_template_assignment")[0]
        teacher = project.list_entities("teacher")[0]
        assert assignment["entity_id"] == teacher["id"]
        constraint = project.list_entities("constraint")[0]
        lesson = project.list_entities("task_lesson")[0]
        assert json.loads(constraint["parameters"]) == {"lessonIds": [lesson["id"]]}

        candidate = project.connection.execute("SELECT * FROM candidates").fetchone()
        assert candidate["status"] == "invalid"
        assert candidate["hard_violations"] == 2
        timetable = TimetableService(project).list_entries(candidate["id"])
        assert timetable["items"][0]["task_lesson_id"] == lesson["id"]
        with pytest.raises(ProjectError, match="硬约束违例"):
            TimetableService(project).validate_move(
                candidate_id=candidate["id"],
                task_lesson_id=lesson["id"],
                weekday=1,
                start_slot=0,
                room_id=None,
            )

        snapshot_row = project.connection.execute(
            "SELECT payload_path FROM data_snapshots"
        ).fetchone()
        payload = (project.project_directory / snapshot_row["payload_path"]).read_text(
            encoding="utf-8"
        )
        assert uid(4) not in payload
        issue = project.connection.execute("SELECT * FROM validation_issues").fetchone()
        assert issue["code"] == "LEGACY_INVALID_CANDIDATES_IMPORTED"
        assert project.integrity_check() == {"integrity": "ok", "foreign_key_issues": []}


def test_failed_history_import_rolls_back_database_and_removes_snapshot_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = complete_snapshot()
    snapshot["timetable_entries"][0]["weekday"] = 0
    importer = LegacySupabaseImporter("postgresql://postgres@localhost/postgres")
    monkeypatch.setattr(importer, "_read_snapshot", lambda _: snapshot)
    workspace = ProjectWorkspace(tmp_path / "workspace")

    with pytest.raises(sqlite3.IntegrityError):
        importer.import_project(uid(100), workspace)

    manifest = workspace.list_projects()[0]
    with workspace.open_project(manifest["project_id"]) as project:
        assert project.revision == 0
        assert project.list_entities("teacher") == []
        assert project.connection.execute("SELECT count(*) FROM candidates").fetchone()[0] == 0
        assert list((project.project_directory / "artifacts" / "problem").iterdir()) == []
