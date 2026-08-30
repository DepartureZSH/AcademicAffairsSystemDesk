from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from xml.etree.ElementTree import Element, SubElement, fromstring, tostring

from stt_desktop.scheduler_engine import run_cp_sat_v1
from stt_desktop.storage.project import ProjectError, ProjectRepository, utc_now, uuid7


SOLVER_VERSION = "stt-cp-sat-v1+desktop-1"
VALIDATOR_VERSION = "desktop-validator-1"
SNAPSHOT_TABLES = (
    "terms",
    "bell_schedules",
    "time_slots",
    "teachers",
    "rooms",
    "homerooms",
    "subjects",
    "teaching_tasks",
    "task_lessons",
    "availability_rules",
    "constraints",
    "timetable_template_assignments",
)


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_text(path: Path, value: str) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid7()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    encoded = value.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def _rows(project: ProjectRepository, table: str, where: str = "", params: tuple = ()) -> list[dict]:
    query = f"SELECT * FROM {table}"  # noqa: S608 - internal allowlist only
    if where:
        query += f" WHERE {where}"  # noqa: S608 - internal fixed fragments only
    query += " ORDER BY id"
    return [dict(row) for row in project.connection.execute(query, params).fetchall()]


def _bits_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return any(a == "1" and b == "1" for a, b in zip(left, right))


def _day_enabled(bits: str, weekday: int) -> bool:
    return not bits or weekday > len(bits) or bits[weekday - 1] == "1"


def _day_bits(weekday: int, day_count: int = 7) -> str:
    return "".join("1" if value == weekday else "0" for value in range(1, day_count + 1))


def _slot_windows(slots: list[dict], duration: int) -> list[tuple[dict, list[dict]]]:
    windows: list[tuple[dict, list[dict]]] = []
    for weekday in range(1, 8):
        day_slots = sorted(
            (item for item in slots if int(item["weekday"]) == weekday),
            key=lambda item: int(item["period_index"]),
        )
        for index in range(len(day_slots)):
            window = day_slots[index:index + duration]
            if len(window) != duration:
                continue
            if all(
                int(right["period_index"]) == int(left["period_index"]) + 1
                and int(right["start_slot"]) == int(left["start_slot"]) + int(left["length_slots"])
                for left, right in zip(window, window[1:])
            ):
                windows.append((window[0], window))
    return windows


class SchedulingService:
    def __init__(self, project: ProjectRepository) -> None:
        self.project = project

    def validate_current_project(self) -> dict[str, Any]:
        """Compile current inputs and report obvious blockers without writing project state."""
        snapshot = {
            "project": self.project.project_info(),
            "revision": self.project.revision,
            "tables": {table: _rows(self.project, table) for table in SNAPSHOT_TABLES},
        }
        encoded = _canonical_json(snapshot)
        _, compile_diagnostics = self._build_problem(snapshot)
        errors = [dict(item) for item in compile_diagnostics["errors"]]
        warnings = [dict(item) for item in compile_diagnostics["warnings"]]
        tables = snapshot["tables"]
        teachers = {str(item["id"]): item for item in tables["teachers"]}
        rooms = {str(item["id"]): item for item in tables["rooms"]}
        active_rooms = [item for item in tables["rooms"] if item["status"] == "active"]
        lessons_by_task: dict[str, list[dict[str, Any]]] = {}
        for lesson in tables["task_lessons"]:
            lessons_by_task.setdefault(str(lesson["teaching_task_id"]), []).append(lesson)
        active_tasks = [
            item for item in tables["teaching_tasks"] if item["status"] == "active"
        ]
        active_tasks_by_plan: dict[str, list[dict[str, Any]]] = {}

        for task in active_tasks:
            task_id = str(task["id"])
            teacher_id = str(task.get("primary_teacher_id") or "")
            teacher = teachers.get(teacher_id)
            if not teacher_id:
                errors.append(
                    {
                        "code": "TASK_MISSING_PRIMARY_TEACHER",
                        "message": "教学任务尚未分配主讲教师",
                        "entityType": "teaching_task",
                        "entityId": task_id,
                    }
                )
            elif not teacher or teacher.get("status") != "active":
                errors.append(
                    {
                        "code": "TASK_TEACHER_UNAVAILABLE",
                        "message": "教学任务引用的教师不存在或已停用",
                        "entityType": "teaching_task",
                        "entityId": task_id,
                        "teacherId": teacher_id,
                    }
                )

            enabled_lessons = [
                item for item in lessons_by_task.get(task_id, []) if item["enabled"]
            ]
            expanded_slots = sum(int(item["duration_slots"]) for item in enabled_lessons)
            weekly_slots = int(task["weekly_slots"])
            if expanded_slots != weekly_slots:
                errors.append(
                    {
                        "code": "TASK_LESSON_SLOTS_MISMATCH",
                        "message": f"教学任务周课时为 {weekly_slots}，启用课次合计为 {expanded_slots}",
                        "entityType": "teaching_task",
                        "entityId": task_id,
                        "expectedSlots": weekly_slots,
                        "actualSlots": expanded_slots,
                    }
                )

            fixed_room_id = str(task.get("fixed_room_id") or "")
            required_room_type = str(task.get("required_room_type") or "")
            fixed_room = rooms.get(fixed_room_id) if fixed_room_id else None
            if fixed_room_id and (not fixed_room or fixed_room.get("status") != "active"):
                errors.append(
                    {
                        "code": "TASK_FIXED_ROOM_UNAVAILABLE",
                        "message": "教学任务指定的固定教室不存在或已停用",
                        "entityType": "teaching_task",
                        "entityId": task_id,
                        "roomId": fixed_room_id,
                    }
                )
            elif (
                fixed_room
                and required_room_type
                and str(fixed_room.get("room_type_id") or "") != required_room_type
            ):
                errors.append(
                    {
                        "code": "TASK_FIXED_ROOM_TYPE_MISMATCH",
                        "message": "固定教室不满足教学任务要求的教室类型",
                        "entityType": "teaching_task",
                        "entityId": task_id,
                        "roomId": fixed_room_id,
                        "requiredRoomTypeId": required_room_type,
                    }
                )
            elif required_room_type not in {"", "__no_room__"} and not any(
                str(room.get("room_type_id") or "") == required_room_type
                for room in active_rooms
            ):
                errors.append(
                    {
                        "code": "TASK_ROOM_TYPE_UNAVAILABLE",
                        "message": "没有启用中的教室满足教学任务要求的教室类型",
                        "entityType": "teaching_task",
                        "entityId": task_id,
                        "requiredRoomTypeId": required_room_type,
                    }
                )

            plan_id = str(task.get("course_plan_id") or "")
            if plan_id:
                active_tasks_by_plan.setdefault(plan_id, []).append(task)

        course_plans = _rows(self.project, "course_plans")
        for plan in course_plans:
            planned_slots = int(plan["weekly_slots"])
            if planned_slots == 0:
                continue
            plan_tasks = active_tasks_by_plan.get(str(plan["id"]), [])
            assigned_slots = sum(int(item["weekly_slots"]) for item in plan_tasks)
            if assigned_slots != planned_slots:
                errors.append(
                    {
                        "code": "COURSE_PLAN_TASK_SLOTS_MISMATCH",
                        "message": f"课程计划周课时为 {planned_slots}，启用教学任务合计为 {assigned_slots}",
                        "entityType": "course_plan",
                        "entityId": str(plan["id"]),
                        "expectedSlots": planned_slots,
                        "actualSlots": assigned_slots,
                    }
                )

        return {
            "ready": not errors,
            "revision": self.project.revision,
            "inputHash": _sha256_text(encoded),
            "checkedAt": utc_now(),
            "summary": {
                "activeTaskCount": len(active_tasks),
                "activeLessonCount": int(compile_diagnostics["lesson_count"]),
                "optionCount": int(compile_diagnostics["option_count"]),
                "compiledLimitCount": int(
                    compile_diagnostics["compiled_limit_count"]
                ),
                "assignedScheduleCount": int(
                    compile_diagnostics["assigned_schedule_count"]
                ),
                "errorCount": len(errors),
                "warningCount": len(warnings),
            },
            "errors": errors,
            "warnings": warnings,
        }

    def run_round(
        self,
        *,
        time_budget_seconds: int = 60,
        random_seed: int = 0,
        session_id: str | None = None,
        parent_candidate_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        prepared = self.prepare_round(
            time_budget_seconds=time_budget_seconds,
            random_seed=random_seed,
            session_id=session_id,
            parent_candidate_id=parent_candidate_id,
            name=name,
        )
        if not prepared["solverReady"]:
            return prepared["round"]
        round_id = prepared["roundId"]
        try:
            result = run_cp_sat_v1(
                prepared["problemXml"], round_id, prepared["solverConfig"]
            )
            return self.complete_round(
                round_id,
                result,
                snapshot=prepared["snapshot"],
                compile_diagnostics=prepared["compileDiagnostics"],
            )
        except Exception as exc:
            self.mark_failed(round_id, "LOCAL_SOLVER_ERROR", str(exc))
            raise

    def prepare_round(
        self,
        *,
        time_budget_seconds: int = 60,
        random_seed: int = 0,
        session_id: str | None = None,
        parent_candidate_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        if not 10 <= time_budget_seconds <= 1800:
            raise ProjectError("排课时长必须在 10 到 1800 秒之间")
        now = utc_now()
        session_id = self._ensure_session(session_id, name, now)
        parent = self._load_parent(parent_candidate_id)
        round_id = uuid7()
        self.project.connection.execute(
            """
            INSERT INTO scheduling_rounds(
                id, session_id, parent_candidate_id, status, time_budget_seconds,
                random_seed, algorithm, algorithm_config, created_at, updated_at
            ) VALUES (?, ?, ?, 'preparing', ?, ?, 'cp_sat_v1', ?, ?, ?)
            """,
            (
                round_id,
                session_id,
                parent_candidate_id,
                time_budget_seconds,
                random_seed,
                _canonical_json({"algorithm": "cp_sat_v1"}),
                now,
                now,
            ),
        )
        self._event(round_id, "round_preparing", {"revision": self.project.revision})

        try:
            snapshot_id, input_hash, snapshot = self._snapshot(round_id)
            problem_xml, compile_diagnostics = self._build_problem(snapshot)
            problem_relative = f"artifacts/problem/{round_id}.xml"
            problem_path = self.project.project_directory / problem_relative
            problem_sha, problem_size = _write_text(problem_path, problem_xml)
            self._record_artifact("problem_xml", problem_relative, problem_sha, problem_size)
            self.project.connection.execute(
                """
                UPDATE scheduling_rounds
                SET snapshot_id = ?, input_hash = ?, status = 'solving', started_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (snapshot_id, input_hash, utc_now(), utc_now(), round_id),
            )
            self._event(
                round_id,
                "problem_compiled",
                {
                    "lessonCount": compile_diagnostics["lesson_count"],
                    "optionCount": compile_diagnostics["option_count"],
                    "warningCount": len(compile_diagnostics["warnings"]),
                },
            )
            if compile_diagnostics["errors"]:
                result = self._finish_infeasible(
                    round_id,
                    compile_diagnostics,
                    "输入数据无法构造完整排课问题",
                )
                return {"roundId": round_id, "solverReady": False, "round": result}

            config: dict[str, Any] = {
                "algorithm": "cp_sat_v1",
                "time_limit_seconds": time_budget_seconds,
                "random_seed": random_seed,
            }
            if parent:
                config["warm_start_solution_xml"] = self._read_solution(parent)
            self._event(
                round_id,
                "solver_input_ready",
                {"isolatedProcessEligible": True},
            )
            return {
                "roundId": round_id,
                "solverReady": True,
                "round": self.get_round(round_id),
                "problemXml": problem_xml,
                "solverConfig": config,
                "snapshot": snapshot,
                "compileDiagnostics": compile_diagnostics,
            }
        except Exception as exc:
            self.mark_failed(round_id, "LOCAL_PREPARATION_ERROR", str(exc))
            raise

    def complete_round(
        self,
        round_id: str,
        result: dict[str, Any],
        *,
        snapshot: dict[str, Any],
        compile_diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.project.connection.execute(
            "SELECT * FROM scheduling_rounds WHERE id = ?", (round_id,)
        ).fetchone()
        if not row:
            raise ProjectError("排课轮次不存在")
        if row["status"] != "solving":
            raise ProjectError("排课轮次已结束，拒绝写入迟到的求解结果")
        self.project.connection.execute(
            "UPDATE scheduling_rounds SET status = 'validating', updated_at = ? WHERE id = ?",
            (utc_now(), round_id),
        )
        self._event(round_id, "solution_validating", {})
        if not result.get("complete_schedule_feasible"):
            diagnostics = {
                **compile_diagnostics,
                "solver": self._safe_solver_diagnostics(result),
                "conflicts": result.get("unassigned_explanations") or [],
            }
            return self._finish_infeasible(
                round_id,
                diagnostics,
                str(result.get("log") or "硬约束无解"),
            )

        validation = self._validate_solution(snapshot, str(result["solution_xml"]))
        compile_diagnostics["validation"] = validation
        if validation["hardIssues"]:
            return self._finish_infeasible(
                round_id,
                {
                    **compile_diagnostics,
                    "solver": self._safe_solver_diagnostics(result),
                    "conflicts": validation["hardIssues"],
                },
                "求解结果违反启用的硬约束",
            )
        if validation["softPenalty"] and not result.get(
            "resource_limit_penalty_included"
        ):
            result["distribution_penalty"] = int(
                result.get("distribution_penalty") or 0
            ) + validation["softPenalty"]
            result["total_score"] = int(result.get("total_score") or 0) + validation[
                "softPenalty"
            ]

        self.project.connection.execute("BEGIN IMMEDIATE")
        try:
            candidate = self._persist_candidate(
                round_id=round_id,
                snapshot_id=str(row["snapshot_id"]),
                input_hash=str(row["input_hash"]),
                parent_candidate_id=row["parent_candidate_id"],
                result=result,
                snapshot=snapshot,
                compile_diagnostics=compile_diagnostics,
            )
            finished = utc_now()
            self.project.connection.execute(
                "UPDATE scheduling_rounds SET status = 'succeeded', stop_reason = 'candidate_found', finished_at = ?, updated_at = ? WHERE id = ?",
                (finished, finished, round_id),
            )
            self.project.connection.execute(
                "UPDATE optimization_sessions SET status = 'active', updated_at = ? WHERE id = ?",
                (finished, row["session_id"]),
            )
            self._event(
                round_id, "candidate_persisted", {"candidateId": candidate["id"]}
            )
            self.project.connection.execute("COMMIT")
        except Exception:
            self.project.connection.execute("ROLLBACK")
            raise
        return self.get_round(round_id)

    def mark_cancelled(self, round_id: str, reason: str = "user_cancelled") -> dict[str, Any]:
        row = self.project.connection.execute(
            "SELECT status FROM scheduling_rounds WHERE id = ?", (round_id,)
        ).fetchone()
        if not row:
            raise ProjectError("排课轮次不存在")
        if row["status"] in {"succeeded", "infeasible", "cancelled", "failed", "failed_recoverable"}:
            return self.get_round(round_id)
        finished = utc_now()
        self.project.connection.execute(
            "UPDATE scheduling_rounds SET status = 'cancelled', stop_reason = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            (reason[:200], finished, finished, round_id),
        )
        self._event(round_id, "round_cancelled", {"reason": reason[:200]})
        return self.get_round(round_id)

    def mark_failed(self, round_id: str, code: str, message: str) -> dict[str, Any]:
        row = self.project.connection.execute(
            "SELECT status FROM scheduling_rounds WHERE id = ?", (round_id,)
        ).fetchone()
        if not row:
            raise ProjectError("排课轮次不存在")
        if row["status"] in {"succeeded", "infeasible", "cancelled"}:
            return self.get_round(round_id)
        finished = utc_now()
        self.project.connection.execute(
            """
            UPDATE scheduling_rounds
            SET status = 'failed_recoverable', error_code = ?, error_message = ?,
                finished_at = ?, updated_at = ? WHERE id = ?
            """,
            (code[:100], message[:1000], finished, finished, round_id),
        )
        self._event(round_id, "round_failed", {"code": code[:100]})
        return self.get_round(round_id)

    def recover_interrupted_rounds(self) -> int:
        rows = self.project.connection.execute(
            "SELECT id FROM scheduling_rounds WHERE status IN ('queued', 'preparing', 'solving', 'validating')"
        ).fetchall()
        for row in rows:
            self.mark_failed(
                row["id"],
                "INTERRUPTED_ON_RESTART",
                "上次本地算法进程或应用在轮次完成前退出，可安全重试",
            )
        return len(rows)

    def record_event(
        self, round_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        self._event(round_id, event_type, payload)

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self.project.connection.execute(
            """
            SELECT s.*,
                   COUNT(DISTINCT r.id) AS round_count,
                   COUNT(DISTINCT c.id) AS candidate_count
            FROM optimization_sessions s
            LEFT JOIN scheduling_rounds r ON r.session_id = s.id
            LEFT JOIN candidates c ON c.round_id = r.id
            GROUP BY s.id ORDER BY s.created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_rounds(self, session_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE r.session_id = ?" if session_id else ""
        params = (session_id,) if session_id else ()
        rows = self.project.connection.execute(
            f"""
            SELECT r.*, c.id AS candidate_id, c.total_score, c.hard_violations
            FROM scheduling_rounds r
            LEFT JOIN candidates c ON c.round_id = r.id
            {where}
            ORDER BY r.created_at DESC
            """,  # noqa: S608 - fixed optional predicate
            params,
        ).fetchall()
        return [self._decode_round(dict(row)) for row in rows]

    def get_round(self, round_id: str) -> dict[str, Any]:
        rows = self.project.connection.execute(
            """
            SELECT r.*, c.id AS candidate_id, c.total_score, c.hard_violations,
                   c.name AS candidate_name, c.diagnostics AS candidate_diagnostics
            FROM scheduling_rounds r
            LEFT JOIN candidates c ON c.round_id = r.id
            WHERE r.id = ?
            """,
            (round_id,),
        ).fetchall()
        if not rows:
            raise ProjectError("排课轮次不存在")
        result = self._decode_round(dict(rows[0]))
        result["events"] = [
            {**dict(row), "payload": json.loads(row["payload"])}
            for row in self.project.connection.execute(
                "SELECT * FROM round_events WHERE round_id = ? ORDER BY sequence", (round_id,)
            ).fetchall()
        ]
        if result.get("candidate_diagnostics"):
            result["candidate_diagnostics"] = json.loads(result["candidate_diagnostics"])
        return result

    def list_candidates(self) -> list[dict[str, Any]]:
        rows = self.project.connection.execute(
            """
            SELECT c.*, r.session_id, r.time_budget_seconds, r.random_seed,
                   COUNT(e.id) AS entry_count
            FROM candidates c
            JOIN scheduling_rounds r ON r.id = c.round_id
            LEFT JOIN timetable_entries e ON e.candidate_id = c.id
            GROUP BY c.id ORDER BY c.created_at DESC
            """
        ).fetchall()
        metric_rows = self.project.connection.execute(
            """
            SELECT candidate_id, metric_key, metric_value
            FROM candidate_metrics
            ORDER BY candidate_id, metric_key
            """
        ).fetchall()
        metrics: dict[str, dict[str, float]] = {}
        for metric in metric_rows:
            metrics.setdefault(str(metric["candidate_id"]), {})[
                str(metric["metric_key"])
            ] = float(metric["metric_value"])
        return [
            {
                **dict(row),
                "diagnostics": json.loads(row["diagnostics"]),
                "metrics": metrics.get(str(row["id"]), {}),
            }
            for row in rows
        ]

    def _ensure_session(self, session_id: str | None, name: str | None, now: str) -> str:
        if session_id:
            row = self.project.connection.execute(
                "SELECT id FROM optimization_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                raise ProjectError("优化会话不存在")
            return session_id
        session_id = uuid7()
        self.project.connection.execute(
            "INSERT INTO optimization_sessions(id, name, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
            (session_id, (name or "本地优化会话").strip() or "本地优化会话", now, now),
        )
        return session_id

    def _load_parent(self, candidate_id: str | None) -> dict[str, Any] | None:
        if not candidate_id:
            return None
        row = self.project.connection.execute(
            "SELECT * FROM candidates WHERE id = ? AND status = 'valid'", (candidate_id,)
        ).fetchone()
        if not row:
            raise ProjectError("用于继续优化的候选不存在或已失效")
        return dict(row)

    def _snapshot(self, round_id: str) -> tuple[str, str, dict[str, Any]]:
        payload = {
            "project": self.project.project_info(),
            "revision": self.project.revision,
            "tables": {table: _rows(self.project, table) for table in SNAPSHOT_TABLES},
        }
        encoded = _canonical_json(payload)
        input_hash = _sha256_text(encoded)
        snapshot_id = uuid7()
        relative = f"artifacts/problem/{round_id}-snapshot.json"
        sha, size = _write_text(self.project.project_directory / relative, encoded + "\n")
        now = utc_now()
        self.project.connection.execute(
            "INSERT INTO data_snapshots(id, revision, input_hash, payload_path, created_at) VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, self.project.revision, input_hash, relative, now),
        )
        self._record_artifact("data_snapshot", relative, sha, size)
        return snapshot_id, input_hash, payload

    def _build_problem(self, snapshot: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        tables = snapshot["tables"]
        tasks = [item for item in tables["teaching_tasks"] if item["status"] == "active"]
        task_by_id = {item["id"]: item for item in tasks}
        lessons = [
            item for item in tables["task_lessons"]
            if item["enabled"] and item["teaching_task_id"] in task_by_id
        ]
        schedules = tables["bell_schedules"]
        task_terms = {item["term_id"] for item in tasks if item.get("term_id")}
        eligible = [item for item in schedules if not task_terms or item.get("term_id") in task_terms]
        schedule_by_id = {str(item["id"]): item for item in schedules}
        slots_by_schedule: dict[str, list[dict[str, Any]]] = {}
        for slot in tables["time_slots"]:
            if slot["active"]:
                slots_by_schedule.setdefault(str(slot["bell_schedule_id"]), []).append(slot)
        eligible_with_slots = [
            item for item in eligible if slots_by_schedule.get(str(item["id"]))
        ]
        default_schedule = next(
            (item for item in eligible_with_slots if item["is_default"]),
            eligible_with_slots[0]
            if eligible_with_slots
            else (eligible[0] if eligible else None),
        )
        assignment_ids = {
            (str(item["entity_type"]), str(item.get("entity_id") or "")): str(item["bell_schedule_id"])
            for item in tables["timetable_template_assignments"]
        }
        diagnostics: dict[str, Any] = {"errors": [], "warnings": [], "lesson_count": len(lessons), "option_count": 0, "compiled_limit_count": 0, "assigned_schedule_count": 0}
        if not tasks or not lessons:
            diagnostics["errors"].append({"code": "NO_ACTIVE_LESSONS", "message": "没有可参与排课的启用课次"})
        if default_schedule is None:
            diagnostics["errors"].append({"code": "NO_BELL_SCHEDULE", "message": "没有与教学任务学期匹配的作息表"})
        if default_schedule and not slots_by_schedule.get(str(default_schedule["id"])):
            diagnostics["errors"].append({"code": "NO_ACTIVE_TIME_SLOTS", "message": "当前作息表没有启用课节"})

        unusable_assignment_tasks: set[str] = set()

        def schedule_for_task(task: dict[str, Any]) -> dict[str, Any] | None:
            schedule_id = ""
            for entity_type, entity_id in (
                ("homeroom", task.get("homeroom_id")),
                ("teacher", task.get("primary_teacher_id")),
                ("subject", task.get("subject_id")),
                ("all", None),
            ):
                candidate = assignment_ids.get((entity_type, str(entity_id or "")))
                if candidate:
                    schedule_id = candidate
                    break
            selected = schedule_by_id.get(schedule_id) if schedule_id else default_schedule
            if schedule_id and selected is not None and slots_by_schedule.get(schedule_id):
                diagnostics["assigned_schedule_count"] += 1
                return selected
            if schedule_id and str(task["id"]) not in unusable_assignment_tasks:
                diagnostics["warnings"].append(
                    {
                        "code": "ASSIGNED_SCHEDULE_HAS_NO_ACTIVE_SLOTS",
                        "taskId": str(task["id"]),
                        "scheduleId": schedule_id,
                        "message": "教学任务分配的作息表没有启用课节，已回退到可用默认作息",
                    }
                )
                unusable_assignment_tasks.add(str(task["id"]))
            return default_schedule

        rooms = [item for item in tables["rooms"] if item["status"] == "active"]
        room_by_id = {item["id"]: item for item in rooms}
        homeroom_by_id = {item["id"]: item for item in tables["homerooms"]}
        subject_by_id = {item["id"]: item for item in tables["subjects"]}
        teacher_by_id = {item["id"]: item for item in tables["teachers"]}
        rules = tables["availability_rules"]
        constraints = [item for item in tables["constraints"] if item["enabled"]]
        preferred_period_constraints = self._preferred_period_constraints(constraints)

        root = Element("problem", {"name": str(snapshot["project"]["name"]), "nrDays": "7", "nrWeeks": "60", "slotsPerDay": "256"})
        room_node = SubElement(root, "rooms")
        for room in rooms:
            SubElement(room_node, "room", {"id": room["id"], "name": room["name"]})
        classes_node = SubElement(root, "classes")
        lesson_ids_by_teacher: dict[str, list[str]] = {}
        lesson_ids_by_homeroom: dict[str, list[str]] = {}
        lesson_ids_by_task: dict[str, list[str]] = {}
        for lesson in lessons:
            task = task_by_id[lesson["teaching_task_id"]]
            schedule = schedule_for_task(task)
            slots = slots_by_schedule.get(str(schedule["id"]), []) if schedule else []
            label = "-".join(
                value for value in (
                    str(homeroom_by_id.get(task["homeroom_id"], {}).get("name") or ""),
                    str(teacher_by_id.get(task.get("primary_teacher_id"), {}).get("name") or ""),
                    str(subject_by_id.get(task["subject_id"], {}).get("name") or ""),
                    str(lesson.get("label") or f"第{lesson['lesson_index'] + 1}课次"),
                ) if value
            )
            node = SubElement(classes_node, "class", {"id": lesson["id"], "subject": task["subject_id"], "label": label})
            duration = int(lesson.get("duration_slots") or task.get("duration_slots") or 1)
            applicable = self._applicable_rules(
                rules, task, lesson, str(schedule["id"]) if schedule else None
            )
            required_slot_ids = {rule["time_slot_id"] for rule in applicable if rule["required"] and rule.get("time_slot_id")}
            emitted_times: list[tuple[dict[str, str], set[str]]] = []
            for slot, window in _slot_windows(slots, duration):
                weekday = int(slot["weekday"])
                period_index = int(slot["period_index"])
                if not _day_enabled(str(lesson.get("day_bits") or task.get("day_bits") or ""), weekday):
                    continue
                if any(
                    preference["required"]
                    and period_index not in preference["periods"]
                    for preference in preferred_period_constraints
                ):
                    continue
                if required_slot_ids and slot["id"] not in required_slot_ids:
                    continue
                window_ids = {item["id"] for item in window}
                slot_rules = [rule for rule in applicable if not rule.get("time_slot_id") or rule["time_slot_id"] in window_ids]
                hard_blocked = any(not rule["required"] and int(rule["penalty"]) == 0 for rule in slot_rules)
                if hard_blocked:
                    continue
                penalty = sum(int(rule["penalty"]) for rule in slot_rules if not rule["required"])
                penalty += sum(
                    int(preference["weight"])
                    for preference in preferred_period_constraints
                    if not preference["required"]
                    and period_index not in preference["periods"]
                )
                time_attrs = {
                    "days": _day_bits(weekday),
                    "weeks": str(lesson.get("week_bits") or task.get("week_bits") or "1"),
                    "start": str(slot["start_slot"]),
                    "length": str(duration),
                    "periodIndex": str(slot["period_index"]),
                    "penalty": str(penalty),
                }
                SubElement(node, "time", time_attrs)
                emitted_times.append((time_attrs, window_ids))
                diagnostics["option_count"] += 1
            candidate_rooms = self._candidate_rooms(task, homeroom_by_id, rooms, room_by_id)
            for room_id in candidate_rooms:
                room_node = SubElement(node, "room", {"id": room_id, "penalty": "0"})
                room_rules = [
                    rule for rule in rules
                    if rule["entity_type"] == "room"
                    and rule["entity_id"] == room_id
                    and schedule
                    and (not rule.get("bell_schedule_id") or rule["bell_schedule_id"] == schedule["id"])
                    and _bits_overlap(str(rule.get("week_bits") or ""), str(lesson.get("week_bits") or task.get("week_bits") or ""))
                ]
                required_room_slots = {rule["time_slot_id"] for rule in room_rules if rule["required"] and rule.get("time_slot_id")}
                for time_attrs, window_ids in emitted_times:
                    matching = [rule for rule in room_rules if not rule.get("time_slot_id") or rule["time_slot_id"] in window_ids]
                    if (required_room_slots and not required_room_slots.intersection(window_ids)) or any(not rule["required"] and int(rule["penalty"]) == 0 for rule in matching):
                        SubElement(room_node, "unavailable", {key: time_attrs[key] for key in ("days", "weeks", "start")})
                        continue
                    room_penalty = sum(int(rule["penalty"]) for rule in matching if not rule["required"])
                    if room_penalty:
                        SubElement(room_node, "preference", {**{key: time_attrs[key] for key in ("days", "weeks", "start")}, "penalty": str(room_penalty)})
            if node.find("time") is None:
                diagnostics["errors"].append({"code": "LESSON_HAS_NO_TIME_OPTION", "lessonId": lesson["id"], "message": f"{label} 没有可用课节"})
            teacher_id = task.get("primary_teacher_id")
            if teacher_id:
                lesson_ids_by_teacher.setdefault(teacher_id, []).append(lesson["id"])
            lesson_ids_by_homeroom.setdefault(task["homeroom_id"], []).append(lesson["id"])
            lesson_ids_by_task.setdefault(task["id"], []).append(lesson["id"])

        distributions_node = SubElement(root, "distributions")
        limits_node = SubElement(root, "limits")
        for prefix, groups in (("teacher", lesson_ids_by_teacher), ("homeroom", lesson_ids_by_homeroom)):
            for entity_id, lesson_ids in groups.items():
                self._distribution(distributions_node, f"builtin-{prefix}-{entity_id}", "NotOverlap", lesson_ids, True, 0, f"{prefix}资源冲突", prefix)
        self._compile_user_constraints(
            distributions_node,
            limits_node,
            constraints,
            lesson_ids_by_task,
            {
                "teacher": lesson_ids_by_teacher,
                "homeroom": lesson_ids_by_homeroom,
            },
            diagnostics,
        )
        return tostring(root, encoding="unicode"), diagnostics

    @staticmethod
    def _applicable_rules(
        rules: list[dict],
        task: dict,
        lesson: dict,
        bell_schedule_id: str | None,
    ) -> list[dict]:
        targets = {
            ("teacher", task.get("primary_teacher_id")),
            ("homeroom", task.get("homeroom_id")),
            ("lesson", lesson.get("id")),
        }
        return [
            rule
            for rule in rules
            if (rule["entity_type"], rule["entity_id"]) in targets
            and (
                not rule.get("bell_schedule_id")
                or rule["bell_schedule_id"] == bell_schedule_id
            )
            and _bits_overlap(
                str(rule.get("week_bits") or ""),
                str(lesson.get("week_bits") or task.get("week_bits") or ""),
            )
        ]

    @staticmethod
    def _candidate_rooms(task: dict, homerooms: dict[str, dict], rooms: list[dict], room_by_id: dict[str, dict]) -> list[str]:
        fixed = task.get("fixed_room_id")
        if fixed and fixed in room_by_id:
            return [fixed]
        required_type = task.get("required_room_type")
        if required_type:
            return [room["id"] for room in rooms if room.get("room_type_id") == required_type]
        default_room = homerooms.get(task["homeroom_id"], {}).get("default_room_id")
        return [default_room] if default_room in room_by_id else []

    @staticmethod
    def _preferred_period_constraints(constraints: list[dict]) -> list[dict]:
        result = []
        for constraint in constraints:
            if constraint["type"] != "preferred_periods":
                continue
            parameters = json.loads(constraint["parameters"] or "{}")
            periods = {
                int(value)
                for value in parameters.get("periods", [])
                if isinstance(value, int) and value >= 0
            }
            result.append(
                {
                    "constraintId": constraint["id"],
                    "required": constraint["severity"] == "hard",
                    "weight": max(0, int(constraint["weight"])),
                    "periods": periods,
                }
            )
        return result

    def _compile_user_constraints(
        self,
        node: Element,
        limits_node: Element,
        constraints: list[dict],
        lessons_by_task: dict[str, list[str]],
        resource_groups: dict[str, dict[str, list[str]]],
        diagnostics: dict,
    ) -> None:
        all_lessons = [lesson_id for values in lessons_by_task.values() for lesson_id in values]
        for constraint in constraints:
            parameters = json.loads(constraint["parameters"] or "{}")
            required = constraint["severity"] == "hard"
            penalty = int(constraint["weight"])
            lesson_ids = [str(value) for value in parameters.get("lessonIds", []) if str(value) in all_lessons]
            task_ids = [str(value) for value in parameters.get("teachingTaskIds", [])]
            for task_id in task_ids:
                lesson_ids.extend(lessons_by_task.get(task_id, []))
            if constraint["type"] == "same_day_spacing":
                targets = [lesson_ids] if lesson_ids else list(lessons_by_task.values())
                for index, target in enumerate(targets):
                    self._distribution(node, f"user-{constraint['id']}-{index}", "DifferentDays", target, required, penalty, constraint["name"], "custom")
            elif constraint["type"] in {"preferred_periods"}:
                continue
            elif constraint["type"] in {"max_daily_lessons", "consecutive_limit"}:
                limit_key = (
                    "max"
                    if constraint["type"] == "max_daily_lessons"
                    else "maxConsecutive"
                )
                default_limit = 6 if limit_key == "max" else 3
                limit = max(1, int(parameters.get(limit_key, default_limit)))
                selected_resource_type = str(parameters.get("resourceType") or "")
                for resource_type, groups in resource_groups.items():
                    if selected_resource_type and selected_resource_type != resource_type:
                        continue
                    for resource_id, group_lesson_ids in groups.items():
                        targets = [
                            lesson_id
                            for lesson_id in group_lesson_ids
                            if not lesson_ids or lesson_id in lesson_ids
                        ]
                        if not targets:
                            continue
                        self._resource_limit(
                            limits_node,
                            f"user-{constraint['id']}-{resource_type}-{resource_id}",
                            constraint["type"],
                            targets,
                            required,
                            penalty,
                            limit,
                            constraint["name"],
                            resource_type,
                        )
                        diagnostics["compiled_limit_count"] += 1
            elif constraint["type"] in {"NotOverlap", "SameRoom", "DifferentTime", "DifferentDays", "DifferentWeeks", "SameDays", "SameStart", "SameTime", "Precedence", "Consecutive"} and len(lesson_ids) >= 2:
                self._distribution(node, f"user-{constraint['id']}", constraint["type"], lesson_ids, required, penalty, constraint["name"], "custom")
            else:
                diagnostics["warnings"].append({"code": "CONSTRAINT_NOT_COMPILED", "constraintId": constraint["id"], "message": f"约束 {constraint['name']} 当前未生成求解条件"})

    def _validate_solution(self, snapshot: dict[str, Any], solution_xml: str) -> dict[str, Any]:
        tables = snapshot["tables"]
        constraints = [item for item in tables["constraints"] if item["enabled"]]
        lesson_to_task = {
            lesson["id"]: task
            for lesson in tables["task_lessons"]
            for task in tables["teaching_tasks"]
            if task["id"] == lesson["teaching_task_id"]
        }
        assignments: list[dict[str, Any]] = []
        for node in fromstring(solution_xml).findall(".//class"):
            task = lesson_to_task.get(node.attrib.get("id", ""))
            if not task:
                continue
            weekdays = [index + 1 for index, bit in enumerate(node.attrib.get("days", "")) if bit == "1"] or [1]
            for weekday in weekdays:
                assignments.append(
                    {
                        "lessonId": node.attrib.get("id"),
                        "teacherId": task.get("primary_teacher_id"),
                        "homeroomId": task.get("homeroom_id"),
                        "weekday": weekday,
                        "start": int(node.attrib.get("start", "0")),
                        "length": int(node.attrib.get("length", "1")),
                    }
                )
        hard_issues: list[dict[str, Any]] = []
        soft_issues: list[dict[str, Any]] = []
        soft_penalty = 0
        for constraint in constraints:
            if constraint["type"] not in {"max_daily_lessons", "consecutive_limit"}:
                continue
            parameters = json.loads(constraint["parameters"] or "{}")
            limit_key = "max" if constraint["type"] == "max_daily_lessons" else "maxConsecutive"
            limit = max(1, int(parameters.get(limit_key, 6 if limit_key == "max" else 3)))
            issues: list[dict[str, Any]] = []
            for resource_key in ("teacherId", "homeroomId"):
                resource_ids = {item[resource_key] for item in assignments if item.get(resource_key)}
                for resource_id in resource_ids:
                    for weekday in range(1, 8):
                        values = sorted(
                            (item for item in assignments if item.get(resource_key) == resource_id and item["weekday"] == weekday),
                            key=lambda item: item["start"],
                        )
                        if constraint["type"] == "max_daily_lessons":
                            excess = sum(item["length"] for item in values) - limit
                        else:
                            occupied: set[int] = set()
                            for item in values:
                                occupied.update(
                                    range(item["start"], item["start"] + item["length"])
                                )
                            longest = current = 0
                            previous: int | None = None
                            for period in sorted(occupied):
                                current = current + 1 if previous is not None and period == previous + 1 else 1
                                longest = max(longest, current)
                                previous = period
                            excess = longest - limit
                        if excess > 0:
                            issues.append(
                                {
                                    "code": constraint["type"].upper(),
                                    "constraintId": constraint["id"],
                                    "constraintName": constraint["name"],
                                    "resourceType": resource_key.removesuffix("Id"),
                                    "resourceId": resource_id,
                                    "weekday": weekday,
                                    "limit": limit,
                                    "excess": excess,
                                }
                            )
            if constraint["severity"] == "hard":
                hard_issues.extend(issues)
            else:
                soft_issues.extend(issues)
                soft_penalty += sum(int(constraint["weight"]) * int(item["excess"]) for item in issues)
        return {"hardIssues": hard_issues, "softIssues": soft_issues, "softPenalty": soft_penalty}

    @staticmethod
    def _distribution(node: Element, distribution_id: str, kind: str, lesson_ids: Iterable[str], required: bool, penalty: int, name: str, scope: str) -> None:
        unique = list(dict.fromkeys(lesson_ids))
        if len(unique) < 2:
            return
        attrs = {"id": distribution_id, "type": kind, "required": str(required).lower(), "name": name, "scope": scope}
        if not required:
            attrs["penalty"] = str(penalty)
        distribution = SubElement(node, "distribution", attrs)
        for lesson_id in unique:
            SubElement(distribution, "class", {"id": lesson_id})

    @staticmethod
    def _resource_limit(
        node: Element,
        constraint_id: str,
        kind: str,
        lesson_ids: Iterable[str],
        required: bool,
        penalty: int,
        limit: int,
        name: str,
        scope: str,
    ) -> None:
        unique = tuple(dict.fromkeys(lesson_ids))
        if not unique:
            return
        attrs = {
            "id": constraint_id,
            "type": kind,
            "required": str(required).lower(),
            "limit": str(limit),
            "name": name,
            "scope": scope,
        }
        if not required:
            attrs["penalty"] = str(penalty)
        limit_node = SubElement(node, "limit", attrs)
        for lesson_id in unique:
            SubElement(limit_node, "class", {"id": lesson_id})

    def _persist_candidate(self, *, round_id: str, snapshot_id: str, input_hash: str, parent_candidate_id: str | None, result: dict, snapshot: dict, compile_diagnostics: dict) -> dict:
        candidate_id = uuid7()
        relative = f"artifacts/solution/{candidate_id}.xml"
        sha, size = _write_text(self.project.project_directory / relative, str(result["solution_xml"]))
        self._record_artifact("solution_xml", relative, sha, size)
        diagnostics = {"solutionPath": relative, "compile": compile_diagnostics, "solver": self._safe_solver_diagnostics(result)}
        now = utc_now()
        self.project.connection.execute(
            """
            INSERT INTO candidates(id, round_id, parent_candidate_id, snapshot_id, name, status,
                hard_violations, total_score, input_hash, solver_version, validator_version, diagnostics, created_at)
            VALUES (?, ?, ?, ?, ?, 'valid', 0, ?, ?, ?, ?, ?, ?)
            """,
            (candidate_id, round_id, parent_candidate_id, snapshot_id, f"候选 {now[0:19]}", int(result["total_score"]), input_hash, SOLVER_VERSION, VALIDATOR_VERSION, _canonical_json(diagnostics), now),
        )
        task_by_lesson = {item["id"]: next(task for task in snapshot["tables"]["teaching_tasks"] if task["id"] == item["teaching_task_id"]) for item in snapshot["tables"]["task_lessons"]}
        root = fromstring(str(result["solution_xml"]))
        for item in root.findall(".//class"):
            lesson_id = item.attrib["id"]
            task = task_by_lesson.get(lesson_id)
            if not task:
                continue
            days = item.attrib.get("days", "")
            weekdays = [index + 1 for index, value in enumerate(days) if value == "1"] or [1]
            for weekday in weekdays:
                self.project.connection.execute(
                    """
                    INSERT INTO timetable_entries(id, candidate_id, task_lesson_id, teaching_task_id,
                        homeroom_id, subject_id, teacher_id, room_id, weekday, start_slot,
                        duration_slots, week_bits, source_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (uuid7(), candidate_id, lesson_id, task["id"], task["homeroom_id"], task["subject_id"], task.get("primary_teacher_id"), item.attrib.get("room"), weekday, int(item.attrib.get("start", "0")), int(item.attrib.get("length", "1")), item.attrib.get("weeks", ""), lesson_id, now),
                )
        for key in ("total_score", "time_penalty", "room_penalty", "distribution_penalty", "elapsed_ms", "candidate_count"):
            self.project.connection.execute(
                "INSERT INTO candidate_metrics(id, candidate_id, metric_key, metric_value, details) VALUES (?, ?, ?, ?, '{}')",
                (uuid7(), candidate_id, key, float(result.get(key) or 0)),
            )
        return dict(self.project.connection.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone())

    def _finish_infeasible(self, round_id: str, diagnostics: dict, message: str) -> dict[str, Any]:
        finished = utc_now()
        self.project.connection.execute(
            "UPDATE scheduling_rounds SET status = 'infeasible', stop_reason = 'hard_constraints_infeasible', error_code = 'INFEASIBLE', error_message = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            (message[:1000], finished, finished, round_id),
        )
        self._event(round_id, "infeasible_diagnostics", diagnostics)
        return self.get_round(round_id)

    def _read_solution(self, candidate: dict[str, Any]) -> str:
        diagnostics = json.loads(candidate["diagnostics"])
        relative = str(diagnostics.get("solutionPath") or "")
        path = (self.project.project_directory / relative).resolve()
        if not relative or self.project.project_directory not in path.parents:
            raise ProjectError("候选解文件路径无效")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _safe_solver_diagnostics(result: dict) -> dict[str, Any]:
        keys = (
            "solver_status", "feasibility_status", "quality_status", "assigned_count",
            "class_count", "unassigned_count", "hard_feasibility_proven",
            "complete_schedule_feasible", "max_assignable_count", "total_score",
            "candidate_count", "hard_conflict_count", "soft_conflict_count",
            "model_build_ms", "feasibility_search_ms", "quality_search_ms", "elapsed_ms", "log",
            "fast_path", "greedy_search_ms",
        )
        return {key: result.get(key) for key in keys}

    def _record_artifact(self, kind: str, relative: str, sha: str, size: int) -> None:
        self.project.connection.execute(
            "INSERT INTO artifacts(id, kind, relative_path, sha256, size_bytes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid7(), kind, relative, sha, size, utc_now()),
        )

    def _event(self, round_id: str, event_type: str, payload: dict[str, Any]) -> None:
        sequence = int(self.project.connection.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM round_events WHERE round_id = ?", (round_id,)).fetchone()[0])
        self.project.connection.execute(
            "INSERT INTO round_events(id, round_id, sequence, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid7(), round_id, sequence, event_type, _canonical_json(payload), utc_now()),
        )

    @staticmethod
    def _decode_round(row: dict[str, Any]) -> dict[str, Any]:
        row["algorithm_config"] = json.loads(row["algorithm_config"] or "{}")
        return row
