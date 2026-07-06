from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from aimilivpn.system.manager_state import ManagerMutableState
from aimilivpn.system.monitoring_runtime import MonitoringRuntime


@dataclass
class ManagerMonitoringRuntime:
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
    _runtime: MonitoringRuntime | None = field(default=None, init=False)

    def set_collector_heartbeat(self, value: float) -> None:
        self.state.last_collector_heartbeat = value

    def set_checker_heartbeat(self, value: float) -> None:
        self.state.last_checker_heartbeat = value

    def set_pinger_heartbeat(self, value: float) -> None:
        self.state.last_pinger_heartbeat = value

    def runtime(self) -> MonitoringRuntime:
        if self._runtime is None:
            self._runtime = MonitoringRuntime(
                now=self.now,
                sleep=self.sleep,
                set_collector_heartbeat=self.set_collector_heartbeat,
                set_checker_heartbeat=self.set_checker_heartbeat,
                set_pinger_heartbeat=self.set_pinger_heartbeat,
                print_line=self.print_line,
                log_line=self.log_line,
                set_state=self.set_state,
                maintain_valid_nodes=self.maintain_valid_nodes,
                active_openvpn_running=self.active_openvpn_running,
                check_interval_seconds=self.check_interval_seconds,
                check_proxy_health=self.check_proxy_health,
                is_connecting=self.is_connecting,
                set_is_connecting=self.set_is_connecting,
                get_active_node_id=self.get_active_node_id,
                load_ui_config=self.load_ui_config,
                read_nodes=self.read_nodes,
                write_nodes=self.write_nodes,
                run_locked=self.run_locked,
                mark_blacklisted=self.mark_blacklisted,
                auto_switch_node=self.auto_switch_node,
                connect_node=self.connect_node,
                proxy_port=self.proxy_port,
                ping_latency_ms=self.ping_latency_ms,
                parse_int=self.parse_int,
            )
        return self._runtime

    def collector_loop(self) -> None:
        self.runtime().collector_loop()

    def proxy_checker_loop(self) -> None:
        self.runtime().proxy_checker_loop()

    def active_node_pinger_loop(self) -> None:
        self.runtime().active_node_pinger_loop()
