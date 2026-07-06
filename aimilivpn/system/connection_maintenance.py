from __future__ import annotations

from typing import Any

from aimilivpn.core.maintenance import (
    ensure_node_config_files,
    format_fetch_error_message,
    format_maintenance_status_report,
    maintenance_node_status,
    maintenance_recovery_action,
    merge_candidate_nodes,
    should_auto_connect_after_maintenance,
)


def maintain_valid_nodes(ctx: Any, force: bool = False) -> str:
    ctx.ensure_dirs()
    if not ctx.try_acquire_maintenance():
        msg = "节点维护任务正在运行，请稍后再试"
        ctx.set_state(last_check_message=msg)
        return msg

    ctx.set_is_connecting(True)
    try:
        if force:
            ctx.run_locked(ctx.stop_active_openvpn)
        else:
            ctx._recover_interrupted_connection()

        try:
            ctx.set_state(is_connecting=True, last_check_message="正在拉取最新的免费 VPN 节点列表...")
            candidates = ctx.fetch_candidates()
        except Exception as exc:
            ctx.check_and_fix_dns()
            diag_msg = format_fetch_error_message(
                exc,
                api_url=ctx.api_url(),
                diagnose_api_failure=ctx.diagnose_api_failure,
            )
            ctx.set_state(last_fetch_at=ctx.now(), last_fetch_status="error", last_fetch_message=diag_msg)
            candidates = []

        if not candidates:
            return "没有拉取到新节点"

        ctx.run_locked(lambda: ctx._merge_candidate_nodes(candidates))
        to_test_ids = ctx.run_locked(lambda: ctx.select_maintenance_test_nodes(ctx.read_nodes()))

        msg = (
            f"开始维护测试候选节点，待检测 {len(to_test_ids)} 个"
            f"（上限 {ctx.maintenance_test_limit()}，并发 {ctx.node_test_workers()}）"
        )
        ctx.print_line(f"[周期检测] {msg}")
        ctx.log_line("INFO", "Main", msg)

        ctx.set_state(is_connecting=True, last_check_message=msg)
        if to_test_ids:
            ctx.test_multiple_nodes(to_test_ids)
        else:
            ctx.print_line("[周期检测] 当前没有需要重测的节点，跳过 OpenVPN 批量测试。")
        ctx.set_is_connecting(False)

        status = ctx.run_locked(ctx._finish_maintenance_cycle)
        valid_nodes_count = status["valid_nodes_count"]
        message = f"Fetched {len(candidates)} nodes. Tested {len(to_test_ids)} non-active nodes."
        ctx.set_state(
            last_check_at=ctx.now(),
            last_check_message=message,
            active_openvpn_node_id=ctx.get_active_node_id(),
            valid_nodes=valid_nodes_count,
        )
        return message
    finally:
        ctx.set_is_connecting(False)
        ctx.release_maintenance()


def recover_interrupted_connection(ctx: Any) -> None:
    ui_cfg = ctx.load_ui_config()
    action = maintenance_recovery_action(
        ui_config=ui_cfg,
        nodes=ctx.read_nodes(),
        active_node_id=ctx.get_active_node_id(),
        openvpn_running=ctx.active_openvpn_running(),
    )
    if action["action"] == "reconnect_fixed":
        target_id = action["target_id"]
        ctx.print_line(f"[维护线程] 固定 IP 模式下 OpenVPN 未运行，正在重新连接同一节点: {target_id}")
        ctx.set_is_connecting(False)
        try:
            ctx.connect_node(target_id)
        except Exception as exc:
            ctx.print_line(f"[维护线程] 重新连接固定节点 {target_id} 失败: {exc}")
        ctx.set_is_connecting(True)
    elif action["action"] == "auto_switch_after_lost_process":
        ctx.stop_active_openvpn()
        ctx.print_line("[维护线程] 当前 OpenVPN 进程已退出，准备自动切换节点")
        ctx.set_is_connecting(False)
        ctx.auto_switch_node()
        ctx.set_is_connecting(True)


def merge_candidates(ctx: Any, candidates: list[dict[str, Any]]) -> None:
    active_node = None
    active_node_id = ctx.get_active_node_id()
    if active_node_id:
        current_nodes = ctx.read_nodes()
        active_node = next((node for node in current_nodes if node.get("id") == active_node_id), None)
        if active_node and not ctx.node_matches_allowed(active_node):
            active_node = None

    merged = merge_candidate_nodes(candidates, active_node=active_node, max_nodes=1000)
    ensure_node_config_files(merged, write_config=ctx.write_ovpn_config)
    ctx.write_nodes(merged)


def finish_maintenance_cycle(ctx: Any) -> dict[str, Any]:
    merged = ctx.read_nodes()
    status = maintenance_node_status(merged, node_matches_allowed=ctx.node_matches_allowed)
    active_node = status["active_node_id"]
    status_report = format_maintenance_status_report(
        total_nodes=len(merged),
        available_node_ids=status["available_node_ids"],
        unavailable_node_ids=status["unavailable_node_ids"],
        active_node_id=active_node,
    )
    ctx.print_line(f"[周期检测] {status_report}")
    ctx.log_line("INFO", "Main", status_report)

    if active_node != "none" and not ctx.active_openvpn_running():
        warn_msg = f"[diagnostic warning] active node {active_node} is marked active, but OpenVPN is not running."
        ctx.print_line(warn_msg)
        ctx.log_line("WARNING", "Main", warn_msg)

    if not ctx.active_openvpn_running():
        ui_cfg = ctx.load_ui_config()
        if should_auto_connect_after_maintenance(
            merged,
            ui_config=ui_cfg,
            node_matches_allowed=ctx.node_matches_allowed,
            filter_nodes_by_routing_region=ctx.filter_nodes_by_routing_region,
            parse_int=ctx.parse_int,
        ):
            ctx.auto_switch_node()
    return status
