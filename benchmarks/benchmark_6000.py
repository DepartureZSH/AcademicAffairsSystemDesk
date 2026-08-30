from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from stt_desktop.scheduler_engine import run_cp_sat_v1
from stt_desktop.scheduling import SchedulingService
from stt_desktop.storage import ProjectWorkspace


TEACHER_COUNT = 250
HOMEROOM_COUNT = 150
LESSONS_PER_HOMEROOM = 40
LESSON_COUNT = HOMEROOM_COUNT * LESSONS_PER_HOMEROOM


def create_scale_project(workspace: ProjectWorkspace):
    project = workspace.create_project("确定性 6000 课次基准")
    term_id = "term-scale"
    schedule_id = "schedule-scale"
    subject_id = "subject-scale"
    batches: dict[str, list[dict]] = {
        "term": [
            {
                "id": term_id,
                "name": "规模测试学期",
                "week_count": 20,
                "day_count": 5,
                "active": 1,
            }
        ],
        "bell_schedule": [
            {
                "id": schedule_id,
                "term_id": term_id,
                "name": "五天八节",
                "day_count": 5,
                "slot_duration_minutes": 40,
                "is_default": 1,
            }
        ],
        "time_slot": [],
        "teacher": [],
        "subject": [{"id": subject_id, "name": "综合课程"}],
        "homeroom": [],
        "teaching_task": [],
        "task_lesson": [],
    }
    for weekday in range(1, 6):
        for period in range(8):
            batches["time_slot"].append(
                {
                    "id": f"slot-{weekday}-{period}",
                    "bell_schedule_id": schedule_id,
                    "weekday": weekday,
                    "period_index": period,
                    "label": f"星期{weekday}第{period + 1}节",
                    "start_slot": (weekday - 1) * 16 + period,
                    "length_slots": 1,
                    "start_time_minutes": 480 + period * 50,
                    "end_time_minutes": 520 + period * 50,
                    "active": 1,
                }
            )
    for index in range(TEACHER_COUNT):
        batches["teacher"].append(
            {
                "id": f"teacher-{index:03d}",
                "employee_no": f"T{index:04d}",
                "name": f"教师{index:03d}",
                "status": "active",
            }
        )
    for homeroom_index in range(HOMEROOM_COUNT):
        homeroom_id = f"homeroom-{homeroom_index:03d}"
        teacher_id = f"teacher-{homeroom_index:03d}"
        task_id = f"task-{homeroom_index:03d}"
        batches["homeroom"].append(
            {
                "id": homeroom_id,
                "term_id": term_id,
                "name": f"班级{homeroom_index:03d}",
                "status": "active",
            }
        )
        batches["teaching_task"].append(
            {
                "id": task_id,
                "term_id": term_id,
                "homeroom_id": homeroom_id,
                "subject_id": subject_id,
                "primary_teacher_id": teacher_id,
                "weekly_slots": LESSONS_PER_HOMEROOM,
                "duration_slots": 1,
                "status": "active",
                "week_bits": "1" * 20,
                "day_bits": "11111",
            }
        )
        for lesson_index in range(LESSONS_PER_HOMEROOM):
            batches["task_lesson"].append(
                {
                    "id": f"lesson-{homeroom_index:03d}-{lesson_index:02d}",
                    "teaching_task_id": task_id,
                    "lesson_index": lesson_index,
                    "duration_slots": 1,
                    "source_id": f"scale:{homeroom_index}:{lesson_index}",
                    "week_bits": "1" * 20,
                    "day_bits": "11111",
                    "label": f"第{lesson_index + 1}课次",
                    "enabled": 1,
                }
            )
    project.bulk_insert_entities(batches, expected_revision=0)
    return project


def run_benchmark(workspace_path: Path, time_budget_seconds: int) -> dict:
    started = time.perf_counter()
    workspace = ProjectWorkspace(workspace_path)
    project = create_scale_project(workspace)
    seeded_seconds = time.perf_counter() - started
    try:
        service = SchedulingService(project)
        prepare_started = time.perf_counter()
        prepared = service.prepare_round(
            time_budget_seconds=time_budget_seconds,
            random_seed=20260831,
            name="6000 课次验收",
        )
        prepare_seconds = time.perf_counter() - prepare_started
        if not prepared["solverReady"]:
            raise RuntimeError(prepared["round"]["error_message"])
        solve_started = time.perf_counter()
        solver_result = run_cp_sat_v1(
            prepared["problemXml"],
            prepared["roundId"],
            prepared["solverConfig"],
        )
        solve_seconds = time.perf_counter() - solve_started
        persist_started = time.perf_counter()
        round_result = service.complete_round(
            prepared["roundId"],
            solver_result,
            snapshot=prepared["snapshot"],
            compile_diagnostics=prepared["compileDiagnostics"],
        )
        persist_seconds = time.perf_counter() - persist_started
        return {
            "teachers": TEACHER_COUNT,
            "homerooms": HOMEROOM_COUNT,
            "lessons": LESSON_COUNT,
            "timeBudgetSeconds": time_budget_seconds,
            "seedSeconds": round(seeded_seconds, 3),
            "prepareSeconds": round(prepare_seconds, 3),
            "solverSeconds": round(solve_seconds, 3),
            "persistSeconds": round(persist_seconds, 3),
            "candidateReadySeconds": round(
                prepare_seconds + solve_seconds + persist_seconds, 3
            ),
            "status": round_result["status"],
            "candidateId": round_result["candidate_id"],
            "entryCount": project.connection.execute(
                "SELECT COUNT(*) FROM timetable_entries WHERE candidate_id = ?",
                (round_result["candidate_id"],),
            ).fetchone()[0],
            "solver": {
                key: solver_result.get(key)
                for key in (
                    "solver_status",
                    "feasibility_status",
                    "quality_status",
                    "candidate_count",
                    "hard_conflict_count",
                    "model_build_ms",
                    "feasibility_search_ms",
                    "quality_search_ms",
                    "elapsed_ms",
                    "total_score",
                )
            },
        }
    finally:
        project.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic STT scale benchmark")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--time-budget", type=int, default=60)
    args = parser.parse_args()
    if args.workspace:
        result = run_benchmark(args.workspace.resolve(), args.time_budget)
    else:
        with tempfile.TemporaryDirectory(prefix="stt-scale-") as directory:
            result = run_benchmark(Path(directory), args.time_budget)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "succeeded" and result["entryCount"] == LESSON_COUNT else 1


if __name__ == "__main__":
    raise SystemExit(main())
