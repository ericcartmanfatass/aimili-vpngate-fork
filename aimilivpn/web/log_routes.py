from __future__ import annotations

from typing import Any

from aimilivpn.web.route_contexts import LogsRouteContext

def handle_logs_get(handler: Any, effective_path: str, context: LogsRouteContext) -> bool:
    if effective_path != "/api/logs":
        return False
    handler.send_json({"logs": context.read_log_entries()})
    return True
