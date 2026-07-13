from __future__ import annotations

import io
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from types import MethodType
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout
from io import StringIO

from aimilivpn.system import console_routes
from aimilivpn.web.http_utils import InvalidRequestBody, RequestBodyTooLarge


def build_login_handler(*, secure: bool) -> console_routes.Handler:
    handler = object.__new__(console_routes.Handler)
    handler.wfile = io.BytesIO()
    handler.response_status = None
    handler.response_headers = []
    handler.headers = {}
    handler.effective_path = MethodType(lambda self: "/api/login", handler)  # type: ignore[method-assign]
    handler.body_json = MethodType(  # type: ignore[method-assign]
        lambda self: {"username": "admin", "password": "correct"},
        handler,
    )
    handler.secret_path = MethodType(lambda self: "console-secret", handler)  # type: ignore[method-assign]
    handler.is_secure_request = MethodType(lambda self: secure, handler)  # type: ignore[attr-defined]
    handler.send_response = MethodType(  # type: ignore[method-assign]
        lambda self, status: setattr(self, "response_status", status),
        handler,
    )
    handler.send_header = MethodType(  # type: ignore[method-assign]
        lambda self, name, value: self.response_headers.append((name, value)),
        handler,
    )
    handler.end_headers = MethodType(lambda self: None, handler)  # type: ignore[method-assign]
    return handler


class ConsoleRouteSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        console_routes.reset_runtime_security_state()

    def tearDown(self) -> None:
        console_routes.reset_runtime_security_state()

    def test_trusted_https_login_sets_secure_cookie(self) -> None:
        handler = build_login_handler(secure=True)
        auth = {"username": "admin", "password_hash": "hash", "secret_path": "console-secret"}

        with (
            patch.object(console_routes, "load_console_auth", return_value=auth),
            patch.object(console_routes, "verify_username", return_value=True),
            patch.object(console_routes, "verify_password", return_value=True),
            patch.object(console_routes, "generate_session_token", return_value="token-1"),
        ):
            handler.do_POST()

        self.assertEqual(handler.response_status, HTTPStatus.OK)
        cookies = [value for name, value in handler.response_headers if name == "Set-Cookie"]
        self.assertEqual(len(cookies), 1)
        self.assertIn("console_session=token-1", cookies[0])
        self.assertIn("Secure", cookies[0])
        self.assertIn("HttpOnly", cookies[0])
        self.assertIn("SameSite=Lax", cookies[0])

    def test_access_log_redacts_console_secret_path(self) -> None:
        handler = object.__new__(console_routes.Handler)
        handler.secret_path = MethodType(lambda self: "console-private", handler)  # type: ignore[method-assign]

        with redirect_stdout(StringIO()) as output:
            handler.log_message('"GET /console-private/api/instances HTTP/1.1" %s', "200")

        self.assertNotIn("console-private", output.getvalue())
        self.assertIn("/<secret-path>/api/instances", output.getvalue())

    def test_invalid_and_oversized_bodies_map_to_400_and_413(self) -> None:
        for error, expected in (
            (InvalidRequestBody("bad framing"), HTTPStatus.BAD_REQUEST),
            (RequestBodyTooLarge("private oversized detail"), HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
        ):
            with self.subTest(expected=expected):
                handler = build_login_handler(secure=False)
                handler.body_json = MethodType(lambda self, err=error: (_ for _ in ()).throw(err), handler)  # type: ignore[method-assign]
                handler.do_POST()
                self.assertEqual(handler.response_status, expected)
                self.assertNotIn(str(error).encode(), handler.wfile.getvalue())

    def test_handler_setup_applies_request_timeout(self) -> None:
        handler = object.__new__(console_routes.Handler)
        handler.connection = Mock()

        with patch.object(BaseHTTPRequestHandler, "setup"):
            handler.setup()

        handler.connection.settimeout.assert_called_once_with(console_routes.REQUEST_TIMEOUT_SECONDS)

    def test_login_verification_exception_uses_generic_failure(self) -> None:
        handler = build_login_handler(secure=False)
        auth = {"username": "admin", "password_hash": "hash", "secret_path": "console-secret"}

        with (
            patch.object(console_routes, "load_console_auth", return_value=auth),
            patch.object(console_routes, "verify_username", side_effect=RuntimeError("sensitive detail")),
        ):
            handler.do_POST()

        self.assertEqual(handler.response_status, HTTPStatus.FORBIDDEN)
        self.assertNotIn(b"sensitive detail", handler.wfile.getvalue())
        self.assertIn(b"login failed", handler.wfile.getvalue())

    def test_rate_limited_login_uses_generic_failure(self) -> None:
        handler = build_login_handler(secure=False)
        with patch.object(console_routes.login_limiter, "allow", return_value=False):
            handler.do_POST()

        self.assertEqual(handler.response_status, HTTPStatus.TOO_MANY_REQUESTS)
        self.assertIn(b"login failed", handler.wfile.getvalue())

    def test_logout_removes_server_side_session(self) -> None:
        handler = build_login_handler(secure=False)
        handler.effective_path = MethodType(lambda self: "/api/logout", handler)  # type: ignore[method-assign]
        handler.headers = {"Cookie": "console_session=token-1"}
        console_routes.sessions["token-1"] = 9999999999.0

        handler.do_POST()

        self.assertNotIn("token-1", console_routes.sessions)

    def test_expired_sessions_are_removed(self) -> None:
        console_routes.sessions.update({"old": 99.0, "valid": 101.0})

        console_routes.cleanup_expired_sessions(now=100.0)

        self.assertEqual(console_routes.sessions, {"valid": 101.0})

    def test_auth_configuration_change_revokes_sessions(self) -> None:
        console_routes.sync_auth_session_state({"username": "admin", "password_hash": "one"})
        console_routes.sessions["token-1"] = 9999999999.0

        console_routes.sync_auth_session_state({"username": "admin", "password_hash": "two"})

        self.assertEqual(console_routes.sessions, {})


if __name__ == "__main__":
    unittest.main()
