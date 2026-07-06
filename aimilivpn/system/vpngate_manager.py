#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from typing import Any

from aimilivpn.system import manager_runtime_context as runtime_context


MANAGER_CONTEXT = runtime_context.build_manager_runtime_context(compiled=bool(globals().get("__compiled__")))

install_ipv4_preferred_getaddrinfo = runtime_context.install_ipv4_preferred_getaddrinfo
vpn_utils = runtime_context.vpn_utils
redact_log_message = runtime_context.redact_log_message
QualityResult = runtime_context.QualityResult
ScamalyticsError = runtime_context.ScamalyticsError
proxy_server = runtime_context.proxy_server
console_token = runtime_context.console_token
diagnose_with_host_keyword = runtime_context.diagnose_with_host_keyword
exit_process = runtime_context.exit_process
is_linux = runtime_context.is_linux
module_log_writer = runtime_context.module_log_writer
print_line = runtime_context.print_line
set_stderr = runtime_context.set_stderr
set_stdout = runtime_context.set_stdout
bounded_int = runtime_context.bounded_int
parse_int = runtime_context.parse_int
safe_name = runtime_context.safe_name
default_index_html = runtime_context.default_index_html
default_login_html = runtime_context.default_login_html
start_daemon_threads = runtime_context.start_daemon_threads
wait_for_gateway = runtime_context.wait_for_gateway
quality_to_dict = runtime_context.quality_to_dict
region_to_dict = runtime_context.region_to_dict
serve_web_forever = runtime_context.serve_web_forever
time = runtime_context.time

MANAGER_ENVIRONMENT = MANAGER_CONTEXT.environment
ROOT_DIR = MANAGER_CONTEXT.root_dir
MANAGER_CONFIG = MANAGER_CONTEXT.config
API_URL = MANAGER_CONTEXT.api_url
FETCH_INTERVAL_SECONDS = MANAGER_CONTEXT.fetch_interval_seconds
CHECK_INTERVAL_SECONDS = MANAGER_CONTEXT.check_interval_seconds
TARGET_VALID_NODES = MANAGER_CONTEXT.target_valid_nodes
MAX_SCAN_ROWS = MANAGER_CONTEXT.max_scan_rows
OPENVPN_TEST_TIMEOUT_SECONDS = MANAGER_CONTEXT.openvpn_test_timeout_seconds
OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS = MANAGER_CONTEXT.openvpn_maintenance_test_timeout_seconds
NODE_TEST_WORKERS = MANAGER_CONTEXT.node_test_workers
MAX_MAINTENANCE_TEST_NODES = MANAGER_CONTEXT.max_maintenance_test_nodes
NODE_RETEST_INTERVAL_SECONDS = MANAGER_CONTEXT.node_retest_interval_seconds
OPENVPN_CMD = MANAGER_CONTEXT.openvpn_cmd
OPENVPN_AUTH_USER = MANAGER_CONTEXT.openvpn_auth_user
OPENVPN_AUTH_PASS = MANAGER_CONTEXT.openvpn_auth_pass
LOCAL_PROXY_HOST = MANAGER_CONTEXT.local_proxy_host
LOCAL_PROXY_PORT = MANAGER_CONTEXT.local_proxy_port
UI_HOST = MANAGER_CONTEXT.ui_host
UI_PORT = MANAGER_CONTEXT.ui_port
INVALID_BACKOFF_SECONDS = MANAGER_CONTEXT.invalid_backoff_seconds
INSTANCE_ID = MANAGER_CONTEXT.instance_id
TUN_DEV = MANAGER_CONTEXT.tun_dev
POLICY_TABLE = MANAGER_CONTEXT.policy_table
ALLOWED_COUNTRIES = MANAGER_CONTEXT.allowed_countries
EXCLUDE_DATACENTER = MANAGER_CONTEXT.exclude_datacenter
ALLOW_INSECURE_FETCH = MANAGER_CONTEXT.allow_insecure_fetch

RUNTIME_PATHS = MANAGER_CONTEXT.runtime_paths
DATA_DIR = MANAGER_CONTEXT.data_dir
CONFIG_DIR = MANAGER_CONTEXT.config_dir
NODES_FILE = MANAGER_CONTEXT.nodes_file
STATE_FILE = MANAGER_CONTEXT.state_file
AUTH_FILE = MANAGER_CONTEXT.auth_file
UPSTREAM_PROXY_AUTH_FILE = MANAGER_CONTEXT.upstream_proxy_auth_file_path
BLACKLIST_FILE = MANAGER_CONTEXT.blacklist_file
REGIONS_FILE = MANAGER_CONTEXT.regions_file
QUALITY_RESULTS_FILE = MANAGER_CONTEXT.quality_results_file

REPOSITORIES = MANAGER_CONTEXT.repositories
NODE_REPOSITORY = MANAGER_CONTEXT.node_repository
REGION_REPOSITORY = MANAGER_CONTEXT.region_repository
QUALITY_REPOSITORY = MANAGER_CONTEXT.quality_repository
SHARED_STATE = MANAGER_CONTEXT.shared_state
UI_ENDPOINTS = MANAGER_CONTEXT.ui_endpoints

manager_repository_runtime = MANAGER_CONTEXT.manager_repository_runtime
repository_facade = MANAGER_CONTEXT.repository_facade
read_nodes = MANAGER_CONTEXT.read_nodes
write_nodes = MANAGER_CONTEXT.write_nodes
read_regions = MANAGER_CONTEXT.read_regions
region_from_payload = MANAGER_CONTEXT.region_from_payload
filter_nodes_by_region = MANAGER_CONTEXT.filter_nodes_by_region
region_target_id = MANAGER_CONTEXT.region_target_id
get_region_routing_target = MANAGER_CONTEXT.get_region_routing_target
routing_target_label = MANAGER_CONTEXT.routing_target_label
node_matches_country_target = MANAGER_CONTEXT.node_matches_country_target
node_matches_routing_region = MANAGER_CONTEXT.node_matches_routing_region
filter_nodes_by_routing_region = MANAGER_CONTEXT.filter_nodes_by_routing_region
validate_routing_region_target = MANAGER_CONTEXT.validate_routing_region_target

manager_quality_runtime = MANAGER_CONTEXT.manager_quality_runtime
get_scamalytics_provider = MANAGER_CONTEXT.get_scamalytics_provider
latest_quality_for_node = MANAGER_CONTEXT.latest_quality_for_node
latest_quality_map = MANAGER_CONTEXT.latest_quality_map
check_quality_region = MANAGER_CONTEXT.check_quality_region
quality_provider_status = MANAGER_CONTEXT.quality_provider_status

lock = MANAGER_CONTEXT.lock
maintenance_lock = MANAGER_CONTEXT.maintenance_lock
mutable_state = MANAGER_CONTEXT.mutable_state
active_sessions = MANAGER_CONTEXT.active_sessions

manager_auth_runtime = MANAGER_CONTEXT.manager_auth_runtime
get_session_token = MANAGER_CONTEXT.get_session_token

manager_ui_runtime = MANAGER_CONTEXT.manager_ui_runtime
generate_random_password = MANAGER_CONTEXT.generate_random_password
generate_random_username = MANAGER_CONTEXT.generate_random_username
ui_config_store = MANAGER_CONTEXT.ui_config_store
load_ui_config = MANAGER_CONTEXT.load_ui_config
save_ui_config = MANAGER_CONTEXT.save_ui_config

manager_runtime_state = MANAGER_CONTEXT.manager_runtime_state
write_json = MANAGER_CONTEXT.write_json
read_json = MANAGER_CONTEXT.read_json
runtime_state_store = MANAGER_CONTEXT.runtime_state_store
set_state = MANAGER_CONTEXT.set_state
get_state = MANAGER_CONTEXT.get_state

manager_runtime_files = MANAGER_CONTEXT.manager_runtime_files
ensure_dirs = MANAGER_CONTEXT.ensure_dirs
upstream_proxy_auth_file = MANAGER_CONTEXT.upstream_proxy_auth_file
write_ovpn_config = MANAGER_CONTEXT.write_ovpn_config

manager_thread_runtime = MANAGER_CONTEXT.manager_thread_runtime
run_with_lock = MANAGER_CONTEXT.run_with_lock
try_acquire_maintenance_lock = MANAGER_CONTEXT.try_acquire_maintenance_lock
release_maintenance_lock = MANAGER_CONTEXT.release_maintenance_lock
start_background_thread = MANAGER_CONTEXT.start_background_thread
start_daemon_thread = MANAGER_CONTEXT.start_daemon_thread
start_maintenance_thread = MANAGER_CONTEXT.start_maintenance_thread

manager_node_view_runtime = MANAGER_CONTEXT.manager_node_view_runtime
node_matches_allowed_countries = MANAGER_CONTEXT.node_matches_allowed_countries
context_active_node_id = MANAGER_CONTEXT.context_active_node_id
sort_all_nodes = MANAGER_CONTEXT.sort_all_nodes

manager_proxy_health_runtime = MANAGER_CONTEXT.manager_proxy_health_runtime
check_proxy_health = MANAGER_CONTEXT.check_proxy_health

json_log_runtime = MANAGER_CONTEXT.json_log_runtime
json_log_writer = MANAGER_CONTEXT.json_log_writer
cleanup_old_logs = MANAGER_CONTEXT.cleanup_old_logs
log_to_json = MANAGER_CONTEXT.log_to_json

manager_fetch_runtime = MANAGER_CONTEXT.manager_fetch_runtime
vpngate_fetch_facade = MANAGER_CONTEXT.vpngate_fetch_facade
fetch_api_text_via_proxy = MANAGER_CONTEXT.fetch_api_text_via_proxy
fetch_api_text = MANAGER_CONTEXT.fetch_api_text
blacklist_store = MANAGER_CONTEXT.blacklist_store
load_blacklist = MANAGER_CONTEXT.load_blacklist
mark_blacklisted = MANAGER_CONTEXT.mark_blacklisted
fetch_candidates = MANAGER_CONTEXT.fetch_candidates
cached_nodes = MANAGER_CONTEXT.cached_nodes

manager_connection_runtime = MANAGER_CONTEXT.manager_connection_runtime
clear_active_connection_state = MANAGER_CONTEXT.clear_active_connection_state
get_is_connecting = MANAGER_CONTEXT.get_is_connecting
set_is_connecting = MANAGER_CONTEXT.set_is_connecting
get_active_openvpn_node_id = MANAGER_CONTEXT.get_active_openvpn_node_id
set_active_openvpn_node_id = MANAGER_CONTEXT.set_active_openvpn_node_id
set_active_openvpn_connection = MANAGER_CONTEXT.set_active_openvpn_connection
connection_runtime_facade = MANAGER_CONTEXT.connection_runtime_facade
connection_orchestrator = MANAGER_CONTEXT.connection_orchestrator
stop_active_openvpn = MANAGER_CONTEXT.stop_active_openvpn
active_openvpn_running = MANAGER_CONTEXT.active_openvpn_running
get_last_active_ping_time = MANAGER_CONTEXT.get_last_active_ping_time
set_last_active_ping_time = MANAGER_CONTEXT.set_last_active_ping_time
get_last_active_latency = MANAGER_CONTEXT.get_last_active_latency
set_last_active_latency = MANAGER_CONTEXT.set_last_active_latency

manager_monitoring_runtime = MANAGER_CONTEXT.manager_monitoring_runtime
monitoring_runtime = MANAGER_CONTEXT.monitoring_runtime
set_collector_heartbeat = MANAGER_CONTEXT.set_collector_heartbeat
set_checker_heartbeat = MANAGER_CONTEXT.set_checker_heartbeat
set_pinger_heartbeat = MANAGER_CONTEXT.set_pinger_heartbeat
collector_loop = MANAGER_CONTEXT.collector_loop
background_proxy_checker = MANAGER_CONTEXT.background_proxy_checker
active_node_pinger = MANAGER_CONTEXT.active_node_pinger

manager_web_runtime = MANAGER_CONTEXT.manager_web_runtime
web_runtime_wiring = MANAGER_CONTEXT.web_runtime_wiring
clear_active_sessions = MANAGER_CONTEXT.clear_active_sessions
schedule_server_restart = MANAGER_CONTEXT.schedule_server_restart
save_ui_config_locked = MANAGER_CONTEXT.save_ui_config_locked
add_active_session = MANAGER_CONTEXT.add_active_session
remove_active_session = MANAGER_CONTEXT.remove_active_session
proxy_gateway_status = MANAGER_CONTEXT.proxy_gateway_status
read_api_log_entries = MANAGER_CONTEXT.read_api_log_entries
route_context_factory = MANAGER_CONTEXT.route_context_factory
web_server_runtime = MANAGER_CONTEXT.web_server_runtime

manager_openvpn_runtime = MANAGER_CONTEXT.manager_openvpn_runtime
openvpn_runtime_facade = MANAGER_CONTEXT.openvpn_runtime_facade
policy_routing_facade = MANAGER_CONTEXT.policy_routing_facade
split_openvpn_command = MANAGER_CONTEXT.split_openvpn_command
get_openvpn_version = MANAGER_CONTEXT.get_openvpn_version
stop_process = MANAGER_CONTEXT.stop_process
kill_existing_openvpn_processes = MANAGER_CONTEXT.kill_existing_openvpn_processes
setup_policy_routing = MANAGER_CONTEXT.setup_policy_routing
cleanup_policy_routing = MANAGER_CONTEXT.cleanup_policy_routing

manager_service_runtime = MANAGER_CONTEXT.manager_service_runtime
manager_entry_runtime = MANAGER_CONTEXT.manager_entry_runtime
service_runtime = MANAGER_CONTEXT.service_runtime
manager_node_probe_runtime = MANAGER_CONTEXT.manager_node_probe_runtime
node_probe_runtime = MANAGER_CONTEXT.node_probe_runtime
test_node_by_id = MANAGER_CONTEXT.test_node_by_id
select_maintenance_test_nodes = MANAGER_CONTEXT.select_maintenance_test_nodes


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


def check_quality_ip(ip: str) -> QualityResult:
    return manager_quality_runtime.check_quality_ip(
        ip,
        provider_getter=get_scamalytics_provider,
    )


def check_quality_region(region_id: str, limit: int = 20) -> dict[str, Any]:
    return manager_quality_runtime.check_quality_region(region_id, limit)


def openvpn_command(config_file: str, route_nopull: bool, dev: str = TUN_DEV) -> list[str]:
    return MANAGER_CONTEXT.openvpn_command(config_file, route_nopull, dev)


def update_handshake_status(line_lower: str) -> None:
    MANAGER_CONTEXT.update_handshake_status(line_lower)


def run_openvpn_until_ready(
    config_file: str,
    keep_alive: bool,
    route_nopull: bool,
    timeout: int | None = None,
    dev: str = TUN_DEV,
) -> tuple[bool, str, subprocess.Popen[str] | None]:
    return MANAGER_CONTEXT.run_openvpn_until_ready(
        config_file,
        keep_alive=keep_alive,
        route_nopull=route_nopull,
        timeout=timeout,
        dev=dev,
    )


def test_multiple_nodes(
    node_ids: list[str],
    timeout: int = OPENVPN_MAINTENANCE_TEST_TIMEOUT_SECONDS,
    max_workers: int = NODE_TEST_WORKERS,
) -> list[dict[str, Any]]:
    return MANAGER_CONTEXT.test_multiple_nodes(
        node_ids,
        timeout=timeout,
        max_workers=max_workers,
    )


def auto_switch_node(attempt: int = 0) -> None:
    MANAGER_CONTEXT.auto_switch_node(attempt)


def connect_node(node_id: str) -> str:
    return MANAGER_CONTEXT.connect_node(node_id)


def maintain_valid_nodes(force: bool = False) -> str:
    return MANAGER_CONTEXT.maintain_valid_nodes(force)


def _bind_compat_callbacks() -> None:
    manager_quality_runtime.test_multiple_nodes = lambda node_ids: test_multiple_nodes(node_ids)
    manager_connection_runtime.cleanup_policy_routing = lambda: cleanup_policy_routing()
    manager_connection_runtime.stop_process = lambda process: stop_process(process)
    manager_connection_runtime.kill_existing_openvpn_processes = lambda: kill_existing_openvpn_processes()
    manager_connection_runtime.run_openvpn_until_ready = lambda config_file: run_openvpn_until_ready(
        config_file,
        keep_alive=True,
        route_nopull=True,
    )
    manager_connection_runtime.setup_policy_routing = lambda interface: setup_policy_routing(interface)
    manager_connection_runtime.check_proxy_health = lambda: check_proxy_health()
    manager_connection_runtime.select_maintenance_test_nodes = lambda nodes: select_maintenance_test_nodes(nodes)
    manager_connection_runtime.test_multiple_nodes = lambda node_ids: test_multiple_nodes(node_ids)
    manager_monitoring_runtime.maintain_valid_nodes = lambda force: maintain_valid_nodes(force)
    manager_monitoring_runtime.active_openvpn_running = lambda: active_openvpn_running()
    manager_monitoring_runtime.check_proxy_health = lambda: check_proxy_health()
    manager_monitoring_runtime.auto_switch_node = lambda: auto_switch_node()
    manager_monitoring_runtime.connect_node = lambda node_id: connect_node(node_id)
    manager_web_runtime.test_node_by_id = lambda node_id: test_node_by_id(node_id)
    manager_web_runtime.check_quality_ip = lambda ip: check_quality_ip(ip)
    manager_web_runtime.check_quality_region = lambda region_id, limit: check_quality_region(region_id, limit)
    manager_web_runtime.test_multiple_nodes = lambda nodes: test_multiple_nodes(nodes)
    manager_web_runtime.connect_node = lambda node_id: connect_node(node_id)
    manager_web_runtime.stop_active_openvpn = lambda: stop_active_openvpn()
    manager_web_runtime.maintain_valid_nodes = lambda force: maintain_valid_nodes(force)
    manager_web_runtime.start_maintenance = lambda: start_maintenance_thread()
    manager_web_runtime.check_proxy_health = lambda: check_proxy_health()
    manager_web_runtime.active_openvpn_running = lambda: active_openvpn_running()
    manager_openvpn_runtime.status_callback = lambda line: update_handshake_status(line)
    manager_service_runtime.kill_existing_openvpn_processes = lambda: kill_existing_openvpn_processes()
    manager_service_runtime.collector_loop = lambda: collector_loop()
    manager_service_runtime.background_proxy_checker = lambda: background_proxy_checker()
    manager_service_runtime.active_node_pinger = lambda: active_node_pinger()
    manager_service_runtime.web_server_runtime = lambda: web_server_runtime()
    manager_entry_runtime.web_server_runtime = lambda: web_server_runtime()
    manager_entry_runtime._handler_class = None
    manager_node_probe_runtime.run_openvpn = lambda *args, **kwargs: run_openvpn_until_ready(*args, **kwargs)
    manager_node_probe_runtime.record_quality = record_quality_result_from_probe


_bind_compat_callbacks()


Handler = manager_entry_runtime.handler_class()
MANAGER_CONTEXT.handler_class = Handler


def main() -> None:
    MANAGER_CONTEXT.main()


if __name__ == "__main__":
    main()
