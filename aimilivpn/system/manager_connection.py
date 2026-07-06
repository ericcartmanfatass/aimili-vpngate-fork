from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import subprocess

from aimilivpn.core.connection import clear_active_flags, delete_file_if_exists, find_active_config_file
from aimilivpn.system.connection_orchestrator import ConnectionOrchestrator
from aimilivpn.system.connection_runtime import ActiveConnectionRuntimeFacade
from aimilivpn.system.manager_state import ManagerMutableState


@dataclass
class ManagerConnectionRuntime:
    state: ManagerMutableState
    lock: Any
    cleanup_policy_routing: Callable[[], None]
    read_nodes: Callable[[], list[dict[str, Any]]]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    load_ui_config: Callable[[], dict[str, Any]]
    save_ui_config: Callable[[dict[str, Any]], None]
    stop_process: Callable[[subprocess.Popen[str] | None], None]
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
    _connection_runtime_facade: ActiveConnectionRuntimeFacade | None = field(default=None, init=False)
    _connection_orchestrator: ConnectionOrchestrator | None = field(default=None, init=False)

    def connection_runtime_facade(self) -> ActiveConnectionRuntimeFacade:
        if self._connection_runtime_facade is None:
            self._connection_runtime_facade = ActiveConnectionRuntimeFacade(
                cleanup_policy_routing=self.cleanup_policy_routing,
                read_nodes=self.read_nodes,
                write_nodes=self.write_nodes,
                load_ui_config=self.load_ui_config,
                save_ui_config=self.save_ui_config,
                find_active_config_file=find_active_config_file,
                clear_active_flags=clear_active_flags,
                stop_process=self.stop_process,
                kill_existing_processes=self.kill_existing_openvpn_processes,
                delete_file_if_exists=delete_file_if_exists,
                set_state=self.set_state,
                run_exclusive=self.run_locked,
                log_line=self.log_vpn_line,
                print_line=self.print_line,
            )
        return self._connection_runtime_facade

    def connection_orchestrator(self) -> ConnectionOrchestrator:
        if self._connection_orchestrator is None:
            self._connection_orchestrator = ConnectionOrchestrator(
                connection_runtime=self.connection_runtime_facade,
                ensure_dirs=self.ensure_dirs,
                run_locked=self.run_locked,
                read_nodes=self.read_nodes,
                write_nodes=self.write_nodes,
                load_ui_config=self.load_ui_config,
                set_state=self.set_state,
                log_line=self.log_line,
                print_line=self.print_line,
                start_thread=self.start_thread,
                try_acquire_maintenance=self.try_acquire_maintenance,
                release_maintenance=self.release_maintenance,
                get_is_connecting=self.get_is_connecting,
                set_is_connecting=self.set_is_connecting,
                get_active_node_id=self.get_active_openvpn_node_id,
                set_active_node_id=self.set_active_openvpn_node_id,
                get_last_active_latency=self.get_last_active_latency,
                set_last_active_latency=self.set_last_active_latency,
                set_last_active_ping_time=self.set_last_active_ping_time,
                set_active_connection=self.set_active_openvpn_connection,
                node_matches_allowed=self.node_matches_allowed,
                allowed_countries=self.allowed_countries,
                filter_nodes_by_routing_region=self.filter_nodes_by_routing_region,
                routing_target_label=self.routing_target_label,
                parse_int=self.parse_int,
                ping_latency_ms=self.ping_latency_ms,
                write_ovpn_config=self.write_ovpn_config,
                run_openvpn_until_ready=self.run_openvpn_until_ready,
                stop_active_openvpn=self.stop_active_openvpn,
                active_openvpn_running=self.active_openvpn_running,
                setup_policy_routing=self.setup_policy_routing,
                check_proxy_health=self.check_proxy_health,
                clear_active_connection_state=self.clear_active_connection_state,
                fetch_candidates=self.fetch_candidates,
                check_and_fix_dns=self.check_and_fix_dns,
                diagnose_api_failure=self.diagnose_api_failure,
                select_maintenance_test_nodes=self.select_maintenance_test_nodes,
                test_multiple_nodes=self.test_multiple_nodes,
                now=self.now,
                api_url=self.api_url,
                tun_dev=self.tun_dev,
                proxy_host=self.proxy_host,
                proxy_port=self.proxy_port,
                maintenance_test_limit=self.maintenance_test_limit,
                node_test_workers=self.node_test_workers,
                exclude_datacenter=self.exclude_datacenter,
            )
        return self._connection_orchestrator

    def clear_active_connection_state(self, message: str) -> None:
        process, node_id = self.connection_runtime_facade().clear_active_state(
            self.state.active_openvpn_process,
            message,
        )
        self.state.set_active_connection(process, node_id)

    def get_is_connecting(self) -> bool:
        return self.state.is_connecting

    def set_is_connecting(self, value: bool) -> None:
        self.state.is_connecting = value

    def get_active_openvpn_node_id(self) -> str:
        return self.state.active_openvpn_node_id

    def set_active_openvpn_node_id(self, node_id: str) -> None:
        self.state.active_openvpn_node_id = node_id

    def set_active_openvpn_connection(self, process: Any, node_id: str) -> None:
        self.state.set_active_connection(process, node_id)

    def stop_active_openvpn(self) -> None:
        with self.lock:
            process, node_id = self.connection_runtime_facade().stop_active(
                self.state.active_openvpn_process,
                self.state.active_openvpn_node_id,
            )
            self.state.set_active_connection(process, node_id)

    def active_openvpn_running(self) -> bool:
        return self.connection_runtime_facade().is_running(self.state.active_openvpn_process)

    def get_last_active_ping_time(self) -> float:
        return self.state.last_active_ping_time

    def set_last_active_ping_time(self, value: float) -> None:
        self.state.set_last_active_ping_time(value)

    def get_last_active_latency(self) -> int:
        return self.state.last_active_latency

    def set_last_active_latency(self, value: int) -> None:
        self.state.set_last_active_latency(value)
