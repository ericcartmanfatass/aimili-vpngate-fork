from __future__ import annotations

import time

import vpn_utils
from aimilivpn.core.connection_state import ConnectionPhase
from aimilivpn.core.logging_utils import redact_log_message
from aimilivpn.system import manager_wiring as wiring
from aimilivpn.system import proxy_server
from aimilivpn.system.manager_callbacks import (
    diagnose_with_host_keyword,
    is_linux,
    module_log_writer,
    print_line,
)
from aimilivpn.system.manager_helpers import parse_int, safe_name


def build_thread_runtime(ctx: object) -> None:
    def report_thread_error(name: str, exc: BaseException) -> None:
        print(f"[runtime] background task {name} failed: {type(exc).__name__}", flush=True)
        ctx.set_connection_phase(ConnectionPhase.FAILED, f"background task {name} failed", "")

    ctx.manager_thread_runtime = wiring.build_thread_runtime(wiring.ThreadRuntimeWiring(
        lock=ctx.lock,
        maintenance_lock=ctx.maintenance_lock,
        maintain_valid_nodes=lambda force: ctx.maintain_valid_nodes(force),
        on_thread_error=report_thread_error,
    ))
    ctx.run_with_lock = ctx.manager_thread_runtime.run_with_lock
    ctx.try_acquire_maintenance_lock = ctx.manager_thread_runtime.try_acquire_maintenance_lock
    ctx.release_maintenance_lock = ctx.manager_thread_runtime.release_maintenance_lock
    ctx.start_background_thread = ctx.manager_thread_runtime.start_background_thread
    ctx.start_daemon_thread = ctx.manager_thread_runtime.start_daemon_thread
    ctx.start_maintenance_thread = ctx.manager_thread_runtime.start_maintenance_thread
    ctx.start_runtime_tasks = ctx.manager_thread_runtime.start_tasks
    ctx.stop_requested = ctx.manager_thread_runtime.stop_requested
    ctx.wait_for_stop = ctx.manager_thread_runtime.wait
    ctx.shutdown_background_threads = ctx.manager_thread_runtime.shutdown


def build_node_view_runtime(ctx: object) -> None:
    ctx.manager_node_view_runtime = wiring.build_node_view_runtime(wiring.NodeViewRuntimeWiring(
        allowed_countries=lambda: ctx.allowed_countries,
        active_node_id=ctx.mutable_state.active_node_id,
        parse_int=parse_int,
    ))
    ctx.node_matches_allowed_countries = ctx.manager_node_view_runtime.node_matches_allowed_countries
    ctx.context_active_node_id = ctx.manager_node_view_runtime.context_active_node_id
    ctx.sort_all_nodes = ctx.manager_node_view_runtime.sort_all_nodes


def build_proxy_health_runtime(ctx: object) -> None:
    ctx.manager_proxy_health_runtime = wiring.build_proxy_health_runtime(wiring.ProxyHealthRuntimeWiring(
        proxy_host=lambda: ctx.local_proxy_host,
        proxy_port=lambda: ctx.local_proxy_port,
        tun_dev=lambda: ctx.tun_dev,
        is_linux=is_linux,
        get_proxy_credentials=proxy_server.get_proxy_credentials,
        diagnose_local_obstructions=diagnose_with_host_keyword(vpn_utils.diagnose_local_obstructions),
    ))
    ctx.check_proxy_health = ctx.manager_proxy_health_runtime.check_proxy_health


def build_json_log_runtime(ctx: object) -> None:
    ctx.json_log_runtime = wiring.build_json_log_runtime(wiring.JsonLogRuntimeWiring(
        data_dir=ctx.data_dir,
        lock=ctx.lock,
        redact_message=redact_log_message,
    ))
    ctx.json_log_writer = ctx.json_log_runtime.writer
    ctx.cleanup_old_logs = ctx.json_log_runtime.cleanup_old_logs
    ctx.log_to_json = ctx.json_log_runtime.log_to_json


def build_fetch_runtime(ctx: object) -> None:
    ctx.manager_fetch_runtime = wiring.build_fetch_runtime(wiring.FetchRuntimeWiring(
        api_url=ctx.api_url,
        config_dir=ctx.config_dir,
        max_scan_rows=ctx.max_scan_rows,
        allowed_countries=ctx.allowed_countries,
        allow_insecure_fetch=ctx.allow_insecure_fetch,
        blacklist_file=ctx.blacklist_file,
        lock=ctx.lock,
        invalid_backoff_seconds=ctx.invalid_backoff_seconds,
        read_nodes=ctx.read_nodes,
        set_state=ctx.set_state,
        log_line=module_log_writer(ctx.log_to_json, "Main"),
        diagnose_api_failure=vpn_utils.diagnose_api_failure,
        get_upstream_proxy=vpn_utils.get_upstream_proxy,
        get_upstream_proxy_auth=vpn_utils.get_upstream_proxy_auth,
        country_translations=vpn_utils.COUNTRY_TRANSLATIONS,
        safe_name=safe_name,
        now=time.time,
        blacklist_repository=ctx.manager_repository_runtime.facade(),
    ))
    ctx.vpngate_fetch_facade = ctx.manager_fetch_runtime.facade
    ctx.fetch_api_text_via_proxy = ctx.manager_fetch_runtime.fetch_api_text_via_proxy
    ctx.fetch_api_text = ctx.manager_fetch_runtime.fetch_api_text
    ctx.blacklist_store = ctx.manager_fetch_runtime.blacklist_store
    ctx.load_blacklist = ctx.manager_fetch_runtime.load_blacklist
    ctx.mark_blacklisted = ctx.manager_fetch_runtime.mark_blacklisted
    ctx.fetch_candidates = ctx.manager_fetch_runtime.fetch_candidates
    ctx.cached_nodes = ctx.manager_fetch_runtime.cached_nodes
