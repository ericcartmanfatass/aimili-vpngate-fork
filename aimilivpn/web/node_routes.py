from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aimilivpn.core.connection_state import ConnectionPhase
from aimilivpn.web.api_contract import InvalidListQuery, parse_list_query
from aimilivpn.web.api_errors import send_api_error, send_client_error
from aimilivpn.web.operations import OperationCapacityError
from aimilivpn.web.route_contexts import NodeRouteContext

def handle_node_get(handler: Any, effective_path: str, context: NodeRouteContext) -> bool:
    if effective_path == "/api/v1/operations" or effective_path.startswith("/api/v1/operations/"):
        return _handle_operation_get(handler, effective_path, context)
    if effective_path != "/api/nodes":
        return False

    nodes = context.read_nodes()
    try:
        query = parse_list_query(
            handler,
            allowed_filters=("region", "country", "status", "ip_type"),
            allowed_sort=("id", "country", "latency", "quality", "score"),
            default_sort="id",
            default_limit=200,
        )
    except InvalidListQuery:
        send_client_error(handler, "invalid_query", "invalid list query")
        return True
    region_id = query.filters.get("region", "")
    if region_id:
        try:
            nodes = context.filter_nodes_by_region(nodes, region_id)
        except KeyError:
            handler.send_json({"error": "地区不存在"}, HTTPStatus.NOT_FOUND)
            return True
    country = query.filters.get("country", "").upper()
    status = query.filters.get("status", "")
    ip_type = query.filters.get("ip_type", "")
    if country:
        nodes = [node for node in nodes if str(node.get("country_short") or "").upper() == country]
    if status:
        nodes = [node for node in nodes if str(node.get("probe_status") or "") == status]
    if ip_type:
        nodes = [node for node in nodes if str(node.get("ip_type") or "") == ip_type]

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
    stripped_nodes.sort(key=lambda node: _node_sort_value(node, query.sort), reverse=query.order == "desc")
    page, pagination = query.page(stripped_nodes)
    handler.send_json({"nodes": page, "state": context.get_state(), "pagination": pagination})
    return True

def handle_node_post(handler: Any, effective_path: str, context: NodeRouteContext) -> bool:
    if effective_path == "/api/check":
        if context.submit_operation is not None:
            return _submit_operation(handler, context, "check_nodes", "all", lambda: context.maintain_valid_nodes(True))
        try:
            handler.send_json({"ok": True, "message": context.maintain_valid_nodes(True)})
        except Exception as exc:
            send_api_error(handler, "maintenance_failed", exc=exc, operation="forced maintenance")
        return True

    if effective_path == "/api/refresh_nodes":
        if context.submit_operation is not None:
            return _submit_operation(handler, context, "refresh_nodes", "all", lambda: context.maintain_valid_nodes(True))
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
            node_ids = _validated_node_ids(payload.get("ids", []))
            if context.submit_operation is not None:
                return _submit_operation(
                    handler,
                    context,
                    "test_nodes",
                    ",".join(node_ids),
                    lambda: {"nodes": context.test_multiple_nodes(node_ids)},
                )
            tested_nodes = context.test_multiple_nodes(node_ids)
            handler.send_json({"ok": True, "nodes": tested_nodes})
        except ValueError:
            send_client_error(handler, "invalid_node_ids", "invalid node ids")
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="node batch test")
        return True

    if effective_path == "/api/disconnect":
        if context.submit_operation is not None:
            return _submit_operation(handler, context, "disconnect", "connection", lambda: _disconnect(context))
        try:
            _disconnect(context)
            handler.send_json({"ok": True})
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="disconnect")
        return True

    if effective_path == "/api/connect":
        try:
            payload = handler.read_json_body()
            node_id = str(payload.get("id") or "").strip()
            if not node_id:
                raise ValueError("node id is required")
            if context.submit_operation is not None:
                return _submit_operation(
                    handler,
                    context,
                    "connect",
                    node_id,
                    lambda: {"message": context.connect_node(node_id)},
                )
            handler.send_json({"ok": True, "message": context.connect_node(node_id)})
        except ValueError:
            send_client_error(handler, "invalid_node_request", "node id is required")
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="connect")
        return True

    if effective_path == "/api/test_node":
        try:
            payload = handler.read_json_body()
            node_id = str(payload.get("id") or "").strip()
            if not node_id:
                raise ValueError("node id is required")
            if context.submit_operation is not None:
                return _submit_operation(
                    handler,
                    context,
                    "test_node",
                    node_id,
                    lambda: {"node": context.test_node_by_id(node_id)},
                )
            updated_node = context.test_node_by_id(node_id)
            handler.send_json({"ok": True, "node": updated_node})
        except ValueError:
            send_client_error(handler, "invalid_node_request", "node id is required")
        except Exception as exc:
            send_api_error(handler, "node_operation_failed", exc=exc, operation="node test")
        return True

    return False


def _submit_operation(
    handler: Any,
    context: NodeRouteContext,
    kind: str,
    target: str,
    task: Any,
) -> bool:
    explicit_key = str(getattr(handler, "headers", {}).get("X-Idempotency-Key", "") or "").strip()
    if len(explicit_key) > 128:
        send_client_error(handler, "invalid_idempotency_key", "invalid idempotency key")
        return True
    key = explicit_key or f"implicit:{kind}:{target}"
    assert context.submit_operation is not None
    try:
        operation, duplicate = context.submit_operation(kind, key, task, bool(explicit_key))
    except OperationCapacityError:
        send_client_error(handler, "operation_capacity", "operation capacity reached", HTTPStatus.SERVICE_UNAVAILABLE)
        return True
    handler.send_json(
        {
            "ok": True,
            "operation_id": operation["id"],
            "operation": operation,
            "deduplicated": duplicate,
        },
        HTTPStatus.ACCEPTED,
    )
    return True


def _handle_operation_get(handler: Any, effective_path: str, context: NodeRouteContext) -> bool:
    if context.get_operation is None or context.list_operations is None:
        handler.send_json({"ok": False, "error": "operations unavailable", "error_code": "operations_unavailable"}, HTTPStatus.NOT_FOUND)
        return True
    if effective_path == "/api/v1/operations":
        try:
            query = parse_list_query(
                handler,
                allowed_filters=("status", "kind"),
                allowed_sort=("created_at", "updated_at", "kind", "status"),
                default_sort="created_at",
                default_order="desc",
                default_limit=100,
            )
        except InvalidListQuery:
            send_client_error(handler, "invalid_query", "invalid list query")
            return True
        operations = context.list_operations()
        for name in ("status", "kind"):
            expected = query.filters.get(name, "")
            if expected:
                operations = [item for item in operations if str(item.get(name) or "") == expected]
        operations.sort(key=lambda item: item.get(query.sort) or "", reverse=query.order == "desc")
        page, pagination = query.page(operations)
        handler.send_json({"ok": True, "operations": page, "pagination": pagination})
        return True
    operation_id = effective_path.removeprefix("/api/v1/operations/").strip()
    operation = context.get_operation(operation_id)
    if operation is None:
        handler.send_json({"ok": False, "error": "操作不存在", "error_code": "operation_not_found"}, HTTPStatus.NOT_FOUND)
    else:
        handler.send_json({"ok": True, "operation": operation})
    return True


def _disconnect(context: NodeRouteContext) -> dict[str, Any]:
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
    return {"disconnected": True}


def _validated_node_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        raise ValueError("ids must contain 1-100 items")
    node_ids = [str(item or "").strip() for item in value]
    if any(not node_id or len(node_id) > 128 for node_id in node_ids):
        raise ValueError("invalid node id")
    return list(dict.fromkeys(node_ids))


def _node_sort_value(node: dict[str, Any], field: str) -> Any:
    if field == "latency":
        return _safe_int(node.get("latency_ms") or node.get("ping"), 999999)
    if field in {"quality", "score"}:
        return _safe_int(node.get("quality_score") or node.get("score"), 0)
    if field == "country":
        return str(node.get("country_short") or node.get("country") or "").lower()
    return str(node.get("id") or "").lower()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
