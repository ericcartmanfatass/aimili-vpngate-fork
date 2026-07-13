from __future__ import annotations

from http import HTTPStatus
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from io import StringIO
from contextlib import redirect_stdout

from aimilivpn.web.server import DualStackHTTPServer, WebRequestHandler, WebServerRuntime


class FakeLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def build_runtime(
    sessions: dict[str, float] | None = None,
    secret_path: str = "secret",
    console_token: str = "",
) -> WebServerRuntime:
    return WebServerRuntime(
        load_ui_config=lambda: {"secret_path": secret_path},
        route_context_factory=lambda: SimpleNamespace(now=lambda: 100.0),  # type: ignore[return-value]
        active_sessions=sessions or {},
        session_lock=FakeLock(),
        console_token=lambda: console_token,
    )


def build_handler(runtime: WebServerRuntime, headers: dict[str, str] | None = None) -> WebRequestHandler:
    handler = object.__new__(WebRequestHandler)
    handler.server = SimpleNamespace(runtime=runtime)  # type: ignore[assignment]
    handler.headers = headers or {}
    handler.path = "/"
    handler.client_address = ("127.0.0.1", 43123)
    handler.response_status = None
    handler.response_headers = []

    def send_response(status: HTTPStatus) -> None:
        handler.response_status = status

    def send_header(name: str, value: str) -> None:
        handler.response_headers.append((name, value))

    def end_headers() -> None:
        handler.headers_ended = True

    handler.send_response = send_response  # type: ignore[method-assign]
    handler.send_header = send_header  # type: ignore[method-assign]
    handler.end_headers = end_headers  # type: ignore[method-assign]
    return handler


class WebRequestHandlerTests(unittest.TestCase):
    def test_ipv6_wildcard_bind_failure_falls_back_to_ipv4_loopback(self) -> None:
        runtime = build_runtime()
        server = object.__new__(DualStackHTTPServer)

        with patch.object(ThreadingHTTPServer, "__init__", side_effect=[OSError("no ipv6"), None]) as init:
            DualStackHTTPServer.__init__(server, ("::", 8787), WebRequestHandler, runtime)

        self.assertEqual(init.call_args_list[1].args[0], ("127.0.0.1", 8787))

    def test_forwarded_https_requires_explicit_proxy_trust(self) -> None:
        handler = build_handler(build_runtime(), {"X-Forwarded-Proto": "https"})

        self.assertFalse(handler.is_secure_request())

        trusted_runtime = build_runtime()
        trusted_runtime = WebServerRuntime(
            **{**trusted_runtime.__dict__, "trust_proxy_headers": True, "trusted_proxy_addresses": ("127.0.0.1",)}
        )
        trusted_handler = build_handler(trusted_runtime, {"X-Forwarded-Proto": "https"})
        self.assertTrue(trusted_handler.is_secure_request())

    def test_console_token_authorizes_request(self) -> None:
        handler = build_handler(
            build_runtime(console_token="token-1"),
            {"X-Aimili-Console-Token": "token-1"},
        )

        self.assertTrue(handler.has_console_token())
        self.assertTrue(handler.is_authorized())

    def test_session_cookie_authorizes_request(self) -> None:
        handler = build_handler(
            build_runtime(sessions={"session-1": 110.0}),
            {"Cookie": "session=session-1"},
        )

        self.assertTrue(handler.is_authorized())

    def test_validate_path_redirects_secret_root(self) -> None:
        handler = build_handler(build_runtime(secret_path="secret"))
        handler.path = "/secret"

        effective_path = handler.validate_path()

        self.assertEqual(effective_path, "")
        self.assertEqual(handler.response_status, HTTPStatus.FOUND)
        self.assertIn(("Location", "/secret/"), handler.response_headers)

    def test_access_log_redacts_secret_path(self) -> None:
        handler = build_handler(build_runtime(secret_path="private123"))
        handler.log_date_time_string = lambda: "now"  # type: ignore[method-assign]

        with redirect_stdout(StringIO()) as output:
            handler.log_message('"GET /private123/api/status HTTP/1.1" %s', "200")

        self.assertNotIn("private123", output.getvalue())
        self.assertIn("/<secret-path>/api/status", output.getvalue())

    def test_dispatch_maps_unexpected_exception_without_echoing_details(self) -> None:
        handler = build_handler(build_runtime())
        responses: list[tuple[dict[str, object], HTTPStatus]] = []
        handler.send_json = lambda payload, status: responses.append((payload, status))  # type: ignore[method-assign]

        handler.dispatch_safely(
            lambda: (_ for _ in ()).throw(RuntimeError("private filesystem and password detail"))
        )

        payload, status = responses[-1]
        self.assertEqual(status, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertEqual(payload["error_code"], "internal_error")
        self.assertNotIn("private filesystem", str(payload))

    def test_api_get_requires_authorization(self) -> None:
        handler = build_handler(build_runtime())
        handler.validate_path = lambda: "/api/v1/nodes"  # type: ignore[method-assign]
        responses: list[tuple[dict[str, object], HTTPStatus]] = []
        handler.send_json = lambda payload, status: responses.append((payload, status))  # type: ignore[method-assign]

        handler._do_get()

        payload, status = responses[-1]
        self.assertEqual(status, HTTPStatus.UNAUTHORIZED)
        self.assertEqual(payload["error_code"], "unauthorized")

    def test_all_mutations_reject_oversized_body_before_routing(self) -> None:
        handler = build_handler(build_runtime(), {"Content-Length": "262145"})
        responses: list[tuple[dict[str, object], HTTPStatus]] = []
        handler.send_json = lambda payload, status: responses.append((payload, status))  # type: ignore[method-assign]

        handler.dispatch_safely(handler._do_post)

        payload, status = responses[-1]
        self.assertEqual(status, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(payload["error_code"], "request_too_large")

    def test_mutation_emits_payload_free_audit_record(self) -> None:
        base = build_runtime(sessions={"session-1": 110.0})
        route_context = SimpleNamespace(now=lambda: 100.0, api_post=lambda *args: object())
        runtime = WebServerRuntime(**{**base.__dict__, "route_context_factory": lambda: route_context})
        handler = build_handler(runtime, {"Cookie": "session=session-1", "Content-Length": "0"})
        handler.validate_path = lambda: "/api/connect"  # type: ignore[method-assign]

        with patch("aimilivpn.web.server.handle_api_post"), redirect_stdout(StringIO()) as output:
            handler._do_post()

        audit = output.getvalue()
        self.assertIn("mutation method=POST path=/api/connect", audit)
        self.assertNotIn("password", audit)


if __name__ == "__main__":
    unittest.main()
