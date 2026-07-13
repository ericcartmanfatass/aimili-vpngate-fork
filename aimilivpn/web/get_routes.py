from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aimilivpn.web.api_contract import canonical_route, contract_summary
from aimilivpn.web.log_routes import handle_logs_get
from aimilivpn.web.node_routes import handle_node_get
from aimilivpn.web.region_quality_routes import handle_region_quality_get
from aimilivpn.web.route_contexts import ApiGetRouteContext
from aimilivpn.web.status_routes import handle_status_get


def handle_api_get(handler: Any, effective_path: str, context: ApiGetRouteContext) -> bool:
    effective_path = canonical_route("GET", effective_path)
    if effective_path == "/api/v1":
        handler.send_json({"ok": True, **contract_summary()})
        return True
    if effective_path == "/api/v1/settings":
        config = context.node.load_ui_config()
        safe_fields = {
            key: config.get(key)
            for key in ("host", "port", "proxy_port", "routing_mode", "force_country", "routing_ip_type", "fav_fail_fallback")
            if key in config
        }
        handler.send_json({"ok": True, "settings": safe_fields})
        return True
    if handle_region_quality_get(handler, effective_path, context.region_quality):
        return True
    if handle_node_get(handler, effective_path, context.node):
        return True
    if effective_path.startswith("/configs/"):
        handler.send_json({"ok": False, "error": "raw OpenVPN configs are not exposed", "error_code": "sensitive_resource"}, HTTPStatus.FORBIDDEN)
        return True
    if handle_status_get(handler, effective_path, context.status):
        return True
    if handle_logs_get(handler, effective_path, context.logs):
        return True
    return False
