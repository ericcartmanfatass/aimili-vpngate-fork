from __future__ import annotations

from typing import Any

from aimilivpn.core.connection import (
    auto_switch_block_reason,
    auto_switch_connect_message,
    auto_switch_no_candidate_message,
    auto_switch_retry_message,
    clear_active_flags,
)
from aimilivpn.core.connection_state import ConnectionPhase
from aimilivpn.core.nodes import select_auto_switch_candidates


def auto_switch_node(ctx: Any, attempt: int = 0) -> None:
    ui_cfg = ctx.load_ui_config()
    block_reason = auto_switch_block_reason(ui_cfg)
    if block_reason == "disabled":
        ctx.cancel_retry_scheduled()
        ctx.set_state(
            connection_retry_level=0,
            next_connection_retry_at=0,
            connection_waiting_for_global_nodes=False,
        )
        ctx.transition(ConnectionPhase.IDLE, "连接已禁用")
        ctx.print_line("[自动切换] 连接已禁用，不进行自动切换。")
        return
    if attempt <= 0 and _resume_persisted_retry(ctx):
        return
    if block_reason == "fixed_ip":
        _retry_fixed_node(ctx, ui_cfg, attempt)
        return

    ctx.transition(ConnectionPhase.SWITCHING, "正在选择备用节点")
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
        ctx.clear_no_candidate_suppression()
        limit = max(1, int(getattr(ctx, "connection_candidate_limit", 3) or 3))
        attempted: list[str] = []
        for next_node in candidates[:limit]:
            node_id = str(next_node["id"])
            attempted.append(node_id)
            message = auto_switch_connect_message(node_id)
            ctx.print_line(f"[自动切换] {message}")
            ctx.log_line("INFO", "VPN", message)
            try:
                ctx.connect_node(node_id)
            except Exception as exc:
                error_message = auto_switch_retry_message(node_id, exc)
                ctx.print_line(f"[自动切换] {error_message}")
                ctx.log_line("WARNING", "VPN", error_message)
                marker = getattr(ctx, "mark_blacklisted", None)
                if callable(marker):
                    marker(next_node, str(exc))
                continue
            _clear_retry_state(ctx)
            return

        summary = f"本轮 {len(attempted)} 个候选节点均连接失败，将按退避策略重试。"
        ctx.print_line(f"[自动切换] {summary}")
        ctx.log_line("WARNING", "VPN", summary)
        _schedule_retry(ctx, attempt)
        return

    message = auto_switch_no_candidate_message(
        routing_mode=str(routing_mode or "auto"),
        target_country=str(target_country or ""),
        routing_target_label=ctx.routing_target_label,
    )
    if ctx.should_log_no_candidate(message):
        ctx.print_line(f"[自动切换] {message}")
        ctx.log_line("WARNING", "VPN", message)
    ctx.stop_active_openvpn()

    def clear_nodes() -> None:
        nodes = ctx.read_nodes()
        clear_active_flags(nodes)
        ctx.write_nodes(nodes)

    ctx.run_locked(clear_nodes)
    ctx.set_state(
        active_openvpn_node_id="",
        last_check_message=message,
        connection_retry_level=0,
        next_connection_retry_at=0,
        connection_waiting_for_global_nodes=True,
    )
    ctx.transition(ConnectionPhase.IDLE, message)


def _retry_fixed_node(ctx: Any, ui_cfg: dict[str, Any], attempt: int) -> None:
    node_id = str(ui_cfg.get("fixed_node_id") or ctx.get_active_node_id() or "").strip()
    if not node_id:
        message = "固定 IP 模式尚未选择节点，已停止连接重试。"
        ctx.set_state(
            connection_retry_level=0,
            next_connection_retry_at=0,
            connection_waiting_for_global_nodes=False,
            last_check_message=message,
        )
        ctx.transition(ConnectionPhase.IDLE, message)
        ctx.print_line(f"[自动切换] {message}")
        return

    ctx.transition(ConnectionPhase.CONNECTING, f"正在重试固定节点 {node_id}", node_id)
    try:
        ctx.connect_node(node_id)
    except Exception as exc:
        message = f"固定节点 {node_id} 连接失败: {exc}"
        ctx.print_line(f"[自动切换] {message}")
        ctx.log_line("WARNING", "VPN", message)
        _schedule_retry(ctx, attempt)
        return
    _clear_retry_state(ctx)


def _clear_retry_state(ctx: Any) -> None:
    ctx.set_state(
        connection_retry_level=0,
        next_connection_retry_at=0,
        connection_waiting_for_global_nodes=False,
    )


def _resume_persisted_retry(ctx: Any) -> bool:
    get_state = getattr(ctx, "get_state", None)
    if not callable(get_state):
        return False
    state = get_state()
    if not isinstance(state, dict):
        return False
    retry_at = float(state.get("next_connection_retry_at") or 0)
    remaining = retry_at - float(ctx.now())
    if remaining <= 0:
        return False
    retry_level = max(1, int(state.get("connection_retry_level") or 1))
    delay = max(1, int(remaining + 0.999))
    if not ctx.mark_retry_scheduled():
        return True
    message = f"正在恢复连接退避，将在 {delay} 秒后重试。"
    ctx.transition(ConnectionPhase.IDLE, message)
    try:
        generation = ctx.retry_generation()
        ctx.start_thread(lambda: _retry_after_backoff(ctx, retry_level, delay, generation))
    except Exception:
        ctx.clear_retry_scheduled()
        raise
    return True


def _schedule_retry(ctx: Any, attempt: int) -> None:
    retry_delay = _retry_delay(ctx, attempt)
    backoff = tuple(getattr(ctx, "instance_retry_backoff_seconds", ()) or ())
    retry_level = min(attempt + 1, max(1, len(backoff)))
    ctx.set_state(
        connection_retry_level=retry_level,
        next_connection_retry_at=ctx.now() + retry_delay,
        connection_waiting_for_global_nodes=False,
    )
    if not ctx.mark_retry_scheduled():
        return
    try:
        generation = ctx.retry_generation()
        ctx.start_thread(lambda: _retry_after_backoff(ctx, attempt + 1, retry_delay, generation))
    except Exception:
        ctx.clear_retry_scheduled()
        raise


def _retry_delay(ctx: Any, attempt: int) -> int:
    values = tuple(getattr(ctx, "instance_retry_backoff_seconds", ()) or ())
    if not values:
        return 0
    return max(0, int(values[min(max(0, attempt), len(values) - 1)]))


def _retry_after_backoff(ctx: Any, attempt: int, delay: int, generation: int) -> None:
    wait_for_stop = getattr(ctx, "wait_for_stop", None)
    remaining = max(0, int(delay))
    stopped = False
    while remaining > 0 and ctx.retry_generation_is_current(generation):
        step = min(1, remaining)
        if callable(wait_for_stop) and bool(wait_for_stop(step)):
            stopped = True
            break
        if not ctx.load_ui_config().get("connection_enabled", True):
            ctx.cancel_retry_scheduled()
            ctx.set_state(connection_retry_level=0, next_connection_retry_at=0)
            return
        remaining -= step
    if not ctx.retry_generation_is_current(generation):
        return
    ctx.clear_retry_scheduled()
    if not stopped:
        ctx.auto_switch_node(attempt)
