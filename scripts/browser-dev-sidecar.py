"""Isolated local workspace for browser UI development; never loads .env or accounts."""

import os
import socket
import sys
import threading
from pathlib import Path

import uvicorn

from stt_desktop.api.app import create_app
from stt_desktop.service_config import AppServiceConfig
from stt_desktop.storage import ProjectWorkspace

root = Path(__file__).resolve().parents[1]
workspace = ProjectWorkspace(Path(os.environ.pop("STT_BROWSER_WORKSPACE", str(root / ".local" / "browser-dev"))).resolve())
app = create_app(
    workspace=workspace,
    services=AppServiceConfig(1, "development", True, {}),
    session_token=os.environ.pop("STT_BROWSER_SESSION_TOKEN"),
)
projects = workspace.list_projects()
project = (
    workspace.open_project(projects[0]["project_id"])
    if projects
    else workspace.create_project("本地界面测试项目")
)
app.state.sidecar.current_project = project
if not project.list_entities("term"):
    project.save_entity(
        "term", {"name": "第一学期", "week_count": 20, "day_count": 7}, project.revision
    )
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(("127.0.0.1", 0))
print(f"STT_BROWSER_READY:{sock.getsockname()[1]}", flush=True)
server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))


# Exiting the owning Vite process closes stdin, releasing the SQLite project lock.
def monitor_parent():
    sys.stdin.buffer.read()
    server.should_exit = True


threading.Thread(target=monitor_parent, daemon=True).start()
server.run(sockets=[sock])
