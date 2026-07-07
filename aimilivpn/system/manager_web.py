from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, MutableMapping

from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.system.manager_web_wiring import build_web_runtime_wiring
from aimilivpn.system.web_runtime import WebRuntimeWiring
from aimilivpn.web.context_factory import WebRouteContextFactory
from aimilivpn.web.server import WebServerRuntime


LOGIN_HTML_FALLBACK = """<!doctype html><html><body><h1>AimiliVPN Login</h1></body></html>"""
INDEX_HTML_FALLBACK = """<!doctype html><html><body><h1>AimiliVPN</h1></body></html>"""


def default_login_html() -> str:
    return LOGIN_HTML_FALLBACK


def default_index_html() -> str:
    return INDEX_HTML_FALLBACK


@dataclass
class ManagerWebRuntime:
    region_repository: Any
    read_regions: Callable[[], list[RegionProfile]]
    read_nodes: Callable[[], list[dict[str, Any]]]
    region_from_payload: Callable[[dict[str, Any], RegionProfile | None], RegionProfile]
    quality_provider_status: Callable[[], dict[str, Any]]
    latest_quality_for_node: Callable[[str], QualityResult | None]
    latest_quality_map: Callable[[], dict[str, QualityResult]]
    test_node_by_id: Callable[[str], dict[str, Any]]
    check_quality_ip: Callable[[str], QualityResult]
    check_quality_region: Callable[[str, int], dict[str, Any]]
    bounded_int: Callable[[Any, int, int, int], int]
    scamalytics_errors: tuple[type[BaseException], ...]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    filter_nodes_by_region: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    get_state: Callable[[], dict[str, Any]]
    set_state: Callable[..., None]
    get_active_node_id: Callable[[], str]
    get_last_active_ping_time: Callable[[], float]
    set_last_active_ping_time: Callable[[float], None]
    get_last_active_latency: Callable[[], int]
    set_last_active_latency: Callable[[int], None]
    now: Callable[[], float]
    ping_latency_ms: Callable[[str, int, int], int]
    parse_int: Callable[[Any], int]
    start_daemon_thread: Callable[[Callable[..., None], tuple[Any, ...]], None]
    test_multiple_nodes: Callable[[Any], list[dict[str, Any]]]
    connect_node: Callable[[str], str]
    stop_active_openvpn: Callable[[], None]
    load_ui_config: Callable[[], dict[str, Any]]
    save_ui_config_unlocked: Callable[[dict[str, Any]], None]
    maintain_valid_nodes: Callable[[bool], str]
    maintenance_running: Callable[[], bool]
    start_maintenance: Callable[[], None]
    validate_routing_region_target: Callable[[str, str], None]
    verify_password: Callable[[str, str], bool]
    verify_username: Callable[[str, str], bool]
    generate_session_token: Callable[[], str]
    check_proxy_health: Callable[[], dict[str, Any]]
    ui_host: Callable[[], str]
    ui_port: Callable[[], int]
    proxy_host: Callable[[], str]
    proxy_port: Callable[[], int]
    active_openvpn_running: Callable[[], bool]
    is_linux: Callable[[], bool]
    tun_dev: Callable[[], str]
    server_start_time: Callable[[], float]
    last_collector_heartbeat: Callable[[], float]
    last_checker_heartbeat: Callable[[], float]
    last_pinger_heartbeat: Callable[[], float]
    check_interval_seconds: Callable[[], int]
    login_html_fallback: Callable[[], str]
    index_html_fallback: Callable[[], str]
    active_sessions: MutableMapping[str, float]
    lock: Any
    data_dir: Callable[[], Path]
    console_token: Callable[[], str]
    diagnose_local_obstructions: Callable[[int, str], tuple[bool, str] | None]
    start_thread: Callable[[Callable[[], None]], None]
    sleep: Callable[[int | float], None]
    exit_process: Callable[[int], None]
    print_line: Callable[[str], None]
    _wiring: WebRuntimeWiring | None = field(default=None, init=False)

    def wiring(self) -> WebRuntimeWiring:
        if self._wiring is None:
            self._wiring = build_web_runtime_wiring(self)
        return self._wiring

    def clear_active_sessions(self) -> None:
        self.wiring().clear_active_sessions()

    def schedule_server_restart(self, message: str) -> None:
        self.wiring().schedule_server_restart(message)

    def save_ui_config_locked(self, config: dict[str, Any]) -> None:
        self.wiring().save_ui_config_locked(config)

    def add_active_session(self, token: str, expires_at: float) -> None:
        self.wiring().add_active_session(token, expires_at)

    def remove_active_session(self, token: str) -> None:
        self.wiring().remove_active_session(token)

    def proxy_gateway_status(self) -> tuple[bool, str]:
        return self.wiring().proxy_gateway_status()

    def read_api_log_entries(self) -> list[dict[str, Any]]:
        return self.wiring().read_api_log_entries()

    def route_context_factory(self) -> WebRouteContextFactory:
        return self.wiring().route_context_factory()

    def web_server_runtime(self) -> WebServerRuntime:
        return self.wiring().web_server_runtime()
