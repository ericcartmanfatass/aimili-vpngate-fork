from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from aimilivpn.core.monitoring import (
    active_node_latency_status,
    collector_sleep_seconds,
    mark_active_node_proxy_failed,
    proxy_state_from_health,
    should_auto_switch_after_proxy_failure,
    should_restart_fixed_node_after_proxy_failure,
)


@dataclass
class MonitoringRuntime:
    now: Callable[[], float]
    sleep: Callable[[int | float], None]
    set_collector_heartbeat: Callable[[float], None]
    set_checker_heartbeat: Callable[[float], None]
    set_pinger_heartbeat: Callable[[float], None]
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
    stop_requested: Callable[[], bool] = lambda: False
    wait_for_stop: Callable[[int | float], bool] | None = None

    def _wait(self, seconds: int | float) -> bool:
        if self.wait_for_stop is not None:
            return self.wait_for_stop(seconds)
        self.sleep(seconds)
        return self.stop_requested()

    def collector_loop(self) -> None:
        while not self.stop_requested():
            if self._wait(self.run_collector_cycle()):
                break

    def run_collector_cycle(self) -> int:
        self.set_collector_heartbeat(self.now())
        success = False
        try:
            self.print_line("[守护线程] 开始执行节点拉取与可用性检测周期任务...")
            self.log_line("INFO", "Main", "开始执行节点拉取与可用性检测周期任务...")
            result = self.maintain_valid_nodes(False)
            if "没有拉取到新节点" not in result:
                success = True
            self.log_line("INFO", "Main", f"周期同步与检测任务完成，结果: {result}")
        except Exception as exc:
            err_msg = f"周期节点同步任务执行异常: {exc}"
            self.print_line(f"[错误] {err_msg}")
            self.log_line("ERROR", "Main", err_msg)
            self.set_state(last_check_at=self.now(), last_check_message="后台节点维护失败")

        return collector_sleep_seconds(
            active_running=self.active_openvpn_running(),
            success=success,
            check_interval_seconds=self.check_interval_seconds(),
        )

    def proxy_checker_loop(self) -> None:
        if self._wait(30):
            return
        while not self.stop_requested():
            if self._wait(self.run_proxy_checker_cycle()):
                break

    def run_proxy_checker_cycle(self) -> int:
        self.set_checker_heartbeat(self.now())
        try:
            if self.is_connecting():
                return 5

            result = self.check_proxy_health()
            self.set_state(**proxy_state_from_health(result))
            if result.get("ok"):
                self.log_line(
                    "INFO",
                    "Proxy",
                    f"代理正常，出口 IP: {result.get('ip', '')}，延迟: {result.get('latency_ms', 0)} ms",
                )
            else:
                self._handle_proxy_failure(str(result.get("error", "unknown error")))
        except Exception as exc:
            self.print_line(f"[错误] 后台代理检测异常: {exc}")
            self.log_line("ERROR", "Proxy", f"代理检测异常: {exc}")
        return 30

    def run_active_node_ping_cycle(self) -> int:
        self.set_pinger_heartbeat(self.now())
        try:
            active_running = self.active_openvpn_running()
            active_node_id = self.get_active_node_id()
            nodes = self.read_nodes() if active_running and active_node_id else []
            latency_status = active_node_latency_status(
                active_running=active_running,
                active_node_id=active_node_id,
                is_connecting=self.is_connecting(),
                nodes=nodes,
                ping_latency_ms=self.ping_latency_ms,
                parse_int=self.parse_int,
                timeout_label="检测超时",
                connecting_label="正在检测...",
                idle_label="无活动连接",
            )
            self.set_state(active_node_latency=latency_status)
        except Exception as exc:
            self.print_line(f"[错误] 当前节点延迟检测异常: {exc}")
        return 10

    def active_node_pinger_loop(self) -> None:
        while not self.stop_requested():
            if self._wait(self.run_active_node_ping_cycle()):
                break

    def _handle_proxy_failure(self, error_msg: str) -> None:
        active_node_id = self.get_active_node_id()
        if not active_node_id:
            return

        self.print_line(f"[代理] 本地代理端口 {self.proxy_port()} 不可用: {error_msg}")
        self.log_line("WARNING", "Proxy", f"代理不可用: {error_msg}")

        routing_mode = str(self.load_ui_config().get("routing_mode") or "auto")
        if should_auto_switch_after_proxy_failure(active_node_id, routing_mode):
            self._mark_active_node_proxy_failed(active_node_id, error_msg)
            self.auto_switch_node()
        elif should_restart_fixed_node_after_proxy_failure(active_node_id, routing_mode):
            self.print_line(f"[代理] 固定 IP 模式代理检测失败，正在进入固定节点退避重试: {active_node_id}")
            self.set_is_connecting(False)
            self.auto_switch_node()

    def _mark_active_node_proxy_failed(self, active_node_id: str, error_msg: str) -> None:
        failure_message = f"代理连通性检测失败: {error_msg}"

        def update_nodes() -> None:
            nodes = self.read_nodes()
            active_node = mark_active_node_proxy_failed(nodes, active_node_id, error_message=failure_message)
            if active_node:
                self.mark_blacklisted(active_node, failure_message)
                self.write_nodes(nodes)

        self.run_locked(update_nodes)
