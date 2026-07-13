from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aimilivpn.web.api_contract import canonical_route
from aimilivpn.web.api_errors import send_not_found, send_unauthorized
from aimilivpn.web.auth_routes import handle_auth_post
from aimilivpn.web.config_routes import handle_config_post
from aimilivpn.web.node_routes import handle_node_post
from aimilivpn.web.proxy_routes import handle_proxy_post
from aimilivpn.web.region_quality_routes import handle_region_quality_post
from aimilivpn.web.route_contexts import ApiPostRouteContext


def handle_api_post(handler: Any, effective_path: str, context: ApiPostRouteContext) -> bool:
    effective_path = canonical_route("POST", effective_path)
    if handle_auth_post(handler, effective_path, context.auth):
        return True

    if not context.is_authorized():
        send_unauthorized(handler)
        return True

    if handle_region_quality_post(handler, effective_path, context.region_quality):
        return True
    if handle_node_post(handler, effective_path, context.node):
        return True
    if handle_config_post(handler, effective_path, context.config):
        return True
    if handle_proxy_post(handler, effective_path, context.proxy):
        return True

    send_not_found(handler)
    return True
