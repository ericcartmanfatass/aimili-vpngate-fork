from __future__ import annotations

import time

import vpn_utils
from aimilivpn.system import manager_wiring as wiring
from aimilivpn.system import proxy_server
from aimilivpn.system.manager_callbacks import module_log_writer, print_line, set_stderr, set_stdout
from aimilivpn.system.manager_config import bounded_int
from aimilivpn.system.manager_helpers import parse_int, safe_name
from aimilivpn.system.startup import wait_for_gateway
from aimilivpn.web.server import serve_web_forever


def build_openvpn_runtime(ctx: object) -> None:
    ctx.manager_openvpn_runtime = wiring.build_openvpn_runtime(wiring.OpenVPNRuntimeWiring(
        openvpn_cmd=ctx.openvpn_cmd,
        auth_file=ctx.auth_file,
        data_dir=ctx.data_dir,
        config_dir=ctx.config_dir,
        upstream_proxy_auth_path=ctx.upstream_proxy_auth_file_path,
        root_dir=ctx.root_dir,
        default_dev=lambda: ctx.tun_dev,
        policy_table=lambda: ctx.policy_table,
        default_timeout_seconds=lambda: ctx.openvpn_test_timeout_seconds,
        get_upstream_proxy=vpn_utils.get_upstream_proxy,
        write_upstream_proxy_auth_file=ctx.upstream_proxy_auth_file,
        diagnose_openvpn_failure=vpn_utils.diagnose_openvpn_failure,
        status_callback=lambda line: ctx.update_handshake_status(line),
        log_vpn_line=module_log_writer(ctx.log_to_json, "VPN"),
        log_routing_line=module_log_writer(ctx.log_to_json, "Routing"),
        print_line=print_line,
        sleep=time.sleep,
    ))
    ctx.openvpn_runtime_facade = ctx.manager_openvpn_runtime.openvpn_runtime_facade
    ctx.policy_routing_facade = ctx.manager_openvpn_runtime.policy_routing_facade
    ctx.split_openvpn_command = ctx.manager_openvpn_runtime.split_openvpn_command
    ctx.get_openvpn_version = ctx.manager_openvpn_runtime.get_openvpn_version
    ctx.stop_process = ctx.manager_openvpn_runtime.stop_process
    ctx.kill_existing_openvpn_processes = ctx.manager_openvpn_runtime.kill_existing_openvpn_processes
    ctx.setup_policy_routing = ctx.manager_openvpn_runtime.setup_policy_routing
    ctx.cleanup_policy_routing = ctx.manager_openvpn_runtime.cleanup_policy_routing


def build_service_runtime(ctx: object) -> None:
    ctx.manager_service_runtime = wiring.build_service_runtime(wiring.ServiceRuntimeWiring(
        ensure_dirs=ctx.ensure_dirs,
        kill_existing_openvpn_processes=lambda: ctx.kill_existing_openvpn_processes(),
        data_dir=lambda: ctx.data_dir,
        state_file=lambda: ctx.state_file,
        write_json=ctx.write_json,
        api_url=lambda: ctx.api_url,
        instance_id=lambda: ctx.instance_id,
        tun_dev=lambda: ctx.tun_dev,
        policy_table=lambda: ctx.policy_table,
        allowed_countries=lambda: ctx.allowed_countries,
        target_valid_nodes=lambda: ctx.target_valid_nodes,
        fetch_interval_seconds=lambda: ctx.fetch_interval_seconds,
        check_interval_seconds=lambda: ctx.check_interval_seconds,
        local_proxy_host=lambda: ctx.local_proxy_host,
        local_proxy_port=lambda: ctx.local_proxy_port,
        ui_host=lambda: ctx.ui_host,
        ui_port=lambda: ctx.ui_port,
        start_proxy_server=lambda host, port, tun: proxy_server.start_proxy_server(
            host,
            port,
            tun,
            stop_event=ctx.manager_thread_runtime.stop_event,
        ),
        collector_loop=lambda: ctx.collector_loop(),
        background_proxy_checker=lambda: ctx.background_proxy_checker(),
        active_node_pinger=lambda: ctx.active_node_pinger(),
        start_daemon_threads=ctx.start_runtime_tasks,
        wait_for_gateway=wait_for_gateway,
        load_ui_config=ctx.load_ui_config,
        bounded_int=bounded_int,
        web_server_runtime=lambda: ctx.web_server_runtime(),
        serve_web_forever=serve_web_forever,
        print_line=print_line,
        set_stdout=set_stdout,
        set_stderr=set_stderr,
        shutdown_background_threads=ctx.shutdown_background_threads,
        stop_active_openvpn=ctx.stop_active_openvpn,
        text_log_max_bytes=lambda: ctx.text_log_max_bytes,
        text_log_backup_count=lambda: ctx.text_log_backup_count,
    ))


def build_entry_runtime(ctx: object) -> None:
    ctx.manager_entry_runtime = wiring.build_entry_runtime(wiring.EntryRuntimeWiring(
        service_runtime_factory=ctx.manager_service_runtime.runtime,
        web_server_runtime=lambda: ctx.web_server_runtime(),
    ))
    ctx.service_runtime = ctx.manager_entry_runtime.service_runtime


def build_node_probe_runtime(ctx: object) -> None:
    ctx.manager_node_probe_runtime = wiring.build_node_probe_runtime(wiring.NodeProbeRuntimeWiring(
        read_nodes=ctx.read_nodes,
        write_nodes=ctx.write_nodes,
        run_locked=ctx.run_with_lock,
        node_matches_allowed=ctx.node_matches_allowed_countries,
        allowed_countries=lambda: ctx.allowed_countries,
        config_dir=lambda: ctx.config_dir,
        safe_name=safe_name,
        write_config=ctx.write_ovpn_config,
        ping_latency_ms=vpn_utils.ping_latency_ms,
        run_openvpn=lambda *args, **kwargs: ctx.run_openvpn_until_ready(*args, **kwargs),
        parse_int=parse_int,
        enrich_ip_info=vpn_utils.enrich_ip_info,
        record_quality=ctx.record_quality_result_from_probe,
        sort_nodes=ctx.sort_all_nodes,
        now=time.time,
        print_line=print_line,
        load_ui_config=ctx.load_ui_config,
        filter_nodes_by_routing_region=ctx.filter_nodes_by_routing_region,
        retest_interval_seconds=lambda: ctx.node_retest_interval_seconds,
        max_maintenance_nodes=lambda: ctx.max_maintenance_test_nodes,
    ))
    ctx.node_probe_runtime = ctx.manager_node_probe_runtime.runtime
    ctx.test_node_by_id = ctx.manager_node_probe_runtime.test_node_by_id
    ctx.select_maintenance_test_nodes = ctx.manager_node_probe_runtime.select_maintenance_test_nodes
