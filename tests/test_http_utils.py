from __future__ import annotations

import io
import json
from http import HTTPStatus
import unittest

from aimilivpn.web.http_utils import HttpResponseMixin


class FakeHttpHandler(HttpResponseMixin):
    def __init__(self, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.response_status: HTTPStatus | None = None
        self.response_headers: list[tuple[str, str]] = []
        self.headers_ended = False

    def send_response(self, status: HTTPStatus) -> None:
        self.response_status = status

    def send_header(self, name: str, value: str) -> None:
        self.response_headers.append((name, value))

    def end_headers(self) -> None:
        self.headers_ended = True


class HttpResponseMixinTests(unittest.TestCase):
    def test_send_json_writes_utf8_body_and_no_store_headers(self) -> None:
        handler = FakeHttpHandler()

        handler.send_json({"message": "hello"}, HTTPStatus.CREATED)

        body = handler.wfile.getvalue()
        self.assertEqual(handler.response_status, HTTPStatus.CREATED)
        self.assertTrue(handler.headers_ended)
        self.assertIn(("Content-Type", "application/json; charset=utf-8"), handler.response_headers)
        self.assertIn(("Content-Length", str(len(body))), handler.response_headers)
        self.assertIn(("Cache-Control", "no-store"), handler.response_headers)
        self.assertEqual(json.loads(body.decode("utf-8")), {"message": "hello"})

    def test_read_request_body_uses_content_length(self) -> None:
        handler = FakeHttpHandler(b"abcdef", {"Content-Length": "4"})

        self.assertEqual(handler.read_request_body(), b"abcd")

    def test_read_request_body_rejects_invalid_length(self) -> None:
        handler = FakeHttpHandler(headers={"Content-Length": "abc"})

        with self.assertRaises(ValueError):
            handler.read_request_body()

    def test_read_request_body_rejects_oversized_body(self) -> None:
        handler = FakeHttpHandler(b"abcde", {"Content-Length": "5"})

        with self.assertRaises(ValueError):
            handler.read_request_body(max_bytes=4)

    def test_read_json_body_rejects_non_object_json(self) -> None:
        handler = FakeHttpHandler(b"[1, 2]", {"Content-Length": "6"})

        with self.assertRaises(ValueError):
            handler.read_json_body()


if __name__ == "__main__":
    unittest.main()
