from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aimilivpn.web.log_routes import handle_logs_get
from aimilivpn.web.node_routes import handle_node_get
from aimilivpn.web.region_quality_routes import handle_region_quality_get
from aimilivpn.web.route_contexts import ApiGetRouteContext
from aimilivpn.web.status_routes import handle_status_get


def handle_api_get(handler: Any, effective_path: str, context: ApiGetRouteContext) -> bool:
    if handle_region_quality_get(handler, effective_path, context.region_quality):
        return True
    if handle_node_get(handler, effective_path, context.node):
        return True
    if effective_path.startswith("/configs/"):
        handler.send_json({"error": "raw OpenVPN configs are not exposed"}, HTTPStatus.FORBIDDEN)
        return True
    if handle_status_get(handler, effective_path, context.status):
        return True
    if handle_logs_get(handler, effective_path, context.logs):
        return True
    return False
