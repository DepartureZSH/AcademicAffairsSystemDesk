from __future__ import annotations

import json
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from stt_desktop.scheduler_engine.cgcs import Action, _actions, _score, _violates, parse_problem
from stt_desktop.storage.project import ProjectError, ProjectRepository, utc_now, uuid7

from .service import SchedulingService, _bits_overlap, _canonical_json


class TimetableService:
    def __init__(self, project: ProjectRepository) -> None:
        self.project = project

    def list_entries(
        self,
        candidate_id: str,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        candidate = self._candidate(candidate_id)
        filters = {"teacher": "e.teacher_id", "homeroom": "e.homeroom_id", "room": "e.room_id"}
        if entity_type and entity_type not in filters:
            raise ProjectError("课表筛选类型只支持 teacher、homeroom 或 room")
        where = "e.candidate_id = ?"
        params: list[Any] = [candidate_id]
        if entity_type and entity_id:
            where += f" AND {filters[entity_type]} = ?"  # noqa: S608 - allowlisted column
            params.append(entity_id)
        rows = self.project.connection.execute(
            f"""
            SELECT e.*, t.name AS teacher_name, h.name AS homeroom_name,
                   s.name AS subject_name, r.name AS room_name, l.label AS lesson_label,
                   l.lesson_index
            FROM timetable_entries e
            LEFT JOIN teachers t ON t.id = e.teacher_id
            LEFT JOIN homerooms h ON h.id = e.homeroom_id
            LEFT JOIN subjects s ON s.id = e.subject_id
            LEFT JOIN rooms r ON r.id = e.room_id
            LEFT JOIN task_lessons l ON l.id = e.task_lesson_id
            WHERE {where}
            ORDER BY e.weekday, e.start_slot, h.name, s.name
            """,  # noqa: S608 - fixed query plus allowlisted filter
            tuple(params),
        ).fetchall()
        snapshot = self.project.connection.execute(
            "SELECT revision FROM data_snapshots WHERE id = ?", (candidate["snapshot_id"],)
        ).fetchone()
        return {
            "candidate": candidate,
            "snapshotRevision": int(snapshot["revision"]),
            "currentRevision": self.project.revision,
            "basedOnOldData": int(snapshot["revision"]) != self.project.revision,
            "items": [dict(row) for row in rows],
        }

    def validate_move(
        self,
        *,
        candidate_id: str,
        task_lesson_id: str,
        weekday: int,
        start_slot: int,
        room_id: str | None,
    ) -> dict[str, Any]:
        candidate = self._candidate(candidate_id)
        snapshot = self._snapshot(candidate["snapshot_id"])
        problem_xml, compile_diagnostics = SchedulingService(self.project)._build_problem(snapshot)
        problem = parse_problem(problem_xml)
        entries = self.project.connection.execute(
            "SELECT * FROM timetable_entries WHERE candidate_id = ? ORDER BY id", (candidate_id,)
        ).fetchall()
        if not entries:
            raise ProjectError("候选没有可调整的课表条目")
        source = next((dict(item) for item in entries if item["task_lesson_id"] == task_lesson_id), None)
        if source is None:
            raise ProjectError("要移动的课次不属于当前候选")
        agents = {agent.class_id: agent for agent in problem.agents}
        agent = agents.get(task_lesson_id)
        if agent is None:
            raise ProjectError("课次不在候选绑定的输入快照中")
        requested_room = room_id or None
        requested = next(
            (
                action
                for action in _actions(agent)
                if action.time.start == start_slot
                and len(action.time.days) >= weekday
                and action.time.days[weekday - 1] == "1"
                and action.room_id == requested_room
            ),
            None,
        )
        conflicts: list[dict[str, Any]] = []
        if requested is None:
            conflicts.append(
                {
                    "code": "OPTION_NOT_ALLOWED",
                    "message": "目标时间或教室不属于该课次的合法选项",
                    "taskLessonId": task_lesson_id,
                }
            )
            return {"valid": False, "conflicts": conflicts, "score": None, "preview": None}

        assignments: dict[str, Action] = {}
        for entry in entries:
            lesson_id = entry["task_lesson_id"]
            current_agent = agents.get(lesson_id)
            if current_agent is None:
                conflicts.append({"code": "SNAPSHOT_ENTRY_MISSING", "message": "候选条目无法映射到输入快照", "taskLessonId": lesson_id})
                continue
            if lesson_id == task_lesson_id:
                assignments[lesson_id] = requested
                continue
            action = next(
                (
                    item
                    for item in _actions(current_agent)
                    if item.time.start == entry["start_slot"]
                    and len(item.time.days) >= entry["weekday"]
                    and item.time.days[entry["weekday"] - 1] == "1"
                    and item.time.weeks == entry["week_bits"]
                    and item.time.length == entry["duration_slots"]
                    and item.room_id == entry["room_id"]
                ),
                None,
            )
            if action is None:
                conflicts.append({"code": "EXISTING_ENTRY_INVALID", "message": "原候选条目已不属于输入快照的合法选项", "taskLessonId": lesson_id})
            else:
                assignments[lesson_id] = action

        for other_id, other in assignments.items():
            if other_id == task_lesson_id:
                continue
            if requested.room_id and requested.room_id == other.room_id and self._overlaps(requested, other):
                conflicts.append({"code": "ROOM_OVERLAP", "message": "目标教室在该时段已有课程", "blockingLessonId": other_id, "roomId": requested.room_id})
            for distribution in problem.distributions:
                if not distribution.required or task_lesson_id not in distribution.class_ids or other_id not in distribution.class_ids:
                    continue
                if _violates(distribution, requested, other):
                    conflicts.append({"code": f"HARD_{distribution.distribution_type.upper()}", "message": distribution.name or "目标位置违反硬约束", "constraintId": distribution.distribution_id, "blockingLessonId": other_id})

        solution_xml = self._solution_xml(candidate_id, assignments)
        validation = SchedulingService(self.project)._validate_solution(snapshot, solution_xml)
        conflicts.extend(validation["hardIssues"])
        metrics = _score(assignments, problem.distributions)
        metrics["distribution_penalty"] += int(validation["softPenalty"])
        metrics["total_score"] += int(validation["softPenalty"])
        preview = {
            "taskLessonId": task_lesson_id,
            "weekday": weekday,
            "startSlot": start_slot,
            "durationSlots": requested.time.length,
            "roomId": requested.room_id,
            "weekBits": requested.time.weeks,
        }
        return {
            "valid": not conflicts,
            "conflicts": conflicts,
            "score": metrics,
            "preview": preview,
            "solutionXml": solution_xml if not conflicts else None,
            "compileWarnings": compile_diagnostics["warnings"],
        }

    def fork_with_move(
        self,
        *,
        candidate_id: str,
        task_lesson_id: str,
        weekday: int,
        start_slot: int,
        room_id: str | None,
        name: str | None = None,
    ) -> dict[str, Any]:
        preview = self.validate_move(
            candidate_id=candidate_id,
            task_lesson_id=task_lesson_id,
            weekday=weekday,
            start_slot=start_slot,
            room_id=room_id,
        )
        if not preview["valid"]:
            raise ManualConflictError(preview["conflicts"])
        parent = self._candidate(candidate_id)
        parent_round = self.project.connection.execute(
            "SELECT * FROM scheduling_rounds WHERE id = ?", (parent["round_id"],)
        ).fetchone()
        round_id = uuid7()
        now = utc_now()
        self.project.connection.execute("BEGIN IMMEDIATE")
        try:
            self.project.connection.execute(
                """
                INSERT INTO scheduling_rounds(id, session_id, snapshot_id, parent_candidate_id,
                    status, time_budget_seconds, random_seed, algorithm, algorithm_config,
                    input_hash, started_at, finished_at, stop_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'succeeded', 10, 0, 'manual', ?, ?, ?, ?, 'manual_adjustment', ?, ?)
                """,
                (round_id, parent_round["session_id"], parent["snapshot_id"], candidate_id, _canonical_json({"algorithm": "manual", "operation": "move"}), parent["input_hash"], now, now, now, now),
            )
            snapshot = self._snapshot(parent["snapshot_id"])
            result = {
                "solution_xml": preview["solutionXml"],
                **preview["score"],
                "elapsed_ms": 0,
                "candidate_count": 1,
                "solver_status": "MANUAL_VALIDATED",
                "feasibility_status": "MANUAL_VALIDATED",
                "quality_status": None,
                "assigned_count": len(snapshot["tables"]["task_lessons"]),
                "class_count": len(snapshot["tables"]["task_lessons"]),
                "unassigned_count": 0,
                "hard_feasibility_proven": True,
                "complete_schedule_feasible": True,
                "log": "手工移动通过本地硬约束校验",
            }
            candidate = SchedulingService(self.project)._persist_candidate(
                round_id=round_id,
                snapshot_id=parent["snapshot_id"],
                input_hash=parent["input_hash"],
                parent_candidate_id=candidate_id,
                result=result,
                snapshot=snapshot,
                compile_diagnostics={"manual": True, "move": preview["preview"], "warnings": preview["compileWarnings"]},
            )
            self.project.connection.execute(
                "UPDATE candidates SET name = ? WHERE id = ?",
                ((name or "手工调整候选").strip() or "手工调整候选", candidate["id"]),
            )
            SchedulingService(self.project)._event(round_id, "manual_move_applied", {"parentCandidateId": candidate_id, **preview["preview"]})
            self.project.connection.execute("COMMIT")
        except Exception:
            self.project.connection.execute("ROLLBACK")
            raise
        return SchedulingService(self.project).get_round(round_id)

    def _candidate(self, candidate_id: str) -> dict[str, Any]:
        row = self.project.connection.execute(
            "SELECT * FROM candidates WHERE id = ? AND status = 'valid'", (candidate_id,)
        ).fetchone()
        if not row:
            raise ProjectError("候选不存在或不可用于课表操作")
        return dict(row)

    def _snapshot(self, snapshot_id: str) -> dict[str, Any]:
        row = self.project.connection.execute(
            "SELECT payload_path FROM data_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
        if not row:
            raise ProjectError("候选绑定的数据快照不存在")
        path = (self.project.project_directory / row["payload_path"]).resolve()
        if self.project.project_directory not in path.parents:
            raise ProjectError("数据快照路径越界")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _overlaps(left: Action, right: Action) -> bool:
        return (
            _bits_overlap(left.time.weeks, right.time.weeks)
            and _bits_overlap(left.time.days, right.time.days)
            and left.time.start < right.time.start + right.time.length
            and right.time.start < left.time.start + left.time.length
        )

    @staticmethod
    def _solution_xml(run_id: str, assignments: dict[str, Action]) -> str:
        root = Element("solution", {"run": run_id, "algorithm": "manual"})
        for lesson_id in sorted(assignments):
            action = assignments[lesson_id]
            attrs = {
                "id": lesson_id,
                "days": action.time.days,
                "weeks": action.time.weeks,
                "start": str(action.time.start),
                "length": str(action.time.length),
            }
            if action.time.period_index is not None:
                attrs["periodIndex"] = str(action.time.period_index)
            if action.room_id:
                attrs["room"] = action.room_id
            SubElement(root, "class", attrs)
        return tostring(root, encoding="unicode")


class ManualConflictError(ProjectError):
    def __init__(self, conflicts: list[dict[str, Any]]) -> None:
        super().__init__("手工移动存在硬冲突，未创建候选")
        self.conflicts = conflicts
