from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.nodes import select_auto_switch_candidates

NodePredicate = Callable[[dict[str, Any]], bool]
NodeFilter = Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
ParseInt = Callable[[Any], int]


def select_maintenance_test_nodes(
    nodes: list[dict[str, Any]],
    *,
    now: float,
    routing_mode: str,
    force_country: str,
    node_matches_allowed: NodePredicate,
    filter_nodes_by_routing_region: NodeFilter,
    parse_int: ParseInt,
    retest_interval_seconds: int,
    max_nodes: int,
) -> list[str]:
    candidates = [node for node in nodes if not node.get("active") and node_matches_allowed(node)]
    if routing_mode == "fixed_region" and force_country:
        candidates = filter_nodes_by_routing_region(candidates, str(force_country or ""))

    untested = [
        node for node in candidates
        if node.get("probe_status") in ("", None, "not_checked") or _probed_at(node) <= 0
    ]
    stale_available = [
        node for node in candidates
        if node.get("probe_status") == "available" and now - _probed_at(node) >= retest_interval_seconds
    ]
    stale_unavailable = [
        node for node in candidates
        if node.get("probe_status") == "unavailable" and now - _probed_at(node) >= retest_interval_seconds
    ]

    def priority(node: dict[str, Any]) -> tuple[int, int, float]:
        return (
            parse_int(node.get("latency_ms")) or parse_int(node.get("ping")) or 999999,
            -parse_int(node.get("score")),
            _probed_at(node),
        )

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in (untested, stale_available, stale_unavailable):
        for node in sorted(group, key=priority):
            node_id = str(node.get("id") or "")
            if not node_id or node_id in seen:
                continue
            selected.append(node)
            seen.add(node_id)
            if len(selected) >= max_nodes:
                return [str(item["id"]) for item in selected]
    return [str(item["id"]) for item in selected]


def merge_candidate_nodes(
    candidates: list[dict[str, Any]],
    *,
    active_node: dict[str, Any] | None = None,
    max_nodes: int = 1000,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    if active_node:
        active_id = str(active_node.get("id") or "")
        if active_id:
            merged.append(active_node)
            seen_ids.add(active_id)

    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "")
        if candidate_id and candidate_id not in seen_ids:
            merged.append(candidate)
            seen_ids.add(candidate_id)
        if len(merged) >= max_nodes:
            break
    return merged


def ensure_node_config_files(
    nodes: list[dict[str, Any]],
    *,
    write_config: Callable[[Path, str], None],
    on_error: Callable[[dict[str, Any], Exception], None] | None = None,
) -> None:
    for node in nodes:
        config_file = node.get("config_file")
        if not config_file:
            continue
        config_path = Path(str(config_file))
        if config_path.exists():
            continue
        try:
            write_config(config_path, str(node.get("config_text") or ""))
        except Exception as exc:
            if on_error:
                on_error(node, exc)


def maintenance_node_status(
    nodes: list[dict[str, Any]],
    *,
    node_matches_allowed: NodePredicate,
) -> dict[str, Any]:
    available_node_ids = [
        str(node.get("id"))
        for node in nodes
        if node.get("probe_status") == "available" and node.get("id") and node_matches_allowed(node)
    ]
    unavailable_node_ids = [
        str(node.get("id"))
        for node in nodes
        if node.get("probe_status") == "unavailable" and node.get("id") and node_matches_allowed(node)
    ]
    active_node_id = next((str(node.get("id")) for node in nodes if node.get("active") and node.get("id")), "none")
    return {
        "available_node_ids": available_node_ids,
        "unavailable_node_ids": unavailable_node_ids,
        "active_node_id": active_node_id,
        "valid_nodes_count": len(available_node_ids),
    }


def format_maintenance_status_report(
    *,
    total_nodes: int,
    available_node_ids: list[str],
    unavailable_node_ids: list[str],
    active_node_id: str,
    preview_limit: int = 15,
) -> str:
    return (
        f"周期节点检测完成。实时同步状态：获取到候选节点共 {total_nodes} 个。"
        f"其中【可用节点】{len(available_node_ids)} 个: {available_node_ids[:preview_limit]}...; "
        f"【不可用节点】{len(unavailable_node_ids)} 个; "
        f"当前【正在正常运行的活动连接节点】为: {active_node_id}。"
    )


def should_auto_connect_after_maintenance(
    nodes: list[dict[str, Any]],
    *,
    ui_config: dict[str, Any],
    node_matches_allowed: NodePredicate,
    filter_nodes_by_routing_region: NodeFilter,
    parse_int: ParseInt,
) -> bool:
    if not ui_config.get("connection_enabled", True):
        return False
    if str(ui_config.get("routing_mode") or "auto") == "fixed_ip":
        return False
    return bool(
        select_auto_switch_candidates(
            nodes,
            ui_config=ui_config,
            node_matches_allowed=node_matches_allowed,
            filter_nodes_by_routing_region=filter_nodes_by_routing_region,
            parse_int=parse_int,
        )
    )


def maintenance_recovery_action(
    *,
    ui_config: dict[str, Any],
    nodes: list[dict[str, Any]],
    active_node_id: str,
    openvpn_running: bool,
) -> dict[str, str]:
    if openvpn_running or not ui_config.get("connection_enabled", True):
        return {"action": "none", "target_id": ""}

    routing_mode = str(ui_config.get("routing_mode") or "auto")
    if routing_mode == "fixed_ip":
        target_id = str(active_node_id or ui_config.get("fixed_node_id") or "")
        if target_id and any(node.get("id") == target_id for node in nodes):
            return {"action": "reconnect_fixed", "target_id": target_id}
        return {"action": "none", "target_id": ""}

    if active_node_id:
        return {"action": "auto_switch_after_lost_process", "target_id": active_node_id}
    return {"action": "none", "target_id": ""}


def should_diagnose_fetch_error(message: str, tokens: tuple[str, ...] = ("[ERR_", "错误代码")) -> bool:
    return not any(token in message for token in tokens)


def format_fetch_error_message(
    exc: Exception,
    *,
    api_url: str,
    diagnose_api_failure: Callable[[str], tuple[Any, Any]],
) -> str:
    message = str(exc)
    if not should_diagnose_fetch_error(message):
        return message
    error_code, raw_diagnosis = diagnose_api_failure(api_url)
    return f"[错误代码 {error_code}] 获取节点失败: {exc} | 诊断结果: {raw_diagnosis}"


def _probed_at(node: dict[str, Any]) -> float:
    try:
        return float(node.get("probed_at") or 0)
    except (TypeError, ValueError):
        return 0.0
