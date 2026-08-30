from pathlib import Path

import pytest

from stt_desktop.service_config import ConfigError, load_service_config


ROOT = Path(__file__).resolve().parents[1]


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "services.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def minimal_services(license_mode: str = "mock") -> str:
    return f"""
version: 1
environment: development
allow_mock_services: true
services:
  identity: {{provider: supabase, mode: real, endpoint: http://127.0.0.1:55421}}
  license: {{provider: local, mode: {license_mode}}}
  payment: {{provider: local, mode: mock}}
  smtp: {{provider: local, mode: mock}}
  updates: {{provider: local, mode: mock}}
"""


def test_repository_development_profile_is_valid() -> None:
    config = load_service_config(ROOT / "config" / "services.yaml")

    assert config.environment == "development"
    assert config.service("identity").mode == "real"
    assert config.service("identity").endpoint == "http://127.0.0.1:55421"
    assert config.service("license").mode == "mock"
    assert config.service("license").mock["device_limit"] == 3


def test_production_rejects_mock_services(tmp_path: Path) -> None:
    content = minimal_services().replace(
        "environment: development", "environment: production"
    )
    path = write_config(tmp_path, content)

    with pytest.raises(ConfigError, match="production 环境禁止启用 mock"):
        load_service_config(path)


def test_disallow_flag_rejects_individual_mock(tmp_path: Path) -> None:
    content = minimal_services().replace("allow_mock_services: true", "allow_mock_services: false")
    path = write_config(tmp_path, content)

    with pytest.raises(ConfigError, match="services.license 使用 mock"):
        load_service_config(path)


def test_inline_secrets_are_rejected(tmp_path: Path) -> None:
    content = minimal_services().replace(
        "identity: {provider: supabase, mode: real, endpoint: http://127.0.0.1:55421}",
        "identity: {provider: supabase, mode: real, password: do-not-store-this}",
    )
    path = write_config(tmp_path, content)

    with pytest.raises(ConfigError, match="内联秘密"):
        load_service_config(path)


def test_missing_required_service_is_rejected(tmp_path: Path) -> None:
    content = minimal_services().replace("  updates: {provider: local, mode: mock}\n", "")
    path = write_config(tmp_path, content)

    with pytest.raises(ConfigError, match="updates"):
        load_service_config(path)


def test_staging_requires_https(tmp_path: Path) -> None:
    content = (
        minimal_services(license_mode="real")
        .replace("environment: development", "environment: staging")
        .replace("allow_mock_services: true", "allow_mock_services: false")
        .replace("mode: mock", "mode: disabled")
    )
    path = write_config(tmp_path, content)

    with pytest.raises(ConfigError, match="必须使用 HTTPS"):
        load_service_config(path)
