from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from stt_desktop.api.app import _is_loopback, create_app
from stt_desktop.service_config import load_service_config
from stt_desktop.storage import ProjectWorkspace


TOKEN = "a" * 64


def client(tmp_path: Path) -> TestClient:
    root = Path(__file__).resolve().parents[1]
    app = create_app(
        workspace=ProjectWorkspace(tmp_path / "workspace"),
        services=load_service_config(root / "config" / "services.yaml"),
        session_token=TOKEN,
        enforce_loopback=False,
    )
    return TestClient(app)


def headers(origin: str | None = "tauri://localhost") -> dict[str, str]:
    result = {"Authorization": f"Bearer {TOKEN}"}
    if origin is not None:
        result["Origin"] = origin
    return result


def test_loopback_detection() -> None:
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("::1")
    assert _is_loopback("localhost")
    assert not _is_loopback("192.168.1.20")
    assert not _is_loopback("example.com")


def test_token_and_origin_are_required(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        missing = api.get("/v1/health")
        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "SESSION_TOKEN_INVALID"

        rejected = api.get("/v1/health", headers=headers("https://evil.example"))
        assert rejected.status_code == 403
        assert rejected.json()["error"]["code"] == "ORIGIN_REJECTED"

        accepted = api.get("/v1/health", headers=headers())
        assert accepted.status_code == 200
        assert accepted.json()["protocolVersion"] == "1"
        assert accepted.headers["cache-control"] == "no-store"


def test_project_and_entity_flow_with_revision_conflict(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        created = api.post("/v1/projects", headers=headers(), json={"name": "API 测试"})
        assert created.status_code == 201
        project_id = created.json()["project"]["id"]
        assert created.json()["revision"] == 0

        saved = api.put(
            "/v1/data/teacher",
            headers=headers(origin=None),
            json={"expected_revision": 0, "data": {"name": "教师一"}},
        )
        assert saved.status_code == 200
        teacher_id = saved.json()["item"]["id"]
        assert saved.json()["revision"] == 1

        stale = api.put(
            "/v1/data/teacher",
            headers=headers(),
            json={
                "expected_revision": 0,
                "data": {"id": teacher_id, "name": "旧页面覆盖"},
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
        assert stale.json()["error"]["details"] == {"expected": 0, "actual": 1}

        listed = api.get("/v1/data/teacher", headers=headers())
        assert listed.json()["items"][0]["name"] == "教师一"
        assert listed.json()["revision"] == 1

        closed = api.post("/v1/projects/current/close", headers=headers())
        assert closed.status_code == 204
        reopened = api.post(f"/v1/projects/{project_id}/open", headers=headers())
        assert reopened.status_code == 200
        assert reopened.json()["revision"] == 1


def test_errors_have_correlation_id_and_no_request_body_echo(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.post(
            "/v1/projects",
            headers={**headers(), "X-Correlation-ID": "test-correlation"},
            json={"name": ""},
        )
        body = response.json()
        assert response.status_code == 422
        assert body["error"]["correlationId"] == "test-correlation"
        assert "input" not in str(body)


def test_planning_task_endpoint_generates_lessons_atomically(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        api.post("/v1/projects", headers=headers(), json={"name": "任务 API"})
        revision = 0
        ids: dict[str, str] = {}
        for entity_type, name in (
            ("teacher", "教师"),
            ("subject", "数学"),
            ("homeroom", "一班"),
        ):
            saved = api.put(
                f"/v1/data/{entity_type}",
                headers=headers(),
                json={"expected_revision": revision, "data": {"name": name}},
            )
            assert saved.status_code == 200
            revision = saved.json()["revision"]
            ids[entity_type] = saved.json()["item"]["id"]

        response = api.put(
            "/v1/planning/tasks",
            headers=headers(),
            json={
                "expected_revision": revision,
                "data": {
                    "homeroom_id": ids["homeroom"],
                    "subject_id": ids["subject"],
                    "primary_teacher_id": ids["teacher"],
                    "weekly_slots": 5,
                    "duration_slots": 2,
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["revision"] == revision + 1
        assert [item["duration_slots"] for item in response.json()["lessons"]] == [2, 2, 1]


def test_scheduling_endpoint_returns_infeasible_diagnostics_without_candidate(
    tmp_path: Path,
) -> None:
    with client(tmp_path) as api:
        api.post("/v1/projects", headers=headers(), json={"name": "空排课 API"})

        response = api.post(
            "/v1/scheduling/rounds",
            headers=headers(),
            json={"time_budget_seconds": 10, "random_seed": 3},
        )

        assert response.status_code == 201
        round_data = response.json()["round"]
        assert round_data["status"] == "infeasible"
        assert round_data["candidate_id"] is None
        assert any(
            item["event_type"] == "infeasible_diagnostics"
            for item in round_data["events"]
        )
        candidates = api.get("/v1/scheduling/candidates", headers=headers())
        assert candidates.json()["items"] == []


def test_project_archive_api_exports_and_imports_without_overwriting(tmp_path: Path) -> None:
    archive = tmp_path / "API 项目.sttproj"
    with client(tmp_path) as api:
        created = api.post("/v1/projects", headers=headers(), json={"name": "迁移源"})
        source_id = created.json()["project"]["id"]
        api.put(
            "/v1/data/teacher",
            headers=headers(),
            json={"expected_revision": 0, "data": {"name": "陈老师"}},
        )
        exported = api.post(
            "/v1/project-archives/export",
            headers=headers(),
            json={"destination_path": str(archive), "overwrite": False},
        )
        assert exported.status_code == 201
        assert exported.json()["package"]["verified"]

        api.post("/v1/projects/current/close", headers=headers())
        rejected = api.post(
            "/v1/project-archives/import",
            headers=headers(),
            json={"archive_path": str(archive), "confirmed": False},
        )
        assert rejected.status_code == 409
        imported = api.post(
            "/v1/project-archives/import",
            headers=headers(),
            json={"archive_path": str(archive), "confirmed": True},
        )
        assert imported.status_code == 201
        assert imported.json()["project"]["id"] != source_id
        assert imported.json()["revision"] == 1
        assert api.get("/v1/data/teacher", headers=headers()).json()["items"][0][
            "name"
        ] == "陈老师"
        assert len(api.get("/v1/projects", headers=headers()).json()["projects"]) == 2
