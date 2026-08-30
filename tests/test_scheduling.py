from __future__ import annotations

import json
from pathlib import Path

from stt_desktop.scheduling import SchedulingService
from stt_desktop.storage import ProjectWorkspace


def seed_project(tmp_path: Path, *, slot_count: int = 2):
    workspace = ProjectWorkspace(tmp_path / "workspace")
    project = workspace.create_project("本地排课测试")
    entities: dict[str, list[dict]] = {
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
            for index in range(slot_count)
        ],
        "teacher": [{"id": "teacher-1", "name": "教师一"}],
        "subject": [{"id": "subject-1", "name": "数学"}],
        "homeroom": [
            {"id": "homeroom-1", "term_id": "term-1", "name": "一班"}
        ],
    }
    _, revision = project.bulk_insert_entities(entities, expected_revision=0)
    task, lessons, _ = project.save_teaching_task_bundle(
        {
            "id": "task-1",
            "term_id": "term-1",
            "homeroom_id": "homeroom-1",
            "subject_id": "subject-1",
            "primary_teacher_id": "teacher-1",
            "weekly_slots": 2,
            "duration_slots": 1,
            "status": "active",
            "week_bits": "11111111111111111111",
            "day_bits": "11111",
        },
        expected_revision=revision,
    )
    return project, task, lessons


def test_local_round_persists_snapshot_candidate_and_warm_start(tmp_path: Path) -> None:
    project, _, lessons = seed_project(tmp_path, slot_count=2)
    try:
        service = SchedulingService(project)
        first = service.run_round(time_budget_seconds=10, random_seed=7, name="验证会话")

        assert first["status"] == "succeeded"
        assert first["candidate_id"]
        assert first["hard_violations"] == 0
        assert project.connection.execute("SELECT COUNT(*) FROM data_snapshots").fetchone()[0] == 1
        assert project.connection.execute("SELECT COUNT(*) FROM timetable_entries").fetchone()[0] == len(lessons)
        candidate = service.list_candidates()[0]
        assert candidate["entry_count"] == len(lessons)
        solution_path = project.project_directory / candidate["diagnostics"]["solutionPath"]
        assert solution_path.is_file()
        assert (project.project_directory / f"artifacts/problem/{first['id']}.xml").is_file()

        second = service.run_round(
            time_budget_seconds=10,
            random_seed=8,
            session_id=first["session_id"],
            parent_candidate_id=first["candidate_id"],
        )
        assert second["status"] == "succeeded"
        second_candidate = service.list_candidates()[0]
        assert second_candidate["parent_candidate_id"] == first["candidate_id"]
        assert len(service.list_rounds(first["session_id"])) == 2
    finally:
        project.close()


def test_hard_infeasible_round_has_diagnostics_but_no_candidate(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=1)
    try:
        result = SchedulingService(project).run_round(time_budget_seconds=10)

        assert result["status"] == "infeasible"
        assert result["candidate_id"] is None
        assert project.connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0
        diagnostic_event = next(
            item for item in result["events"] if item["event_type"] == "infeasible_diagnostics"
        )
        assert diagnostic_event["payload"]["solver"]["unassigned_count"] == 1
        assert diagnostic_event["payload"]["conflicts"]
    finally:
        project.close()


def test_snapshot_is_canonical_and_contains_no_remote_service_data(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        result = SchedulingService(project).run_round(time_budget_seconds=10)
        snapshot = project.connection.execute(
            "SELECT * FROM data_snapshots WHERE id = ?", (result["snapshot_id"],)
        ).fetchone()
        payload = json.loads(
            (project.project_directory / snapshot["payload_path"]).read_text(encoding="utf-8")
        )
        assert payload["project"]["name"] == "本地排课测试"
        assert "auth" not in payload["tables"]
        assert "license" not in payload["tables"]
        assert len(snapshot["input_hash"]) == 64
    finally:
        project.close()


def test_double_period_uses_adjacent_slots(tmp_path: Path) -> None:
    project, task, _ = seed_project(tmp_path, slot_count=3)
    try:
        _, lessons, revision = project.save_teaching_task_bundle(
            {"id": task["id"], "weekly_slots": 2, "duration_slots": 2},
            expected_revision=project.revision,
        )
        assert len(lessons) == 1
        result = SchedulingService(project).run_round(time_budget_seconds=10)
        assert result["status"] == "succeeded"
        entry = project.connection.execute(
            "SELECT * FROM timetable_entries WHERE candidate_id = ?",
            (result["candidate_id"],),
        ).fetchone()
        assert entry["duration_slots"] == 2
        assert entry["start_slot"] in {0, 1}
        assert revision == project.revision
    finally:
        project.close()


def test_hard_daily_limit_rejects_candidate_before_persistence(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        project.save_entity(
            "constraint",
            {
                "type": "max_daily_lessons",
                "name": "每天至多一节",
                "severity": "hard",
                "weight": 100,
                "parameters": {"max": 1},
            },
            project.revision,
        )
        result = SchedulingService(project).run_round(time_budget_seconds=10)
        assert result["status"] == "infeasible"
        assert result["candidate_id"] is None
        event = next(
            item for item in result["events"] if item["event_type"] == "infeasible_diagnostics"
        )
        assert event["payload"]["conflicts"][0]["code"] == "MAX_DAILY_LESSONS"
    finally:
        project.close()


def test_room_availability_removes_only_blocked_room_time_pair(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=3)
    try:
        room, _ = project.save_entity(
            "room", {"id": "room-1", "name": "101 教室"}, project.revision
        )
        project.save_entity(
            "homeroom",
            {"id": "homeroom-1", "default_room_id": room["id"]},
            project.revision,
        )
        project.save_entity(
            "availability_rule",
            {
                "entity_type": "room",
                "entity_id": room["id"],
                "bell_schedule_id": "schedule-1",
                "time_slot_id": "slot-0",
                "required": 0,
                "penalty": 0,
                "reason": "首节不可用",
            },
            project.revision,
        )
        result = SchedulingService(project).run_round(time_budget_seconds=10)
        assert result["status"] == "succeeded"
        entries = project.connection.execute(
            "SELECT * FROM timetable_entries WHERE candidate_id = ? ORDER BY start_slot",
            (result["candidate_id"],),
        ).fetchall()
        assert {entry["room_id"] for entry in entries} == {"room-1"}
        assert all(entry["start_slot"] != 0 for entry in entries)
    finally:
        project.close()
