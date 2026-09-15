import base64
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from stt_desktop.storage import ProjectError
from stt_desktop.agent.service import AgentService
from stt_desktop.agent.upstream.official_workbooks import (
    workbook_bytes,
    planning_collection_workbook_bytes,
)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str


class Start(Request):
    scene: Literal["rooms", "school", "planning", "timetable", "constraints"]
    content: str = Field(min_length=1, max_length=250000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)


class AttachmentRequest(Request):
    scene: Literal["rooms", "school", "planning", "timetable", "constraints"]
    filename: str = Field(max_length=250)
    file: str = Field(max_length=2800000)


class Step(Request):
    step: int = Field(ge=0, le=12)
    message: dict


class Clear(Request):
    scene: Literal["rooms", "school", "planning", "timetable", "constraints"]


class ExpectedWrite(Request):
    items: list[dict] = Field(min_length=1, max_length=5000)


class ScopeStart(Request):
    text: str = Field(min_length=1, max_length=4000)


class ScopeResult(Request):
    message: dict


class Workbook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene: Literal["rooms", "school", "planning", "constraints"]
    template_id: str = "blank"
    destination: str | None = None


class WorkflowStart(Request):
    flow: str = Field(max_length=80)
    payload: dict


class WorkflowStep(Request):
    step: int = Field(ge=0, le=6)
    response: dict


def build_agent_router(state, workspace):
    router = APIRouter(prefix="/v1/ai")

    def service(project_id):
        project = state.require_project()
        if project.project_info()["id"] != project_id:
            raise ProjectError("当前项目已切换，请重新打开 AI 对话")
        return AgentService(project, workspace)

    @router.get("/session")
    async def session(project_id: str, scene: str):
        return service(project_id).session(scene)

    @router.post("/turns")
    async def start(request: Start):
        try:
            return service(request.project_id).start(
                request.scene, request.content, request.attachment_ids
            )
        except ValueError as exc:
            raise ProjectError(str(exc)) from exc

    @router.post("/attachments")
    async def attachment(request: AttachmentRequest):
        from stt_desktop.agent.attachments import store_attachment
        from stt_desktop.agent.workflows import decode_file

        return store_attachment(
            service(request.project_id),
            request.scene,
            request.filename,
            decode_file(request.model_dump()),
        )

    @router.post("/workflows")
    async def workflow(request: WorkflowStart):
        from stt_desktop.agent.workflows import run_workflow

        try:
            return run_workflow(service(request.project_id), request.flow, request.payload)
        except ValueError as exc:
            raise ProjectError(str(exc)) from exc

    @router.post("/workflows/{identifier}")
    async def workflow_step(identifier: str, request: WorkflowStep):
        from stt_desktop.agent.workflows import run_workflow

        try:
            return run_workflow(
                service(request.project_id),
                identifier=identifier,
                step=request.step,
                response=request.response,
            )
        except ValueError as exc:
            raise ProjectError(str(exc)) from exc

    @router.post("/clear")
    async def clear(request: Clear):
        return service(request.project_id).clear(request.scene)

    @router.get("/expected-times")
    async def expected_times(project_id: str):
        from stt_desktop.agent.expected_times import read_expected

        return read_expected(service(project_id).project)

    @router.post("/scope-search")
    async def scope_search(request: ScopeStart):
        from stt_desktop.agent.scope_search import prepare_scope

        return prepare_scope(service(request.project_id).project, request.text)

    @router.post("/scope-search/{identifier}")
    async def scope_result(identifier: str, request: ScopeResult):
        from stt_desktop.agent.scope_search import finish_scope

        return finish_scope(service(request.project_id).project, identifier, request.message)

    @router.post("/expected-times")
    async def save_expected_times(request: ExpectedWrite):
        from stt_desktop.agent.expected_times import apply_expected

        return apply_expected(service(request.project_id).project, workspace, request.items)

    @router.post("/turns/{identifier}/step")
    async def step(identifier: str, request: Step):
        try:
            return service(request.project_id).step(identifier, request.step, request.message)
        except ValueError as exc:
            raise ProjectError(str(exc)) from exc

    @router.post("/actions/{identifier}/confirm")
    async def confirm(identifier: str, request: Request):
        return service(request.project_id).confirm(identifier)

    @router.post("/actions/{identifier}/reject")
    async def reject(identifier: str, request: Request):
        return service(request.project_id).reject(identifier)

    @router.post("/workbook")
    async def workbook(request: Workbook):
        data = (
            planning_collection_workbook_bytes()
            if request.scene == "planning"
            else workbook_bytes(request.scene)
            if request.scene != "constraints"
            else b""
        )
        if request.scene == "constraints":
            from stt_desktop.agent.upstream.constraint_workbooks import build_workbook

            data = build_workbook(request.template_id)
        if request.destination:
            path = Path(request.destination)
            if not path.is_absolute() or path.suffix.lower() != ".xlsx":
                raise ProjectError("请选择完整的 Excel 保存路径")
            try:
                with path.open("xb") as handle:
                    handle.write(data)
            except FileExistsError as exc:
                raise ProjectError("文件已存在，请选择其他文件名，避免覆盖已有资料") from exc
            return {"saved": True}
        return {
            "data": base64.b64encode(data).decode(),
            "filename": {
                "rooms": "教室资料模板.xlsx",
                "school": "学校资料模板.xlsx",
                "planning": "课程计划采集模板.xlsx",
                "constraints": "约束填写模板.xlsx",
            }[request.scene],
        }

    return router
