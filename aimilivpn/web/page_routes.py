from __future__ import annotations

import urllib.parse
from http import HTTPStatus
from typing import Any

from aimilivpn.web.route_contexts import PageRouteContext
from aimilivpn.web.static_assets import get_static_asset, guess_content_type
from aimilivpn.web.templates import get_index_html, get_login_html


def handle_page_get(handler: Any, effective_path: str, context: PageRouteContext) -> bool:
    if not context.is_authorized():
        if effective_path in ("/", "/index.html"):
            handler.send_bytes(
                get_login_html(context.login_html_fallback).encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return True
        handler.send_json({"error": "未授权"}, HTTPStatus.UNAUTHORIZED)
        return True

    if effective_path in ("/", "/index.html"):
        handler.send_bytes(
            get_index_html(context.index_html_fallback).encode("utf-8"),
            "text/html; charset=utf-8",
        )
        return True

    if effective_path.startswith("/static/"):
        asset_path = urllib.parse.unquote(effective_path.removeprefix("/static/"))
        try:
            asset = get_static_asset(asset_path)
        except ValueError:
            handler.send_json({"error": "静态资源路径无效"}, HTTPStatus.BAD_REQUEST)
            return True
        if asset is None:
            handler.send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
            return True
        handler.send_bytes(asset, guess_content_type(asset_path))
        return True

    return False
