from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from aimilivpn.core.models import QualityResult, RegionProfile

@dataclass(frozen=True)
class RegionQualityRouteContext:
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
    submit_operation: Callable[[str, str, Callable[[], Any], bool], tuple[dict[str, Any], bool]] | None = None


@dataclass(frozen=True)
class NodeRouteContext:
    read_nodes: Callable[[], list[dict[str, Any]]]
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
    test_node_by_id: Callable[[str], dict[str, Any]]
    connect_node: Callable[[str], str]
    stop_active_openvpn: Callable[[], None]
    load_ui_config: Callable[[], dict[str, Any]]
    save_ui_config: Callable[[dict[str, Any]], None]
    maintain_valid_nodes: Callable[[bool], str]
    maintenance_running: Callable[[], bool]
    start_maintenance: Callable[[], None]
    submit_operation: Callable[[str, str, Callable[[], Any], bool], tuple[dict[str, Any], bool]] | None = None
    get_operation: Callable[[str], dict[str, Any] | None] | None = None
    list_operations: Callable[[], list[dict[str, Any]]] | None = None


@dataclass(frozen=True)
class ConfigRouteContext:
    load_ui_config: Callable[[], dict[str, Any]]
    save_ui_config: Callable[[dict[str, Any]], None]
    validate_routing_region_target: Callable[[str, str], None]
    clear_sessions: Callable[[], None]
    schedule_restart: Callable[[str], None]


@dataclass(frozen=True)
class AuthRouteContext:
    load_ui_config: Callable[[], dict[str, Any]]
    verify_password: Callable[[str, str], bool]
    verify_username: Callable[[str, str], bool]
    generate_session_token: Callable[[], str]
    add_session: Callable[[str, float], None]
    remove_session: Callable[[str], None]
    get_secret_path: Callable[[], str]
    now: Callable[[], float]


@dataclass(frozen=True)
class PageRouteContext:
    is_authorized: Callable[[], bool]
    login_html_fallback: str
    index_html_fallback: str


@dataclass(frozen=True)
class ProxyRouteContext:
    check_proxy_health: Callable[[], dict[str, Any]]
    set_state: Callable[..., None]


@dataclass(frozen=True)
class StatusRouteContext:
    load_ui_config: Callable[[], dict[str, Any]]
    ui_host: str
    ui_port: int
    proxy_host: str
    proxy_port: int
    proxy_gateway_status: Callable[[], tuple[bool, str]]
    active_openvpn_running: Callable[[], bool]
    active_node_id: Callable[[], str]
    is_linux: Callable[[], bool]
    tun_dev: str
    tun_exists: Callable[[], bool]
    now: Callable[[], float]
    server_start_time: float
    last_collector_heartbeat: Callable[[], float]
    last_checker_heartbeat: Callable[[], float]
    last_pinger_heartbeat: Callable[[], float]
    check_interval_seconds: int
    format_local_time: Callable[[float], str]


@dataclass(frozen=True)
class LogsRouteContext:
    read_log_entries: Callable[[], list[dict[str, Any]]]


@dataclass(frozen=True)
class ApiGetRouteContext:
    region_quality: RegionQualityRouteContext
    node: NodeRouteContext
    status: StatusRouteContext
    logs: LogsRouteContext


@dataclass(frozen=True)
class ApiPostRouteContext:
    auth: AuthRouteContext
    region_quality: RegionQualityRouteContext
    node: NodeRouteContext
    config: ConfigRouteContext
    proxy: ProxyRouteContext
    is_authorized: Callable[[], bool]


@dataclass(frozen=True)
class ApiMutationRouteContext:
    region_quality: RegionQualityRouteContext
    is_authorized: Callable[[], bool]
    config: ConfigRouteContext | None = None
