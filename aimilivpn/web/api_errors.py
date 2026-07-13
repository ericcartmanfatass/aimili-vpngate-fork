from __future__ import annotations

from http import HTTPStatus
from typing import Any


SAFE_ERROR_MESSAGES = {
    "internal_error": "request failed",
    "maintenance_failed": "maintenance operation failed",
    "node_operation_failed": "node operation failed",
    "configuration_failed": "configuration update failed",
    "proxy_check_failed": "proxy check failed",
    "region_operation_failed": "region operation failed",
    "quality_provider_failed": "quality provider unavailable",
    "authentication_failed": "login failed",
    "logout_failed": "logout failed",
    "unauthorized": "Unauthorized",
    "not_found": "not found",
    "invalid_query": "invalid query parameters",
    "invalid_node_ids": "invalid node identifiers",
    "invalid_node_request": "invalid node request",
    "invalid_idempotency_key": "invalid idempotency key",
    "operation_capacity": "operation capacity reached",
}

def send_api_error(
    handler: Any,
    code: str,
    status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR,
    *,
    exc: BaseException | None = None,
    operation: str = "request",
) -> None:
    if exc is not None:
        print(f"[web audit] {operation} failed: {type(exc).__name__}", flush=True)
    handler.send_json(
        {
            "ok": False,
            "error": SAFE_ERROR_MESSAGES.get(code, SAFE_ERROR_MESSAGES["internal_error"]),
            "error_code": code,
        },
        status,
    )


def send_client_error(
    handler: Any,
    code: str,
    message: str,
    status: HTTPStatus = HTTPStatus.BAD_REQUEST,
) -> None:
    handler.send_json({"ok": False, "error": message, "error_code": code}, status)


def send_unauthorized(handler: Any) -> None:
    handler.send_json(
        {"ok": False, "error": SAFE_ERROR_MESSAGES["unauthorized"], "error_code": "unauthorized"},
        HTTPStatus.UNAUTHORIZED,
    )


def send_not_found(handler: Any) -> None:
    handler.send_json(
        {"ok": False, "error": SAFE_ERROR_MESSAGES["not_found"], "error_code": "not_found"},
        HTTPStatus.NOT_FOUND,
    )
