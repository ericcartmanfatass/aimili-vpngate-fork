from __future__ import annotations

import urllib.parse
from http import HTTPStatus
from typing import Any

from aimilivpn.core.connection_state import ConnectionPhase
from aimilivpn.web.api_errors import send_api_error
from aimilivpn.web.route_contexts import NodeRouteContext

def handle_node_get(handler: Any, effective_path: str, context: NodeRouteContext) -> bool:
    if effective_path != "/api/nodes":
        return False

    nodes = context.read_nodes()
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)
    region_id = str((query.get("region") or [""])[0]).strip()
    if region_id:
        try:
            nodes = context.filter_nodes_by_region(nodes, region_id)
        except KeyError:
            handler.send_json({"error": "region not found"}, HTTPStatus.NOT_FOUND)
            return True

    active_node_id = context.get_active_node_id()
    active_node = next((n for n in nodes if active_node_id and n.get("id") == active_node_id), None)
    for node in nodes:
        node["active"] = bool(active_node_id and node.get("id") == active_node_id)

    if active_node:
        ip = active_node.get("ip") or active_node.get("remote_host")
        if ip:
            now = context.now()
            if now - context.get_last_active_ping_time() > 15.0:
                context.set_last_active_ping_time(now)

                def bg_ping(ip_addr: str, port: int, fallback: int) -> None:
                    try:
                        latency = context.ping_latency_ms(ip_addr, port, fallback)
                        if latency > 0:
                            context.set_last_active_latency(latency)
                    except Exception:
                        pass

                context.start_daemon_thread(
                    bg_ping,
                    (
                        str(ip),
                        context.parse_int(active_node.get("remote_port")),
                        context.parse_int(active_node.get("ping")),
                    ),
                )
            last_latency = context.get_last_active_latency()
            if last_latency > 0:
                active_node["latency_ms"] = last_latency

    stripped_nodes = []
    for node in nodes:
        stripped = node.copy()
        stripped.pop("config_text", None)
        stripped_nodes.append(stripped)
    handler.send_json({"nodes": stripped_nodes, "state": context.get_state()})
    return True

def handle_node_post(handler: Any, effective_path: str, context: NodeRouteContext) -> bool:
    if effective_path == "/api/check":
        try:
            handler.send_json({"ok": True, "message": context.maintain_valid_nodes(True)})
        except Exception as exc:
            send_api_error(handler, "maintenance_failed", exc=exc, operation="forced maintenance")
        return True

    if effective_path == "/api/refresh_nodes":
        try:
            if context.maintenance_running():
                handler.send_json({"ok": True, "message": "节点维护任务正在运行，请稍后再试", "running": True})
            else:
                context.start_maintenance()
                handler.send_json({"ok": True, "message": "已在后台启动节点更新流程", "running": False})
        except Exception as exc:
            send_api_error(handler, "maintenance_failed", exc=exc, operation="maintenance start")
        return True

    if effective_path == "/api/test_nodes":
        try:
            payload = handler.read_json_body(max_bytes=262144)
            node_ids = payload.get("ids", [])
            tested_nodes = context.test_multiple_nodes(node_ids)
            handler.send_json({"ok": True, "nodes": tested_nodes})
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="node batch test")
        return True

    if effective_path == "/api/disconnect":
        try:
            ui_cfg = context.load_ui_config()
            ui_cfg["connection_enabled"] = False
            context.save_ui_config(ui_cfg)

            context.stop_active_openvpn()
            nodes = context.read_nodes()
            for item in nodes:
                item["active"] = False
            context.write_nodes(nodes)
            context.set_last_active_ping_time(0.0)
            context.set_last_active_latency(0)
            context.set_state(
                active_openvpn_node_id="",
                connection_state=ConnectionPhase.IDLE.value,
                last_check_message="手动断开连接",
                active_node_latency="无活动连接",
            )
            handler.send_json({"ok": True})
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="disconnect")
        return True

    if effective_path == "/api/connect":
        try:
            payload = handler.read_json_body()
            handler.send_json({"ok": True, "message": context.connect_node(str(payload.get("id") or ""))})
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="connect")
        return True

    if effective_path == "/api/test_node":
        try:
            payload = handler.read_json_body()
            node_id = str(payload.get("id") or "")
            updated_node = context.test_node_by_id(node_id)
            handler.send_json({"ok": True, "node": updated_node})
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="node test")
        return True

    return False
