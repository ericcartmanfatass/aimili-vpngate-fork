from __future__ import annotations

import io
from http import HTTPStatus
from types import MethodType
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

from aimilivpn.system import console_routes


def build_login_handler(*, secure: bool) -> console_routes.Handler:
    handler = object.__new__(console_routes.Handler)
    handler.wfile = io.BytesIO()
    handler.response_status = None
    handler.response_headers = []
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
        console_routes.sessions.clear()

    def tearDown(self) -> None:
        console_routes.sessions.clear()

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


if __name__ == "__main__":
    unittest.main()
