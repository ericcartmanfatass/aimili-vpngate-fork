from __future__ import annotations

import unittest
from http import HTTPStatus

from aimilivpn.web.api_errors import send_api_error


class FakeHandler:
    def __init__(self) -> None:
        self.responses: list[tuple[dict[str, object], HTTPStatus]] = []

    def send_json(self, payload: dict[str, object], status: HTTPStatus) -> None:
        self.responses.append((payload, status))


class ApiErrorTests(unittest.TestCase):
    def test_internal_exception_is_mapped_to_stable_safe_error(self) -> None:
        handler = FakeHandler()

        send_api_error(
            handler,
            "node_operation_failed",
            exc=RuntimeError("database password and private path"),
            operation="node test",
        )

        payload, status = handler.responses[-1]
        self.assertEqual(status, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertEqual(payload["error_code"], "node_operation_failed")
        self.assertEqual(payload["error"], "node operation failed")
        self.assertNotIn("database password", str(payload))


if __name__ == "__main__":
    unittest.main()
