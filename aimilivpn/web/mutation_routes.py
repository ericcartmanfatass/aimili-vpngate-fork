from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aimilivpn.web.region_quality_routes import handle_region_delete, handle_region_put
from aimilivpn.web.route_contexts import ApiMutationRouteContext


def handle_api_put(handler: Any, effective_path: str, context: ApiMutationRouteContext) -> bool:
    if not context.is_authorized():
        handler.send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
        return True

    if handle_region_put(handler, effective_path, context.region_quality):
        return True

    handler.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
    return True


def handle_api_delete(handler: Any, effective_path: str, context: ApiMutationRouteContext) -> bool:
    if not context.is_authorized():
        handler.send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
        return True

    if handle_region_delete(handler, effective_path, context.region_quality):
        return True

    handler.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
    return True
