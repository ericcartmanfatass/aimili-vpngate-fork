from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from aimilivpn.system.startup import DaemonTask


@dataclass(frozen=True)
class EntryRuntimeWiring:
    service_runtime_factory: Callable[[], Any]
    web_server_runtime: Callable[[], Any]


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
    shutdown_background_threads: Callable[[], None]
    stop_active_openvpn: Callable[[], None]
    text_log_max_bytes: Callable[[], int]
    text_log_backup_count: Callable[[], int]


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
