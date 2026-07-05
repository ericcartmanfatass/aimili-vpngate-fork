from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.connection import (
    auto_switch_block_reason,
    auto_switch_connect_message,
    auto_switch_no_candidate_message,
    auto_switch_retry_message,
    clear_active_flags,
    connection_success_state,
    mark_connection_active,
    measure_node_latency,
    normalize_node_id,
    should_clear_failed_connection,
)
from aimilivpn.core.maintenance import (
    ensure_node_config_files,
    format_fetch_error_message,
    format_maintenance_status_report,
    maintenance_node_status,
    maintenance_recovery_action,
    merge_candidate_nodes,
    should_auto_connect_after_maintenance,
)
from aimilivpn.core.monitoring import proxy_state_from_health
from aimilivpn.core.nodes import select_auto_switch_candidates
from aimilivpn.system.connection_runtime import ActiveConnectionRuntimeFacade


@dataclass
class ConnectionOrchestrator:
    connection_runtime: Callable[[], ActiveConnectionRuntimeFacade]
    ensure_dirs: Callable[[], None]
    run_locked: Callable[[Callable[[], Any]], Any]
    read_nodes: Callable[[], list[dict[str, Any]]]
    write_nodes: Callable[[list[dict[str, Any]]], None]
    load_ui_config: Callable[[], dict[str, Any]]
    set_state: Callable[..., None]
    log_line: Callable[[str, str, str], None]
    print_line: Callable[[str], None]
    start_thread: Callable[[Callable[[], None]], None]
    try_acquire_maintenance: Callable[[], bool]
    release_maintenance: Callable[[], None]
    get_is_connecting: Callable[[], bool]
    set_is_connecting: Callable[[bool], None]
    get_active_node_id: Callable[[], str]
    set_active_node_id: Callable[[str], None]
    get_last_active_latency: Callable[[], int]
    set_last_active_latency: Callable[[int], None]
    set_last_active_ping_time: Callable[[float], None]
    set_active_connection: Callable[[Any, str], None]
    node_matches_allowed: Callable[[dict[str, Any]], bool]
    allowed_countries: Callable[[], set[str]]
    filter_nodes_by_routing_region: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    routing_target_label: Callable[[str], str]
    parse_int: Callable[[Any], int]
    ping_latency_ms: Callable[[str, int, int], int]
    write_ovpn_config: Callable[[Path, str], None]
    run_openvpn_until_ready: Callable[[str], tuple[bool, str, Any]]
    stop_active_openvpn: Callable[[], None]
    active_openvpn_running: Callable[[], bool]
    setup_policy_routing: Callable[[str], None]
    check_proxy_health: Callable[[], dict[str, Any]]
    clear_active_connection_state: Callable[[str], None]
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

    def auto_switch_node(self, attempt: int = 0) -> None:
        if attempt >= 3:
            self.print_line("[自动切换] 连续切换失败已达 3 次，停止切换以防止主线程死锁，将在后台重新加载节点...")
            return

        ui_cfg = self.load_ui_config()
        block_reason = auto_switch_block_reason(ui_cfg)
        if block_reason == "disabled":
            self.print_line("[自动切换] 连接已禁用，不进行自动切换。")
            return
        if block_reason == "fixed_ip":
            self.print_line("[自动切换] 当前处于固定 IP 模式，不进行自动连接或切换。")
            return

        routing_mode = ui_cfg.get("routing_mode", "auto")
        target_country = ui_cfg.get("force_country", "")

        def select_candidates() -> list[dict[str, Any]]:
            return select_auto_switch_candidates(
                self.read_nodes(),
                ui_config=ui_cfg,
                node_matches_allowed=self.node_matches_allowed,
                filter_nodes_by_routing_region=self.filter_nodes_by_routing_region,
                parse_int=self.parse_int,
                exclude_datacenter=self.exclude_datacenter(),
            )

        candidates = self.run_locked(select_candidates)
        if candidates:
            next_node = candidates[0]
            node_id = str(next_node["id"])
            msg = auto_switch_connect_message(node_id)
            self.print_line(f"[自动切换] {msg}")
            self.log_line("INFO", "VPN", msg)
            try:
                self.connect_node(node_id)
            except Exception as exc:
                err_msg = auto_switch_retry_message(node_id, exc)
                self.print_line(f"[自动切换] {err_msg}")
                self.log_line("WARNING", "VPN", err_msg)
                self.auto_switch_node(attempt + 1)
            return

        msg = auto_switch_no_candidate_message(
            routing_mode=str(routing_mode or "auto"),
            target_country=str(target_country or ""),
            routing_target_label=self.routing_target_label,
        )
        self.print_line(f"[自动切换] {msg}")
        self.log_line("WARNING", "VPN", msg)
        self.stop_active_openvpn()

        def clear_nodes() -> None:
            nodes = self.read_nodes()
            clear_active_flags(nodes)
            self.write_nodes(nodes)

        self.run_locked(clear_nodes)
        self.set_state(active_openvpn_node_id="", last_check_message=msg)

        def bg_fetch_and_switch() -> None:
            try:
                self.maintain_valid_nodes(force=False)
                self.auto_switch_node()
            except Exception as exc:
                self.print_line(f"[自动切换后台补齐] 获取并测试节点失败: {exc}")

        self.start_thread(bg_fetch_and_switch)

    def connect_node(self, node_id: str) -> str:
        node_id = normalize_node_id(node_id)
        stopped_existing = False

        def begin_connect() -> None:
            self.set_is_connecting(
                self.connection_runtime().begin_connect(
                    node_id=node_id,
                    is_connecting=self.get_is_connecting(),
                    busy_log_message="[连接] 正在建立其他连接中，跳过此请求",
                    busy_error_message="当前已有连接或节点检测任务正在运行，请稍后再试",
                    active_node_latency="正在连接",
                    last_check_message="正在初始化连接配置: {node_id}",
                )
            )

        self.run_locked(begin_connect)

        try:
            self.log_line("INFO", "VPN", f"开始连接节点: {node_id}")
            nodes, node = self.connection_runtime().prepare_target(
                node_id,
                node_matches_allowed=self.node_matches_allowed,
                allowed_countries=self.allowed_countries(),
            )

            self.set_state(active_node_latency="清理连接", last_check_message="正在关闭与清理旧的 VPN 连接及网卡...")
            self.stop_active_openvpn()
            stopped_existing = True

            self.set_state(active_node_latency="写入配置", last_check_message="正在写入 OpenVPN 节点配置文件...")
            config_path = Path(node["config_file"])
            try:
                self.write_ovpn_config(config_path, node.get("config_text") or "")
            except Exception as exc:
                raise RuntimeError(f"Failed to write configuration: {exc}") from exc

            self.set_state(active_node_latency="启动核心", last_check_message="正在启动 OpenVPN Core 核心服务并建立连接...")
            ok, message, process = self.run_openvpn_until_ready(str(node["config_file"]))
            if not ok or process is None:
                def handle_failure() -> str:
                    return self.connection_runtime().handle_start_failure(
                        nodes=nodes,
                        node_id=node_id,
                        config_path=config_path,
                        message=message,
                        log_message_template="连接节点 {node_id} 失败: {message}",
                        print_message_template="[连接核心失败] 无法为 VPN 节点 {node_id} 建立隧道连接！详情: {message}",
                    )

                self.set_active_node_id(self.run_locked(handle_failure))
                raise RuntimeError(message)

            def register_active() -> None:
                active_process, active_node_id = self.connection_runtime().register_active_process(process, node_id)
                self.set_active_connection(active_process, active_node_id)

            self.run_locked(register_active)

            self.set_state(active_node_latency="配置路由", last_check_message="正在配置策略路由规则与流量转发...")
            self.setup_policy_routing(self.tun_dev())

            self.set_last_active_ping_time(self.now())
            self.set_last_active_latency(0)

            self.set_state(active_node_latency="测试延迟", last_check_message="正在直连测试代理出口延迟与可用性...")
            try:
                latency = measure_node_latency(
                    node,
                    parse_int=self.parse_int,
                    ping_latency_ms=self.ping_latency_ms,
                )
                if latency > 0:
                    self.set_last_active_latency(latency)
            except Exception:
                pass

            mark_connection_active(
                nodes,
                node_id,
                proxy_host=self.proxy_host(),
                proxy_port=self.proxy_port(),
            )
            self.write_nodes(nodes)

            self.set_state(last_check_message="正在测试本地代理出站联通性与出口 IP...")
            self.set_state(**proxy_state_from_health(self.check_proxy_health()))

            self.set_state(
                **connection_success_state(
                    node_id,
                    latency_ms=self.get_last_active_latency(),
                    timeout_label="检测超时",
                )
            )
            self.log_line("INFO", "VPN", f"节点 {node_id} 连接成功，出口网卡 {self.tun_dev()} 已启用")
            return f"Connected {node_id}"
        except Exception as exc:
            if should_clear_failed_connection(
                stopped_existing=stopped_existing,
                active_node_id=self.get_active_node_id(),
                requested_node_id=node_id,
                active_running=self.active_openvpn_running(),
            ):
                self.clear_active_connection_state(f"连接失败: {exc}")
            else:
                self.set_state(is_connecting=False, last_check_message=f"连接失败: {exc}")
            raise
        finally:
            def finish_connecting() -> None:
                self.set_is_connecting(self.connection_runtime().finish_connecting())

            self.run_locked(finish_connecting)

    def maintain_valid_nodes(self, force: bool = False) -> str:
        self.ensure_dirs()
        if not self.try_acquire_maintenance():
            msg = "节点维护任务正在运行，请稍后再试"
            self.set_state(last_check_message=msg)
            return msg

        self.set_is_connecting(True)
        try:
            if force:
                self.run_locked(self.stop_active_openvpn)
            else:
                self._recover_interrupted_connection()

            try:
                self.set_state(is_connecting=True, last_check_message="正在拉取最新的免费 VPN 节点列表...")
                candidates = self.fetch_candidates()
            except Exception as exc:
                self.check_and_fix_dns()
                diag_msg = format_fetch_error_message(
                    exc,
                    api_url=self.api_url(),
                    diagnose_api_failure=self.diagnose_api_failure,
                )
                self.set_state(last_fetch_at=self.now(), last_fetch_status="error", last_fetch_message=diag_msg)
                candidates = []

            if not candidates:
                return "没有拉取到新节点"

            self.run_locked(lambda: self._merge_candidate_nodes(candidates))
            to_test_ids = self.run_locked(lambda: self.select_maintenance_test_nodes(self.read_nodes()))

            msg = (
                f"开始维护测试候选节点，待检测 {len(to_test_ids)} 个"
                f"（上限 {self.maintenance_test_limit()}，并发 {self.node_test_workers()}）"
            )
            self.print_line(f"[周期检测] {msg}")
            self.log_line("INFO", "Main", msg)

            self.set_state(is_connecting=True, last_check_message=msg)
            if to_test_ids:
                self.test_multiple_nodes(to_test_ids)
            else:
                self.print_line("[周期检测] 当前没有需要重测的节点，跳过 OpenVPN 批量测试。")
            self.set_is_connecting(False)

            status = self.run_locked(self._finish_maintenance_cycle)
            valid_nodes_count = status["valid_nodes_count"]
            message = f"Fetched {len(candidates)} nodes. Tested {len(to_test_ids)} non-active nodes."
            self.set_state(
                last_check_at=self.now(),
                last_check_message=message,
                active_openvpn_node_id=self.get_active_node_id(),
                valid_nodes=valid_nodes_count,
            )
            return message
        finally:
            self.set_is_connecting(False)
            self.release_maintenance()

    def _recover_interrupted_connection(self) -> None:
        ui_cfg = self.load_ui_config()
        action = maintenance_recovery_action(
            ui_config=ui_cfg,
            nodes=self.read_nodes(),
            active_node_id=self.get_active_node_id(),
            openvpn_running=self.active_openvpn_running(),
        )
        if action["action"] == "reconnect_fixed":
            target_id = action["target_id"]
            self.print_line(f"[维护线程] 检测到固定 IP 模式下 OpenVPN 未运行，正在重新拉起同一节点: {target_id}")
            self.set_is_connecting(False)
            try:
                self.connect_node(target_id)
            except Exception as exc:
                self.print_line(f"[维护线程] 重新拉起固定节点 {target_id} 失败: {exc}")
            self.set_is_connecting(True)
        elif action["action"] == "auto_switch_after_lost_process":
            self.stop_active_openvpn()
            self.print_line("[维护线程] 检测到当前 OpenVPN 进程已意外退出，准备自动切换节点")
            self.set_is_connecting(False)
            self.auto_switch_node()
            self.set_is_connecting(True)

    def _merge_candidate_nodes(self, candidates: list[dict[str, Any]]) -> None:
        active_node = None
        active_node_id = self.get_active_node_id()
        if active_node_id:
            current_nodes = self.read_nodes()
            active_node = next((node for node in current_nodes if node.get("id") == active_node_id), None)
            if active_node and not self.node_matches_allowed(active_node):
                active_node = None

        merged = merge_candidate_nodes(candidates, active_node=active_node, max_nodes=1000)
        ensure_node_config_files(merged, write_config=self.write_ovpn_config)
        self.write_nodes(merged)

    def _finish_maintenance_cycle(self) -> dict[str, Any]:
        merged = self.read_nodes()
        status = maintenance_node_status(merged, node_matches_allowed=self.node_matches_allowed)
        active_node = status["active_node_id"]
        status_report = format_maintenance_status_report(
            total_nodes=len(merged),
            available_node_ids=status["available_node_ids"],
            unavailable_node_ids=status["unavailable_node_ids"],
            active_node_id=active_node,
        )
        self.print_line(f"[周期检测] {status_report}")
        self.log_line("INFO", "Main", status_report)

        if active_node != "none" and not self.active_openvpn_running():
            warn_msg = f"[诊断警告] 活动节点 {active_node} 被标记为活动状态，但 OpenVPN 进程实际并未正常运行！"
            self.print_line(warn_msg)
            self.log_line("WARNING", "Main", warn_msg)

        if not self.active_openvpn_running():
            ui_cfg = self.load_ui_config()
            if should_auto_connect_after_maintenance(
                merged,
                ui_config=ui_cfg,
                node_matches_allowed=self.node_matches_allowed,
                filter_nodes_by_routing_region=self.filter_nodes_by_routing_region,
                parse_int=self.parse_int,
            ):
                self.auto_switch_node()
        return status
