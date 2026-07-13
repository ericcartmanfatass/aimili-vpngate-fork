from __future__ import annotations

from aimilivpn.web.auth_routes import (
    AccessPathResult,
    handle_auth_post,
    is_session_authorized,
    parse_cookie_header,
    redact_secret_path,
    resolve_secret_path_request,
)
from aimilivpn.web.config_routes import handle_config_post
from aimilivpn.web.get_routes import handle_api_get
from aimilivpn.web.log_routes import handle_logs_get
from aimilivpn.web.mutation_routes import handle_api_delete, handle_api_put
from aimilivpn.web.node_routes import handle_node_get, handle_node_post
from aimilivpn.web.page_routes import handle_page_get
from aimilivpn.web.post_routes import handle_api_post
from aimilivpn.web.proxy_routes import handle_proxy_post
from aimilivpn.web.region_quality_routes import (
    handle_region_delete,
    handle_region_put,
    handle_region_quality_get,
    handle_region_quality_post,
)
from aimilivpn.web.route_contexts import (
    AuthRouteContext,
    ApiGetRouteContext,
    ApiMutationRouteContext,
    ApiPostRouteContext,
    ConfigRouteContext,
    LogsRouteContext,
    NodeRouteContext,
    PageRouteContext,
    ProxyRouteContext,
    RegionQualityRouteContext,
    StatusRouteContext,
)
from aimilivpn.web.status_routes import handle_status_get

__all__ = [
    "AuthRouteContext",
    "AccessPathResult",
    "ApiGetRouteContext",
    "ApiMutationRouteContext",
    "ApiPostRouteContext",
    "ConfigRouteContext",
    "LogsRouteContext",
    "NodeRouteContext",
    "PageRouteContext",
    "ProxyRouteContext",
    "RegionQualityRouteContext",
    "StatusRouteContext",
    "handle_auth_post",
    "handle_api_get",
    "handle_api_delete",
    "handle_api_post",
    "handle_api_put",
    "handle_config_post",
    "handle_logs_get",
    "handle_node_get",
    "handle_node_post",
    "handle_page_get",
    "handle_proxy_post",
    "handle_region_delete",
    "handle_region_put",
    "handle_region_quality_get",
    "handle_region_quality_post",
    "handle_status_get",
    "is_session_authorized",
    "parse_cookie_header",
    "redact_secret_path",
    "resolve_secret_path_request",
]
