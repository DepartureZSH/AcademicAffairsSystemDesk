from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from stt_desktop.backups import BackupService
from stt_desktop.scheduling import SchedulingService
from stt_desktop.storage import ProjectError, ProjectWorkspace


def backup_fixture(tmp_path: Path):
    workspace = ProjectWorkspace(tmp_path / "workspace")
    project = workspace.create_project("备份源项目")
    _, revision = project.bulk_insert_entities(
        {
            "term": [{"id": "term-1", "name": "第一学期"}],
            "bell_schedule": [
                {"id": "schedule-1", "term_id": "term-1", "name": "默认", "is_default": 1}
            ],
            "time_slot": [
                {
                    "id": "slot-1",
                    "bell_schedule_id": "schedule-1",
                    "weekday": 1,
                    "period_index": 0,
                    "label": "第一节",
                    "start_slot": 0,
                    "length_slots": 1,
                    "start_time_minutes": 480,
                    "end_time_minutes": 520,
                }
            ],
            "teacher": [{"id": "teacher-1", "name": "教师一"}],
            "subject": [{"id": "subject-1", "name": "数学"}],
            "homeroom": [{"id": "homeroom-1", "term_id": "term-1", "name": "一班"}],
        },
        0,
    )
    project.save_teaching_task_bundle(
        {
            "term_id": "term-1",
            "homeroom_id": "homeroom-1",
            "subject_id": "subject-1",
            "primary_teacher_id": "teacher-1",
            "weekly_slots": 1,
            "duration_slots": 1,
        },
        revision,
    )
    SchedulingService(project).run_round(time_budget_seconds=10)
    return workspace, project


def test_verified_backup_restores_to_new_project_with_same_business_data(tmp_path: Path) -> None:
    workspace, project = backup_fixture(tmp_path)
    try:
        service = BackupService(project, workspace)
        destination = tmp_path / "中文项目备份.sttbackup"
        backup = service.create_backup(
            reason="manual",
            retained=True,
            destination_path=str(destination),
        )
        assert backup["verified"]
        assert destination.is_file()
        assert service.verify_record(backup["id"])["valid"]
        source_project_id = project.project_info()["id"]
        source_counts = {
            "teachers": project.connection.execute("SELECT COUNT(*) FROM teachers").fetchone()[0],
            "candidates": project.connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0],
            "entries": project.connection.execute("SELECT COUNT(*) FROM timetable_entries").fetchone()[0],
        }
        restored_info = BackupService.restore_backup(
            workspace, destination, restored_name="恢复副本"
        )
        assert restored_info["projectId"] != source_project_id

        restored = workspace.open_project(restored_info["projectId"])
        try:
            assert restored.project_info()["name"] == "恢复副本"
            assert restored.revision == project.revision
            assert {
                "teachers": restored.connection.execute("SELECT COUNT(*) FROM teachers").fetchone()[0],
                "candidates": restored.connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0],
                "entries": restored.connection.execute("SELECT COUNT(*) FROM timetable_entries").fetchone()[0],
            } == source_counts
            assert restored.integrity_check() == {"integrity": "ok", "foreign_key_issues": []}
        finally:
            restored.close()
        assert project.project_info()["id"] == source_project_id
    finally:
        project.close()


def test_backup_rejects_path_traversal_and_checksum_tampering(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.sttbackup"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../outside.txt", "bad")
    with pytest.raises(ProjectError, match="路径穿越"):
        BackupService.verify_archive(traversal)

    workspace, project = backup_fixture(tmp_path / "valid")
    try:
        service = BackupService(project, workspace)
        backup = service.create_backup(reason="manual")
        source = workspace.root / backup["relativePath"]
        tampered = tmp_path / "tampered.sttbackup"
        with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(tampered, "w") as changed:
            for info in original.infolist():
                content = original.read(info.filename)
                if info.filename == "project/manifest.json":
                    content += b" "
                changed.writestr(info, content)
        with pytest.raises(ProjectError, match="大小|哈希"):
            BackupService.verify_archive(tampered)
    finally:
        project.close()


def test_daily_backup_is_once_per_day_and_automatic_retention_is_ten(tmp_path: Path) -> None:
    workspace, project = backup_fixture(tmp_path)
    try:
        service = BackupService(project, workspace)
        first = service.create_daily_backup_if_needed()
        assert first is not None
        assert service.create_daily_backup_if_needed() is None
        retained = service.create_backup(reason="manual", retained=True)
        for _ in range(11):
            service.create_backup(reason="pre-import")
        automatic = [
            item for item in service.list_backups() if item["reason"] in {"daily", "pre-import"}
        ]
        assert len(automatic) == 10
        assert any(item["id"] == retained["id"] and item["exists"] for item in service.list_backups())
        project.connection.execute(
            "UPDATE backup_records SET retained = 1 WHERE id = ?", (automatic[-1]["id"],)
        )
        service.set_retained(automatic[-1]["id"], False)
        assert not next(item for item in service.list_backups() if item["id"] == automatic[-1]["id"])["retained"]
    finally:
        project.close()
