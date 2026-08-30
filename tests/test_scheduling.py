from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from stt_desktop.scheduling import (
    ManualConflictError,
    SchedulingJobManager,
    SchedulingService,
    TimetableService,
)
from stt_desktop.storage import ProjectError, ProjectWorkspace


def slow_solver_worker(_: str, __: str, ___: str, ____: str) -> None:
    time.sleep(30)


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
        assert (
            first["candidate_diagnostics"]["solver"]["fast_path"]
            == "complete_zero_penalty_greedy"
        )
        assert project.connection.execute("SELECT COUNT(*) FROM data_snapshots").fetchone()[0] == 1
        assert project.connection.execute("SELECT COUNT(*) FROM timetable_entries").fetchone()[0] == len(lessons)
        candidate = service.list_candidates()[0]
        assert candidate["entry_count"] == len(lessons)
        assert candidate["metrics"]["total_score"] == candidate["total_score"]
        assert candidate["metrics"]["time_penalty"] >= 0
        assert candidate["metrics"]["room_penalty"] >= 0
        assert candidate["metrics"]["distribution_penalty"] >= 0
        assert (
            candidate["metrics"]["time_penalty"]
            + candidate["metrics"]["room_penalty"]
            + candidate["metrics"]["distribution_penalty"]
            == candidate["total_score"]
        )
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


def test_preflight_is_read_only_and_reports_project_summary(tmp_path: Path) -> None:
    project, _, lessons = seed_project(tmp_path, slot_count=2)
    try:
        revision = project.revision
        result = SchedulingService(project).validate_current_project()

        assert result["ready"] is True
        assert result["revision"] == revision
        assert result["summary"]["activeTaskCount"] == 1
        assert result["summary"]["activeLessonCount"] == len(lessons)
        assert result["summary"]["optionCount"] == 4
        assert project.revision == revision
        assert project.connection.execute("SELECT count(*) FROM data_snapshots").fetchone()[0] == 0
        assert project.connection.execute("SELECT count(*) FROM scheduling_rounds").fetchone()[0] == 0
    finally:
        project.close()


def test_preflight_reports_missing_teacher_and_course_plan_slot_mismatch(
    tmp_path: Path,
) -> None:
    project, task, _ = seed_project(tmp_path, slot_count=2)
    try:
        plan, _ = project.save_entity(
            "course_plan",
            {
                "term_id": "term-1",
                "homeroom_id": "homeroom-1",
                "subject_id": "subject-1",
                "weekly_slots": 3,
                "duration_slots": 1,
                "week_bits": "1" * 20,
                "day_bits": "11111",
            },
            project.revision,
        )
        project.save_entity(
            "teaching_task",
            {
                "id": task["id"],
                "course_plan_id": plan["id"],
                "primary_teacher_id": None,
            },
            project.revision,
        )

        result = SchedulingService(project).validate_current_project()
        codes = {item["code"] for item in result["errors"]}
        assert result["ready"] is False
        assert "TASK_MISSING_PRIMARY_TEACHER" in codes
        assert "COURSE_PLAN_TASK_SLOTS_MISMATCH" in codes
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


def test_homeroom_timetable_assignment_selects_its_own_schedule(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        project.save_entity(
            "bell_schedule",
            {
                "id": "schedule-special",
                "name": "班级特殊作息",
                "day_count": 5,
                "slot_duration_minutes": 40,
                "is_default": 0,
            },
            project.revision,
        )
        for index in range(2):
            project.save_entity(
                "time_slot",
                {
                    "id": f"special-slot-{index}",
                    "bell_schedule_id": "schedule-special",
                    "weekday": 2,
                    "period_index": index,
                    "label": f"特殊第 {index + 1} 节",
                    "start_slot": 10 + index,
                    "length_slots": 1,
                    "start_time_minutes": 600 + index * 50,
                    "end_time_minutes": 640 + index * 50,
                },
                project.revision,
            )
        project.save_entity(
            "timetable_template_assignment",
            {
                "entity_type": "homeroom",
                "entity_id": "homeroom-1",
                "bell_schedule_id": "schedule-special",
            },
            project.revision,
        )

        result = SchedulingService(project).run_round(time_budget_seconds=10)

        assert result["status"] == "succeeded"
        entries = project.connection.execute(
            "SELECT weekday, start_slot FROM timetable_entries WHERE candidate_id = ?",
            (result["candidate_id"],),
        ).fetchall()
        assert {item["weekday"] for item in entries} == {2}
        assert {item["start_slot"] for item in entries} == {10, 11}
        assert result["candidate_diagnostics"]["compile"]["assigned_schedule_count"] == 2
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


def test_hard_daily_limit_is_enforced_during_search_instead_of_false_infeasible(
    tmp_path: Path,
) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        for index in range(2):
            project.save_entity(
                "time_slot",
                {
                    "id": f"day-2-slot-{index}",
                    "bell_schedule_id": "schedule-1",
                    "weekday": 2,
                    "period_index": index,
                    "label": f"周二第 {index + 1} 节",
                    "start_slot": index,
                    "length_slots": 1,
                    "start_time_minutes": 480 + index * 50,
                    "end_time_minutes": 520 + index * 50,
                },
                project.revision,
            )
        project.save_entity(
            "constraint",
            {
                "type": "max_daily_lessons",
                "name": "每天至多一课时",
                "severity": "hard",
                "weight": 100,
                "parameters": {"max": 1},
            },
            project.revision,
        )

        result = SchedulingService(project).run_round(time_budget_seconds=10)

        assert result["status"] == "succeeded"
        entries = project.connection.execute(
            "SELECT weekday FROM timetable_entries WHERE candidate_id = ?",
            (result["candidate_id"],),
        ).fetchall()
        assert {item["weekday"] for item in entries} == {1, 2}
        assert result["candidate_diagnostics"]["compile"]["compiled_limit_count"] == 2
    finally:
        project.close()


def test_hard_consecutive_limit_is_enforced_during_search(tmp_path: Path) -> None:
    project, task, _ = seed_project(tmp_path, slot_count=3)
    try:
        project.save_teaching_task_bundle(
            {"id": task["id"], "weekly_slots": 3, "duration_slots": 1},
            expected_revision=project.revision,
        )
        project.save_entity(
            "time_slot",
            {
                "id": "day-2-slot-0",
                "bell_schedule_id": "schedule-1",
                "weekday": 2,
                "period_index": 0,
                "label": "周二第一节",
                "start_slot": 0,
                "length_slots": 1,
                "start_time_minutes": 480,
                "end_time_minutes": 520,
            },
            project.revision,
        )
        project.save_entity(
            "constraint",
            {
                "type": "consecutive_limit",
                "name": "连续授课不超过两节",
                "severity": "hard",
                "weight": 100,
                "parameters": {"maxConsecutive": 2},
            },
            project.revision,
        )

        result = SchedulingService(project).run_round(time_budget_seconds=10)

        assert result["status"] == "succeeded"
        entries = project.connection.execute(
            "SELECT weekday, start_slot, duration_slots FROM timetable_entries WHERE candidate_id = ?",
            (result["candidate_id"],),
        ).fetchall()
        occupied_by_day: dict[int, set[int]] = {}
        for item in entries:
            occupied_by_day.setdefault(item["weekday"], set()).update(
                range(item["start_slot"], item["start_slot"] + item["duration_slots"])
            )
        assert all(
            not {0, 1, 2}.issubset(occupied)
            for occupied in occupied_by_day.values()
        )
    finally:
        project.close()


def test_soft_daily_limit_is_part_of_quality_objective_without_double_counting(
    tmp_path: Path,
) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        for index in range(2):
            project.save_entity(
                "time_slot",
                {
                    "id": f"soft-day-2-slot-{index}",
                    "bell_schedule_id": "schedule-1",
                    "weekday": 2,
                    "period_index": index,
                    "label": f"周二第 {index + 1} 节",
                    "start_slot": index,
                    "length_slots": 1,
                    "start_time_minutes": 480 + index * 50,
                    "end_time_minutes": 520 + index * 50,
                },
                project.revision,
            )
        project.save_entity(
            "constraint",
            {
                "type": "max_daily_lessons",
                "name": "尽量每天至多一课时",
                "severity": "soft",
                "weight": 25,
                "parameters": {"max": 1},
            },
            project.revision,
        )

        result = SchedulingService(project).run_round(time_budget_seconds=10)

        assert result["status"] == "succeeded"
        assert result["total_score"] == 0
        assert result["candidate_diagnostics"]["solver"]["fast_path"] is None
        candidate = SchedulingService(project).list_candidates()[0]
        assert candidate["metrics"]["distribution_penalty"] == 0
        assert candidate["metrics"]["total_score"] == 0
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


def test_positive_penalty_does_not_use_zero_lower_bound_fast_path(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        project.save_entity(
            "availability_rule",
            {
                "entity_type": "teacher",
                "entity_id": "teacher-1",
                "bell_schedule_id": "schedule-1",
                "required": 0,
                "penalty": 5,
                "reason": "所有时段均有软罚分",
            },
            project.revision,
        )
        result = SchedulingService(project).run_round(time_budget_seconds=10)
        assert result["status"] == "succeeded"
        solver = result["candidate_diagnostics"]["solver"]
        assert solver["fast_path"] is None
        assert result["total_score"] == 10
        assert solver["model_build_ms"] > 0
    finally:
        project.close()


def test_soft_preferred_period_uses_configured_weight(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        project.save_entity(
            "constraint",
            {
                "type": "preferred_periods",
                "name": "优先第二节",
                "severity": "soft",
                "weight": 7,
                "parameters": {"periods": [1]},
            },
            project.revision,
        )

        result = SchedulingService(project).run_round(time_budget_seconds=10)

        assert result["status"] == "succeeded"
        assert result["total_score"] == 7
        assert result["candidate_diagnostics"]["solver"]["fast_path"] is None
        candidate = SchedulingService(project).list_candidates()[0]
        assert candidate["metrics"]["time_penalty"] == 7
    finally:
        project.close()


def test_hard_preferred_period_removes_nonpreferred_options(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        project.save_entity(
            "time_slot",
            {
                "id": "day-2-preferred-slot",
                "bell_schedule_id": "schedule-1",
                "weekday": 2,
                "period_index": 1,
                "label": "周二第二节",
                "start_slot": 1,
                "length_slots": 1,
                "start_time_minutes": 530,
                "end_time_minutes": 570,
            },
            project.revision,
        )
        project.save_entity(
            "constraint",
            {
                "type": "preferred_periods",
                "name": "只能第二节",
                "severity": "hard",
                "weight": 100,
                "parameters": {"periods": [1]},
            },
            project.revision,
        )

        result = SchedulingService(project).run_round(time_budget_seconds=10)

        assert result["status"] == "succeeded"
        entries = project.connection.execute(
            "SELECT weekday, start_slot FROM timetable_entries WHERE candidate_id = ?",
            (result["candidate_id"],),
        ).fetchall()
        assert {item["weekday"] for item in entries} == {1, 2}
        assert {item["start_slot"] for item in entries} == {1}
        assert result["total_score"] == 0
    finally:
        project.close()


def test_manual_move_previews_conflict_and_creates_immutable_child(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=3)
    try:
        first = SchedulingService(project).run_round(time_budget_seconds=10)
        timetable = TimetableService(project)
        before = timetable.list_entries(first["candidate_id"])
        assert len(before["items"]) == 2
        moving, blocker = before["items"]

        conflict = timetable.validate_move(
            candidate_id=first["candidate_id"],
            task_lesson_id=moving["task_lesson_id"],
            weekday=blocker["weekday"],
            start_slot=blocker["start_slot"],
            room_id=moving["room_id"],
        )
        assert not conflict["valid"]
        assert any(item["code"].startswith("HARD_") for item in conflict["conflicts"])
        with pytest.raises(ManualConflictError):
            timetable.fork_with_move(
                candidate_id=first["candidate_id"],
                task_lesson_id=moving["task_lesson_id"],
                weekday=blocker["weekday"],
                start_slot=blocker["start_slot"],
                room_id=moving["room_id"],
            )

        free_start = next(value for value in range(3) if value not in {item["start_slot"] for item in before["items"]})
        preview = timetable.validate_move(
            candidate_id=first["candidate_id"],
            task_lesson_id=moving["task_lesson_id"],
            weekday=1,
            start_slot=free_start,
            room_id=moving["room_id"],
        )
        assert preview["valid"]
        child_round = timetable.fork_with_move(
            candidate_id=first["candidate_id"],
            task_lesson_id=moving["task_lesson_id"],
            weekday=1,
            start_slot=free_start,
            room_id=moving["room_id"],
            name="手工调整一",
        )
        assert child_round["status"] == "succeeded"
        child = SchedulingService(project).list_candidates()[0]
        assert child["parent_candidate_id"] == first["candidate_id"]
        assert child["name"] == "手工调整一"
        assert timetable.list_entries(first["candidate_id"])["items"] == before["items"]
        moved = timetable.list_entries(child["id"])["items"]
        assert next(item for item in moved if item["task_lesson_id"] == moving["task_lesson_id"])["start_slot"] == free_start
    finally:
        project.close()


def test_timetable_marks_candidate_as_based_on_old_data(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        result = SchedulingService(project).run_round(time_budget_seconds=10)
        service = TimetableService(project)
        assert not service.list_entries(result["candidate_id"])["basedOnOldData"]
        project.save_entity("teacher", {"name": "新增教师"}, project.revision)
        assert service.list_entries(result["candidate_id"])["basedOnOldData"]
    finally:
        project.close()


def test_isolated_solver_process_completes_without_blocking_status_reads(
    tmp_path: Path,
) -> None:
    project, _, lessons = seed_project(tmp_path, slot_count=2)

    async def scenario() -> None:
        manager = SchedulingJobManager()
        started = await manager.start_round(
            project,
            time_budget_seconds=10,
            random_seed=11,
            session_id=None,
            parent_candidate_id=None,
            name="异步进程",
        )
        assert started["status"] == "solving"
        assert manager.has_active_job()
        # A status read succeeds while OR-Tools is owned by the child process.
        assert SchedulingService(project).get_round(started["id"])["status"] == "solving"
        for _ in range(200):
            current = SchedulingService(project).get_round(started["id"])
            if current["status"] not in {"queued", "preparing", "solving", "validating"}:
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError("isolated solver did not finish")
        assert current["status"] == "succeeded"
        assert current["candidate_id"]
        assert (
            project.connection.execute(
                "SELECT COUNT(*) FROM timetable_entries WHERE candidate_id = ?",
                (current["candidate_id"],),
            ).fetchone()[0]
            == len(lessons)
        )
        await manager.shutdown()

    try:
        asyncio.run(scenario())
    finally:
        project.close()


def test_cancelling_isolated_solver_keeps_half_result_invisible(tmp_path: Path) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)

    async def scenario() -> None:
        manager = SchedulingJobManager(worker_target=slow_solver_worker)
        started = await manager.start_round(
            project,
            time_budget_seconds=10,
            random_seed=12,
            session_id=None,
            parent_candidate_id=None,
            name="取消进程",
        )
        cancelled = await manager.cancel_round(started["id"])
        assert cancelled["status"] == "cancelled"
        assert cancelled["stop_reason"] == "user_cancelled"
        assert project.connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0
        await manager.shutdown()

    try:
        asyncio.run(scenario())
    finally:
        project.close()


def test_restart_marks_interrupted_round_recoverable_and_rejects_late_result(
    tmp_path: Path,
) -> None:
    project, _, _ = seed_project(tmp_path, slot_count=2)
    try:
        service = SchedulingService(project)
        prepared = service.prepare_round(time_budget_seconds=10, name="中断轮次")
        assert prepared["round"]["status"] == "solving"
        assert service.recover_interrupted_rounds() == 1
        recovered = service.get_round(prepared["roundId"])
        assert recovered["status"] == "failed_recoverable"
        assert recovered["error_code"] == "INTERRUPTED_ON_RESTART"
        with pytest.raises(ProjectError, match="已结束"):
            service.complete_round(
                prepared["roundId"],
                {"complete_schedule_feasible": False},
                snapshot=prepared["snapshot"],
                compile_diagnostics=prepared["compileDiagnostics"],
            )
        assert project.connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 0
    finally:
        project.close()
