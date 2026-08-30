from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
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


def main() -> int:
    token = _take_required_environment("STT_SIDECAR_TOKEN")
    nonce = _take_required_environment("STT_SIDECAR_NONCE")
    workspace_path = Path(_take_required_environment("STT_WORKSPACE_PATH"))
    config_path = Path(os.environ.pop("STT_SERVICES_CONFIG", "config/services.yaml"))
    services = load_service_config(config_path)
    workspace = ProjectWorkspace(workspace_path)
    app = create_app(workspace=workspace, services=services, session_token=token)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    proof = hmac.new(token.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    print(
        json.dumps(
            {
                "event": "ready",
                "port": port,
                "pid": os.getpid(),
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
    server.run(sockets=[listener])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
