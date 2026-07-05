from __future__ import annotations

from typing import Any, Callable


def collector_sleep_seconds(*, active_running: bool, success: bool, check_interval_seconds: int, retry_seconds: int = 30) -> int:
    return retry_seconds if not active_running and not success else check_interval_seconds


def proxy_state_from_health(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("ok"):
        return {
            "proxy_ok": True,
            "proxy_ip": result.get("ip", ""),
            "proxy_latency_ms": result.get("latency_ms", 0),
            "proxy_error": "",
        }
    return {
        "proxy_ok": False,
        "proxy_ip": "-",
        "proxy_latency_ms": 0,
        "proxy_error": result.get("error", "unknown error"),
    }


def should_auto_switch_after_proxy_failure(active_node_id: str, routing_mode: str) -> bool:
    return bool(active_node_id) and routing_mode != "fixed_ip"


def should_restart_fixed_node_after_proxy_failure(active_node_id: str, routing_mode: str) -> bool:
    return bool(active_node_id) and routing_mode == "fixed_ip"


def mark_active_node_proxy_failed(
    nodes: list[dict[str, Any]],
    active_node_id: str,
    *,
    error_message: str,
) -> dict[str, Any] | None:
    active_node = next((node for node in nodes if node.get("id") == active_node_id), None)
    if not active_node:
        return None
    active_node["probe_status"] = "unavailable"
    active_node["probe_message"] = error_message
    return active_node


def active_node_latency_status(
    *,
    active_running: bool,
    active_node_id: str,
    is_connecting: bool,
    nodes: list[dict[str, Any]],
    ping_latency_ms: Callable[[str, int, int], int],
    parse_int: Callable[[Any], int],
    timeout_label: str,
    connecting_label: str,
    idle_label: str,
) -> str:
    if active_running and active_node_id:
        node = next((item for item in nodes if item.get("id") == active_node_id), None)
        if not node:
            return timeout_label
        ip = node.get("ip") or node.get("remote_host")
        if not ip:
            return timeout_label
        latency = ping_latency_ms(str(ip), parse_int(node.get("remote_port")), parse_int(node.get("ping")))
        return f"{latency} ms" if latency > 0 else timeout_label
    if is_connecting:
        return connecting_label
    return idle_label
