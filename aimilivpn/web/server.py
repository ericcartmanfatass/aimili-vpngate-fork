from __future__ import annotations

import socket
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, MutableMapping, cast

from aimilivpn.web.context_factory import WebRouteContextFactory
from aimilivpn.web.http_utils import HttpResponseMixin
from aimilivpn.web.routes import (
    handle_api_delete,
    handle_api_get,
    handle_api_post,
    handle_api_put,
    handle_page_get,
    is_session_authorized,
    resolve_secret_path_request,
)


@dataclass(frozen=True)
class WebServerRuntime:
    load_ui_config: Callable[[], dict[str, Any]]
    route_context_factory: Callable[[], WebRouteContextFactory]
    active_sessions: MutableMapping[str, float]
    session_lock: Any
    console_token: Callable[[], str]
    default_secret_path: str = "EJsW2EeBo9lY"


class DualStackHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        runtime: WebServerRuntime,
        bind_and_activate: bool = True,
    ) -> None:
        host, port = server_address
        self.runtime = runtime
        if ":" in host or host == "":
            self.address_family = socket.AF_INET6
        else:
            self.address_family = socket.AF_INET

        try:
            super().__init__(server_address, request_handler_class, bind_and_activate)
        except OSError as exc:
            if self.address_family != socket.AF_INET6:
                raise
            fallback_host = "0.0.0.0" if host in ("::", "") else "127.0.0.1"
            print(
                f"[警告] 绑定 Web 管理后台 IPv6 {host}:{port} 失败 ({exc})，正在尝试回退至 IPv4 {fallback_host} ...",
                flush=True,
            )
            try:
                self.socket.close()
            except Exception:
                pass
            self.address_family = socket.AF_INET
            super().__init__((fallback_host, port), request_handler_class, bind_and_activate)

    def server_bind(self) -> None:
        if self.address_family == socket.AF_INET6:
            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                pass
        super().server_bind()


class WebRequestHandler(HttpResponseMixin, BaseHTTPRequestHandler):
    @property
    def runtime(self) -> WebServerRuntime:
        return cast(WebServerRuntime, self.server.runtime)  # type: ignore[attr-defined]

    def has_console_token(self) -> bool:
        expected = self.runtime.console_token()
        provided = self.headers.get("X-Aimili-Console-Token", "")
        return bool(expected) and provided == expected

    def get_secret_path(self) -> str:
        ui_cfg = self.runtime.load_ui_config()
        return ui_cfg.get("secret_path", self.runtime.default_secret_path)

    def is_authorized(self) -> bool:
        cookie_header = self.headers.get("Cookie", "")
        with self.runtime.session_lock:
            return is_session_authorized(
                cookie_header,
                self.runtime.active_sessions,
                self.runtime.route_context_factory().now(),
                trusted=self.has_console_token(),
            )

    def validate_path(self) -> str:
        request_path = urllib.parse.urlsplit(self.path).path
        result = resolve_secret_path_request(
            request_path,
            self.get_secret_path(),
            trusted=self.has_console_token(),
        )
        if result.effective_path:
            return result.effective_path
        if result.redirect_location:
            self.send_response(result.status or HTTPStatus.FOUND)
            self.send_header("Location", result.redirect_location)
            self.end_headers()
            return ""
        self.send_response(result.status or HTTPStatus.NOT_FOUND)
        self.end_headers()
        return ""

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}", flush=True)

    def do_GET(self) -> None:
        effective_path = self.validate_path()
        if effective_path == "":
            return

        route_contexts = self.runtime.route_context_factory()
        if handle_page_get(self, effective_path, route_contexts.page(self.is_authorized)):
            return
        if handle_api_get(self, effective_path, route_contexts.api_get()):
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        effective_path = self.validate_path()
        if effective_path == "":
            return
        handle_api_post(
            self,
            effective_path,
            self.runtime.route_context_factory().api_post(self.get_secret_path, self.is_authorized),
        )

    def do_PUT(self) -> None:
        effective_path = self.validate_path()
        if effective_path == "":
            return
        handle_api_put(
            self,
            effective_path,
            self.runtime.route_context_factory().api_mutation(self.is_authorized),
        )

    def do_DELETE(self) -> None:
        effective_path = self.validate_path()
        if effective_path == "":
            return
        handle_api_delete(
            self,
            effective_path,
            self.runtime.route_context_factory().api_mutation(self.is_authorized),
        )


def serve_web_forever(host: str, port: int, runtime: WebServerRuntime) -> None:
    DualStackHTTPServer((host, port), WebRequestHandler, runtime).serve_forever()
