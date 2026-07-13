from __future__ import annotations

import time

import vpn_utils
from aimilivpn.providers.scamalytics import ScamalyticsError
from aimilivpn.system import manager_wiring as wiring
from aimilivpn.system.manager_callbacks import (
    console_token,
    diagnose_with_host_keyword,
    exit_process,
    is_linux,
    print_line,
)
from aimilivpn.system.manager_config import bounded_int
from aimilivpn.system.manager_helpers import parse_int
from aimilivpn.system.manager_web import default_index_html, default_login_html


def build_web_runtime(ctx: object) -> None:
    ctx.manager_web_runtime = wiring.build_web_runtime(wiring.WebManagerRuntimeWiring(
        region_repository=ctx.region_repository,
        read_regions=ctx.read_regions,
        read_nodes=ctx.read_nodes,
        region_from_payload=ctx.region_from_payload,
        quality_provider_status=ctx.quality_provider_status,
        latest_quality_for_node=ctx.latest_quality_for_node,
        latest_quality_map=ctx.latest_quality_map,
        test_node_by_id=lambda node_id: ctx.test_node_by_id(node_id),
        check_quality_ip=ctx.check_quality_ip,
        check_quality_region=ctx.check_quality_region,
        bounded_int=bounded_int,
        scamalytics_errors=(ScamalyticsError,),
        write_nodes=ctx.write_nodes,
        filter_nodes_by_region=ctx.filter_nodes_by_region,
        get_state=ctx.get_state,
        set_state=ctx.set_state,
        get_active_node_id=lambda: ctx.context_active_node_id(),
        get_last_active_ping_time=lambda: ctx.get_last_active_ping_time(),
        set_last_active_ping_time=lambda value: ctx.set_last_active_ping_time(value),
        get_last_active_latency=lambda: ctx.get_last_active_latency(),
        set_last_active_latency=lambda value: ctx.set_last_active_latency(value),
        now=time.time,
        ping_latency_ms=vpn_utils.ping_latency_ms,
        parse_int=parse_int,
        start_daemon_thread=lambda target, args: ctx.start_daemon_thread(target, args),
        test_multiple_nodes=lambda nodes: ctx.test_multiple_nodes(nodes),
        connect_node=lambda node_id: ctx.connect_node(node_id),
        stop_active_openvpn=lambda: ctx.stop_active_openvpn(),
        load_ui_config=ctx.load_ui_config,
        save_ui_config_unlocked=ctx.save_ui_config,
        maintain_valid_nodes=lambda force: ctx.maintain_valid_nodes(force),
        maintenance_running=ctx.maintenance_lock.locked,
        start_maintenance=lambda: ctx.start_maintenance_thread(),
        validate_routing_region_target=ctx.validate_routing_region_target,
        verify_password=ctx.manager_auth_runtime.verify_password,
        verify_username=ctx.manager_auth_runtime.verify_username,
        generate_session_token=ctx.manager_auth_runtime.generate_session_token,
        check_proxy_health=lambda: ctx.check_proxy_health(),
        ui_host=lambda: ctx.ui_host,
        ui_port=lambda: ctx.ui_port,
        trust_proxy_headers=lambda: ctx.trust_proxy_headers,
        trusted_proxy_addresses=lambda: ctx.trusted_proxy_addresses,
        proxy_host=lambda: ctx.local_proxy_host,
        proxy_port=lambda: ctx.local_proxy_port,
        active_openvpn_running=lambda: ctx.active_openvpn_running(),
        is_linux=is_linux,
        tun_dev=lambda: ctx.tun_dev,
        server_start_time=lambda: ctx.mutable_state.server_start_time,
        last_collector_heartbeat=lambda: ctx.mutable_state.last_collector_heartbeat,
        last_checker_heartbeat=lambda: ctx.mutable_state.last_checker_heartbeat,
        last_pinger_heartbeat=lambda: ctx.mutable_state.last_pinger_heartbeat,
        check_interval_seconds=lambda: ctx.check_interval_seconds,
        login_html_fallback=default_login_html,
        index_html_fallback=default_index_html,
        active_sessions=ctx.active_sessions,
        lock=ctx.lock,
        data_dir=lambda: ctx.data_dir,
        console_token=console_token,
        diagnose_local_obstructions=diagnose_with_host_keyword(vpn_utils.diagnose_local_obstructions),
        start_thread=ctx.start_background_thread,
        sleep=time.sleep,
        exit_process=exit_process,
        print_line=print_line,
    ))
    ctx.web_runtime_wiring = ctx.manager_web_runtime.wiring
    ctx.clear_active_sessions = ctx.manager_web_runtime.clear_active_sessions
    ctx.schedule_server_restart = ctx.manager_web_runtime.schedule_server_restart
    ctx.save_ui_config_locked = ctx.manager_web_runtime.save_ui_config_locked
    ctx.add_active_session = ctx.manager_web_runtime.add_active_session
    ctx.remove_active_session = ctx.manager_web_runtime.remove_active_session
    ctx.proxy_gateway_status = ctx.manager_web_runtime.proxy_gateway_status
    ctx.read_api_log_entries = ctx.manager_web_runtime.read_api_log_entries
    ctx.route_context_factory = ctx.manager_web_runtime.route_context_factory
    ctx.web_server_runtime = ctx.manager_web_runtime.web_server_runtime
