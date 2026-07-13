from __future__ import annotations

import json
import socket
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, MutableMapping, cast

from aimilivpn.web.context_factory import WebRouteContextFactory
from aimilivpn.web.api_errors import send_api_error, send_not_found, send_unauthorized
from aimilivpn.web.http_utils import HttpResponseMixin, InvalidRequestBody, RequestBodyTooLarge
from aimilivpn.web.proxy_trust import (
    DEFAULT_TRUSTED_PROXY_ADDRESSES,
    management_http_notice,
    request_uses_trusted_https,
)
from aimilivpn.web.routes import (
    handle_api_delete,
    handle_api_get,
    handle_api_post,
    handle_api_put,
    handle_page_get,
    is_session_authorized,
    redact_secret_path,
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
    trust_proxy_headers: bool = False
    trusted_proxy_addresses: tuple[str, ...] = DEFAULT_TRUSTED_PROXY_ADDRESSES


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
            fallback_host = "127.0.0.1"
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

    def is_secure_request(self) -> bool:
        return request_uses_trusted_https(
            self,
            trust_proxy_headers=self.runtime.trust_proxy_headers,
            trusted_proxy_addresses=self.runtime.trusted_proxy_addresses,
        )

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
        message = redact_secret_path(format % args, self.get_secret_path())
        print(f"[{self.log_date_time_string()}] {message}", flush=True)

    def dispatch_safely(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except RequestBodyTooLarge:
            self.send_json(
                {"ok": False, "error": "request body too large", "error_code": "request_too_large"},
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
        except (InvalidRequestBody, json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(
                {"ok": False, "error": "invalid request body", "error_code": "invalid_request"},
                HTTPStatus.BAD_REQUEST,
            )
        except OSError as exc:
            print(f"[web audit] response transport failed: {type(exc).__name__}", flush=True)
        except Exception as exc:
            send_api_error(self, "internal_error", exc=exc, operation="request dispatch")

    def do_GET(self) -> None:
        self.dispatch_safely(self._do_get)

    def _do_get(self) -> None:
        effective_path = self.validate_path()
        if effective_path == "":
            return
        if effective_path.startswith("/api/") and not self.is_authorized():
            send_unauthorized(self)
            return

        route_contexts = self.runtime.route_context_factory()
        if handle_page_get(self, effective_path, route_contexts.page(self.is_authorized)):
            return
        if handle_api_get(self, effective_path, route_contexts.api_get()):
            return
        send_not_found(self)

    def do_POST(self) -> None:
        self.dispatch_safely(self._do_post)

    def _do_post(self) -> None:
        self.validate_request_size()
        effective_path = self.validate_path()
        if effective_path == "":
            return
        self._audit_write("POST", effective_path)
        handle_api_post(
            self,
            effective_path,
            self.runtime.route_context_factory().api_post(self.get_secret_path, self.is_authorized),
        )

    def do_PUT(self) -> None:
        self.dispatch_safely(self._do_put)

    def _do_put(self) -> None:
        self.validate_request_size()
        effective_path = self.validate_path()
        if effective_path == "":
            return
        self._audit_write("PUT", effective_path)
        handle_api_put(
            self,
            effective_path,
            self.runtime.route_context_factory().api_mutation(self.is_authorized),
        )

    def do_DELETE(self) -> None:
        self.dispatch_safely(self._do_delete)

    def _do_delete(self) -> None:
        self.validate_request_size()
        effective_path = self.validate_path()
        if effective_path == "":
            return
        self._audit_write("DELETE", effective_path)
        handle_api_delete(
            self,
            effective_path,
            self.runtime.route_context_factory().api_mutation(self.is_authorized),
        )

    def _audit_write(self, method: str, effective_path: str) -> None:
        client = self.client_address[0] if getattr(self, "client_address", None) else "unknown"
        print(f"[web audit] mutation method={method} path={effective_path} client={client}", flush=True)


def serve_web_forever(host: str, port: int, runtime: WebServerRuntime) -> None:
    print(
        management_http_notice(
            "Web UI",
            host,
            port,
            trust_proxy_headers=runtime.trust_proxy_headers,
        ),
        flush=True,
    )
    DualStackHTTPServer((host, port), WebRequestHandler, runtime).serve_forever()
