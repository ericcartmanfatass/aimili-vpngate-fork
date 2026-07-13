from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any


class InvalidRequestBody(ValueError):
    """The request body framing or payload is malformed."""


class RequestBodyTooLarge(InvalidRequestBody):
    """The declared request body exceeds the configured limit."""


class HttpResponseMixin:
    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def read_request_body(self, max_bytes: int = 65536) -> bytes:
        length = _parse_content_length(self.headers.get("Content-Length"))
        if length < 0:
            raise InvalidRequestBody("invalid Content-Length")
        if length > max_bytes:
            raise RequestBodyTooLarge(f"request body exceeds {max_bytes} bytes")
        body = self.rfile.read(length) if length > 0 else b""
        if len(body) != length:
            raise InvalidRequestBody("incomplete request body")
        return body

    def read_json_body(self, max_bytes: int = 65536) -> dict[str, Any]:
        body = self.read_request_body(max_bytes)
        if not body:
            return {}
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, dict):
            raise InvalidRequestBody("request JSON must be an object")
        return data


def _parse_content_length(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return -1
