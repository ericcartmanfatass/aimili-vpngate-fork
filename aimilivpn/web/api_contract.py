from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any, Iterable


API_VERSION = "v1"
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500
API_RESOURCE_PATHS = (
    "/api/v1/status",
    "/api/v1/nodes",
    "/api/v1/regions",
    "/api/v1/quality-results",
    "/api/v1/quality-providers",
    "/api/v1/settings",
    "/api/v1/logs",
    "/api/v1/operations",
)


def contract_summary() -> dict[str, Any]:
    return {
        "api_version": API_VERSION,
        "resources": list(API_RESOURCE_PATHS),
        "pagination": {"default_limit": DEFAULT_PAGE_LIMIT, "max_limit": MAX_PAGE_LIMIT},
        "idempotency_header": "X-Idempotency-Key",
        "error_fields": ["ok", "error", "error_code"],
    }


class InvalidListQuery(ValueError):
    pass


@dataclass(frozen=True)
class ListQuery:
    limit: int
    offset: int
    sort: str
    order: str
    filters: dict[str, str]

    def page(self, items: list[Any]) -> tuple[list[Any], dict[str, int]]:
        total = len(items)
        page = items[self.offset:self.offset + self.limit]
        return page, {"limit": self.limit, "offset": self.offset, "returned": len(page), "total": total}


_ALIASES = {
    ("GET", "/api/v1/status"): "/api/gateway_status",
    ("GET", "/api/v1/nodes"): "/api/nodes",
    ("GET", "/api/v1/regions"): "/api/regions",
    ("GET", "/api/v1/quality-results"): "/api/quality",
    ("GET", "/api/v1/quality-providers"): "/api/quality/providers",
    ("GET", "/api/v1/logs"): "/api/logs",
    ("POST", "/api/v1/regions"): "/api/regions",
    ("POST", "/api/v1/quality-checks/nodes"): "/api/test_nodes",
    ("POST", "/api/v1/quality-checks/node"): "/api/quality/check-node",
    ("POST", "/api/v1/quality-checks/ip"): "/api/quality/check-ip",
    ("POST", "/api/v1/quality-checks/region"): "/api/quality/check-region",
    ("POST", "/api/v1/operations/refresh-nodes"): "/api/refresh_nodes",
    ("POST", "/api/v1/operations/check-nodes"): "/api/check",
    ("POST", "/api/v1/operations/connect"): "/api/connect",
    ("POST", "/api/v1/operations/disconnect"): "/api/disconnect",
    ("POST", "/api/v1/proxy-checks"): "/api/test_proxy",
    ("PUT", "/api/v1/settings"): "/api/update_settings",
    ("PUT", "/api/v1/settings/routing"): "/api/update_routing",
    ("PUT", "/api/v1/settings/credentials"): "/api/update_credentials",
}


def canonical_route(method: str, path: str) -> str:
    method = method.upper()
    direct = _ALIASES.get((method, path))
    if direct is not None:
        return direct
    prefix = "/api/v1/regions/"
    if path.startswith(prefix):
        suffix = path.removeprefix(prefix)
        if method in {"GET", "PUT", "DELETE"}:
            return f"/api/regions/{suffix}"
        if method == "POST" and suffix.endswith("/preview"):
            return f"/api/regions/{suffix}"
    return path


def parse_list_query(
    handler: Any,
    *,
    allowed_filters: Iterable[str] = (),
    allowed_sort: Iterable[str],
    default_sort: str,
    default_order: str = "asc",
    default_limit: int = DEFAULT_PAGE_LIMIT,
    max_limit: int = MAX_PAGE_LIMIT,
) -> ListQuery:
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query, keep_blank_values=True)
    allowed_filter_set = set(allowed_filters)
    allowed = {"limit", "offset", "sort", "order", *allowed_filter_set}
    unknown = set(query) - allowed
    if unknown:
        raise InvalidListQuery("unsupported query parameter")
    if any(len(values) != 1 for values in query.values()):
        raise InvalidListQuery("query parameters must not be repeated")
    limit = _bounded_int(query, "limit", default_limit, 1, max_limit)
    offset = _bounded_int(query, "offset", 0, 0, 1_000_000)
    sort = _value(query, "sort", default_sort)
    if sort not in set(allowed_sort):
        raise InvalidListQuery("unsupported sort field")
    order = _value(query, "order", default_order).lower()
    if order not in {"asc", "desc"}:
        raise InvalidListQuery("order must be asc or desc")
    filters = {key: _value(query, key, "").strip() for key in allowed_filter_set if key in query}
    return ListQuery(limit=limit, offset=offset, sort=sort, order=order, filters=filters)


def _bounded_int(query: dict[str, list[str]], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = _value(query, name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise InvalidListQuery(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise InvalidListQuery(f"{name} is out of range")
    return value


def _value(query: dict[str, list[str]], name: str, default: str) -> str:
    values = query.get(name)
    return str(values[0]) if values else default
