"""Local sidecar services for 时奕教务排课."""

from .service_config import AppServiceConfig, ConfigError, ServiceDefinition, load_service_config

__all__ = [
    "AppServiceConfig",
    "ConfigError",
    "ServiceDefinition",
    "load_service_config",
]
