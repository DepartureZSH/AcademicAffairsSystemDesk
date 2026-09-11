import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not PWSH, reason="PowerShell build configuration test")


def invoke(tmp_path, dotenv, runtime=None):
    fixture = tmp_path / ".env"
    fixture.write_text(dotenv, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in (
        "STT_SUPABASE_PUBLISHABLE_KEY", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY")}
    env["STT_TEST_ENV_FILE"] = str(fixture)
    if runtime:
        env["STT_SUPABASE_PUBLISHABLE_KEY"] = runtime
    command = ". ./scripts/DesktopClientConfig.ps1; try { $key = Get-DesktopPublishableKey -EnvFile $env:STT_TEST_ENV_FILE; Write-Output 'VALID'; if ($env:SUPABASE_PASSWORD) { throw 'unexpected secret import' } } catch { Write-Output $_.Exception.Message; exit 1 }"
    env.pop("SUPABASE_PASSWORD", None)
    return subprocess.run([PWSH, "-NoProfile", "-Command", command], cwd=ROOT,
                          env=env, capture_output=True, text=True, encoding="utf-8")


@pytest.mark.parametrize("name", ["STT_SUPABASE_PUBLISHABLE_KEY", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY"])
def test_accepts_only_allowlisted_values_without_printing(tmp_path, name):
    key = "sb_publishable_test_only"
    result = invoke(tmp_path, f'{name}="{key}"\nSUPABASE_PASSWORD=must_not_be_imported\n')
    assert result.returncode == 0, result.stdout + result.stderr
    assert key not in result.stdout + result.stderr


@pytest.mark.parametrize("role,success", [("anon", True), ("service_role", False), ("authenticated", False)])
def test_legacy_jwt_role_guard(tmp_path, role, success):
    encoded = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    key = f"e30.{encoded}.test_signature"
    result = invoke(tmp_path, f"SUPABASE_PUBLISHABLE_KEY={key}")
    assert (result.returncode == 0) is success
    assert key not in result.stdout + result.stderr


@pytest.mark.parametrize("value", ["", "sb_secret_never_bundle", "not-a-key"])
def test_missing_and_invalid_keys_stop_build(tmp_path, value):
    result = invoke(tmp_path, f"SUPABASE_PUBLISHABLE_KEY={value}")
    assert result.returncode != 0
    if value:
        assert value not in result.stdout + result.stderr


def test_explicit_invalid_env_does_not_fall_back_to_file(tmp_path):
    result = invoke(tmp_path, "SUPABASE_PUBLISHABLE_KEY=sb_publishable_good", "sb_secret_bad")
    assert result.returncode != 0


def test_release_build_requires_and_tracks_public_configuration():
    source = (ROOT / "apps/desktop/src-tauri/build.rs").read_text(encoding="utf-8")
    assert "cargo:rerun-if-env-changed=STT_SUPABASE_PUBLISHABLE_KEY" in source
    assert 'Ok("release") && key.is_none()' in source
    build = (ROOT / "scripts/build-windows.ps1").read_text(encoding="utf-8")
    assert build.index("Get-DesktopPublishableKey -EnvFile") < build.index("'build-sidecar.ps1'")
    assert "$env:STT_SUPABASE_PUBLISHABLE_KEY = $buildPublishableKey" in build
    assert "$env:STT_SUPABASE_PUBLISHABLE_KEY = $oldPublishableKey" in build
