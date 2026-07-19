from __future__ import annotations

from pathlib import Path
from typing import Any


def auto_switch_block_reason(ui_config: dict[str, Any]) -> str | None:
    if not ui_config.get("connection_enabled", True):
        return "disabled"
    if str(ui_config.get("routing_mode") or "auto") == "fixed_ip":
        return "fixed_ip"
    return None


def auto_switch_no_candidate_message(
    *,
    routing_mode: str,
    target_country: str,
    routing_target_label: Any,
) -> str:
    if routing_mode == "fixed_region" and target_country:
        return (
            f"没有可用的【{routing_target_label(target_country)}】备用节点，"
            "已进入等待全局节点库更新状态。"
        )
    return "没有可用的备选节点，已进入等待全局节点库更新状态。"


def auto_switch_retry_message(node_id: str, error: Exception) -> str:
    return f"切换到备用节点 {node_id} 失败: {error}，将尝试下一个..."


def auto_switch_connect_message(node_id: str) -> str:
    return f"当前连接已失效或代理连通性检测失败，正在自动切换至最佳备用节点: {node_id}"


def normalize_node_id(value: Any) -> str:
    node_id = str(value or "").strip()
    if not node_id:
        raise ValueError("节点 ID 不能为空")
    return node_id


def require_connectable_node(
    nodes: list[dict[str, Any]],
    node_id: str,
    *,
    node_matches_allowed: Any,
    allowed_countries: set[str],
) -> dict[str, Any]:
    node = next((item for item in nodes if item.get("id") == node_id), None)
    if not node:
        raise ValueError(f"未找到节点: {node_id}")
    if not node_matches_allowed(node):
        raise ValueError(f"节点 {node_id} 不属于此实例允许的国家: {sorted(allowed_countries)}")
    return node


def enable_connection_config(ui_config: dict[str, Any], node_id: str) -> dict[str, Any]:
    ui_config["connection_enabled"] = True
    if ui_config.get("routing_mode") == "fixed_ip":
        ui_config["fixed_node_id"] = node_id
    return ui_config


def prepare_connection_target(
    nodes: list[dict[str, Any]],
    node_id: str,
    ui_config: dict[str, Any],
    *,
    node_matches_allowed: Any,
    allowed_countries: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    node = require_connectable_node(
        nodes,
        node_id,
        node_matches_allowed=node_matches_allowed,
        allowed_countries=allowed_countries,
    )
    return node, enable_connection_config(ui_config, node_id)


def connection_failure_state(message: str) -> dict[str, Any]:
    return {
        "active_openvpn_node_id": "",
        "is_connecting": False,
        "active_node_latency": "无活动连接",
        "last_check_message": f"连接失败: {message}",
    }


def connection_success_state(node_id: str, *, latency_ms: int, timeout_label: str) -> dict[str, Any]:
    return {
        "active_openvpn_node_id": node_id,
        "is_connecting": False,
        "last_check_message": f"已连接 {node_id}",
        "active_node_latency": latency_label(latency_ms, timeout_label=timeout_label),
    }


def should_clear_failed_connection(
    *,
    stopped_existing: bool,
    active_node_id: str,
    requested_node_id: str,
    active_running: bool,
) -> bool:
    return stopped_existing or (active_node_id == requested_node_id and not active_running)


def delete_file_if_exists(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        target = Path(path)
        if target.exists():
            target.unlink()
            return True
    except Exception:
        return False
    return False


def clear_active_flags(nodes: list[dict[str, Any]]) -> None:
    for node in nodes:
        node["active"] = False


def find_active_config_file(nodes: list[dict[str, Any]], active_node_id: str) -> str | None:
    if not active_node_id:
        return None
    node = next((item for item in nodes if item.get("id") == active_node_id), None)
    if not node:
        return None
    config_file = node.get("config_file")
    return str(config_file) if config_file else None


def mark_active_node(nodes: list[dict[str, Any]], node_id: str, *, proxy_url: str) -> None:
    for node in nodes:
        is_active = node.get("id") == node_id
        node["active"] = is_active
        if is_active:
            node["probe_message"] = f"当前节点，HTTP 代理: {proxy_url}"


def mark_connection_failed(nodes: list[dict[str, Any]], node_id: str, *, message: str) -> dict[str, Any] | None:
    failed_node: dict[str, Any] | None = None
    for node in nodes:
        node["active"] = False
        if node.get("id") == node_id:
            node["probe_status"] = "unavailable"
            node["probe_message"] = message
            failed_node = node
    return failed_node


def mark_connection_active(
    nodes: list[dict[str, Any]],
    node_id: str,
    *,
    proxy_host: str,
    proxy_port: int,
) -> str:
    proxy_url = build_proxy_url(proxy_host, proxy_port)
    mark_active_node(nodes, node_id, proxy_url=proxy_url)
    return proxy_url


def build_proxy_url(proxy_host: str, proxy_port: int) -> str:
    display_host = f"[{proxy_host}]" if ":" in proxy_host else proxy_host
    return f"http://{display_host}:{proxy_port}"


def latency_label(latency_ms: int, *, timeout_label: str = "timeout") -> str:
    return f"{latency_ms} ms" if latency_ms > 0 else timeout_label


def measure_node_latency(
    node: dict[str, Any],
    *,
    parse_int: Any,
    ping_latency_ms: Any,
) -> int:
    ip = node.get("ip") or node.get("remote_host")
    if not ip:
        return 0
    return ping_latency_ms(
        str(ip),
        parse_int(node.get("remote_port")),
        parse_int(node.get("ping")),
    )
