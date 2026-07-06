from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping

from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository
from aimilivpn.system.manager_state import ManagerMutableState
from aimilivpn.system.runtime_paths import RuntimePaths
from aimilivpn.system.startup import DaemonTask


@dataclass(frozen=True)
class ManagerRepositories:
    node_repository: NodeRepository
    region_repository: RegionRepository
    quality_repository: QualityRepository


@dataclass(frozen=True)
class ManagerSharedState:
    lock: Any
    maintenance_lock: Any
    mutable_state: ManagerMutableState
    active_sessions: MutableMapping[str, float]


@dataclass(frozen=True)
class ManagerUiEndpoints:
    ui_host: str
    ui_port: int
    local_proxy_port: int


@dataclass(frozen=True)
class ConnectionRuntimeWiring:
    state: ManagerMutableState
    lock: Any
    cleanup_policy_routing: Callable[[], None]
    read_nodes: Callable[[], list[dict[str, Any]]]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    load_ui_config: Callable[[], dict[str, Any]]
    save_ui_config: Callable[[dict[str, Any]], None]
    stop_process: Callable[[Any], None]
    kill_existing_openvpn_processes: Callable[[], None]
    set_state: Callable[..., None]
    run_locked: Callable[[Callable[[], Any]], Any]
    log_vpn_line: Callable[[str, str], None]
    log_line: Callable[[str, str, str], None]
    print_line: Callable[[str], None]
    ensure_dirs: Callable[[], None]
    start_thread: Callable[[Callable[[], None]], None]
    try_acquire_maintenance: Callable[[], bool]
    release_maintenance: Callable[[], None]
    node_matches_allowed: Callable[[dict[str, Any]], bool]
    allowed_countries: Callable[[], set[str]]
    filter_nodes_by_routing_region: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    routing_target_label: Callable[[str], str]
    parse_int: Callable[[Any], int]
    ping_latency_ms: Callable[[str, int, int], int]
    write_ovpn_config: Callable[[Path, str], None]
    run_openvpn_until_ready: Callable[[str], tuple[bool, str, Any]]
    setup_policy_routing: Callable[[str], None]
    check_proxy_health: Callable[[], dict[str, Any]]
    fetch_candidates: Callable[[], list[dict[str, Any]]]
    check_and_fix_dns: Callable[[], None]
    diagnose_api_failure: Callable[[str], tuple[Any, Any]]
    select_maintenance_test_nodes: Callable[[list[dict[str, Any]]], list[str]]
    test_multiple_nodes: Callable[[list[str]], list[dict[str, Any]]]
    now: Callable[[], float]
    api_url: Callable[[], str]
    tun_dev: Callable[[], str]
    proxy_host: Callable[[], str]
    proxy_port: Callable[[], int]
    maintenance_test_limit: Callable[[], int]
    node_test_workers: Callable[[], int]
    exclude_datacenter: Callable[[], bool]


@dataclass(frozen=True)
class RepositoryRuntimeWiring:
    node_repository: NodeRepository
    region_repository: RegionRepository
    country_translations: Mapping[str, str]


@dataclass(frozen=True)
class QualityRuntimeWiring:
    root_dir: Path
    quality_repository: QualityRepository
    region_repository: RegionRepository
    region_target_id: Callable[[str], str]
    read_nodes: Callable[[], list[dict[str, Any]]]
    node_allowed: Callable[[dict[str, Any]], bool]
    bounded_int: Callable[[Any, int, int | None, int | None], int]
    test_multiple_nodes: Callable[[list[str]], list[dict[str, Any]]]


@dataclass(frozen=True)
class FetchRuntimeWiring:
    api_url: str
    config_dir: Path
    max_scan_rows: int
    allowed_countries: set[str]
    allow_insecure_fetch: bool
    blacklist_file: Path
    lock: Any
    invalid_backoff_seconds: int
    read_nodes: Callable[[], list[dict[str, Any]]]
    set_state: Callable[..., None]
    log_line: Callable[[str, str], None]
    diagnose_api_failure: Callable[[str], tuple[Any, str]]
    get_upstream_proxy: Callable[[], tuple[str, str, int]]
    get_upstream_proxy_auth: Callable[[], tuple[str | None, str | None]]
    country_translations: dict[str, str]
    safe_name: Callable[[str], str]
    now: Callable[[], float]


@dataclass(frozen=True)
class EntryRuntimeWiring:
    service_runtime_factory: Callable[[], Any]
    web_server_runtime: Callable[[], Any]


@dataclass(frozen=True)
class UiRuntimeWiring:
    data_dir: Callable[[], Path]
    lock: Any
    ui_host: Callable[[], str]
    ui_port: Callable[[], int]
    proxy_port: Callable[[], int]
    bounded_int: Callable[[Any, int, int, int], int]


@dataclass(frozen=True)
class RuntimeStateWiring:
    state_file: Callable[[], Path]
    lock: Any
    mutable_state: ManagerMutableState
    load_ui_config: Callable[[], dict[str, Any]]
    api_url: Callable[[], str]
    instance_id: Callable[[], str]
    tun_dev: Callable[[], str]
    policy_table: Callable[[], str]
    allowed_countries: Callable[[], Iterable[str]]
    target_valid_nodes: Callable[[], int]
    fetch_interval_seconds: Callable[[], int]
    check_interval_seconds: Callable[[], int]
    local_proxy_host: Callable[[], str]
    local_proxy_port: Callable[[], int]


@dataclass(frozen=True)
class RuntimeFilesWiring:
    paths: Callable[[], RuntimePaths]
    auth_user: Callable[[], str]
    auth_pass: Callable[[], str]
    get_upstream_proxy_auth: Callable[[], tuple[str | None, str | None]]
    print_line: Callable[[str], None]


@dataclass(frozen=True)
class ThreadRuntimeWiring:
    lock: Any
    maintenance_lock: Any
    maintain_valid_nodes: Callable[[bool], Any]


@dataclass(frozen=True)
class NodeViewRuntimeWiring:
    allowed_countries: Callable[[], Iterable[str]]
    active_node_id: Callable[[], str]
    parse_int: Callable[[Any], int]


@dataclass(frozen=True)
class ProxyHealthRuntimeWiring:
    proxy_host: Callable[[], str]
    proxy_port: Callable[[], int]
    tun_dev: Callable[[], str]
    is_linux: Callable[[], bool]
    get_proxy_credentials: Callable[[], tuple[str | None, str | None]]
    diagnose_local_obstructions: Callable[[int, str], tuple[bool, str] | None]


@dataclass(frozen=True)
class JsonLogRuntimeWiring:
    data_dir: Path
    lock: object
    redact_message: Callable[[str], str]


@dataclass(frozen=True)
class MonitoringRuntimeWiring:
    state: ManagerMutableState
    now: Callable[[], float]
    sleep: Callable[[int | float], None]
    print_line: Callable[[str], None]
    log_line: Callable[[str, str, str], None]
    set_state: Callable[..., None]
    maintain_valid_nodes: Callable[[bool], str]
    active_openvpn_running: Callable[[], bool]
    check_interval_seconds: Callable[[], int]
    check_proxy_health: Callable[[], dict[str, Any]]
    is_connecting: Callable[[], bool]
    set_is_connecting: Callable[[bool], None]
    get_active_node_id: Callable[[], str]
    load_ui_config: Callable[[], dict[str, Any]]
    read_nodes: Callable[[], list[dict[str, Any]]]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    run_locked: Callable[[Callable[[], Any]], Any]
    mark_blacklisted: Callable[[dict[str, Any], str], None]
    auto_switch_node: Callable[[], None]
    connect_node: Callable[[str], str]
    proxy_port: Callable[[], int]
    ping_latency_ms: Callable[[str, int, int], int]
    parse_int: Callable[[Any], int]


@dataclass(frozen=True)
class ServiceRuntimeWiring:
    ensure_dirs: Callable[[], None]
    kill_existing_openvpn_processes: Callable[[], None]
    data_dir: Callable[[], Path]
    state_file: Callable[[], Path]
    write_json: Callable[[Path, Any], None]
    api_url: Callable[[], str]
    instance_id: Callable[[], str]
    tun_dev: Callable[[], str]
    policy_table: Callable[[], str]
    allowed_countries: Callable[[], set[str]]
    target_valid_nodes: Callable[[], int]
    fetch_interval_seconds: Callable[[], int]
    check_interval_seconds: Callable[[], int]
    local_proxy_host: Callable[[], str]
    local_proxy_port: Callable[[], int]
    ui_host: Callable[[], str]
    ui_port: Callable[[], int]
    start_proxy_server: Callable[[str, int, str], None]
    collector_loop: Callable[[], None]
    background_proxy_checker: Callable[[], None]
    active_node_pinger: Callable[[], None]
    start_daemon_threads: Callable[[Iterable[DaemonTask]], None]
    wait_for_gateway: Callable[[str, int], bool]
    load_ui_config: Callable[[], dict[str, Any]]
    bounded_int: Callable[[Any, int, int, int], int]
    web_server_runtime: Callable[[], Any]
    serve_web_forever: Callable[[str, int, Any], None]
    print_line: Callable[[str], None]
    set_stdout: Callable[[Any], None]
    set_stderr: Callable[[Any], None]


@dataclass(frozen=True)
class OpenVPNRuntimeWiring:
    openvpn_cmd: str
    auth_file: Path
    data_dir: Path
    config_dir: Path
    upstream_proxy_auth_path: Path
    root_dir: Path
    default_dev: Callable[[], str]
    policy_table: Callable[[], str]
    default_timeout_seconds: Callable[[], int]
    get_upstream_proxy: Callable[[], tuple[str | None, str | None, int | None]]
    write_upstream_proxy_auth_file: Callable[[], str | None]
    diagnose_openvpn_failure: Callable[[list[str]], tuple[int, str]]
    status_callback: Callable[[str], None]
    log_vpn_line: Callable[[str, str], None]
    log_routing_line: Callable[[str, str], None]
    print_line: Callable[[str], None]
    sleep: Callable[[float], None]


@dataclass(frozen=True)
class NodeProbeRuntimeWiring:
    read_nodes: Callable[[], list[dict[str, Any]]]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    run_locked: Callable[[Callable[[], Any]], Any]
    node_matches_allowed: Callable[[dict[str, Any]], bool]
    allowed_countries: Callable[[], set[str]]
    config_dir: Callable[[], Path]
    safe_name: Callable[[str], str]
    write_config: Callable[[Path, str], None]
    ping_latency_ms: Callable[[str, int, int], int]
    run_openvpn: Callable[..., tuple[bool, str, object]]
    parse_int: Callable[[Any], int]
    enrich_ip_info: Callable[[list[dict[str, Any]]], None]
    record_quality: Callable[[dict[str, Any], bool | None, int, str], Any]
    sort_nodes: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    now: Callable[[], float]
    print_line: Callable[[str], None]
    load_ui_config: Callable[[], dict[str, Any]]
    filter_nodes_by_routing_region: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    retest_interval_seconds: Callable[[], int]
    max_maintenance_nodes: Callable[[], int]


@dataclass(frozen=True)
class WebManagerRuntimeWiring:
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
