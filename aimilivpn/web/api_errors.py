from __future__ import annotations

from http import HTTPStatus
from typing import Any


SAFE_ERROR_MESSAGES = {
    "internal_error": "请求失败",
    "maintenance_failed": "节点维护操作失败",
    "node_operation_failed": "节点操作失败",
    "configuration_failed": "配置更新失败",
    "proxy_check_failed": "代理检测失败",
    "region_operation_failed": "地区操作失败",
    "quality_provider_failed": "质量服务暂不可用",
    "authentication_failed": "登录失败",
    "logout_failed": "退出失败",
    "unauthorized": "未授权",
    "not_found": "未找到",
    "invalid_query": "查询参数无效",
    "invalid_node_ids": "节点标识无效",
    "invalid_node_request": "节点请求无效",
    "invalid_idempotency_key": "幂等键无效",
    "operation_capacity": "操作队列已满",
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
