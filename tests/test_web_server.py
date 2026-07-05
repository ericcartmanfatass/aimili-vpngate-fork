from __future__ import annotations

from http import HTTPStatus
from types import SimpleNamespace
import unittest

from aimilivpn.web.server import WebRequestHandler, WebServerRuntime


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


if __name__ == "__main__":
    unittest.main()
