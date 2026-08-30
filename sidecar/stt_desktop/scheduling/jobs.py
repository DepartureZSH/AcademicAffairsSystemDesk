from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from stt_desktop.scheduler_engine import run_cp_sat_v1
from stt_desktop.storage.project import ProjectError, ProjectRepository, uuid7

from .service import SchedulingService


def _solver_worker(
    problem_path: str, request_path: str, result_path: str, round_id: str
) -> None:
    """Run OR-Tools in an isolated process and publish one atomic result file."""
    target = Path(result_path)
    temporary = target.with_name(f".{target.name}.{uuid7()}.tmp")
    try:
        problem_xml = Path(problem_path).read_text(encoding="utf-8")
        config = json.loads(Path(request_path).read_text(encoding="utf-8"))
        result = {"ok": True, "result": run_cp_sat_v1(problem_xml, round_id, config)}
    except BaseException as exc:  # worker must always publish a bounded failure envelope
        result = {
            "ok": False,
            "errorType": type(exc).__name__[:100],
            "message": str(exc)[:1000],
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


@dataclass
class SolverJob:
    round_id: str
    project: ProjectRepository
    process: multiprocessing.Process
    request_path: Path
    result_path: Path
    snapshot: dict[str, Any]
    compile_diagnostics: dict[str, Any]
    monitor_task: asyncio.Task[None] | None = None
    cancel_requested: bool = False


class SchedulingJobManager:
    """Own isolated solver processes while keeping the local API responsive."""

    def __init__(
        self,
        worker_target: Callable[[str, str, str, str], None] = _solver_worker,
    ) -> None:
        self._jobs: dict[str, SolverJob] = {}
        self._worker_target = worker_target

    @property
    def active_round_ids(self) -> tuple[str, ...]:
        return tuple(self._jobs)

    def has_active_job(self) -> bool:
        return bool(self._jobs)

    async def start_round(
        self,
        project: ProjectRepository,
        *,
        time_budget_seconds: int,
        random_seed: int,
        session_id: str | None,
        parent_candidate_id: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        if self._jobs:
            raise ProjectError("当前已有排课轮次运行，请等待完成或先取消")
        service = SchedulingService(project)
        prepared = service.prepare_round(
            time_budget_seconds=time_budget_seconds,
            random_seed=random_seed,
            session_id=session_id,
            parent_candidate_id=parent_candidate_id,
            name=name,
        )
        if not prepared["solverReady"]:
            return prepared["round"]

        round_id = str(prepared["roundId"])
        problem_path = project.project_directory / f"artifacts/problem/{round_id}.xml"
        request_path = project.project_directory / f"artifacts/problem/.{round_id}-worker.json"
        result_path = project.project_directory / f"artifacts/solution/.{round_id}-worker.json"
        self._write_json(request_path, prepared["solverConfig"])
        context = multiprocessing.get_context("spawn")
        process = context.Process(
            target=self._worker_target,
            args=(str(problem_path), str(request_path), str(result_path), round_id),
            name=f"stt-solver-{round_id[:8]}",
            daemon=True,
        )
        job = SolverJob(
            round_id=round_id,
            project=project,
            process=process,
            request_path=request_path,
            result_path=result_path,
            snapshot=prepared["snapshot"],
            compile_diagnostics=prepared["compileDiagnostics"],
        )
        self._jobs[round_id] = job
        try:
            process.start()
        except Exception as exc:
            self._jobs.pop(round_id, None)
            self._cleanup_files(job)
            service.mark_failed(round_id, "SOLVER_PROCESS_START_FAILED", str(exc))
            raise ProjectError("无法启动本地算法工作进程") from exc
        service.record_event(round_id, "solver_worker_started", {"isolatedProcess": True})
        job.monitor_task = asyncio.create_task(
            self._monitor(job), name=f"monitor-solver-{round_id[:8]}"
        )
        return service.get_round(round_id)

    async def cancel_round(self, round_id: str) -> dict[str, Any]:
        job = self._jobs.get(round_id)
        if not job:
            raise ProjectError("该排课轮次没有正在运行的本地算法进程")
        job.cancel_requested = True
        if job.process.is_alive():
            job.process.terminate()
            await asyncio.to_thread(job.process.join, 5)
            if job.process.is_alive():
                job.process.kill()
                await asyncio.to_thread(job.process.join, 1)
        service = SchedulingService(job.project)
        current = service.get_round(round_id)
        if current["status"] not in {"succeeded", "infeasible", "failed_recoverable"}:
            current = service.mark_cancelled(round_id)
        return current

    async def shutdown(self) -> None:
        for round_id in tuple(self._jobs):
            try:
                await self.cancel_round(round_id)
            except Exception:
                job = self._jobs.get(round_id)
                if job and job.process.is_alive():
                    job.process.kill()
        tasks = [job.monitor_task for job in self._jobs.values() if job.monitor_task]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _monitor(self, job: SolverJob) -> None:
        try:
            await asyncio.to_thread(job.process.join)
            service = SchedulingService(job.project)
            if job.cancel_requested:
                current = service.get_round(job.round_id)
                if current["status"] not in {
                    "succeeded",
                    "infeasible",
                    "cancelled",
                    "failed_recoverable",
                }:
                    service.mark_cancelled(job.round_id)
                return
            if job.process.exitcode != 0 or not job.result_path.is_file():
                service.mark_failed(
                    job.round_id,
                    "SOLVER_PROCESS_EXITED",
                    f"算法工作进程异常退出（代码 {job.process.exitcode}）",
                )
                return
            try:
                envelope = json.loads(job.result_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                service.mark_failed(job.round_id, "SOLVER_RESULT_INVALID", str(exc))
                return
            if not envelope.get("ok") or not isinstance(envelope.get("result"), dict):
                service.mark_failed(
                    job.round_id,
                    "SOLVER_WORKER_ERROR",
                    str(envelope.get("message") or "算法工作进程未返回有效结果"),
                )
                return
            try:
                service.complete_round(
                    job.round_id,
                    envelope["result"],
                    snapshot=job.snapshot,
                    compile_diagnostics=job.compile_diagnostics,
                )
            except Exception as exc:
                service.mark_failed(job.round_id, "SOLVER_FINALIZE_ERROR", str(exc))
        finally:
            self._jobs.pop(job.round_id, None)
            self._cleanup_files(job)

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_name(f".{path.name}.{uuid7()}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _cleanup_files(job: SolverJob) -> None:
        expected = {
            (job.project.project_directory / "artifacts/problem").resolve(),
            (job.project.project_directory / "artifacts/solution").resolve(),
        }
        for path in (job.request_path, job.result_path):
            resolved = path.resolve()
            if resolved.parent in expected and resolved.name.startswith("."):
                resolved.unlink(missing_ok=True)
