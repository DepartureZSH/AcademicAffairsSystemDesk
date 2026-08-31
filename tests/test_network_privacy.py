from __future__ import annotations

import socket
from pathlib import Path

from stt_desktop.backups import BackupService
from stt_desktop.project_archives import ProjectArchiveService
from stt_desktop.scheduling import SchedulingService
from stt_desktop.storage import ProjectWorkspace
from stt_desktop.transfers import ExportService


def test_business_workflow_uses_no_network(monkeypatch, tmp_path: Path) -> None:
    attempted: list[str] = []

    def deny_network(*args, **kwargs):
        target = args[1] if len(args) > 1 else kwargs
        attempted.append(repr(target))
        raise AssertionError(f"教务业务流程尝试访问网络: {target!r}")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(socket.socket, "sendto", deny_network)

    workspace = ProjectWorkspace(tmp_path / "workspace")
    project = workspace.create_project("完全离线排课验收")
    try:
        _, revision = project.bulk_insert_entities(
            {
                "term": [
                    {
                        "id": "term-1",
                        "name": "第一学期",
                        "week_count": 20,
                        "day_count": 5,
                        "active": 1,
                    }
                ],
                "bell_schedule": [
                    {
                        "id": "schedule-1",
                        "term_id": "term-1",
                        "name": "默认作息",
                        "day_count": 5,
                        "slot_duration_minutes": 40,
                        "is_default": 1,
                    }
                ],
                "time_slot": [
                    {
                        "id": f"slot-{index}",
                        "bell_schedule_id": "schedule-1",
                        "weekday": 1,
                        "period_index": index,
                        "label": f"第 {index + 1} 节",
                        "start_slot": index,
                        "length_slots": 1,
                        "start_time_minutes": 480 + index * 50,
                        "end_time_minutes": 520 + index * 50,
                    }
                    for index in range(2)
                ],
                "teacher": [{"id": "teacher-1", "name": "离线教师"}],
                "subject": [{"id": "subject-1", "name": "本地课程"}],
                "homeroom": [
                    {"id": "homeroom-1", "term_id": "term-1", "name": "本地班级"}
                ],
            },
            expected_revision=0,
        )
        project.save_teaching_task_bundle(
            {
                "term_id": "term-1",
                "homeroom_id": "homeroom-1",
                "subject_id": "subject-1",
                "primary_teacher_id": "teacher-1",
                "weekly_slots": 2,
                "duration_slots": 1,
                "week_bits": "11111111111111111111",
                "day_bits": "11111",
            },
            expected_revision=revision,
        )

        round_result = SchedulingService(project).run_round(
            time_budget_seconds=10,
            random_seed=2026,
        )
        assert round_result["status"] == "succeeded"
        exported = ExportService(project).export_candidate(
            candidate_id=round_result["candidate_id"],
            export_type="xlsx",
        )
        assert exported["status"] == "succeeded"
        assert len(exported["sha256"]) == 64
        assert (project.project_directory / exported["relativePath"]).is_file()

        backup_path = tmp_path / "离线恢复.sttbackup"
        backup = BackupService(project, workspace).create_backup(
            reason="network-privacy-test",
            destination_path=str(backup_path),
        )
        assert backup["verified"]
        restored = BackupService.restore_backup(
            workspace,
            backup_path,
            restored_name="离线恢复副本",
        )
        assert restored["projectId"] != project.project_info()["id"]

        package_path = tmp_path / "离线迁移.sttproj"
        package = ProjectArchiveService(project, workspace).export_project(
            str(package_path)
        )
        assert package["verified"]
        imported = ProjectArchiveService.import_project(
            workspace,
            package_path,
            imported_name="离线迁移副本",
        )
        assert imported["projectId"] != project.project_info()["id"]
    finally:
        project.close()

    assert attempted == []
