from __future__ import annotations

import time

import vpn_utils
from aimilivpn.system import manager_wiring as wiring
from aimilivpn.system.manager_callbacks import module_log_writer, print_line
from aimilivpn.system.manager_helpers import parse_int


def build_connection_runtime(ctx: object) -> None:
    ctx.manager_connection_runtime = wiring.build_connection_runtime(wiring.ConnectionRuntimeWiring(
        state=ctx.mutable_state,
        lock=ctx.lock,
        cleanup_policy_routing=lambda: ctx.cleanup_policy_routing(),
        read_nodes=ctx.read_nodes,
        write_nodes=ctx.write_nodes,
        load_ui_config=ctx.load_ui_config,
        save_ui_config=ctx.save_ui_config,
        stop_process=lambda process: ctx.stop_process(process),
        kill_existing_openvpn_processes=lambda: ctx.kill_existing_openvpn_processes(),
        set_state=ctx.set_state,
        run_locked=ctx.run_with_lock,
        log_vpn_line=module_log_writer(ctx.log_to_json, "VPN"),
        log_line=ctx.log_to_json,
        print_line=print_line,
        ensure_dirs=ctx.ensure_dirs,
        start_thread=ctx.start_background_thread,
        try_acquire_maintenance=ctx.try_acquire_maintenance_lock,
        release_maintenance=ctx.release_maintenance_lock,
        node_matches_allowed=ctx.node_matches_allowed_countries,
        allowed_countries=lambda: ctx.allowed_countries,
        filter_nodes_by_routing_region=ctx.filter_nodes_by_routing_region,
        routing_target_label=ctx.routing_target_label,
        parse_int=parse_int,
        ping_latency_ms=vpn_utils.ping_latency_ms,
        write_ovpn_config=ctx.write_ovpn_config,
        run_openvpn_until_ready=lambda config_file: ctx.run_openvpn_until_ready(
            config_file,
            keep_alive=True,
            route_nopull=True,
        ),
        setup_policy_routing=lambda interface: ctx.setup_policy_routing(interface),
        check_proxy_health=lambda: ctx.check_proxy_health(),
        fetch_candidates=ctx.fetch_candidates,
        check_and_fix_dns=vpn_utils.check_and_fix_dns,
        diagnose_api_failure=vpn_utils.diagnose_api_failure,
        select_maintenance_test_nodes=lambda nodes: ctx.select_maintenance_test_nodes(nodes),
        test_multiple_nodes=lambda node_ids: ctx.test_multiple_nodes(node_ids),
        now=time.time,
        api_url=lambda: ctx.api_url,
        tun_dev=lambda: ctx.tun_dev,
        proxy_host=lambda: ctx.local_proxy_host,
        proxy_port=lambda: ctx.local_proxy_port,
        maintenance_test_limit=lambda: ctx.max_maintenance_test_nodes,
        node_test_workers=lambda: ctx.node_test_workers,
        exclude_datacenter=lambda: ctx.exclude_datacenter,
        set_connection_phase=ctx.set_connection_phase,
        wait_for_stop=ctx.wait_for_stop,
        instance_retry_backoff_seconds=ctx.instance_retry_backoff_seconds,
        connection_candidate_limit=ctx.connection_candidate_limit,
        mark_blacklisted=ctx.mark_blacklisted,
        get_state=ctx.get_state,
    ))
    ctx.clear_active_connection_state = ctx.manager_connection_runtime.clear_active_connection_state
    ctx.get_is_connecting = ctx.manager_connection_runtime.get_is_connecting
    ctx.set_is_connecting = ctx.manager_connection_runtime.set_is_connecting
    ctx.get_active_openvpn_node_id = ctx.manager_connection_runtime.get_active_openvpn_node_id
    ctx.set_active_openvpn_node_id = ctx.manager_connection_runtime.set_active_openvpn_node_id
    ctx.set_active_openvpn_connection = ctx.manager_connection_runtime.set_active_openvpn_connection
    ctx.connection_runtime_facade = ctx.manager_connection_runtime.connection_runtime_facade
    ctx.connection_orchestrator = ctx.manager_connection_runtime.connection_orchestrator
    ctx.stop_active_openvpn = ctx.manager_connection_runtime.stop_active_openvpn
    ctx.active_openvpn_running = ctx.manager_connection_runtime.active_openvpn_running
    ctx.get_last_active_ping_time = ctx.manager_connection_runtime.get_last_active_ping_time
    ctx.set_last_active_ping_time = ctx.manager_connection_runtime.set_last_active_ping_time
    ctx.get_last_active_latency = ctx.manager_connection_runtime.get_last_active_latency
    ctx.set_last_active_latency = ctx.manager_connection_runtime.set_last_active_latency


def build_monitoring_runtime(ctx: object) -> None:
    ctx.manager_monitoring_runtime = wiring.build_monitoring_runtime(wiring.MonitoringRuntimeWiring(
        state=ctx.mutable_state,
        now=time.time,
        sleep=time.sleep,
        print_line=print_line,
        log_line=ctx.log_to_json,
        set_state=ctx.set_state,
        maintain_valid_nodes=lambda force: ctx.maintain_valid_nodes(force),
        active_openvpn_running=lambda: ctx.active_openvpn_running(),
        check_interval_seconds=lambda: ctx.check_interval_seconds,
        check_proxy_health=lambda: ctx.check_proxy_health(),
        is_connecting=ctx.get_is_connecting,
        set_is_connecting=ctx.set_is_connecting,
        get_active_node_id=ctx.get_active_openvpn_node_id,
        load_ui_config=ctx.load_ui_config,
        read_nodes=ctx.read_nodes,
        write_nodes=ctx.write_nodes,
        run_locked=ctx.run_with_lock,
        mark_blacklisted=ctx.mark_blacklisted,
        auto_switch_node=lambda: ctx.auto_switch_node(),
        connect_node=lambda node_id: ctx.connect_node(node_id),
        proxy_port=lambda: ctx.local_proxy_port,
        ping_latency_ms=vpn_utils.ping_latency_ms,
        parse_int=parse_int,
        stop_requested=ctx.stop_requested,
        wait_for_stop=ctx.wait_for_stop,
    ))
    ctx.monitoring_runtime = ctx.manager_monitoring_runtime.runtime
    ctx.set_collector_heartbeat = ctx.manager_monitoring_runtime.set_collector_heartbeat
    ctx.set_checker_heartbeat = ctx.manager_monitoring_runtime.set_checker_heartbeat
    ctx.set_pinger_heartbeat = ctx.manager_monitoring_runtime.set_pinger_heartbeat
    ctx.collector_loop = ctx.manager_monitoring_runtime.collector_loop
    ctx.background_proxy_checker = ctx.manager_monitoring_runtime.proxy_checker_loop
    ctx.active_node_pinger = ctx.manager_monitoring_runtime.active_node_pinger_loop
