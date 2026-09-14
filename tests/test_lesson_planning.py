import json
import sqlite3
from pathlib import Path
from xml.etree.ElementTree import fromstring

import pytest

from stt_desktop.lesson_planning import save_course_arrangement
from stt_desktop.lesson_config import parse_lesson_config, preferred_options
from stt_desktop.storage import ProjectError, RevisionConflictError
from stt_desktop.storage.project import ENTITY_SPECS
from stt_desktop.scheduling import SchedulingService
from stt_desktop.scheduling.service import SNAPSHOT_TABLES
from test_scheduling import seed_project


def drafts_for(lessons):
    fields = {
        "id",
        "label",
        "enabled",
        "duration_slots",
        "week_bits",
        "day_bits",
        "planning_config",
    }
    return [{key: value for key, value in lesson.items() if key in fields} for lesson in lessons]


def task_data(task):
    return {
        key: value
        for key, value in task.items()
        if key in ENTITY_SPECS["teaching_task"].fields | {"id"}
    }


def problem(project):
    snapshot = {
        "project": project.project_info(),
        "tables": {
            table: [dict(row) for row in project.connection.execute(f"SELECT * FROM {table}")]  # noqa: S608
            for table in SNAPSHOT_TABLES
        },
    }
    xml, diagnostics = SchedulingService(project)._build_problem(snapshot)
    return fromstring(xml), diagnostics


def test_atomic_edit_preserves_ids_preferences_and_room_options(tmp_path):
    project, task, lessons = seed_project(tmp_path, slot_count=3)
    with project:
        room, _ = project.save_entity("room", {"name": "实验室"}, project.revision)
        drafts = drafts_for(lessons)
        drafts[0]["planning_config"] = {
            "room_mode": "custom",
            "room_ids": [room["id"]],
            "preferred_times": [{"time_slot_id": "slot-1", "week_bits": "10" * 10, "penalty": 10}],
        }
        before = project.revision
        saved, result, revision = save_course_arrangement(project, task_data(task), drafts, before)
        assert revision == before + 1 and saved["weekly_slots"] == 2
        assert [item["id"] for item in result] == [item["id"] for item in lessons]
        xml, diagnostics = problem(project)
        node = xml.find(f"classes/class[@id='{lessons[0]['id']}']")
        assert [item.attrib for item in node.findall("time")] == [
            {
                "days": "1000000",
                "weeks": "10" * 10,
                "start": "1",
                "length": "1",
                "periodIndex": "1",
                "penalty": "10",
            }
        ]
        assert [item.get("id") for item in node.findall("room")] == [room["id"]]
        assert not diagnostics["errors"]
        # Reordering also preserves identity and increments the revision only once.
        _, reordered, _ = save_course_arrangement(
            project, task_data(saved), list(reversed(drafts)), revision
        )
        assert [item["id"] for item in reordered] == list(
            reversed([item["id"] for item in lessons])
        )


def test_forbidden_time_and_disabled_lessons_reach_local_solver(tmp_path):
    project, task, lessons = seed_project(tmp_path, slot_count=2)
    with project:
        drafts = drafts_for(lessons)
        drafts[0]["planning_config"] = {
            "preferred_times": [{"time_slot_id": "slot-0", "week_bits": "1" * 20, "penalty": -1}]
        }
        drafts[1]["enabled"] = False
        save_course_arrangement(project, task_data(task), drafts, project.revision)
        xml, _ = problem(project)
        assert len(xml.findall("classes/class")) == 1
        assert [item.get("start") for item in xml.findall("classes/class/time")] == ["1"]
        result = SchedulingService(project).run_round(time_budget_seconds=10, random_seed=0)
        assert result["status"] == "succeeded" and result["hard_violations"] == 0
        assert (
            project.connection.execute("SELECT start_slot FROM timetable_entries").fetchone()[0]
            == 1
        )


def test_no_allowed_time_returns_diagnostic_not_fake_candidate(tmp_path):
    project, task, lessons = seed_project(tmp_path, slot_count=1)
    with project:
        drafts = drafts_for(lessons)
        for item in drafts:
            item["planning_config"] = {
                "preferred_times": [
                    {"time_slot_id": "slot-0", "week_bits": "1" * 20, "penalty": -1}
                ]
            }
        save_course_arrangement(project, task_data(task), drafts, project.revision)
        xml, diagnostics = problem(project)
        assert not xml.findall("classes/class/time")
        assert any(item["code"] == "LESSON_HAS_NO_TIME_OPTION" for item in diagnostics["errors"])


def test_stale_foreign_duplicate_ids_and_invalid_times_are_atomic(tmp_path):
    project, task, lessons = seed_project(tmp_path)
    with project:
        before = project.revision
        with pytest.raises(RevisionConflictError):
            save_course_arrangement(project, task_data(task), drafts_for(lessons), before - 1)
        cases = []
        foreign = drafts_for(lessons)
        foreign[0]["id"] = "foreign"
        cases.append(foreign)
        duplicate = drafts_for(lessons)
        duplicate.append(duplicate[0])
        cases.append(duplicate)
        bad_slot = drafts_for(lessons)
        bad_slot[0]["planning_config"] = {
            "preferred_times": [{"time_slot_id": "missing", "week_bits": "1", "penalty": 0}]
        }
        cases.append(bad_slot)
        bad_duration = drafts_for(lessons)
        bad_duration[0]["duration_slots"] = 1.5
        cases.append(bad_duration)
        for drafts in cases:
            with pytest.raises(ProjectError):
                save_course_arrangement(project, task_data(task), drafts, before)
            assert project.revision == before
            assert project.list_entities("task_lesson") == lessons
        bad_task = {**task_data(task), "primary_teacher_id": "missing"}
        with pytest.raises(sqlite3.IntegrityError):
            save_course_arrangement(project, bad_task, drafts_for(lessons), before)
        assert (
            project.revision == before and project.get_entity("teaching_task", task["id"]) == task
        )


def test_deletion_cleans_availability_and_protects_constraints(tmp_path):
    project, task, lessons = seed_project(tmp_path)
    with project:
        project.save_entity(
            "availability_rule",
            {"entity_type": "lesson", "entity_id": lessons[0]["id"]},
            project.revision,
        )
        constraint, _ = project.save_entity(
            "constraint",
            {
                "name": "引用课次",
                "type": "SameDays",
                "parameters": {"lesson_ids": [lessons[0]["id"]]},
            },
            project.revision,
        )
        with pytest.raises(ProjectError, match="约束引用"):
            save_course_arrangement(
                project, task_data(task), drafts_for(lessons[1:]), project.revision
            )
        project.delete_entity("constraint", constraint["id"], project.revision)
        save_course_arrangement(project, task_data(task), drafts_for(lessons[1:]), project.revision)
        assert project.list_entities("availability_rule") == []
        assert project.get_entity("task_lesson", lessons[1]["id"])["lesson_index"] == 0


def test_teacher_number_migration_preserves_relations_and_backup(tmp_path):
    project, task, lessons = seed_project(tmp_path)
    workspace = project.workspace
    project_id, path, manifest_path = (
        project.project_info()["id"],
        project.database_path,
        project.manifest_path,
    )
    project.close()
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE teachers ADD COLUMN employee_no TEXT")
        connection.execute("UPDATE teachers SET employee_no = 'T001'")
        connection.execute("ALTER TABLE task_lessons DROP COLUMN planning_config")
        connection.execute("ALTER TABLE teaching_tasks DROP COLUMN planning_config")
        connection.execute("ALTER TABLE subjects DROP COLUMN default_duration_minutes")
        connection.execute("DROP TABLE ai_documents")
        connection.execute("UPDATE app_metadata SET value = '2' WHERE key = 'schema_version'")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with workspace.open_project(project_id) as migrated:
        assert "employee_no" not in {
            row["name"] for row in migrated.connection.execute("PRAGMA table_info(teachers)")
        }
        assert "employee_no" not in migrated.list_entities("teacher")[0]
        assert migrated.get_entity("teaching_task", task["id"])["primary_teacher_id"] == "teacher-1"
        assert (
            migrated.connection.execute(
                "SELECT COUNT(*) FROM backup_records WHERE reason = 'pre-migration'"
            ).fetchone()[0]
            == 1
        )
        assert migrated.integrity_check()["foreign_key_issues"] == []
        with pytest.raises(ProjectError, match="未知字段"):
            migrated.save_entity(
                "teacher", {"name": "新教师", "employee_no": "T002"}, migrated.revision
            )


def test_preference_overlap_forbidden_wins_and_default_is_all():
    config = parse_lesson_config(
        {
            "preferred_times": [
                {"time_slot_id": "a", "week_bits": "11", "penalty": 10},
                {"time_slot_id": "b", "week_bits": "10", "penalty": -1},
            ]
        }
    )
    assert preferred_options(config, "a", {"a", "b"}, "11") == []
    assert preferred_options(config, "a", {"a"}, "11") == [("11", 10)]
    assert preferred_options(parse_lesson_config({}), "x", {"x"}, "11") == [("11", 0)]


def test_lesson_ui_contracts_and_fullscreen_mask():
    root = Path(__file__).resolve().parents[1]
    view = (root / "apps/desktop/src/web-course-editor/CourseEditor.vue").read_text(encoding="utf-8")
    for text in ("新增课次", "复制课次", "删除课次", "选择期望时间", "课次教室", "课次期望上课时间", "新手指导", "不安排", "默认教室列表"):
        assert text in view
    assert "@click.self" not in view.replace('@click.self="skipGuide"', '')
    school = (root / "apps/desktop/src/components/SchoolDataView.vue").read_text(encoding="utf-8")
    assert "employee_no" not in school and "工号" not in school
    css = (root / "scripts/web-planning-ui-overrides.css").read_text(encoding="utf-8")
    mask = css.split(".web-planning.subject-editor-mask {", 1)[1].split("}", 1)[0]
    assert "max-width: none;" in mask and "inset: 0;" in mask and "box-sizing: border-box;" in mask
    assert (
        ".web-planning .table-column-filters > span { display: flex; align-items: center; min-height: 40px;"
        in css
    )
