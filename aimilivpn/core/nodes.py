from __future__ import annotations

from typing import Any, Callable

ParseInt = Callable[[Any], int]
NodePredicate = Callable[[dict[str, Any]], bool]
NodeRegionFilter = Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]


def sort_nodes_for_display(nodes: list[dict[str, Any]], *, parse_int: ParseInt) -> list[dict[str, Any]]:
    available_nodes = sorted(
        [node for node in nodes if node.get("probe_status") == "available" or node.get("active")],
        key=lambda node: (
            0 if node.get("ip_type") in ("residential", "mobile") else 1,
            parse_int(node.get("latency_ms")) or 999999,
            -parse_int(node.get("score")),
        ),
    )
    untested_nodes = sorted(
        [node for node in nodes if node.get("probe_status") == "not_checked" and not node.get("active")],
        key=lambda node: (-parse_int(node.get("score")), parse_int(node.get("ping"))),
    )
    unavailable_nodes = sorted(
        [node for node in nodes if node.get("probe_status") == "unavailable" and not node.get("active")],
        key=lambda node: (-parse_int(node.get("score")), -_float_value(node.get("probed_at"))),
    )
    return available_nodes + untested_nodes + unavailable_nodes


def select_auto_switch_candidates(
    nodes: list[dict[str, Any]],
    *,
    ui_config: dict[str, Any],
    node_matches_allowed: NodePredicate,
    filter_nodes_by_routing_region: NodeRegionFilter,
    parse_int: ParseInt,
    exclude_datacenter: bool = False,
) -> list[dict[str, Any]]:
    routing_mode = str(ui_config.get("routing_mode") or "auto")
    target_region = str(ui_config.get("force_country") or "")
    candidates = [
        node for node in nodes
        if node.get("probe_status") == "available"
        and not node.get("active")
        and node_matches_allowed(node)
        and (not exclude_datacenter or node.get("quality") != "datacenter")
    ]

    if routing_mode == "fixed_region" and target_region:
        candidates = filter_nodes_by_routing_region(candidates, target_region)
    elif routing_mode == "favorites":
        favorite_ids = set(ui_config.get("favorite_node_ids", []))
        favorite_candidates = [node for node in candidates if node.get("id") in favorite_ids]
        if favorite_candidates:
            candidates = favorite_candidates
        elif not ui_config.get("fav_fail_fallback", True):
            candidates = []

    routing_ip_type = str(ui_config.get("routing_ip_type") or "all")
    if routing_ip_type == "residential":
        candidates = [node for node in candidates if node.get("ip_type") in ("residential", "mobile")]
    elif routing_ip_type == "hosting":
        candidates = [node for node in candidates if node.get("ip_type") == "hosting"]

    return sorted(
        candidates,
        key=lambda node: (parse_int(node.get("latency_ms")) or 999999, -parse_int(node.get("score"))),
    )


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
