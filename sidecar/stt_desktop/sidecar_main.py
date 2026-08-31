from __future__ import annotations

import hashlib
import hmac
import json
import multiprocessing
import os
import socket
import sys
import threading
from pathlib import Path

import uvicorn

from stt_desktop.api import PROTOCOL_VERSION, create_app
from stt_desktop.service_config import load_service_config
from stt_desktop.storage import ProjectWorkspace


def _take_required_environment(name: str) -> str:
    value = os.environ.pop(name, None)
    if not value:
        raise RuntimeError(f"缺少必要环境变量: {name}")
    return value


def _ready_process_ids() -> tuple[int, int]:
    """Return the launcher PID expected by Tauri and this server worker PID."""
    worker_pid = os.getpid()
    frozen_onefile_worker = bool(getattr(sys, "frozen", False)) and bool(
        os.environ.get("_PYI_APPLICATION_HOME_DIR")
    )
    launcher_pid = os.getppid() if frozen_onefile_worker else worker_pid
    return launcher_pid, worker_pid


def _watch_shutdown(requested: threading.Event, server: uvicorn.Server) -> None:
    requested.wait()
    server.should_exit = True


def main() -> int:
    # Required when the packaged Windows sidecar spawns the isolated solver.
    multiprocessing.freeze_support()
    token = _take_required_environment("STT_SIDECAR_TOKEN")
    nonce = _take_required_environment("STT_SIDECAR_NONCE")
    workspace_path = Path(_take_required_environment("STT_WORKSPACE_PATH"))
    config_path = Path(os.environ.pop("STT_SERVICES_CONFIG", "config/services.yaml"))
    services = load_service_config(config_path)
    workspace = ProjectWorkspace(workspace_path)
    shutdown_requested = threading.Event()
    app = create_app(
        workspace=workspace,
        services=services,
        session_token=token,
        shutdown_requested=shutdown_requested,
    )

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    proof = hmac.new(token.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    launcher_pid, worker_pid = _ready_process_ids()
    print(
        json.dumps(
            {
                "event": "ready",
                "port": port,
                "pid": launcher_pid,
                "workerPid": worker_pid,
                "protocolVersion": PROTOCOL_VERSION,
                "nonceProof": proof,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    threading.Thread(
        target=_watch_shutdown,
        args=(shutdown_requested, server),
        daemon=True,
        name="sidecar-shutdown-watcher",
    ).start()
    server.run(sockets=[listener])
    listener.close()
    # PyInstaller one-file workers can retain non-daemon runtime threads after
    # Uvicorn has completed its graceful lifespan shutdown.  At this point all
    # application cleanup has already run, so terminate the frozen worker
    # explicitly and allow the bootloader launcher to reap it.
    if bool(getattr(sys, "frozen", False)):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
