from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping
from urllib.parse import urlparse

import yaml

EnvironmentName = Literal["development", "test", "staging", "production"]
ServiceMode = Literal["real", "mock", "disabled"]

_ENVIRONMENTS = {"development", "test", "staging", "production"}
_MODES = {"real", "mock", "disabled"}
_SENSITIVE_KEY_PARTS = (
    "password",
    "private_key",
    "service_role",
    "secret_value",
    "access_token",
    "refresh_token",
    "license_key",
)


class ConfigError(ValueError):
    """Raised when the service profile is unsafe or malformed."""


@dataclass(frozen=True)
class ServiceDefinition:
    name: str
    provider: str
    mode: ServiceMode
    endpoint: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    mock: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AppServiceConfig:
    version: int
    environment: EnvironmentName
    allow_mock_services: bool
    services: Mapping[str, ServiceDefinition]

    def service(self, name: str) -> ServiceDefinition:
        try:
            return self.services[name]
        except KeyError as exc:
            raise ConfigError(f"未配置服务: {name}") from exc


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path} 必须是 YAML 对象")
    return value


def _require_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} 必须是非空字符串")
    return value.strip()


def _reject_inline_secrets(value: Any, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            child_path = f"{path}.{raw_key}"
            if not key.endswith("_env") and any(part in key for part in _SENSITIVE_KEY_PARTS):
                raise ConfigError(f"{child_path} 疑似包含内联秘密；只允许引用环境变量名")
            _reject_inline_secrets(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_inline_secrets(child, f"{path}[{index}]")


def _validate_endpoint(endpoint: str, environment: EnvironmentName, path: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError(f"{path} 必须是有效的 http/https URL")
    if environment in {"staging", "production"} and parsed.scheme != "https":
        raise ConfigError(f"{path} 在 {environment} 环境必须使用 HTTPS")


def load_service_config(path: str | Path) -> AppServiceConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"服务配置不存在: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"服务配置 YAML 无法解析: {exc}") from exc

    root = _require_mapping(raw, "root")
    _reject_inline_secrets(root)

    version = root.get("version")
    if version != 1:
        raise ConfigError(f"不支持的服务配置版本: {version!r}")

    environment_raw = _require_non_empty_string(root.get("environment"), "environment")
    if environment_raw not in _ENVIRONMENTS:
        raise ConfigError(f"不支持的 environment: {environment_raw}")
    environment: EnvironmentName = environment_raw  # type: ignore[assignment]

    allow_mock_services = root.get("allow_mock_services")
    if not isinstance(allow_mock_services, bool):
        raise ConfigError("allow_mock_services 必须是布尔值")
    if environment in {"staging", "production"} and allow_mock_services:
        raise ConfigError(f"{environment} 环境禁止启用 mock 服务")

    services_raw = _require_mapping(root.get("services"), "services")
    services: dict[str, ServiceDefinition] = {}
    for raw_name, raw_definition in services_raw.items():
        name = _require_non_empty_string(raw_name, "services.<name>")
        definition = _require_mapping(raw_definition, f"services.{name}")
        provider = _require_non_empty_string(
            definition.get("provider"), f"services.{name}.provider"
        )
        mode_raw = _require_non_empty_string(definition.get("mode"), f"services.{name}.mode")
        if mode_raw not in _MODES:
            raise ConfigError(f"services.{name}.mode 不支持: {mode_raw}")
        mode: ServiceMode = mode_raw  # type: ignore[assignment]
        if mode == "mock" and not allow_mock_services:
            raise ConfigError(f"services.{name} 使用 mock，但 allow_mock_services=false")

        endpoint_raw = definition.get("endpoint")
        endpoint = None
        if endpoint_raw is not None:
            endpoint = _require_non_empty_string(endpoint_raw, f"services.{name}.endpoint")
            _validate_endpoint(endpoint, environment, f"services.{name}.endpoint")

        env_raw = definition.get("env", {})
        env_mapping = _require_mapping(env_raw, f"services.{name}.env")
        env = {
            _require_non_empty_string(key, f"services.{name}.env.<key>"): _require_non_empty_string(
                value, f"services.{name}.env.{key}"
            )
            for key, value in env_mapping.items()
        }
        mock = _require_mapping(definition.get("mock", {}), f"services.{name}.mock")
        services[name] = ServiceDefinition(
            name=name,
            provider=provider,
            mode=mode,
            endpoint=endpoint,
            env=env,
            mock=dict(mock),
        )

    required_services = {"identity", "license", "payment", "smtp", "updates"}
    missing = sorted(required_services - services.keys())
    if missing:
        raise ConfigError(f"缺少必要服务配置: {', '.join(missing)}")

    return AppServiceConfig(
        version=version,
        environment=environment,
        allow_mock_services=allow_mock_services,
        services=services,
    )
