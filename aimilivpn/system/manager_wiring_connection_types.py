from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.connection_state import ConnectionPhase
from aimilivpn.system.manager_state import ManagerMutableState


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
    set_connection_phase: Callable[[ConnectionPhase | str, str, str], None]
    wait_for_stop: Callable[[float], bool] | None = None
    instance_retry_backoff_seconds: tuple[int, ...] = (60, 300, 900, 1800)


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
    stop_requested: Callable[[], bool]
    wait_for_stop: Callable[[int | float], bool]
