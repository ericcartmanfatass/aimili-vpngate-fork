from __future__ import annotations

import unittest

from aimilivpn.web.operations import OperationCapacityError, OperationRegistry


class OperationRegistryTests(unittest.TestCase):
    def test_active_retry_reuses_operation_without_starting_duplicate(self) -> None:
        pending: list[object] = []
        calls: list[str] = []
        registry = OperationRegistry(clock=lambda: 100.0)

        first, first_duplicate = registry.submit(
            "connect",
            "implicit:connect:jp_1",
            lambda: calls.append("connected") or {"ok": True},
            start_thread=pending.append,
            reuse_completed=False,
        )
        second, second_duplicate = registry.submit(
            "connect",
            "implicit:connect:jp_1",
            lambda: calls.append("duplicate"),
            start_thread=pending.append,
            reuse_completed=False,
        )

        self.assertFalse(first_duplicate)
        self.assertTrue(second_duplicate)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(pending), 1)
        pending[0]()  # type: ignore[operator]
        self.assertEqual(calls, ["connected"])
        self.assertEqual(registry.get(first.id).status, "succeeded")  # type: ignore[union-attr]

    def test_explicit_idempotency_key_reuses_completed_operation(self) -> None:
        registry = OperationRegistry(clock=lambda: 100.0)
        starter = lambda target: target()

        first, _ = registry.submit(
            "disconnect", "request-1", lambda: {"disconnected": True},
            start_thread=starter, reuse_completed=True,
        )
        second, duplicate = registry.submit(
            "disconnect", "request-1", lambda: {"disconnected": False},
            start_thread=starter, reuse_completed=True,
        )

        self.assertTrue(duplicate)
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.result, {"disconnected": True})

    def test_failure_has_stable_code_without_exception_detail(self) -> None:
        registry = OperationRegistry(clock=lambda: 100.0)
        record, _ = registry.submit(
            "refresh_nodes",
            "request-2",
            lambda: (_ for _ in ()).throw(RuntimeError("private path and password")),
            start_thread=lambda target: target(),
            reuse_completed=True,
        )

        payload = record.public_dict()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error_code"], "refresh_nodes_failed")
        self.assertNotIn("private path", str(payload))

    def test_public_result_removes_sensitive_fields(self) -> None:
        registry = OperationRegistry(clock=lambda: 100.0)
        record, _ = registry.submit(
            "test_node",
            "request-3",
            lambda: {"node": {"id": "jp_1", "config_text": "secret"}, "raw_response": {"secret": True}},
            start_thread=lambda target: target(),
            reuse_completed=True,
        )

        payload = record.public_dict()
        self.assertEqual(payload["result"], {"node": {"id": "jp_1"}})

    def test_active_operation_capacity_is_bounded(self) -> None:
        registry = OperationRegistry(clock=lambda: 100.0, max_records=10)
        pending: list[object] = []
        for index in range(10):
            registry.submit(
                "quality_check_ip",
                f"request-{index}",
                lambda: None,
                start_thread=pending.append,
                reuse_completed=True,
            )

        with self.assertRaises(OperationCapacityError):
            registry.submit(
                "quality_check_ip",
                "request-overflow",
                lambda: None,
                start_thread=pending.append,
                reuse_completed=True,
            )

        self.assertEqual(len(registry.list()), 10)


if __name__ == "__main__":
    unittest.main()
