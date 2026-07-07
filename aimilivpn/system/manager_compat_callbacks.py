from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def bind_compat_callbacks(namespace: MutableMapping[str, Any]) -> None:
    manager_quality_runtime = namespace["manager_quality_runtime"]
    manager_connection_runtime = namespace["manager_connection_runtime"]
    manager_monitoring_runtime = namespace["manager_monitoring_runtime"]
    manager_web_runtime = namespace["manager_web_runtime"]
    manager_openvpn_runtime = namespace["manager_openvpn_runtime"]
    manager_service_runtime = namespace["manager_service_runtime"]
    manager_entry_runtime = namespace["manager_entry_runtime"]
    manager_node_probe_runtime = namespace["manager_node_probe_runtime"]

    manager_quality_runtime.test_multiple_nodes = lambda node_ids: namespace["test_multiple_nodes"](node_ids)
    manager_connection_runtime.cleanup_policy_routing = lambda: namespace["cleanup_policy_routing"]()
    manager_connection_runtime.stop_process = lambda process: namespace["stop_process"](process)
    manager_connection_runtime.kill_existing_openvpn_processes = lambda: namespace["kill_existing_openvpn_processes"]()
    manager_connection_runtime.run_openvpn_until_ready = lambda config_file: namespace["run_openvpn_until_ready"](
        config_file,
        keep_alive=True,
        route_nopull=True,
    )
    manager_connection_runtime.setup_policy_routing = lambda interface: namespace["setup_policy_routing"](interface)
    manager_connection_runtime.check_proxy_health = lambda: namespace["check_proxy_health"]()
    manager_connection_runtime.select_maintenance_test_nodes = (
        lambda nodes: namespace["select_maintenance_test_nodes"](nodes)
    )
    manager_connection_runtime.test_multiple_nodes = lambda node_ids: namespace["test_multiple_nodes"](node_ids)

    manager_monitoring_runtime.maintain_valid_nodes = lambda force: namespace["maintain_valid_nodes"](force)
    manager_monitoring_runtime.active_openvpn_running = lambda: namespace["active_openvpn_running"]()
    manager_monitoring_runtime.check_proxy_health = lambda: namespace["check_proxy_health"]()
    manager_monitoring_runtime.auto_switch_node = lambda: namespace["auto_switch_node"]()
    manager_monitoring_runtime.connect_node = lambda node_id: namespace["connect_node"](node_id)

    manager_web_runtime.test_node_by_id = lambda node_id: namespace["test_node_by_id"](node_id)
    manager_web_runtime.check_quality_ip = lambda ip: namespace["check_quality_ip"](ip)
    manager_web_runtime.check_quality_region = (
        lambda region_id, limit: namespace["check_quality_region"](region_id, limit)
    )
    manager_web_runtime.test_multiple_nodes = lambda nodes: namespace["test_multiple_nodes"](nodes)
    manager_web_runtime.connect_node = lambda node_id: namespace["connect_node"](node_id)
    manager_web_runtime.stop_active_openvpn = lambda: namespace["stop_active_openvpn"]()
    manager_web_runtime.maintain_valid_nodes = lambda force: namespace["maintain_valid_nodes"](force)
    manager_web_runtime.start_maintenance = lambda: namespace["start_maintenance_thread"]()
    manager_web_runtime.check_proxy_health = lambda: namespace["check_proxy_health"]()
    manager_web_runtime.active_openvpn_running = lambda: namespace["active_openvpn_running"]()

    manager_openvpn_runtime.status_callback = lambda line: namespace["update_handshake_status"](line)

    manager_service_runtime.kill_existing_openvpn_processes = lambda: namespace["kill_existing_openvpn_processes"]()
    manager_service_runtime.collector_loop = lambda: namespace["collector_loop"]()
    manager_service_runtime.background_proxy_checker = lambda: namespace["background_proxy_checker"]()
    manager_service_runtime.active_node_pinger = lambda: namespace["active_node_pinger"]()
    manager_service_runtime.web_server_runtime = lambda: namespace["web_server_runtime"]()

    manager_entry_runtime.web_server_runtime = lambda: namespace["web_server_runtime"]()
    manager_entry_runtime._handler_class = None

    manager_node_probe_runtime.run_openvpn = (
        lambda *args, **kwargs: namespace["run_openvpn_until_ready"](*args, **kwargs)
    )
    manager_node_probe_runtime.record_quality = (
        lambda *args, **kwargs: namespace["record_quality_result_from_probe"](*args, **kwargs)
    )
