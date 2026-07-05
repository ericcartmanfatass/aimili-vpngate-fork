from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aimilivpn.web.route_contexts import ProxyRouteContext

def handle_proxy_post(handler: Any, effective_path: str, context: ProxyRouteContext) -> bool:
    if effective_path != "/api/test_proxy":
        return False

    try:
        handler.read_request_body()
        result = context.check_proxy_health()
        if result["ok"]:
            context.set_state(
                proxy_ok=True,
                proxy_ip=result["ip"],
                proxy_latency_ms=result["latency_ms"],
                proxy_error="",
            )
        else:
            context.set_state(
                proxy_ok=False,
                proxy_ip="-",
                proxy_latency_ms=0,
                proxy_error=result.get("error", "未知错误"),
            )
        handler.send_json(result)
    except Exception as exc:
        handler.send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
    return True
