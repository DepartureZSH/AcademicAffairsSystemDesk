from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from stt_desktop.storage import (
    ProjectError,
    ProjectLockedError,
    ProjectSchemaTooNewError,
    ProjectWorkspace,
    RevisionConflictError,
)


def test_create_project_builds_required_layout(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    project = workspace.create_project("第一学期排课")
    try:
        info = project.project_info()
        manifest = json.loads(project.manifest_path.read_text(encoding="utf-8"))

        assert info["name"] == "第一学期排课"
        assert manifest["project_id"] == info["id"]
        assert manifest["schema_version"] == 1
        assert manifest["revision"] == 0
        assert (project.project_directory / "attachments").is_dir()
        assert (project.project_directory / "artifacts" / "problem").is_dir()
        assert project.integrity_check() == {"integrity": "ok", "foreign_key_issues": []}
    finally:
        project.close()


def test_project_allows_only_one_writer(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    first = workspace.create_project("锁测试")
    project_id = first.project_info()["id"]
    try:
        with pytest.raises(ProjectLockedError):
            workspace.open_project(project_id)
    finally:
        first.close()

    reopened = workspace.open_project(project_id)
    reopened.close()


def test_stale_lock_file_does_not_block_reopen(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    project = workspace.create_project("崩溃恢复锁测试")
    project_id = project.project_info()["id"]
    lock_path = project.project_directory / ".stt.lock"
    project.close()

    assert lock_path.is_file()
    lock_path.write_text('{"pid":999999,"token":"stale"}', encoding="utf-8")

    reopened = workspace.open_project(project_id)
    reopened.close()


def test_crud_increments_revision_and_rejects_stale_write(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    with workspace.create_project("版本测试") as project:
        teacher, revision = project.save_entity(
            "teacher",
            {"name": "测试教师", "employee_no": "T-001", "department": "教务处"},
            expected_revision=0,
        )
        assert revision == 1
        assert project.revision == 1
        assert project.manifest["revision"] == 1
        assert project.get_entity("teacher", teacher["id"])["name"] == "测试教师"

        with pytest.raises(RevisionConflictError) as conflict:
            project.save_entity(
                "teacher", {"id": teacher["id"], "name": "旧页面覆盖"}, expected_revision=0
            )
        assert conflict.value.actual == 1
        assert project.get_entity("teacher", teacher["id"])["name"] == "测试教师"

        updated, revision = project.save_entity(
            "teacher", {"id": teacher["id"], "name": "新名称"}, expected_revision=1
        )
        assert revision == 2
        assert updated["name"] == "新名称"


def test_foreign_keys_prevent_invalid_business_data(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    with workspace.create_project("外键测试") as project:
        with pytest.raises(sqlite3.IntegrityError):
            project.save_entity(
                "course_plan",
                {
                    "homeroom_id": "missing-homeroom",
                    "subject_id": "missing-subject",
                    "weekly_slots": 5,
                },
                expected_revision=0,
            )
        assert project.revision == 0


def test_schema_too_new_is_rejected_before_database_open(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    project = workspace.create_project("未来版本")
    project_id = project.project_info()["id"]
    manifest_path = project.manifest_path
    project.close()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ProjectSchemaTooNewError):
        workspace.open_project(project_id)


def test_invalid_project_id_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")

    with pytest.raises(ProjectError):
        workspace.open_project("../../outside")


def test_unknown_fields_and_entity_types_are_rejected(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    with workspace.create_project("字段测试") as project:
        with pytest.raises(ProjectError, match="未知字段"):
            project.save_entity("teacher", {"name": "A", "phone": "not-stored"}, 0)
        with pytest.raises(ProjectError, match="不支持的实体类型"):
            project.list_entities("organization")


def test_bulk_import_is_one_revision_and_rolls_back_as_a_unit(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    with workspace.create_project("批量导入") as project:
        counts, revision = project.bulk_insert_entities(
            {
                "teacher": [{"id": "teacher-1", "name": "教师一"}],
                "subject": [{"id": "subject-1", "name": "数学"}],
                "homeroom": [{"id": "class-1", "name": "一年级一班"}],
                "course_plan": [
                    {
                        "id": "plan-1",
                        "homeroom_id": "class-1",
                        "subject_id": "subject-1",
                        "weekly_slots": 5,
                    }
                ],
            },
            expected_revision=0,
        )
        assert counts == {"teacher": 1, "subject": 1, "homeroom": 1, "course_plan": 1}
        assert revision == 1
        assert project.revision == 1

        with pytest.raises(sqlite3.IntegrityError):
            project.bulk_insert_entities(
                {
                    "teacher": [{"id": "teacher-2", "name": "教师二"}],
                    "course_plan": [
                        {
                            "id": "bad-plan",
                            "homeroom_id": "missing",
                            "subject_id": "subject-1",
                            "weekly_slots": 1,
                        }
                    ],
                },
                expected_revision=1,
            )
        assert project.get_entity("teacher", "teacher-2") is None
        assert project.revision == 1


def test_teaching_task_and_lessons_are_saved_as_one_revision(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    with workspace.create_project("教学任务") as project:
        _, revision = project.bulk_insert_entities(
            {
                "teacher": [{"id": "teacher-1", "name": "教师一"}],
                "subject": [{"id": "subject-1", "name": "数学"}],
                "homeroom": [{"id": "class-1", "name": "一班"}],
            },
            expected_revision=0,
        )
        task, lessons, revision = project.save_teaching_task_bundle(
            {
                "homeroom_id": "class-1",
                "subject_id": "subject-1",
                "primary_teacher_id": "teacher-1",
                "weekly_slots": 5,
                "duration_slots": 2,
                "status": "active",
            },
            expected_revision=revision,
        )
        assert revision == 2
        assert [lesson["duration_slots"] for lesson in lessons] == [2, 2, 1]

        task, lessons, revision = project.save_teaching_task_bundle(
            {"id": task["id"], "weekly_slots": 4, "duration_slots": 2},
            expected_revision=revision,
        )
        assert revision == 3
        assert [lesson["duration_slots"] for lesson in lessons] == [2, 2]
        assert len(project.list_entities("task_lesson")) == 2


def test_constraint_parameters_require_json_object(tmp_path: Path) -> None:
    workspace = ProjectWorkspace(tmp_path / "workspace")
    with workspace.create_project("约束 JSON") as project:
        with pytest.raises(ProjectError, match="有效 JSON"):
            project.save_entity(
                "constraint",
                {"type": "spacing", "name": "间隔", "parameters": "{bad"},
                0,
            )
        with pytest.raises(ProjectError, match="JSON 对象"):
            project.save_entity(
                "constraint",
                {"type": "spacing", "name": "间隔", "parameters": "[]"},
                0,
            )
