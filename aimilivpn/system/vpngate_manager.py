#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import select
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
import sys

# Prefer IPv4 resolution to avoid slow AAAA DNS timeouts (e.g. in WSL),
# but fall back to system default (IPv6) if IPv4 resolution fails.
# This ensures pure-IPv6 VPS (with NAT64/clatd) can still function.
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0:
        if isinstance(host, str) and ":" in host:
            return _orig_getaddrinfo(host, port, socket.AF_INET6, type, proto, flags)
        # Try IPv4 first for speed; fall back to system default (allows IPv6/NAT64)
        try:
            results = _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
            if results:
                return results
        except socket.gaierror:
            pass
        return _orig_getaddrinfo(host, port, 0, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo

import vpn_utils
from aimilivpn.core.config import load_config
from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.core.auth import (
    generate_password as secure_generate_password,
    generate_session_token,
    verify_password,
    verify_username,
)
from aimilivpn.core.logging_utils import redact_log_message
from aimilivpn.core.nodes import sort_nodes_for_display
from aimilivpn.core.probe import TestIndexPool
from aimilivpn.core import openvpn as openvpn_core
from aimilivpn.core import proxy as proxy_core
from aimilivpn.core.connection import (
    clear_active_flags,
    delete_file_if_exists,
    find_active_config_file,
)
from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository
from aimilivpn.providers.local_probe import quality_result_to_node_patch
from aimilivpn.providers.scamalytics import (
    ScamalyticsError,
    ScamalyticsProvider,
)
from aimilivpn.system.blacklist_store import BlacklistStore
from aimilivpn.system.connection_orchestrator import ConnectionOrchestrator
from aimilivpn.system.connection_runtime import ActiveConnectionRuntimeFacade
from aimilivpn.system.json_logs import JsonLogWriter, cleanup_json_logs
from aimilivpn.system.monitoring_runtime import MonitoringRuntime
from aimilivpn.system.node_probe_runtime import NodeProbeRuntime
from aimilivpn.system.openvpn_runtime import OpenVPNRuntimeFacade
from aimilivpn.system.policy_routing import PolicyRoutingFacade
from aimilivpn.system import proxy_server
from aimilivpn.system import quality_runtime
from aimilivpn.system.repository_facade import RepositoryFacade
from aimilivpn.system.runtime_paths import (
    build_runtime_paths,
    ensure_runtime_dirs,
    write_upstream_proxy_auth_file,
)
from aimilivpn.system.service_runtime import Tee, VpnGateServiceRuntime
from aimilivpn.system.state_store import RuntimeStateStore, read_json_file, write_json_file
from aimilivpn.system.startup import start_daemon_threads, wait_for_gateway
from aimilivpn.system.ui_config import UiConfigStore, generate_username
from aimilivpn.system.web_runtime import WebRuntimeWiring
from aimilivpn.system.vpngate_fetch import VpnGateFetchFacade
from aimilivpn.web.api import quality_to_dict, region_to_dict
from aimilivpn.web.context_factory import WebRouteContextFactory
from aimilivpn.web.server import WebRequestHandler, WebServerRuntime, serve_web_forever

def env_int(name: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        print(f"[配置警告] 环境变量 {name}={raw!r} 不是有效整数，使用默认值 {default}", flush=True)
        value = default
    if min_value is not None and value < min_value:
        print(f"[配置警告] 环境变量 {name}={value} 小于允许值 {min_value}，使用默认值 {default}", flush=True)
        return default
    if max_value is not None and value > max_value:
        print(f"[配置警告] 环境变量 {name}={value} 大于允许值 {max_value}，使用默认值 {default}", flush=True)
        return default
    return value

def bounded_int(value: Any, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed

API_URL = "https://www.vpngate.net/api/iphone/"
FETCH_INTERVAL_SECONDS = env_int("FETCH_INTERVAL_SECONDS", 1260, 1)
CHECK_INTERVAL_SECONDS = env_int("CHECK_INTERVAL_SECONDS", 1260, 1)
TARGET_VALID_NODES = env_int("TARGET_VALID_NODES", 3, 1)
MAX_SCAN_ROWS = env_int("MAX_SCAN_ROWS", 300, 1)
OPENVPN_TEST_TIMEOUT_SECONDS = env_int("OPENVPN_TEST_TIMEOUT_SECONDS", 35, 1)
OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS = env_int("OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS", 8, 3)
NODE_TEST_WORKERS = env_int("NODE_TEST_WORKERS", 2, 1, 10)
MAX_MAINTENANCE_TEST_NODES = env_int("MAX_MAINTENANCE_TEST_NODES", max(18, TARGET_VALID_NODES * 6), 1)
NODE_RETEST_INTERVAL_SECONDS = env_int("NODE_RETEST_INTERVAL_SECONDS", 6 * 3600, 60)
OPENVPN_CMD = os.environ.get("OPENVPN_CMD", "openvpn")
OPENVPN_AUTH_USER = os.environ.get("OPENVPN_AUTH_USER", "vpn")
OPENVPN_AUTH_PASS = os.environ.get("OPENVPN_AUTH_PASS", "vpn")
LOCAL_PROXY_HOST = os.environ.get("LOCAL_PROXY_HOST", "127.0.0.1")
LOCAL_PROXY_PORT = env_int("LOCAL_PROXY_PORT", 7928, 1, 65535)
UI_HOST = os.environ.get("UI_HOST", "::")
UI_PORT = env_int("UI_PORT", 8787, 1, 65535)
INVALID_BACKOFF_SECONDS = env_int("INVALID_BACKOFF_SECONDS", 30 * 60, 1)
INSTANCE_ID = os.environ.get("INSTANCE_ID", "default").strip().lower() or "default"
TUN_DEV = os.environ.get("TUN_DEV", "tun0").strip() or "tun0"
POLICY_TABLE = os.environ.get("POLICY_TABLE", "100").strip() or "100"
_allowed_countries_raw = os.environ.get("ALLOWED_COUNTRIES", "").strip().upper()
ALLOWED_COUNTRIES: set[str] = {
    item.strip()
    for item in _allowed_countries_raw.split(",")
    if item.strip()
}
EXCLUDE_DATACENTER = os.environ.get("EXCLUDE_DATACENTER", "0").strip().lower() in ("1", "true", "yes", "on")
ALLOW_INSECURE_FETCH = os.environ.get("ALLOW_INSECURE_FETCH", "0").strip().lower() in ("1", "true", "yes", "on")

ROOT_DIR = (
    Path(sys.executable).resolve().parent
    if globals().get("__compiled__")
    else Path(os.environ.get("AIMILIVPN_INSTALL_DIR") or Path.cwd()).resolve()
)
RUNTIME_PATHS = build_runtime_paths(ROOT_DIR, os.environ.get("VPNGATE_DATA_DIR"))
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
_scamalytics_provider: ScamalyticsProvider | None = None

lock = threading.RLock()
maintenance_lock = threading.Lock()
active_sessions: dict[str, float] = {}
active_openvpn_process: subprocess.Popen[str] | None = None
active_openvpn_node_id = ""
is_connecting = True
last_active_ping_time = 0.0
last_active_latency = 0

last_collector_heartbeat = 0.0
last_checker_heartbeat = 0.0
last_pinger_heartbeat = 0.0
server_start_time = time.time()

def ensure_dirs() -> None:
    ensure_runtime_dirs(RUNTIME_PATHS, OPENVPN_AUTH_USER, OPENVPN_AUTH_PASS)

def upstream_proxy_auth_file() -> str | None:
    return write_upstream_proxy_auth_file(
        RUNTIME_PATHS,
        vpn_utils.get_upstream_proxy_auth,
        lambda message: print(message, flush=True),
    )

def write_json(path: Path, data: Any) -> None:
    write_json_file(path, data, lock)

def read_json(path: Path, default: Any) -> Any:
    return read_json_file(path, default, lock)

def generate_random_password() -> str:
    return secure_generate_password()

def generate_random_username() -> str:
    return generate_username()


def ui_config_store() -> UiConfigStore:
    return UiConfigStore(
        data_dir=DATA_DIR,
        lock=lock,
        ui_host=UI_HOST,
        ui_port=UI_PORT,
        proxy_port=LOCAL_PROXY_PORT,
        bounded_int=bounded_int,
        password_factory=generate_random_password,
        username_factory=generate_random_username,
    )

def load_ui_config() -> dict[str, Any]:
    return ui_config_store().load()

def save_ui_config(config: dict[str, Any]) -> None:
    ui_config_store().save(config)

# 初始化时优先从 ui_auth.json 加载保存的代理出站端口和网页端口配置以覆盖环境变量
try:
    _init_cfg = load_ui_config()
    if "proxy_port" in _init_cfg:
        LOCAL_PROXY_PORT = bounded_int(_init_cfg["proxy_port"], LOCAL_PROXY_PORT, 1024, 65535)
    if "port" in _init_cfg:
        UI_PORT = bounded_int(_init_cfg["port"], UI_PORT, 1, 65535)
    if "host" in _init_cfg:
        UI_HOST = _init_cfg["host"]
except Exception:
    pass

def get_session_token(password: str, username: str = "admin") -> str:
    return generate_session_token()

_log_cleanup_state: dict[str, float] = {}


def json_log_writer() -> JsonLogWriter:
    return JsonLogWriter(
        logs_dir=DATA_DIR / "logs",
        lock=lock,
        redact_message=redact_log_message,
        cleanup_state=_log_cleanup_state,
    )


def cleanup_old_logs(logs_dir: Path) -> None:
    cleanup_json_logs(logs_dir, lock, _log_cleanup_state)


def log_to_json(level: str, module: str, message: str) -> None:
    json_log_writer().write(level, module, message)


def runtime_state_store() -> RuntimeStateStore:
    return RuntimeStateStore(
        state_file=STATE_FILE,
        lock=lock,
        active_node_id=lambda: str(active_openvpn_node_id or ""),
        is_connecting=lambda: is_connecting,
        load_ui_config=load_ui_config,
        api_url=API_URL,
        instance_id=INSTANCE_ID,
        tun_dev=TUN_DEV,
        policy_table=POLICY_TABLE,
        allowed_countries=ALLOWED_COUNTRIES,
        target_valid_nodes=TARGET_VALID_NODES,
        fetch_interval_seconds=FETCH_INTERVAL_SECONDS,
        check_interval_seconds=CHECK_INTERVAL_SECONDS,
        local_proxy_host=LOCAL_PROXY_HOST,
        local_proxy_port=LOCAL_PROXY_PORT,
    )


def set_state(**updates: Any) -> None:
    runtime_state_store().set_state(**updates)

def repository_facade() -> RepositoryFacade:
    return RepositoryFacade(
        node_repository=NODE_REPOSITORY,
        region_repository=REGION_REPOSITORY,
        country_translations=vpn_utils.COUNTRY_TRANSLATIONS,
    )

def read_nodes() -> list[dict[str, Any]]:
    return repository_facade().read_nodes()

def write_nodes(nodes: list[dict[str, Any]]) -> None:
    repository_facade().write_nodes(nodes)

def read_regions() -> list[RegionProfile]:
    return repository_facade().read_regions()

def region_from_payload(payload: dict[str, Any], existing: RegionProfile | None = None) -> RegionProfile:
    return repository_facade().region_from_payload(payload, existing)

def filter_nodes_by_region(nodes: list[dict[str, Any]], region_id: str) -> list[dict[str, Any]]:
    return repository_facade().filter_nodes_by_region(nodes, region_id)

def region_target_id(target: str) -> str:
    return repository_facade().region_target_id(target)

def get_region_routing_target(target: str) -> RegionProfile | None:
    return repository_facade().get_region_routing_target(target)

def routing_target_label(target: str) -> str:
    return repository_facade().routing_target_label(target)

def node_matches_country_target(node: dict[str, Any], target: str) -> bool:
    return repository_facade().node_matches_country_target(node, target)

def node_matches_routing_region(node: dict[str, Any], target: str) -> bool:
    return repository_facade().node_matches_routing_region(node, target)

def filter_nodes_by_routing_region(nodes: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    return repository_facade().filter_nodes_by_routing_region(nodes, target)


def get_scamalytics_provider() -> ScamalyticsProvider | None:
    global _scamalytics_provider
    _scamalytics_provider = quality_runtime.configured_scamalytics_provider(load_config(ROOT_DIR), _scamalytics_provider)
    return _scamalytics_provider


def enrich_quality_with_scamalytics(result: QualityResult) -> QualityResult:
    return quality_runtime.enrich_with_scamalytics(result, get_scamalytics_provider)


def record_quality_result_from_probe(
    node: dict[str, Any],
    openvpn_success: bool | None,
    latency_ms: int,
    probe_message: str = "",
) -> QualityResult:
    return quality_runtime.record_from_probe(
        node,
        openvpn_success,
        latency_ms,
        probe_message,
        quality_repository=QUALITY_REPOSITORY,
        provider_getter=get_scamalytics_provider,
    )

def latest_quality_for_node(node_id: str) -> QualityResult | None:
    return quality_runtime.latest_for_node(QUALITY_REPOSITORY, node_id)

def latest_quality_map() -> dict[str, QualityResult]:
    return quality_runtime.latest_map(QUALITY_REPOSITORY)

def check_quality_ip(ip: str) -> QualityResult:
    return quality_runtime.check_ip(ip, provider_getter=get_scamalytics_provider, quality_repository=QUALITY_REPOSITORY)

def check_quality_region(region_id: str, limit: int = 20) -> dict[str, Any]:
    return quality_runtime.check_region(
        region_id,
        limit,
        region_target_id=region_target_id,
        region_repository=REGION_REPOSITORY,
        quality_repository=QUALITY_REPOSITORY,
        read_nodes=read_nodes,
        node_allowed=node_matches_allowed_countries,
        bounded_int=bounded_int,
        test_multiple_nodes=test_multiple_nodes,
    )

def quality_provider_status() -> dict[str, Any]:
    return quality_runtime.provider_status(ROOT_DIR)

def validate_routing_region_target(routing_mode: str, target: str) -> None:
    repository_facade().validate_routing_region_target(routing_mode, target)

def node_matches_allowed_countries(node: dict[str, Any]) -> bool:
    if not ALLOWED_COUNTRIES:
        return True
    country_short = str(node.get("country_short") or "").strip().upper()
    if country_short in ALLOWED_COUNTRIES:
        return True
    node_id = str(node.get("id") or "").strip().upper()
    return any(node_id.startswith(f"{country}_") for country in ALLOWED_COUNTRIES)

def get_state() -> dict[str, Any]:
    return runtime_state_store().get_state()

def run_with_lock(callback):
    with lock:
        return callback()

def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("._") or "node"

def clear_active_connection_state(message: str) -> None:
    global active_openvpn_process, active_openvpn_node_id
    active_openvpn_process, active_openvpn_node_id = connection_runtime_facade().clear_active_state(
        active_openvpn_process,
        message,
    )


def get_is_connecting() -> bool:
    return is_connecting


def set_is_connecting(value: bool) -> None:
    global is_connecting
    is_connecting = value


def get_active_openvpn_node_id() -> str:
    return active_openvpn_node_id


def set_active_openvpn_node_id(node_id: str) -> None:
    global active_openvpn_node_id
    active_openvpn_node_id = node_id


def set_active_openvpn_connection(process: Any, node_id: str) -> None:
    global active_openvpn_process, active_openvpn_node_id
    active_openvpn_process = process
    active_openvpn_node_id = node_id


def try_acquire_maintenance_lock() -> bool:
    return maintenance_lock.acquire(blocking=False)


def release_maintenance_lock() -> None:
    maintenance_lock.release()


def start_background_thread(target: Any) -> None:
    threading.Thread(target=target, daemon=True).start()

def set_collector_heartbeat(value: float) -> None:
    global last_collector_heartbeat
    last_collector_heartbeat = value


def set_checker_heartbeat(value: float) -> None:
    global last_checker_heartbeat
    last_checker_heartbeat = value


def set_pinger_heartbeat(value: float) -> None:
    global last_pinger_heartbeat
    last_pinger_heartbeat = value
def parse_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def vpngate_fetch_facade() -> VpnGateFetchFacade:
    return VpnGateFetchFacade(
        api_url=API_URL,
        config_dir=CONFIG_DIR,
        max_scan_rows=MAX_SCAN_ROWS,
        allowed_countries=ALLOWED_COUNTRIES,
        allow_insecure_fetch=ALLOW_INSECURE_FETCH,
        load_blacklist=load_blacklist,
        cached_nodes=cached_nodes,
        set_state=set_state,
        log_line=lambda level, message: log_to_json(level, "Main", message),
        diagnose_api_failure=vpn_utils.diagnose_api_failure,
        get_upstream_proxy=vpn_utils.get_upstream_proxy,
        get_upstream_proxy_auth=vpn_utils.get_upstream_proxy_auth,
        country_translations=vpn_utils.COUNTRY_TRANSLATIONS,
        safe_name=safe_name,
    )


def fetch_api_text_via_proxy(url: str, ptype: str, phost: str, pport: int, use_ssl_verify: bool = True) -> str:
    return vpngate_fetch_facade().fetch_api_text_via_proxy(url, ptype, phost, pport, use_ssl_verify)

def fetch_api_text(url: str | None = None, use_ssl_verify: bool = True) -> str:
    return vpngate_fetch_facade().fetch_api_text(url, use_ssl_verify)

def write_ovpn_config(path: Path, config_text: str) -> None:
    openvpn_core.write_ovpn_config(path, config_text)

def blacklist_store() -> BlacklistStore:
    return BlacklistStore(
        path=BLACKLIST_FILE,
        lock=lock,
        backoff_seconds=INVALID_BACKOFF_SECONDS,
        now=time.time,
    )

def load_blacklist() -> dict[str, dict[str, Any]]:
    return blacklist_store().load()

def mark_blacklisted(node: dict[str, Any], message: str) -> None:
    blacklist_store().mark(node, message)

def fetch_candidates() -> list[dict[str, Any]]:
    return vpngate_fetch_facade().fetch_candidates()

def cached_nodes() -> list[dict[str, Any]]:
    return read_nodes()

_openvpn_runtime_facade: OpenVPNRuntimeFacade | None = None
_policy_routing_facade: PolicyRoutingFacade | None = None
_connection_runtime_facade: ActiveConnectionRuntimeFacade | None = None
_connection_orchestrator: ConnectionOrchestrator | None = None
_monitoring_runtime: MonitoringRuntime | None = None
_web_runtime_wiring: WebRuntimeWiring | None = None
_service_runtime: VpnGateServiceRuntime | None = None


def openvpn_runtime_facade() -> OpenVPNRuntimeFacade:
    global _openvpn_runtime_facade
    if _openvpn_runtime_facade is None:
        _openvpn_runtime_facade = OpenVPNRuntimeFacade(
            openvpn_cmd=OPENVPN_CMD,
            auth_file=AUTH_FILE,
            data_dir=DATA_DIR,
            config_dir=CONFIG_DIR,
            upstream_proxy_auth_path=UPSTREAM_PROXY_AUTH_FILE,
            get_upstream_proxy=vpn_utils.get_upstream_proxy,
            write_upstream_proxy_auth_file=upstream_proxy_auth_file,
            print_line=lambda message: print(message, flush=True),
        )
    return _openvpn_runtime_facade


def policy_routing_facade() -> PolicyRoutingFacade:
    global _policy_routing_facade
    if _policy_routing_facade is None:
        _policy_routing_facade = PolicyRoutingFacade(
            sleep=time.sleep,
            print_line=lambda message: print(message, flush=True),
            log_line=lambda level, message: log_to_json(level, "Routing", message),
        )
    return _policy_routing_facade


def connection_runtime_facade() -> ActiveConnectionRuntimeFacade:
    global _connection_runtime_facade
    if _connection_runtime_facade is None:
        _connection_runtime_facade = ActiveConnectionRuntimeFacade(
            cleanup_policy_routing=cleanup_policy_routing,
            read_nodes=read_nodes,
            write_nodes=write_nodes,
            load_ui_config=load_ui_config,
            save_ui_config=save_ui_config,
            find_active_config_file=find_active_config_file,
            clear_active_flags=clear_active_flags,
            stop_process=stop_process,
            kill_existing_processes=kill_existing_openvpn_processes,
            delete_file_if_exists=delete_file_if_exists,
            set_state=set_state,
            run_exclusive=run_with_lock,
            log_line=lambda level, message: log_to_json(level, "VPN", message),
            print_line=lambda message: print(message, flush=True),
        )
    return _connection_runtime_facade


def connection_orchestrator() -> ConnectionOrchestrator:
    global _connection_orchestrator
    if _connection_orchestrator is None:
        _connection_orchestrator = ConnectionOrchestrator(
            connection_runtime=lambda: connection_runtime_facade(),
            ensure_dirs=lambda: ensure_dirs(),
            run_locked=run_with_lock,
            read_nodes=lambda: read_nodes(),
            write_nodes=lambda nodes: write_nodes(nodes),
            load_ui_config=lambda: load_ui_config(),
            set_state=lambda **updates: set_state(**updates),
            log_line=lambda level, module, message: log_to_json(level, module, message),
            print_line=lambda message: print(message, flush=True),
            start_thread=start_background_thread,
            try_acquire_maintenance=try_acquire_maintenance_lock,
            release_maintenance=release_maintenance_lock,
            get_is_connecting=get_is_connecting,
            set_is_connecting=set_is_connecting,
            get_active_node_id=get_active_openvpn_node_id,
            set_active_node_id=set_active_openvpn_node_id,
            get_last_active_latency=get_last_active_latency,
            set_last_active_latency=set_last_active_latency,
            set_last_active_ping_time=set_last_active_ping_time,
            set_active_connection=set_active_openvpn_connection,
            node_matches_allowed=lambda node: node_matches_allowed_countries(node),
            allowed_countries=lambda: ALLOWED_COUNTRIES,
            filter_nodes_by_routing_region=lambda nodes, target: filter_nodes_by_routing_region(nodes, target),
            routing_target_label=lambda target: routing_target_label(target),
            parse_int=parse_int,
            ping_latency_ms=lambda host, port, fallback: vpn_utils.ping_latency_ms(host, port, fallback),
            write_ovpn_config=lambda path, text: write_ovpn_config(path, text),
            run_openvpn_until_ready=lambda config_file: run_openvpn_until_ready(
                config_file,
                keep_alive=True,
                route_nopull=True,
            ),
            stop_active_openvpn=lambda: stop_active_openvpn(),
            active_openvpn_running=lambda: active_openvpn_running(),
            setup_policy_routing=lambda interface: setup_policy_routing(interface),
            check_proxy_health=lambda: check_proxy_health(),
            clear_active_connection_state=lambda message: clear_active_connection_state(message),
            fetch_candidates=lambda: fetch_candidates(),
            check_and_fix_dns=lambda: vpn_utils.check_and_fix_dns(),
            diagnose_api_failure=lambda url: vpn_utils.diagnose_api_failure(url),
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
    return _connection_orchestrator

def monitoring_runtime() -> MonitoringRuntime:
    global _monitoring_runtime
    if _monitoring_runtime is None:
        _monitoring_runtime = MonitoringRuntime(
            now=time.time,
            sleep=time.sleep,
            set_collector_heartbeat=set_collector_heartbeat,
            set_checker_heartbeat=set_checker_heartbeat,
            set_pinger_heartbeat=set_pinger_heartbeat,
            print_line=lambda message: print(message, flush=True),
            log_line=lambda level, module, message: log_to_json(level, module, message),
            set_state=lambda **updates: set_state(**updates),
            maintain_valid_nodes=lambda force: maintain_valid_nodes(force),
            active_openvpn_running=lambda: active_openvpn_running(),
            check_interval_seconds=lambda: CHECK_INTERVAL_SECONDS,
            check_proxy_health=lambda: check_proxy_health(),
            is_connecting=get_is_connecting,
            set_is_connecting=set_is_connecting,
            get_active_node_id=get_active_openvpn_node_id,
            load_ui_config=lambda: load_ui_config(),
            read_nodes=lambda: read_nodes(),
            write_nodes=lambda nodes: write_nodes(nodes),
            run_locked=run_with_lock,
            mark_blacklisted=lambda node, message: mark_blacklisted(node, message),
            auto_switch_node=lambda: auto_switch_node(),
            connect_node=lambda node_id: connect_node(node_id),
            proxy_port=lambda: LOCAL_PROXY_PORT,
            ping_latency_ms=lambda host, port, fallback: vpn_utils.ping_latency_ms(host, port, fallback),
            parse_int=parse_int,
        )
    return _monitoring_runtime

def web_runtime_wiring() -> WebRuntimeWiring:
    global _web_runtime_wiring
    if _web_runtime_wiring is None:
        _web_runtime_wiring = WebRuntimeWiring(
            region_repository=REGION_REPOSITORY,
            read_regions=lambda: read_regions(),
            read_nodes=lambda: read_nodes(),
            region_from_payload=lambda payload, existing=None: region_from_payload(payload, existing),
            quality_provider_status=lambda: quality_provider_status(),
            latest_quality_for_node=lambda node_id: latest_quality_for_node(node_id),
            latest_quality_map=lambda: latest_quality_map(),
            test_node_by_id=lambda node_id: test_node_by_id(node_id),
            check_quality_ip=lambda ip: check_quality_ip(ip),
            check_quality_region=lambda region_id, limit: check_quality_region(region_id, limit),
            bounded_int=bounded_int,
            scamalytics_errors=(ScamalyticsError,),
            write_nodes=lambda nodes: write_nodes(nodes),
            filter_nodes_by_region=lambda nodes, region_id: filter_nodes_by_region(nodes, region_id),
            get_state=lambda: get_state(),
            set_state=lambda **updates: set_state(**updates),
            get_active_node_id=context_active_node_id,
            get_last_active_ping_time=get_last_active_ping_time,
            set_last_active_ping_time=set_last_active_ping_time,
            get_last_active_latency=get_last_active_latency,
            set_last_active_latency=set_last_active_latency,
            now=time.time,
            ping_latency_ms=lambda host, port, fallback: vpn_utils.ping_latency_ms(host, port, fallback),
            parse_int=parse_int,
            start_daemon_thread=start_daemon_thread,
            test_multiple_nodes=lambda nodes: test_multiple_nodes(nodes),
            connect_node=lambda node_id: connect_node(node_id),
            stop_active_openvpn=lambda: stop_active_openvpn(),
            load_ui_config=lambda: load_ui_config(),
            save_ui_config_unlocked=lambda config: save_ui_config(config),
            maintain_valid_nodes=lambda force: maintain_valid_nodes(force),
            maintenance_running=maintenance_lock.locked,
            start_maintenance=start_maintenance_thread,
            validate_routing_region_target=lambda mode, target: validate_routing_region_target(mode, target),
            verify_password=verify_password,
            verify_username=verify_username,
            generate_session_token=generate_session_token,
            check_proxy_health=lambda: check_proxy_health(),
            ui_host=lambda: UI_HOST,
            ui_port=lambda: UI_PORT,
            proxy_host=lambda: LOCAL_PROXY_HOST,
            proxy_port=lambda: LOCAL_PROXY_PORT,
            active_openvpn_running=lambda: active_openvpn_running(),
            is_linux=lambda: sys.platform.startswith("linux"),
            tun_dev=lambda: TUN_DEV,
            server_start_time=lambda: server_start_time,
            last_collector_heartbeat=lambda: last_collector_heartbeat,
            last_checker_heartbeat=lambda: last_checker_heartbeat,
            last_pinger_heartbeat=lambda: last_pinger_heartbeat,
            check_interval_seconds=lambda: CHECK_INTERVAL_SECONDS,
            login_html_fallback=lambda: LOGIN_HTML,
            index_html_fallback=lambda: INDEX_HTML,
            active_sessions=active_sessions,
            lock=lock,
            data_dir=lambda: DATA_DIR,
            console_token=lambda: os.environ.get("INSTANCE_API_TOKEN", ""),
            diagnose_local_obstructions=lambda port, host: vpn_utils.diagnose_local_obstructions(port, host=host),
            start_thread=start_background_thread,
            sleep=time.sleep,
            exit_process=os._exit,
            print_line=lambda message: print(message, flush=True),
        )
    return _web_runtime_wiring

def split_openvpn_command() -> list[str]:
    return openvpn_runtime_facade().split_command()

def get_openvpn_version() -> float:
    return openvpn_runtime_facade().get_version()

def openvpn_command(config_file: str, route_nopull: bool, dev: str = TUN_DEV) -> list[str]:
    return openvpn_runtime_facade().command(config_file, route_nopull, dev)

def stop_process(process: subprocess.Popen[str] | None) -> None:
    openvpn_runtime_facade().stop_process(process)

def kill_existing_openvpn_processes() -> None:
    openvpn_runtime_facade().kill_existing_processes()

def update_handshake_status(line_lower: str) -> None:
    status_map = {
        "resolving": ("解析域名", "正在解析服务器域名与 IP 地址..."),
        "udp link local": ("物理连接", "已创建本地套接字，开始尝试发送数据包..."),
        "tcp link local": ("物理连接", "已创建本地套接字，开始尝试发送数据包..."),
        "tls: initial packet": ("证书握手", "已成功发送首包，正在与远程服务器建立 TLS 安全通道..."),
        "verify ok": ("证书校验", "服务器证书校验成功，正在进行身份验证..."),
        "peer connection initiated": ("协商加密", "控制通道已建立，已初始化与服务器的加密对等连接..."),
        "push_request": ("请求配置", "正在向服务器发送 PUSH_REQUEST 请求配置参数与 IP 分配..."),
        "push_reply": ("应用配置", "已接收服务器 PUSH_REPLY，获取到 IP 分配，正在准备配置网卡..."),
        "tun/tap device": ("创建网卡", "正在创建虚拟通道并打开 TUN 虚拟网卡设备..."),
        "do_ifconfig": ("网卡配置", "正在为虚拟网卡配置 IP 地址及相关网络属性..."),
    }
    for key, (short_status, detailed_desc) in status_map.items():
        if key in line_lower:
            set_state(active_node_latency=short_status, last_check_message=detailed_desc)
            break

def run_openvpn_until_ready(config_file: str, keep_alive: bool, route_nopull: bool, timeout: int | None = None, dev: str = TUN_DEV) -> tuple[bool, str, subprocess.Popen[str] | None]:
    limit = timeout if timeout is not None else OPENVPN_TEST_TIMEOUT_SECONDS
    return openvpn_runtime_facade().run_until_ready(
        config_file=config_file,
        keep_alive=keep_alive,
        route_nopull=route_nopull,
        timeout=limit,
        dev=dev,
        cwd=ROOT_DIR,
        diagnose_failure=vpn_utils.diagnose_openvpn_failure,
        log_line=lambda level, message: log_to_json(level, "VPN", message),
        status_callback=update_handshake_status,
        print_line=lambda message: print(message, flush=True),
    )


def setup_policy_routing(interface: str = TUN_DEV, table: str = POLICY_TABLE) -> None:
    policy_routing_facade().setup(interface, table)

def cleanup_policy_routing(table: str = POLICY_TABLE) -> None:
    policy_routing_facade().cleanup(table)

def stop_active_openvpn() -> None:
    global active_openvpn_process, active_openvpn_node_id
    with lock:
        active_openvpn_process, active_openvpn_node_id = connection_runtime_facade().stop_active(
            active_openvpn_process,
            active_openvpn_node_id,
        )

def active_openvpn_running() -> bool:
    return connection_runtime_facade().is_running(active_openvpn_process)

def sort_all_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sort_nodes_for_display(nodes, parse_int=parse_int)

test_index_pool = TestIndexPool()
_node_probe_runtime: NodeProbeRuntime | None = None


def node_probe_runtime() -> NodeProbeRuntime:
    global _node_probe_runtime
    if _node_probe_runtime is None:
        _node_probe_runtime = NodeProbeRuntime(
            read_nodes=lambda: read_nodes(),
            write_nodes=lambda nodes: write_nodes(nodes),
            run_locked=run_with_lock,
            node_matches_allowed=lambda node: node_matches_allowed_countries(node),
            allowed_countries=lambda: ALLOWED_COUNTRIES,
            config_dir=lambda: CONFIG_DIR,
            safe_name=lambda value: safe_name(value),
            write_config=lambda path, text: write_ovpn_config(path, text),
            ping_latency_ms=lambda host, port, fallback: vpn_utils.ping_latency_ms(host, port, fallback),
            run_openvpn=lambda *args, **kwargs: run_openvpn_until_ready(*args, **kwargs),
            index_pool=lambda: test_index_pool,
            parse_int=parse_int,
            enrich_ip_info=lambda nodes: vpn_utils.enrich_ip_info(nodes),
            record_quality=lambda node, openvpn_success, latency_ms, message: record_quality_result_from_probe(
                node,
                openvpn_success,
                latency_ms,
                message,
            ),
            quality_to_patch=quality_result_to_node_patch,
            sort_nodes=sort_all_nodes,
            now=time.time,
            print_line=lambda message: print(message, flush=True),
            load_ui_config=lambda: load_ui_config(),
            filter_nodes_by_routing_region=lambda nodes, target: filter_nodes_by_routing_region(nodes, target),
            retest_interval_seconds=lambda: NODE_RETEST_INTERVAL_SECONDS,
            max_maintenance_nodes=lambda: MAX_MAINTENANCE_TEST_NODES,
        )
    return _node_probe_runtime

def test_node_by_id(node_id: str) -> dict[str, Any]:
    return node_probe_runtime().test_node_by_id(node_id)

def test_multiple_nodes(
    node_ids: list[str],
    timeout: int = OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS,
    max_workers: int = NODE_TEST_WORKERS,
) -> list[dict[str, Any]]:
    return node_probe_runtime().test_multiple_nodes(
        node_ids,
        timeout=timeout,
        max_workers=max_workers,
    )

def select_maintenance_test_nodes(nodes: list[dict[str, Any]]) -> list[str]:
    return node_probe_runtime().select_maintenance_test_nodes(nodes)

def auto_switch_node(attempt: int = 0) -> None:
    connection_orchestrator().auto_switch_node(attempt)

def connect_node(node_id: str) -> str:
    return connection_orchestrator().connect_node(node_id)

def maintain_valid_nodes(force: bool = False) -> str:
    return connection_orchestrator().maintain_valid_nodes(force)


def collector_loop() -> None:
    monitoring_runtime().collector_loop()

LOGIN_HTML = """<!doctype html><html><body><h1>AimiliVPN Login</h1></body></html>"""

INDEX_HTML = """<!doctype html><html><body><h1>AimiliVPN</h1></body></html>"""

def check_proxy_health() -> dict[str, Any]:
    return proxy_core.check_proxy_health(
        proxy_host=LOCAL_PROXY_HOST,
        proxy_port=LOCAL_PROXY_PORT,
        tun_dev=TUN_DEV,
        is_linux=sys.platform.startswith("linux"),
        get_proxy_credentials=proxy_server.get_proxy_credentials,
        diagnose_local_obstructions=lambda port, host: vpn_utils.diagnose_local_obstructions(port, host=host),
    )

def background_proxy_checker() -> None:
    monitoring_runtime().proxy_checker_loop()

def active_node_pinger() -> None:
    monitoring_runtime().active_node_pinger_loop()


def context_active_node_id() -> str:
    return str(active_openvpn_node_id or "")


def get_last_active_ping_time() -> float:
    return last_active_ping_time


def set_last_active_ping_time(value: float) -> None:
    global last_active_ping_time
    last_active_ping_time = value


def get_last_active_latency() -> int:
    return last_active_latency


def set_last_active_latency(value: int) -> None:
    global last_active_latency
    last_active_latency = value


def start_daemon_thread(target: Any, args: tuple[Any, ...]) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def start_maintenance_thread() -> None:
    threading.Thread(target=maintain_valid_nodes, args=(False,), daemon=True).start()


def clear_active_sessions() -> None:
    web_runtime_wiring().clear_active_sessions()

def schedule_server_restart(message: str) -> None:
    web_runtime_wiring().schedule_server_restart(message)

def save_ui_config_locked(config: dict[str, Any]) -> None:
    web_runtime_wiring().save_ui_config_locked(config)

def add_active_session(token: str, expires_at: float) -> None:
    web_runtime_wiring().add_active_session(token, expires_at)

def remove_active_session(token: str) -> None:
    web_runtime_wiring().remove_active_session(token)

def proxy_gateway_status() -> tuple[bool, str]:
    return web_runtime_wiring().proxy_gateway_status()

def read_api_log_entries() -> list[dict[str, Any]]:
    return web_runtime_wiring().read_api_log_entries()

def route_context_factory() -> WebRouteContextFactory:
    return web_runtime_wiring().route_context_factory()

def web_server_runtime() -> WebServerRuntime:
    return web_runtime_wiring().web_server_runtime()



def service_runtime() -> VpnGateServiceRuntime:
    global _service_runtime
    if _service_runtime is None:
        _service_runtime = VpnGateServiceRuntime(
            ensure_dirs=ensure_dirs,
            kill_existing_openvpn_processes=kill_existing_openvpn_processes,
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
            collector_loop=collector_loop,
            background_proxy_checker=background_proxy_checker,
            active_node_pinger=active_node_pinger,
            start_daemon_threads=start_daemon_threads,
            wait_for_gateway=wait_for_gateway,
            load_ui_config=load_ui_config,
            bounded_int=bounded_int,
            web_server_runtime=web_server_runtime,
            serve_web_forever=serve_web_forever,
            print_line=lambda message: print(message, flush=True),
            set_stdout=lambda stream: setattr(sys, "stdout", stream),
            set_stderr=lambda stream: setattr(sys, "stderr", stream),
            tee_factory=lambda file_path: Tee(file_path),
        )
    return _service_runtime
class Handler(WebRequestHandler):
    @property
    def runtime(self) -> WebServerRuntime:
        return web_server_runtime()



def main() -> None:
    service_runtime().main()

if __name__ == "__main__":
    main()
