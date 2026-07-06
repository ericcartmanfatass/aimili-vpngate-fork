#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING
import sys

from aimilivpn.system.socket_resolution import install_ipv4_preferred_getaddrinfo

install_ipv4_preferred_getaddrinfo()
import vpn_utils
from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.core.logging_utils import redact_log_message
from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository
from aimilivpn.providers.scamalytics import ScamalyticsError
from aimilivpn.system.manager_auth import ManagerAuthRuntime
from aimilivpn.system.manager_callbacks import (
    console_token,
    diagnose_with_host_keyword,
    exit_process,
    is_linux,
    module_log_writer,
    print_line,
    set_stderr,
    set_stdout,
)
from aimilivpn.system.manager_entry import ManagerEntryRuntime
from aimilivpn.system.manager_fetch import ManagerFetchRuntime
from aimilivpn.system.manager_connection import ManagerConnectionRuntime
from aimilivpn.system.manager_logging import ManagerJsonLogRuntime
from aimilivpn.system.manager_monitoring import ManagerMonitoringRuntime
from aimilivpn.system.manager_node_view import ManagerNodeViewRuntime
from aimilivpn.system.manager_node_probe import ManagerNodeProbeRuntime
from aimilivpn.system.manager_openvpn import ManagerOpenVPNRuntime
from aimilivpn.system.manager_proxy_health import ManagerProxyHealthRuntime
from aimilivpn.system.openvpn_status import update_handshake_status as update_openvpn_handshake_status
from aimilivpn.system import proxy_server
from aimilivpn.system.manager_helpers import parse_int, safe_name
from aimilivpn.system.manager_quality import ManagerQualityRuntime
from aimilivpn.system.manager_repository import ManagerRepositoryRuntime
from aimilivpn.system.manager_config import (
    bounded_int,
    load_manager_runtime_config,
)
from aimilivpn.system.manager_runtime_files import ManagerRuntimeFiles
from aimilivpn.system.manager_service import ManagerServiceRuntime
from aimilivpn.system.manager_state import ManagerMutableState
from aimilivpn.system.manager_runtime_state import ManagerRuntimeState
from aimilivpn.system.manager_threads import ManagerThreadRuntime
from aimilivpn.system.startup import start_daemon_threads, wait_for_gateway
from aimilivpn.system.manager_ui import ManagerUiRuntime
from aimilivpn.system.manager_web import ManagerWebRuntime, default_index_html, default_login_html
from aimilivpn.web.api import quality_to_dict, region_to_dict
from aimilivpn.web.context_factory import WebRouteContextFactory
from aimilivpn.web.server import WebServerRuntime, serve_web_forever

if TYPE_CHECKING:
    from aimilivpn.providers.scamalytics import ScamalyticsProvider
    from aimilivpn.system.blacklist_store import BlacklistStore
    from aimilivpn.system.connection_orchestrator import ConnectionOrchestrator
    from aimilivpn.system.connection_runtime import ActiveConnectionRuntimeFacade
    from aimilivpn.system.monitoring_runtime import MonitoringRuntime
    from aimilivpn.system.node_probe_runtime import NodeProbeRuntime
    from aimilivpn.system.openvpn_runtime import OpenVPNRuntimeFacade
    from aimilivpn.system.policy_routing import PolicyRoutingFacade
    from aimilivpn.system.repository_facade import RepositoryFacade
    from aimilivpn.system.service_runtime import VpnGateServiceRuntime
    from aimilivpn.system.state_store import RuntimeStateStore
    from aimilivpn.system.ui_config import UiConfigStore
    from aimilivpn.system.vpngate_fetch import VpnGateFetchFacade
    from aimilivpn.system.web_runtime import WebRuntimeWiring

ROOT_DIR = (
    Path(sys.executable).resolve().parent
    if globals().get("__compiled__")
    else Path(os.environ.get("AIMILIVPN_INSTALL_DIR") or Path.cwd()).resolve()
)
MANAGER_CONFIG = load_manager_runtime_config(ROOT_DIR)
API_URL = MANAGER_CONFIG.api_url
FETCH_INTERVAL_SECONDS = MANAGER_CONFIG.fetch_interval_seconds
CHECK_INTERVAL_SECONDS = MANAGER_CONFIG.check_interval_seconds
TARGET_VALID_NODES = MANAGER_CONFIG.target_valid_nodes
MAX_SCAN_ROWS = MANAGER_CONFIG.max_scan_rows
OPENVPN_TEST_TIMEOUT_SECONDS = MANAGER_CONFIG.openvpn_test_timeout_seconds
OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS = MANAGER_CONFIG.openvpn_maintenance_test_timeout_seconds
NODE_TEST_WORKERS = MANAGER_CONFIG.node_test_workers
MAX_MAINTENANCE_TEST_NODES = MANAGER_CONFIG.max_maintenance_test_nodes
NODE_RETEST_INTERVAL_SECONDS = MANAGER_CONFIG.node_retest_interval_seconds
OPENVPN_CMD = MANAGER_CONFIG.openvpn_cmd
OPENVPN_AUTH_USER = MANAGER_CONFIG.openvpn_auth_user
OPENVPN_AUTH_PASS = MANAGER_CONFIG.openvpn_auth_pass
LOCAL_PROXY_HOST = MANAGER_CONFIG.local_proxy_host
LOCAL_PROXY_PORT = MANAGER_CONFIG.local_proxy_port
UI_HOST = MANAGER_CONFIG.ui_host
UI_PORT = MANAGER_CONFIG.ui_port
INVALID_BACKOFF_SECONDS = MANAGER_CONFIG.invalid_backoff_seconds
INSTANCE_ID = MANAGER_CONFIG.instance_id
TUN_DEV = MANAGER_CONFIG.tun_dev
POLICY_TABLE = MANAGER_CONFIG.policy_table
ALLOWED_COUNTRIES = MANAGER_CONFIG.allowed_countries
EXCLUDE_DATACENTER = MANAGER_CONFIG.exclude_datacenter
ALLOW_INSECURE_FETCH = MANAGER_CONFIG.allow_insecure_fetch
RUNTIME_PATHS = MANAGER_CONFIG.paths
DATA_DIR = RUNTIME_PATHS.data_dir
CONFIG_DIR = RUNTIME_PATHS.config_dir
NODES_FILE = RUNTIME_PATHS.nodes_file
STATE_FILE = RUNTIME_PATHS.state_file
AUTH_FILE = RUNTIME_PATHS.auth_file
UPSTREAM_PROXY_AUTH_FILE = RUNTIME_PATHS.upstream_proxy_auth_file
BLACKLIST_FILE = RUNTIME_PATHS.blacklist_file
REGIONS_FILE = RUNTIME_PATHS.regions_file
QUALITY_RESULTS_FILE = RUNTIME_PATHS.quality_results_file
NODE_REPOSITORY = NodeRepository(NODES_FILE)
REGION_REPOSITORY = RegionRepository(REGIONS_FILE)
QUALITY_REPOSITORY = QualityRepository(QUALITY_RESULTS_FILE)
manager_repository_runtime = ManagerRepositoryRuntime(
    node_repository=NODE_REPOSITORY,
    region_repository=REGION_REPOSITORY,
    country_translations=vpn_utils.COUNTRY_TRANSLATIONS,
)
manager_quality_runtime = ManagerQualityRuntime(
    root_dir=ROOT_DIR,
    quality_repository=QUALITY_REPOSITORY,
    region_repository=REGION_REPOSITORY,
    region_target_id=lambda target: region_target_id(target),
    read_nodes=lambda: read_nodes(),
    node_allowed=lambda node: node_matches_allowed_countries(node),
    bounded_int=bounded_int,
    test_multiple_nodes=lambda node_ids: test_multiple_nodes(node_ids),
)

lock = threading.RLock()
maintenance_lock = threading.Lock()
mutable_state = ManagerMutableState()
active_sessions = mutable_state.active_sessions
manager_auth_runtime = ManagerAuthRuntime()
manager_ui_runtime = ManagerUiRuntime(
    data_dir=lambda: DATA_DIR,
    lock=lock,
    ui_host=lambda: UI_HOST,
    ui_port=lambda: UI_PORT,
    proxy_port=lambda: LOCAL_PROXY_PORT,
    bounded_int=bounded_int,
)
manager_runtime_state = ManagerRuntimeState(
    state_file=lambda: STATE_FILE,
    lock=lock,
    mutable_state=mutable_state,
    load_ui_config=lambda: load_ui_config(),
    api_url=lambda: API_URL,
    instance_id=lambda: INSTANCE_ID,
    tun_dev=lambda: TUN_DEV,
    policy_table=lambda: POLICY_TABLE,
    allowed_countries=lambda: ALLOWED_COUNTRIES,
    target_valid_nodes=lambda: TARGET_VALID_NODES,
    fetch_interval_seconds=lambda: FETCH_INTERVAL_SECONDS,
    check_interval_seconds=lambda: CHECK_INTERVAL_SECONDS,
    local_proxy_host=lambda: LOCAL_PROXY_HOST,
    local_proxy_port=lambda: LOCAL_PROXY_PORT,
)
manager_runtime_files = ManagerRuntimeFiles(
    paths=lambda: RUNTIME_PATHS,
    auth_user=lambda: OPENVPN_AUTH_USER,
    auth_pass=lambda: OPENVPN_AUTH_PASS,
    get_upstream_proxy_auth=vpn_utils.get_upstream_proxy_auth,
    print_line=print_line,
)
manager_thread_runtime = ManagerThreadRuntime(
    lock=lock,
    maintenance_lock=maintenance_lock,
    maintain_valid_nodes=lambda force: maintain_valid_nodes(force),
)
manager_node_view_runtime = ManagerNodeViewRuntime(
    allowed_countries=lambda: ALLOWED_COUNTRIES,
    active_node_id=mutable_state.active_node_id,
    parse_int=parse_int,
)
manager_proxy_health_runtime = ManagerProxyHealthRuntime(
    proxy_host=lambda: LOCAL_PROXY_HOST,
    proxy_port=lambda: LOCAL_PROXY_PORT,
    tun_dev=lambda: TUN_DEV,
    is_linux=is_linux,
    get_proxy_credentials=proxy_server.get_proxy_credentials,
    diagnose_local_obstructions=diagnose_with_host_keyword(vpn_utils.diagnose_local_obstructions),
)

def ensure_dirs() -> None:
    manager_runtime_files.ensure_dirs()

def upstream_proxy_auth_file() -> str | None:
    return manager_runtime_files.upstream_proxy_auth_file()

def write_json(path: Path, data: Any) -> None:
    manager_runtime_state.write_json(path, data)

def read_json(path: Path, default: Any) -> Any:
    return manager_runtime_state.read_json(path, default)

def generate_random_password() -> str:
    return manager_ui_runtime.generate_random_password()

def generate_random_username() -> str:
    return manager_ui_runtime.generate_random_username()


def ui_config_store() -> UiConfigStore:
    return manager_ui_runtime.store()

def load_ui_config() -> dict[str, Any]:
    return manager_ui_runtime.load()

def save_ui_config(config: dict[str, Any]) -> None:
    manager_ui_runtime.save(config)

# 初始化时优先从 ui_auth.json 加载保存的代理出站端口和网页端口配置以覆盖环境变量
try:
    UI_HOST, UI_PORT, LOCAL_PROXY_PORT = manager_ui_runtime.apply_saved_overrides()
except Exception:
    pass

def get_session_token(password: str, username: str = "admin") -> str:
    return manager_auth_runtime.get_session_token(password, username)

json_log_runtime = ManagerJsonLogRuntime(
    data_dir=DATA_DIR,
    lock=lock,
    redact_message=redact_log_message,
)


def json_log_writer():
    return json_log_runtime.writer()


def cleanup_old_logs(logs_dir: Path) -> None:
    json_log_runtime.cleanup_old_logs(logs_dir)


def log_to_json(level: str, module: str, message: str) -> None:
    json_log_runtime.log_to_json(level, module, message)


def runtime_state_store() -> RuntimeStateStore:
    return manager_runtime_state.store()


def set_state(**updates: Any) -> None:
    manager_runtime_state.set_state(**updates)

def repository_facade() -> RepositoryFacade:
    return manager_repository_runtime.facade()

def read_nodes() -> list[dict[str, Any]]:
    return manager_repository_runtime.read_nodes()

def write_nodes(nodes: list[dict[str, Any]]) -> None:
    manager_repository_runtime.write_nodes(nodes)

def read_regions() -> list[RegionProfile]:
    return manager_repository_runtime.read_regions()

def region_from_payload(payload: dict[str, Any], existing: RegionProfile | None = None) -> RegionProfile:
    return manager_repository_runtime.region_from_payload(payload, existing)

def filter_nodes_by_region(nodes: list[dict[str, Any]], region_id: str) -> list[dict[str, Any]]:
    return manager_repository_runtime.filter_nodes_by_region(nodes, region_id)

def region_target_id(target: str) -> str:
    return manager_repository_runtime.region_target_id(target)

def get_region_routing_target(target: str) -> RegionProfile | None:
    return manager_repository_runtime.get_region_routing_target(target)

def routing_target_label(target: str) -> str:
    return manager_repository_runtime.routing_target_label(target)

def node_matches_country_target(node: dict[str, Any], target: str) -> bool:
    return manager_repository_runtime.node_matches_country_target(node, target)

def node_matches_routing_region(node: dict[str, Any], target: str) -> bool:
    return manager_repository_runtime.node_matches_routing_region(node, target)

def filter_nodes_by_routing_region(nodes: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    return manager_repository_runtime.filter_nodes_by_routing_region(nodes, target)


def get_scamalytics_provider() -> ScamalyticsProvider | None:
    return manager_quality_runtime.get_scamalytics_provider()


def enrich_quality_with_scamalytics(result: QualityResult) -> QualityResult:
    return manager_quality_runtime.enrich_quality_with_scamalytics(
        result,
        provider_getter=get_scamalytics_provider,
    )


def record_quality_result_from_probe(
    node: dict[str, Any],
    openvpn_success: bool | None,
    latency_ms: int,
    probe_message: str = "",
) -> QualityResult:
    return manager_quality_runtime.record_quality_result_from_probe(
        node,
        openvpn_success,
        latency_ms,
        probe_message,
        provider_getter=get_scamalytics_provider,
    )

def latest_quality_for_node(node_id: str) -> QualityResult | None:
    return manager_quality_runtime.latest_quality_for_node(node_id)

def latest_quality_map() -> dict[str, QualityResult]:
    return manager_quality_runtime.latest_quality_map()

def check_quality_ip(ip: str) -> QualityResult:
    return manager_quality_runtime.check_quality_ip(ip, provider_getter=get_scamalytics_provider)

def check_quality_region(region_id: str, limit: int = 20) -> dict[str, Any]:
    return manager_quality_runtime.check_quality_region(region_id, limit)

def quality_provider_status() -> dict[str, Any]:
    return manager_quality_runtime.quality_provider_status()

def validate_routing_region_target(routing_mode: str, target: str) -> None:
    manager_repository_runtime.validate_routing_region_target(routing_mode, target)

def node_matches_allowed_countries(node: dict[str, Any]) -> bool:
    return manager_node_view_runtime.node_matches_allowed_countries(node)

def get_state() -> dict[str, Any]:
    return manager_runtime_state.get_state()

def run_with_lock(callback):
    return manager_thread_runtime.run_with_lock(callback)

def clear_active_connection_state(message: str) -> None:
    manager_connection_runtime.clear_active_connection_state(message)


def get_is_connecting() -> bool:
    return manager_connection_runtime.get_is_connecting()


def set_is_connecting(value: bool) -> None:
    manager_connection_runtime.set_is_connecting(value)


def get_active_openvpn_node_id() -> str:
    return manager_connection_runtime.get_active_openvpn_node_id()


def set_active_openvpn_node_id(node_id: str) -> None:
    manager_connection_runtime.set_active_openvpn_node_id(node_id)


def set_active_openvpn_connection(process: Any, node_id: str) -> None:
    manager_connection_runtime.set_active_openvpn_connection(process, node_id)


def try_acquire_maintenance_lock() -> bool:
    return manager_thread_runtime.try_acquire_maintenance_lock()


def release_maintenance_lock() -> None:
    manager_thread_runtime.release_maintenance_lock()


def start_background_thread(target: Any) -> None:
    manager_thread_runtime.start_background_thread(target)

def set_collector_heartbeat(value: float) -> None:
    manager_monitoring_runtime.set_collector_heartbeat(value)


def set_checker_heartbeat(value: float) -> None:
    manager_monitoring_runtime.set_checker_heartbeat(value)


def set_pinger_heartbeat(value: float) -> None:
    manager_monitoring_runtime.set_pinger_heartbeat(value)

manager_fetch_runtime = ManagerFetchRuntime(
    api_url=API_URL,
    config_dir=CONFIG_DIR,
    max_scan_rows=MAX_SCAN_ROWS,
    allowed_countries=ALLOWED_COUNTRIES,
    allow_insecure_fetch=ALLOW_INSECURE_FETCH,
    blacklist_file=BLACKLIST_FILE,
    lock=lock,
    invalid_backoff_seconds=INVALID_BACKOFF_SECONDS,
    read_nodes=read_nodes,
    set_state=set_state,
    log_line=module_log_writer(log_to_json, "Main"),
    diagnose_api_failure=vpn_utils.diagnose_api_failure,
    get_upstream_proxy=vpn_utils.get_upstream_proxy,
    get_upstream_proxy_auth=vpn_utils.get_upstream_proxy_auth,
    country_translations=vpn_utils.COUNTRY_TRANSLATIONS,
    safe_name=safe_name,
    now=time.time,
)

def vpngate_fetch_facade() -> VpnGateFetchFacade:
    return manager_fetch_runtime.facade()


def fetch_api_text_via_proxy(url: str, ptype: str, phost: str, pport: int, use_ssl_verify: bool = True) -> str:
    return manager_fetch_runtime.fetch_api_text_via_proxy(url, ptype, phost, pport, use_ssl_verify)

def fetch_api_text(url: str | None = None, use_ssl_verify: bool = True) -> str:
    return manager_fetch_runtime.fetch_api_text(url, use_ssl_verify)

def write_ovpn_config(path: Path, config_text: str) -> None:
    manager_runtime_files.write_ovpn_config(path, config_text)

def blacklist_store() -> BlacklistStore:
    return manager_fetch_runtime.blacklist_store()

def load_blacklist() -> dict[str, dict[str, Any]]:
    return manager_fetch_runtime.load_blacklist()

def mark_blacklisted(node: dict[str, Any], message: str) -> None:
    manager_fetch_runtime.mark_blacklisted(node, message)

def fetch_candidates() -> list[dict[str, Any]]:
    return manager_fetch_runtime.fetch_candidates()

def cached_nodes() -> list[dict[str, Any]]:
    return manager_fetch_runtime.cached_nodes()

manager_connection_runtime = ManagerConnectionRuntime(
    state=mutable_state,
    lock=lock,
    cleanup_policy_routing=lambda: cleanup_policy_routing(),
    read_nodes=read_nodes,
    write_nodes=write_nodes,
    load_ui_config=load_ui_config,
    save_ui_config=save_ui_config,
    stop_process=lambda process: stop_process(process),
    kill_existing_openvpn_processes=lambda: kill_existing_openvpn_processes(),
    set_state=set_state,
    run_locked=run_with_lock,
    log_vpn_line=module_log_writer(log_to_json, "VPN"),
    log_line=log_to_json,
    print_line=print_line,
    ensure_dirs=ensure_dirs,
    start_thread=start_background_thread,
    try_acquire_maintenance=try_acquire_maintenance_lock,
    release_maintenance=release_maintenance_lock,
    node_matches_allowed=node_matches_allowed_countries,
    allowed_countries=lambda: ALLOWED_COUNTRIES,
    filter_nodes_by_routing_region=filter_nodes_by_routing_region,
    routing_target_label=routing_target_label,
    parse_int=parse_int,
    ping_latency_ms=vpn_utils.ping_latency_ms,
    write_ovpn_config=write_ovpn_config,
    run_openvpn_until_ready=lambda config_file: run_openvpn_until_ready(
        config_file,
        keep_alive=True,
        route_nopull=True,
    ),
    setup_policy_routing=lambda interface: setup_policy_routing(interface),
    check_proxy_health=lambda: check_proxy_health(),
    fetch_candidates=fetch_candidates,
    check_and_fix_dns=vpn_utils.check_and_fix_dns,
    diagnose_api_failure=vpn_utils.diagnose_api_failure,
    select_maintenance_test_nodes=lambda nodes: select_maintenance_test_nodes(nodes),
    test_multiple_nodes=lambda node_ids: test_multiple_nodes(node_ids),
    now=time.time,
    api_url=lambda: API_URL,
    tun_dev=lambda: TUN_DEV,
    proxy_host=lambda: LOCAL_PROXY_HOST,
    proxy_port=lambda: LOCAL_PROXY_PORT,
    maintenance_test_limit=lambda: MAX_MAINTENANCE_TEST_NODES,
    node_test_workers=lambda: NODE_TEST_WORKERS,
    exclude_datacenter=lambda: EXCLUDE_DATACENTER,
)

manager_monitoring_runtime = ManagerMonitoringRuntime(
    state=mutable_state,
    now=time.time,
    sleep=time.sleep,
    print_line=print_line,
    log_line=log_to_json,
    set_state=set_state,
    maintain_valid_nodes=lambda force: maintain_valid_nodes(force),
    active_openvpn_running=lambda: active_openvpn_running(),
    check_interval_seconds=lambda: CHECK_INTERVAL_SECONDS,
    check_proxy_health=lambda: check_proxy_health(),
    is_connecting=get_is_connecting,
    set_is_connecting=set_is_connecting,
    get_active_node_id=get_active_openvpn_node_id,
    load_ui_config=load_ui_config,
    read_nodes=read_nodes,
    write_nodes=write_nodes,
    run_locked=run_with_lock,
    mark_blacklisted=mark_blacklisted,
    auto_switch_node=lambda: auto_switch_node(),
    connect_node=lambda node_id: connect_node(node_id),
    proxy_port=lambda: LOCAL_PROXY_PORT,
    ping_latency_ms=vpn_utils.ping_latency_ms,
    parse_int=parse_int,
)

manager_web_runtime = ManagerWebRuntime(
    region_repository=REGION_REPOSITORY,
    read_regions=read_regions,
    read_nodes=read_nodes,
    region_from_payload=region_from_payload,
    quality_provider_status=quality_provider_status,
    latest_quality_for_node=latest_quality_for_node,
    latest_quality_map=latest_quality_map,
    test_node_by_id=lambda node_id: test_node_by_id(node_id),
    check_quality_ip=check_quality_ip,
    check_quality_region=check_quality_region,
    bounded_int=bounded_int,
    scamalytics_errors=(ScamalyticsError,),
    write_nodes=write_nodes,
    filter_nodes_by_region=filter_nodes_by_region,
    get_state=get_state,
    set_state=set_state,
    get_active_node_id=lambda: context_active_node_id(),
    get_last_active_ping_time=lambda: get_last_active_ping_time(),
    set_last_active_ping_time=lambda value: set_last_active_ping_time(value),
    get_last_active_latency=lambda: get_last_active_latency(),
    set_last_active_latency=lambda value: set_last_active_latency(value),
    now=time.time,
    ping_latency_ms=vpn_utils.ping_latency_ms,
    parse_int=parse_int,
    start_daemon_thread=lambda target, args: start_daemon_thread(target, args),
    test_multiple_nodes=lambda nodes: test_multiple_nodes(nodes),
    connect_node=lambda node_id: connect_node(node_id),
    stop_active_openvpn=lambda: stop_active_openvpn(),
    load_ui_config=load_ui_config,
    save_ui_config_unlocked=save_ui_config,
    maintain_valid_nodes=lambda force: maintain_valid_nodes(force),
    maintenance_running=maintenance_lock.locked,
    start_maintenance=lambda: start_maintenance_thread(),
    validate_routing_region_target=validate_routing_region_target,
    verify_password=manager_auth_runtime.verify_password,
    verify_username=manager_auth_runtime.verify_username,
    generate_session_token=manager_auth_runtime.generate_session_token,
    check_proxy_health=lambda: check_proxy_health(),
    ui_host=lambda: UI_HOST,
    ui_port=lambda: UI_PORT,
    proxy_host=lambda: LOCAL_PROXY_HOST,
    proxy_port=lambda: LOCAL_PROXY_PORT,
    active_openvpn_running=lambda: active_openvpn_running(),
    is_linux=is_linux,
    tun_dev=lambda: TUN_DEV,
    server_start_time=lambda: mutable_state.server_start_time,
    last_collector_heartbeat=lambda: mutable_state.last_collector_heartbeat,
    last_checker_heartbeat=lambda: mutable_state.last_checker_heartbeat,
    last_pinger_heartbeat=lambda: mutable_state.last_pinger_heartbeat,
    check_interval_seconds=lambda: CHECK_INTERVAL_SECONDS,
    login_html_fallback=default_login_html,
    index_html_fallback=default_index_html,
    active_sessions=active_sessions,
    lock=lock,
    data_dir=lambda: DATA_DIR,
    console_token=console_token,
    diagnose_local_obstructions=diagnose_with_host_keyword(vpn_utils.diagnose_local_obstructions),
    start_thread=start_background_thread,
    sleep=time.sleep,
    exit_process=exit_process,
    print_line=print_line,
)

manager_openvpn_runtime = ManagerOpenVPNRuntime(
    openvpn_cmd=OPENVPN_CMD,
    auth_file=AUTH_FILE,
    data_dir=DATA_DIR,
    config_dir=CONFIG_DIR,
    upstream_proxy_auth_path=UPSTREAM_PROXY_AUTH_FILE,
    root_dir=ROOT_DIR,
    default_dev=lambda: TUN_DEV,
    policy_table=lambda: POLICY_TABLE,
    default_timeout_seconds=lambda: OPENVPN_TEST_TIMEOUT_SECONDS,
    get_upstream_proxy=vpn_utils.get_upstream_proxy,
    write_upstream_proxy_auth_file=upstream_proxy_auth_file,
    diagnose_openvpn_failure=vpn_utils.diagnose_openvpn_failure,
    status_callback=lambda line: update_handshake_status(line),
    log_vpn_line=module_log_writer(log_to_json, "VPN"),
    log_routing_line=module_log_writer(log_to_json, "Routing"),
    print_line=print_line,
    sleep=time.sleep,
)

manager_service_runtime = ManagerServiceRuntime(
    ensure_dirs=ensure_dirs,
    kill_existing_openvpn_processes=lambda: kill_existing_openvpn_processes(),
    data_dir=lambda: DATA_DIR,
    state_file=lambda: STATE_FILE,
    write_json=write_json,
    api_url=lambda: API_URL,
    instance_id=lambda: INSTANCE_ID,
    tun_dev=lambda: TUN_DEV,
    policy_table=lambda: POLICY_TABLE,
    allowed_countries=lambda: ALLOWED_COUNTRIES,
    target_valid_nodes=lambda: TARGET_VALID_NODES,
    fetch_interval_seconds=lambda: FETCH_INTERVAL_SECONDS,
    check_interval_seconds=lambda: CHECK_INTERVAL_SECONDS,
    local_proxy_host=lambda: LOCAL_PROXY_HOST,
    local_proxy_port=lambda: LOCAL_PROXY_PORT,
    ui_host=lambda: UI_HOST,
    ui_port=lambda: UI_PORT,
    start_proxy_server=proxy_server.start_proxy_server,
    collector_loop=lambda: collector_loop(),
    background_proxy_checker=lambda: background_proxy_checker(),
    active_node_pinger=lambda: active_node_pinger(),
    start_daemon_threads=start_daemon_threads,
    wait_for_gateway=wait_for_gateway,
    load_ui_config=load_ui_config,
    bounded_int=bounded_int,
    web_server_runtime=lambda: web_server_runtime(),
    serve_web_forever=serve_web_forever,
    print_line=print_line,
    set_stdout=set_stdout,
    set_stderr=set_stderr,
)
manager_entry_runtime = ManagerEntryRuntime(
    service_runtime_factory=manager_service_runtime.runtime,
    web_server_runtime=lambda: web_server_runtime(),
)


def openvpn_runtime_facade() -> OpenVPNRuntimeFacade:
    return manager_openvpn_runtime.openvpn_runtime_facade()


def policy_routing_facade() -> PolicyRoutingFacade:
    return manager_openvpn_runtime.policy_routing_facade()


def connection_runtime_facade() -> ActiveConnectionRuntimeFacade:
    return manager_connection_runtime.connection_runtime_facade()


def connection_orchestrator() -> ConnectionOrchestrator:
    return manager_connection_runtime.connection_orchestrator()

def monitoring_runtime() -> MonitoringRuntime:
    return manager_monitoring_runtime.runtime()

def web_runtime_wiring() -> WebRuntimeWiring:
    return manager_web_runtime.wiring()

def split_openvpn_command() -> list[str]:
    return manager_openvpn_runtime.split_openvpn_command()

def get_openvpn_version() -> float:
    return manager_openvpn_runtime.get_openvpn_version()

def openvpn_command(config_file: str, route_nopull: bool, dev: str = TUN_DEV) -> list[str]:
    return manager_openvpn_runtime.openvpn_command(config_file, route_nopull, dev)

def stop_process(process: subprocess.Popen[str] | None) -> None:
    manager_openvpn_runtime.stop_process(process)

def kill_existing_openvpn_processes() -> None:
    manager_openvpn_runtime.kill_existing_openvpn_processes()

def update_handshake_status(line_lower: str) -> None:
    update_openvpn_handshake_status(line_lower, set_state)

def run_openvpn_until_ready(config_file: str, keep_alive: bool, route_nopull: bool, timeout: int | None = None, dev: str = TUN_DEV) -> tuple[bool, str, subprocess.Popen[str] | None]:
    return manager_openvpn_runtime.run_openvpn_until_ready(
        config_file,
        keep_alive=keep_alive,
        route_nopull=route_nopull,
        timeout=timeout,
        dev=dev,
    )


def setup_policy_routing(interface: str = TUN_DEV, table: str = POLICY_TABLE) -> None:
    manager_openvpn_runtime.setup_policy_routing(interface, table)

def cleanup_policy_routing(table: str = POLICY_TABLE) -> None:
    manager_openvpn_runtime.cleanup_policy_routing(table)

def stop_active_openvpn() -> None:
    manager_connection_runtime.stop_active_openvpn()

def active_openvpn_running() -> bool:
    return manager_connection_runtime.active_openvpn_running()

def sort_all_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return manager_node_view_runtime.sort_all_nodes(nodes)

manager_node_probe_runtime = ManagerNodeProbeRuntime(
    read_nodes=read_nodes,
    write_nodes=write_nodes,
    run_locked=run_with_lock,
    node_matches_allowed=node_matches_allowed_countries,
    allowed_countries=lambda: ALLOWED_COUNTRIES,
    config_dir=lambda: CONFIG_DIR,
    safe_name=safe_name,
    write_config=write_ovpn_config,
    ping_latency_ms=vpn_utils.ping_latency_ms,
    run_openvpn=lambda *args, **kwargs: run_openvpn_until_ready(*args, **kwargs),
    parse_int=parse_int,
    enrich_ip_info=vpn_utils.enrich_ip_info,
    record_quality=record_quality_result_from_probe,
    sort_nodes=sort_all_nodes,
    now=time.time,
    print_line=print_line,
    load_ui_config=load_ui_config,
    filter_nodes_by_routing_region=filter_nodes_by_routing_region,
    retest_interval_seconds=lambda: NODE_RETEST_INTERVAL_SECONDS,
    max_maintenance_nodes=lambda: MAX_MAINTENANCE_TEST_NODES,
)


def node_probe_runtime() -> NodeProbeRuntime:
    return manager_node_probe_runtime.runtime()

def test_node_by_id(node_id: str) -> dict[str, Any]:
    return manager_node_probe_runtime.test_node_by_id(node_id)

def test_multiple_nodes(
    node_ids: list[str],
    timeout: int = OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS,
    max_workers: int = NODE_TEST_WORKERS,
) -> list[dict[str, Any]]:
    return manager_node_probe_runtime.test_multiple_nodes(
        node_ids,
        timeout=timeout,
        max_workers=max_workers,
    )

def select_maintenance_test_nodes(nodes: list[dict[str, Any]]) -> list[str]:
    return manager_node_probe_runtime.select_maintenance_test_nodes(nodes)

def auto_switch_node(attempt: int = 0) -> None:
    connection_orchestrator().auto_switch_node(attempt)

def connect_node(node_id: str) -> str:
    return connection_orchestrator().connect_node(node_id)

def maintain_valid_nodes(force: bool = False) -> str:
    return connection_orchestrator().maintain_valid_nodes(force)


def collector_loop() -> None:
    manager_monitoring_runtime.collector_loop()

def check_proxy_health() -> dict[str, Any]:
    return manager_proxy_health_runtime.check_proxy_health()

def background_proxy_checker() -> None:
    manager_monitoring_runtime.proxy_checker_loop()

def active_node_pinger() -> None:
    manager_monitoring_runtime.active_node_pinger_loop()


def context_active_node_id() -> str:
    return manager_node_view_runtime.context_active_node_id()


def get_last_active_ping_time() -> float:
    return manager_connection_runtime.get_last_active_ping_time()


def set_last_active_ping_time(value: float) -> None:
    manager_connection_runtime.set_last_active_ping_time(value)


def get_last_active_latency() -> int:
    return manager_connection_runtime.get_last_active_latency()


def set_last_active_latency(value: int) -> None:
    manager_connection_runtime.set_last_active_latency(value)


def start_daemon_thread(target: Any, args: tuple[Any, ...]) -> None:
    manager_thread_runtime.start_daemon_thread(target, args)


def start_maintenance_thread() -> None:
    manager_thread_runtime.start_maintenance_thread()


def clear_active_sessions() -> None:
    manager_web_runtime.clear_active_sessions()

def schedule_server_restart(message: str) -> None:
    manager_web_runtime.schedule_server_restart(message)

def save_ui_config_locked(config: dict[str, Any]) -> None:
    manager_web_runtime.save_ui_config_locked(config)

def add_active_session(token: str, expires_at: float) -> None:
    manager_web_runtime.add_active_session(token, expires_at)

def remove_active_session(token: str) -> None:
    manager_web_runtime.remove_active_session(token)

def proxy_gateway_status() -> tuple[bool, str]:
    return manager_web_runtime.proxy_gateway_status()

def read_api_log_entries() -> list[dict[str, Any]]:
    return manager_web_runtime.read_api_log_entries()

def route_context_factory() -> WebRouteContextFactory:
    return manager_web_runtime.route_context_factory()

def web_server_runtime() -> WebServerRuntime:
    return manager_web_runtime.web_server_runtime()



def service_runtime() -> VpnGateServiceRuntime:
    return manager_entry_runtime.service_runtime()


Handler = manager_entry_runtime.handler_class()



def main() -> None:
    manager_entry_runtime.main()

if __name__ == "__main__":
    main()
