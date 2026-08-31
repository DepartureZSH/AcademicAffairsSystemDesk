from __future__ import annotations

import hmac
import ipaddress
import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from stt_desktop.backups import BackupService
from stt_desktop.project_archives import ProjectArchiveService
from stt_desktop.scheduling import (
    ManualConflictError,
    SchedulingJobManager,
    SchedulingService,
    TimetableService,
)
from stt_desktop.service_config import AppServiceConfig
from stt_desktop.storage import (
    ProjectError,
    ProjectLockedError,
    ProjectRepository,
    ProjectSchemaTooNewError,
    ProjectWorkspace,
    RevisionConflictError,
)
from stt_desktop.storage.schema import SCHEMA_VERSION
from stt_desktop.transfers import ExportService, ImportService

PROTOCOL_VERSION = "1"
DEFAULT_ALLOWED_ORIGINS = frozenset(
    {"tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"}
)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_name: str = Field(min_length=1, max_length=200)
    confirmed: bool


class EntityWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    data: dict[str, Any]


class SchedulingRoundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time_budget_seconds: int = Field(default=60, ge=10, le=1800)
    random_seed: int = Field(default=0, ge=0, le=2_147_483_647)
    session_id: str | None = None
    parent_candidate_id: str | None = None
    name: str | None = Field(default=None, max_length=200)


class ManualMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    task_lesson_id: str
    weekday: int = Field(ge=1, le=7)
    start_slot: int = Field(ge=0)
    room_id: str | None = None
    name: str | None = Field(default=None, max_length=200)


class CandidateExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    export_type: str
    destination_path: str | None = Field(default=None, max_length=32_767)
    overwrite: bool = False
    entity_type: str | None = Field(default=None, pattern="^(teacher|homeroom|room|grade)$")
    entity_id: str | None = Field(default=None, max_length=200)
    week_mode: str = Field(default="all", pattern="^(all|odd|even)$")
    layout: str = Field(default="landscape", pattern="^(landscape|portrait)$")
    color_mode: str = Field(default="color", pattern="^(color|grayscale)$")


class BackupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="manual", min_length=1, max_length=200)
    retained: bool = False
    destination_path: str | None = Field(default=None, max_length=32_767)
    overwrite: bool = False


class BackupRetainedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retained: bool


class BackupRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archive_path: str | None = Field(default=None, min_length=1, max_length=32_767)
    backup_id: str | None = None
    restored_name: str | None = Field(default=None, max_length=200)
    confirmed: bool


class ProjectArchiveExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination_path: str = Field(min_length=1, max_length=32_767)
    overwrite: bool = False


class ProjectArchiveImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archive_path: str = Field(min_length=1, max_length=32_767)
    imported_name: str | None = Field(default=None, max_length=200)
    confirmed: bool


class ProjectCloneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


class ImportPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_path: str = Field(min_length=1, max_length=32_767)
    entity_type: str
    mapping: dict[str, str] | None = None
    sheet_name: str | None = Field(default=None, max_length=255)


class ImportRemapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mapping: dict[str, str]
    sheet_name: str | None = Field(default=None, max_length=255)


class ImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)


class ImportTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: str
    file_format: str
    destination_path: str = Field(min_length=1, max_length=32_767)
    overwrite: bool = False


@dataclass
class SidecarState:
    workspace: ProjectWorkspace
    services: AppServiceConfig
    current_project: ProjectRepository | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)

    def close_current(self) -> None:
        with self.lock:
            if self.current_project is not None:
                self.current_project.close()
                self.current_project = None

    def require_project(self) -> ProjectRepository:
        with self.lock:
            if self.current_project is None:
                raise HTTPException(status_code=409, detail=("NO_PROJECT_OPEN", "当前没有打开项目"))
            return self.current_project


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _error_response(
    status_code: int,
    code: str,
    message: str,
    correlation_id: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "correlationId": correlation_id,
            }
        },
        headers={"X-Correlation-ID": correlation_id},
    )


def create_app(
    *,
    workspace: ProjectWorkspace,
    services: AppServiceConfig,
    session_token: str,
    allowed_origins: frozenset[str] = DEFAULT_ALLOWED_ORIGINS,
    enforce_loopback: bool = True,
    shutdown_requested: threading.Event | None = None,
) -> FastAPI:
    if len(session_token.encode("utf-8")) < 32:
        raise ValueError("sidecar 会话令牌至少需要 256 位熵")
    state = SidecarState(workspace=workspace, services=services)
    scheduling_jobs = SchedulingJobManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await scheduling_jobs.shutdown()
        state.close_current()

    app = FastAPI(
        title="时奕教务排课本地服务",
        version=PROTOCOL_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.sidecar = state

    @app.middleware("http")
    async def secure_local_request(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        if enforce_loopback and not _is_loopback(request.client.host if request.client else None):
            return _error_response(403, "NON_LOOPBACK_CLIENT", "只允许本机回环请求", correlation_id)
        origin = request.headers.get("Origin")
        if origin is not None and origin not in allowed_origins:
            return _error_response(403, "ORIGIN_REJECTED", "请求 Origin 不在白名单", correlation_id)
        authorization = request.headers.get("Authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied, session_token):
            return _error_response(401, "SESSION_TOKEN_INVALID", "本机会话令牌无效", correlation_id)
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RevisionConflictError)
    async def revision_conflict(request: Request, error: RevisionConflictError):
        return _error_response(
            409,
            "REVISION_CONFLICT",
            str(error),
            request.state.correlation_id,
            {"expected": error.expected, "actual": error.actual},
        )

    @app.exception_handler(ProjectLockedError)
    async def project_locked(request: Request, error: ProjectLockedError):
        return _error_response(
            423, "PROJECT_LOCKED", str(error), request.state.correlation_id
        )

    @app.exception_handler(ProjectSchemaTooNewError)
    async def schema_too_new(request: Request, error: ProjectSchemaTooNewError):
        return _error_response(
            409, "PROJECT_SCHEMA_TOO_NEW", str(error), request.state.correlation_id
        )

    @app.exception_handler(ProjectError)
    async def project_error(request: Request, error: ProjectError):
        return _error_response(400, "PROJECT_ERROR", str(error), request.state.correlation_id)

    @app.exception_handler(ManualConflictError)
    async def manual_conflict(request: Request, error: ManualConflictError):
        return _error_response(
            409,
            "MANUAL_MOVE_CONFLICT",
            str(error),
            request.state.correlation_id,
            {"conflicts": error.conflicts},
        )

    @app.exception_handler(sqlite3.IntegrityError)
    async def data_integrity_error(request: Request, _: sqlite3.IntegrityError):
        return _error_response(
            400,
            "DATA_INTEGRITY_ERROR",
            "数据违反唯一性、引用或范围约束",
            request.state.correlation_id,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        safe_details = [
            {"location": list(item["loc"]), "type": item["type"], "message": item["msg"]}
            for item in error.errors()
        ]
        return _error_response(
            422,
            "REQUEST_INVALID",
            "请求参数无效",
            request.state.correlation_id,
            {"issues": safe_details},
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        if isinstance(error.detail, tuple) and len(error.detail) == 2:
            code, message = error.detail
        else:
            code, message = "HTTP_ERROR", str(error.detail)
        return _error_response(error.status_code, code, message, request.state.correlation_id)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, _: Exception):
        return _error_response(
            500,
            "INTERNAL_ERROR",
            "本地服务发生未预期错误",
            request.state.correlation_id,
        )

    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "protocolVersion": PROTOCOL_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "serviceModes": {
                name: service.mode for name, service in services.services.items()
            },
            "projectOpen": state.current_project is not None,
            "activeSchedulingRounds": list(scheduling_jobs.active_round_ids),
        }

    @app.post("/v1/runtime/shutdown", status_code=202)
    async def shutdown_runtime(background_tasks: BackgroundTasks) -> dict[str, str]:
        if shutdown_requested is None:
            raise HTTPException(
                status_code=503,
                detail=("SHUTDOWN_UNAVAILABLE", "当前运行模式不支持远程关闭"),
            )
        background_tasks.add_task(shutdown_requested.set)
        return {"status": "shutting_down"}

    @app.get("/v1/projects")
    async def list_projects() -> dict[str, Any]:
        return {"projects": workspace.list_projects()}

    @app.post("/v1/projects", status_code=201)
    async def create_project(request: ProjectCreateRequest) -> dict[str, Any]:
        if scheduling_jobs.has_active_job():
            raise ProjectError("排课轮次运行期间不能切换项目，请先取消或等待完成")
        with state.lock:
            state.close_current()
            state.current_project = workspace.create_project(request.name)
            return {
                "project": state.current_project.project_info(),
                "revision": state.current_project.revision,
            }

    @app.post("/v1/projects/{project_id}/open")
    async def open_project(project_id: str) -> dict[str, Any]:
        if scheduling_jobs.has_active_job():
            raise ProjectError("排课轮次运行期间不能切换项目，请先取消或等待完成")
        with state.lock:
            current = state.current_project
            if current and current.project_info()["id"] == project_id:
                return {"project": current.project_info(), "revision": current.revision}
            state.close_current()
            state.current_project = workspace.open_project(project_id)
            SchedulingService(state.current_project).recover_interrupted_rounds()
            return {
                "project": state.current_project.project_info(),
                "revision": state.current_project.revision,
            }

    @app.delete("/v1/projects/{project_id}")
    async def delete_project(
        project_id: str, request: ProjectDeleteRequest
    ) -> dict[str, Any]:
        if not request.confirmed:
            raise ProjectError("删除项目必须由用户明确确认")
        if scheduling_jobs.has_active_job():
            raise ProjectError("排课轮次运行期间不能删除项目，请先取消或等待完成")
        with state.lock:
            current = state.current_project
            if current and current.project_info()["id"] == project_id:
                raise ProjectError("当前项目正在打开，请先关闭后再删除")
            return {"deleted": workspace.delete_project(project_id, request.expected_name)}

    @app.post("/v1/projects/current/close", status_code=204, response_class=Response)
    async def close_project() -> Response:
        if scheduling_jobs.has_active_job():
            raise ProjectError("排课轮次运行期间不能关闭项目，请先取消或等待完成")
        state.close_current()
        return Response(status_code=204)

    @app.get("/v1/projects/current")
    async def current_project() -> dict[str, Any]:
        project = state.require_project()
        return {"project": project.project_info(), "revision": project.revision}

    @app.get("/v1/data/{entity_type}")
    async def list_entities(
        entity_type: str,
        limit: int | None = Query(default=None, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        project = state.require_project()
        if limit is not None:
            items, total = project.list_entities_page(
                entity_type, limit=limit, offset=offset
            )
            return {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
                "revision": project.revision,
            }
        return {
            "items": project.list_entities(entity_type),
            "total": None,
            "limit": None,
            "offset": 0,
            "revision": project.revision,
        }

    @app.get("/v1/data/{entity_type}/{entity_id}")
    async def get_entity(entity_type: str, entity_id: str) -> dict[str, Any]:
        project = state.require_project()
        entity = project.get_entity(entity_type, entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail=("ENTITY_NOT_FOUND", "实体不存在"))
        return {"item": entity, "revision": project.revision}

    @app.put("/v1/data/{entity_type}")
    async def save_entity(entity_type: str, request: EntityWriteRequest) -> dict[str, Any]:
        project = state.require_project()
        item, revision = project.save_entity(
            entity_type, request.data, request.expected_revision
        )
        backup_warning = _daily_backup_warning(project, workspace)
        return {"item": item, "revision": revision, "backupWarning": backup_warning}

    @app.put("/v1/planning/tasks")
    async def save_teaching_task_bundle(request: EntityWriteRequest) -> dict[str, Any]:
        project = state.require_project()
        task, lessons, revision = project.save_teaching_task_bundle(
            request.data, request.expected_revision
        )
        backup_warning = _daily_backup_warning(project, workspace)
        return {
            "task": task,
            "lessons": lessons,
            "revision": revision,
            "backupWarning": backup_warning,
        }

    @app.delete("/v1/data/{entity_type}/{entity_id}")
    async def delete_entity(
        entity_type: str,
        entity_id: str,
        expected_revision: int = Query(ge=0),
    ) -> dict[str, Any]:
        project = state.require_project()
        if project.revision != expected_revision:
            raise RevisionConflictError(expected_revision, project.revision)
        BackupService(project, workspace).create_backup(reason="pre-destructive")
        revision = project.delete_entity(entity_type, entity_id, expected_revision)
        return {"deletedId": entity_id, "revision": revision}

    @app.post("/v1/validation/preflight")
    async def validate_project_before_scheduling() -> dict[str, Any]:
        project = state.require_project()
        return SchedulingService(project).validate_current_project()

    @app.post("/v1/scheduling/rounds", status_code=201)
    async def run_scheduling_round(request: SchedulingRoundRequest) -> dict[str, Any]:
        project = state.require_project()
        result = await scheduling_jobs.start_round(
            project,
            time_budget_seconds=request.time_budget_seconds,
            random_seed=request.random_seed,
            session_id=request.session_id,
            parent_candidate_id=request.parent_candidate_id,
            name=request.name,
        )
        return {"round": result, "revision": project.revision}

    @app.post("/v1/scheduling/rounds/{round_id}/cancel")
    async def cancel_scheduling_round(round_id: str) -> dict[str, Any]:
        project = state.require_project()
        result = await scheduling_jobs.cancel_round(round_id)
        return {"round": result, "revision": project.revision}

    @app.get("/v1/scheduling/sessions")
    async def list_scheduling_sessions() -> dict[str, Any]:
        project = state.require_project()
        return {"items": SchedulingService(project).list_sessions(), "revision": project.revision}

    @app.get("/v1/scheduling/rounds")
    async def list_scheduling_rounds(session_id: str | None = None) -> dict[str, Any]:
        project = state.require_project()
        return {
            "items": SchedulingService(project).list_rounds(session_id),
            "revision": project.revision,
        }

    @app.get("/v1/scheduling/rounds/{round_id}")
    async def get_scheduling_round(round_id: str) -> dict[str, Any]:
        project = state.require_project()
        return {"round": SchedulingService(project).get_round(round_id), "revision": project.revision}

    @app.get("/v1/scheduling/candidates")
    async def list_scheduling_candidates() -> dict[str, Any]:
        project = state.require_project()
        return {"items": SchedulingService(project).list_candidates(), "revision": project.revision}

    @app.get("/v1/timetables/{candidate_id}")
    async def get_timetable(
        candidate_id: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        project = state.require_project()
        result = TimetableService(project).list_entries(
            candidate_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        return {**result, "revision": project.revision}

    @app.post("/v1/timetables/validate-move")
    async def validate_manual_move(request: ManualMoveRequest) -> dict[str, Any]:
        project = state.require_project()
        return TimetableService(project).validate_move(
            candidate_id=request.candidate_id,
            task_lesson_id=request.task_lesson_id,
            weekday=request.weekday,
            start_slot=request.start_slot,
            room_id=request.room_id,
        )

    @app.post("/v1/timetables/manual-fork", status_code=201)
    async def apply_manual_move(request: ManualMoveRequest) -> dict[str, Any]:
        project = state.require_project()
        result = TimetableService(project).fork_with_move(
            candidate_id=request.candidate_id,
            task_lesson_id=request.task_lesson_id,
            weekday=request.weekday,
            start_slot=request.start_slot,
            room_id=request.room_id,
            name=request.name,
        )
        return {"round": result, "revision": project.revision}

    @app.post("/v1/exports", status_code=201)
    async def export_candidate(request: CandidateExportRequest) -> dict[str, Any]:
        project = state.require_project()
        result = ExportService(project).export_candidate(
            candidate_id=request.candidate_id,
            export_type=request.export_type,
            destination_path=request.destination_path,
            overwrite=request.overwrite,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            week_mode=request.week_mode,
            layout=request.layout,
            color_mode=request.color_mode,
        )
        return {"export": result, "revision": project.revision}

    @app.get("/v1/exports")
    async def list_exports() -> dict[str, Any]:
        project = state.require_project()
        return {"items": ExportService(project).list_exports(), "revision": project.revision}

    @app.post("/v1/backups", status_code=201)
    async def create_backup(request: BackupCreateRequest) -> dict[str, Any]:
        project = state.require_project()
        result = BackupService(project, workspace).create_backup(
            reason=request.reason,
            retained=request.retained,
            destination_path=request.destination_path,
            overwrite=request.overwrite,
        )
        return {"backup": result, "revision": project.revision}

    @app.get("/v1/backups")
    async def list_backups() -> dict[str, Any]:
        project = state.require_project()
        return {
            "items": BackupService(project, workspace).list_backups(),
            "revision": project.revision,
        }

    @app.post("/v1/backups/{backup_id}/verify")
    async def verify_backup(backup_id: str) -> dict[str, Any]:
        project = state.require_project()
        return BackupService(project, workspace).verify_record(backup_id)

    @app.put("/v1/backups/{backup_id}/retained")
    async def retain_backup(
        backup_id: str, request: BackupRetainedRequest
    ) -> dict[str, Any]:
        project = state.require_project()
        item = BackupService(project, workspace).set_retained(
            backup_id, request.retained
        )
        return {"item": item, "revision": project.revision}

    @app.post("/v1/backups/restore", status_code=201)
    async def restore_backup(request: BackupRestoreRequest) -> dict[str, Any]:
        if scheduling_jobs.has_active_job():
            raise ProjectError("排课轮次运行期间不能恢复项目，请先取消或等待完成")
        if not request.confirmed:
            raise HTTPException(
                status_code=409,
                detail=("RESTORE_CONFIRMATION_REQUIRED", "恢复前必须明确确认所选备份路径"),
            )
        project = state.require_project()
        if bool(request.archive_path) == bool(request.backup_id):
            raise HTTPException(
                status_code=422,
                detail=("RESTORE_SOURCE_INVALID", "必须且只能指定备份记录或外部备份文件之一"),
            )
        archive_path = request.archive_path
        if request.backup_id:
            archive_path = str(
                BackupService(project, workspace).record_path(request.backup_id)
            )
        restored = BackupService.restore_backup(
            workspace,
            str(archive_path),
            restored_name=request.restored_name,
        )
        with state.lock:
            state.close_current()
            state.current_project = workspace.open_project(restored["projectId"])
            SchedulingService(state.current_project).recover_interrupted_rounds()
            return {
                "restored": restored,
                "project": state.current_project.project_info(),
                "revision": state.current_project.revision,
            }

    @app.post("/v1/project-archives/export", status_code=201)
    async def export_project_archive(
        request: ProjectArchiveExportRequest,
    ) -> dict[str, Any]:
        project = state.require_project()
        package = ProjectArchiveService(project, workspace).export_project(
            request.destination_path, overwrite=request.overwrite
        )
        return {"package": package, "revision": project.revision}

    @app.post("/v1/projects/current/clone", status_code=201)
    async def clone_current_project(request: ProjectCloneRequest) -> dict[str, Any]:
        if scheduling_jobs.has_active_job():
            raise ProjectError("排课轮次运行期间不能另存项目，请先取消或等待完成")
        project = state.require_project()
        cloned = ProjectArchiveService(project, workspace).clone_project(request.name)
        with state.lock:
            state.close_current()
            state.current_project = workspace.open_project(cloned["projectId"])
            SchedulingService(state.current_project).recover_interrupted_rounds()
            return {
                "cloned": cloned,
                "project": state.current_project.project_info(),
                "revision": state.current_project.revision,
            }

    @app.post("/v1/project-archives/import", status_code=201)
    async def import_project_archive(
        request: ProjectArchiveImportRequest,
    ) -> dict[str, Any]:
        if scheduling_jobs.has_active_job():
            raise ProjectError("排课轮次运行期间不能导入项目，请先取消或等待完成")
        if not request.confirmed:
            raise HTTPException(
                status_code=409,
                detail=("PROJECT_IMPORT_CONFIRMATION_REQUIRED", "导入项目前必须明确确认"),
            )
        imported = ProjectArchiveService.import_project(
            workspace,
            request.archive_path,
            imported_name=request.imported_name,
        )
        with state.lock:
            state.close_current()
            state.current_project = workspace.open_project(imported["projectId"])
            SchedulingService(state.current_project).recover_interrupted_rounds()
            return {
                "imported": imported,
                "project": state.current_project.project_info(),
                "revision": state.current_project.revision,
            }

    @app.post("/v1/imports/preview", status_code=201)
    async def preview_import(request: ImportPreviewRequest) -> dict[str, Any]:
        project = state.require_project()
        preview = ImportService(project, workspace).preview_file(
            source_path=request.source_path,
            entity_type=request.entity_type,
            mapping=request.mapping,
            sheet_name=request.sheet_name,
        )
        return {"preview": preview, "revision": project.revision}

    @app.post("/v1/imports/template", status_code=201)
    async def create_import_template(request: ImportTemplateRequest) -> dict[str, Any]:
        project = state.require_project()
        result = ImportService(project, workspace).create_template(
            entity_type=request.entity_type,
            file_format=request.file_format,
            destination_path=request.destination_path,
            overwrite=request.overwrite,
        )
        return {"template": result, "revision": project.revision}

    @app.post("/v1/imports/{job_id}/remap")
    async def remap_import(job_id: str, request: ImportRemapRequest) -> dict[str, Any]:
        project = state.require_project()
        preview = ImportService(project, workspace).remap_preview(
            job_id,
            mapping=request.mapping,
            sheet_name=request.sheet_name,
        )
        return {"preview": preview, "revision": project.revision}

    @app.post("/v1/imports/{job_id}/confirm")
    async def confirm_import(job_id: str, request: ImportConfirmRequest) -> dict[str, Any]:
        project = state.require_project()
        result = ImportService(project, workspace).confirm_import(
            job_id, request.expected_revision
        )
        return {"import": result, "revision": result["revision"]}

    @app.post("/v1/imports/{job_id}/abandon")
    async def abandon_import(job_id: str) -> dict[str, Any]:
        project = state.require_project()
        return {
            "import": ImportService(project, workspace).abandon(job_id),
            "revision": project.revision,
        }

    @app.get("/v1/imports")
    async def list_imports() -> dict[str, Any]:
        project = state.require_project()
        return {
            "items": ImportService(project, workspace).list_imports(),
            "revision": project.revision,
        }

    return app


def _daily_backup_warning(
    project: ProjectRepository, workspace: ProjectWorkspace
) -> str | None:
    try:
        BackupService(project, workspace).create_daily_backup_if_needed()
        return None
    except Exception:
        return "本次业务数据已保存，但每日自动备份失败；请在备份恢复页重试"
