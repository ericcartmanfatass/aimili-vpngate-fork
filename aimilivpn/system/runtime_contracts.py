from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from aimilivpn.system.manager_config import ManagerRuntimeConfig
from aimilivpn.system.manager_wiring_foundation_types import ManagerRepositories


@runtime_checkable
class ConnectionRuntime(Protocol):
    def connection_orchestrator(self) -> Any: ...
    def stop_active_openvpn(self) -> None: ...
    def active_openvpn_running(self) -> bool: ...


@runtime_checkable
class MonitoringRuntime(Protocol):
    def collector_loop(self) -> None: ...
    def proxy_checker_loop(self) -> None: ...
    def active_node_pinger_loop(self) -> None: ...


@runtime_checkable
class RuntimeLifecycle(Protocol):
    def stop_requested(self) -> bool: ...
    def shutdown(self, timeout_seconds: float = 5.0) -> None: ...
    def failures(self) -> tuple[tuple[str, BaseException], ...]: ...


@runtime_checkable
class LogRuntime(Protocol):
    def log_to_json(self, level: str, module: str, message: str) -> None: ...


@runtime_checkable
class WebApiRuntime(Protocol):
    def route_context_factory(self) -> Any: ...
    def web_server_runtime(self) -> Any: ...


@dataclass(frozen=True)
class ManagerRuntimeServices:
    config: ManagerRuntimeConfig
    repositories: ManagerRepositories
    connection: ConnectionRuntime
    monitoring: MonitoringRuntime
    lifecycle: RuntimeLifecycle
    logs: LogRuntime
    web: WebApiRuntime
