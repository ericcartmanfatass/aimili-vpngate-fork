from __future__ import annotations

from typing import Any

from aimilivpn.core.connection import (
    auto_switch_block_reason,
    auto_switch_connect_message,
    auto_switch_no_candidate_message,
    auto_switch_retry_message,
    clear_active_flags,
)
from aimilivpn.core.nodes import select_auto_switch_candidates


def auto_switch_node(ctx: Any, attempt: int = 0) -> None:
    if attempt >= 3:
        ctx.print_line("[自动切换] 连续切换失败已达 3 次，停止切换以防止主线程死锁，将在后台重新加载节点...")
        return

    ui_cfg = ctx.load_ui_config()
    block_reason = auto_switch_block_reason(ui_cfg)
    if block_reason == "disabled":
        ctx.print_line("[自动切换] 连接已禁用，不进行自动切换。")
        return
    if block_reason == "fixed_ip":
        ctx.print_line("[自动切换] 当前处于固定 IP 模式，不进行自动连接或切换。")
        return

    routing_mode = ui_cfg.get("routing_mode", "auto")
    target_country = ui_cfg.get("force_country", "")

    def select_candidates() -> list[dict[str, Any]]:
        return select_auto_switch_candidates(
            ctx.read_nodes(),
            ui_config=ui_cfg,
            node_matches_allowed=ctx.node_matches_allowed,
            filter_nodes_by_routing_region=ctx.filter_nodes_by_routing_region,
            parse_int=ctx.parse_int,
            exclude_datacenter=ctx.exclude_datacenter(),
        )

    candidates = ctx.run_locked(select_candidates)
    if candidates:
        next_node = candidates[0]
        node_id = str(next_node["id"])
        msg = auto_switch_connect_message(node_id)
        ctx.print_line(f"[自动切换] {msg}")
        ctx.log_line("INFO", "VPN", msg)
        try:
            ctx.connect_node(node_id)
        except Exception as exc:
            err_msg = auto_switch_retry_message(node_id, exc)
            ctx.print_line(f"[自动切换] {err_msg}")
            ctx.log_line("WARNING", "VPN", err_msg)
            ctx.auto_switch_node(attempt + 1)
        return

    msg = auto_switch_no_candidate_message(
        routing_mode=str(routing_mode or "auto"),
        target_country=str(target_country or ""),
        routing_target_label=ctx.routing_target_label,
    )
    ctx.print_line(f"[自动切换] {msg}")
    ctx.log_line("WARNING", "VPN", msg)
    ctx.stop_active_openvpn()

    def clear_nodes() -> None:
        nodes = ctx.read_nodes()
        clear_active_flags(nodes)
        ctx.write_nodes(nodes)

    ctx.run_locked(clear_nodes)
    ctx.set_state(active_openvpn_node_id="", last_check_message=msg)

    def bg_fetch_and_switch() -> None:
        try:
            ctx.maintain_valid_nodes(force=False)
            ctx.auto_switch_node()
        except Exception as exc:
            ctx.print_line(f"[自动切换后台补齐] 获取并测试节点失败: {exc}")

    ctx.start_thread(bg_fetch_and_switch)

