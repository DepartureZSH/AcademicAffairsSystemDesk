from __future__ import annotations

from stt_desktop import sidecar_main


def test_source_runtime_reports_current_process_for_both_pids(monkeypatch) -> None:
    monkeypatch.delattr(sidecar_main.sys, "frozen", raising=False)
    monkeypatch.delenv("_PYI_APPLICATION_HOME_DIR", raising=False)
    monkeypatch.setattr(sidecar_main.os, "getpid", lambda: 1234)
    monkeypatch.setattr(sidecar_main.os, "getppid", lambda: 999)

    assert sidecar_main._ready_process_ids() == (1234, 1234)


def test_frozen_onefile_worker_reports_launcher_and_worker_pids(monkeypatch) -> None:
    monkeypatch.setattr(sidecar_main.sys, "frozen", True, raising=False)
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "C:/Temp/_MEI123")
    monkeypatch.setattr(sidecar_main.os, "getpid", lambda: 5678)
    monkeypatch.setattr(sidecar_main.os, "getppid", lambda: 1234)

    assert sidecar_main._ready_process_ids() == (1234, 5678)
