from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aimilivpn.web.api_contract import canonical_route
from aimilivpn.web.api_errors import send_not_found, send_unauthorized
from aimilivpn.web.config_routes import handle_config_post
from aimilivpn.web.region_quality_routes import handle_region_delete, handle_region_put
from aimilivpn.web.route_contexts import ApiMutationRouteContext


def handle_api_put(handler: Any, effective_path: str, context: ApiMutationRouteContext) -> bool:
    effective_path = canonical_route("PUT", effective_path)
    if not context.is_authorized():
        send_unauthorized(handler)
        return True

    if handle_region_put(handler, effective_path, context.region_quality):
        return True
    if context.config is not None and handle_config_post(handler, effective_path, context.config):
        return True

    send_not_found(handler)
    return True


def handle_api_delete(handler: Any, effective_path: str, context: ApiMutationRouteContext) -> bool:
    effective_path = canonical_route("DELETE", effective_path)
    if not context.is_authorized():
        send_unauthorized(handler)
        return True

    if handle_region_delete(handler, effective_path, context.region_quality):
        return True

    send_not_found(handler)
    return True
