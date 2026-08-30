from __future__ import annotations

from pathlib import Path

import pytest

from stt_desktop.importers.legacy_supabase import LegacyImportError, LegacySupabaseImporter
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
