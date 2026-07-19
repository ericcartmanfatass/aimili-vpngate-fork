from __future__ import annotations

from typing import Any

from aimilivpn.web.api_contract import InvalidListQuery, parse_list_query
from aimilivpn.web.api_errors import send_client_error
from aimilivpn.web.route_contexts import LogsRouteContext

def handle_logs_get(handler: Any, effective_path: str, context: LogsRouteContext) -> bool:
    if effective_path != "/api/logs":
        return False
    try:
        query = parse_list_query(
            handler,
            allowed_filters=("level", "module"),
            allowed_sort=("timestamp", "level", "module"),
            default_sort="timestamp",
            default_order="desc",
            default_limit=200,
        )
    except InvalidListQuery:
        send_client_error(handler, "invalid_query", "日志列表查询参数无效。")
        return True
    logs = context.read_log_entries()
    for field in ("level", "module"):
        expected = query.filters.get(field, "")
        if expected:
            logs = [entry for entry in logs if str(entry.get(field) or "") == expected]
    logs.sort(key=lambda entry: str(entry.get(query.sort) or ""), reverse=query.order == "desc")
    page, pagination = query.page(logs)
    handler.send_json({"logs": page, "pagination": pagination})
    return True
