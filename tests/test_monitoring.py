from __future__ import annotations

import unittest
from typing import Any

from aimilivpn.core.monitoring import (
    active_node_latency_status,
    collector_sleep_seconds,
    mark_active_node_proxy_failed,
    proxy_state_from_health,
    should_auto_switch_after_proxy_failure,
    should_restart_fixed_node_after_proxy_failure,
)


def parse_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class MonitoringTests(unittest.TestCase):
    def test_collector_sleep_seconds_uses_retry_when_idle_and_unsuccessful(self) -> None:
        self.assertEqual(
            collector_sleep_seconds(active_running=False, success=False, check_interval_seconds=300),
            30,
        )
        self.assertEqual(
            collector_sleep_seconds(active_running=True, success=False, check_interval_seconds=300),
            300,
        )

    def test_proxy_state_from_health(self) -> None:
        self.assertEqual(
            proxy_state_from_health({"ok": True, "ip": "203.0.113.1", "latency_ms": 80}),
            {"proxy_ok": True, "proxy_ip": "203.0.113.1", "proxy_latency_ms": 80, "proxy_error": ""},
        )
        self.assertEqual(
            proxy_state_from_health({"ok": False, "error": "down"}),
            {"proxy_ok": False, "proxy_ip": "-", "proxy_latency_ms": 0, "proxy_error": "down"},
        )

    def test_proxy_failure_routing_decisions(self) -> None:
        self.assertTrue(should_auto_switch_after_proxy_failure("node1", "auto"))
        self.assertFalse(should_auto_switch_after_proxy_failure("node1", "fixed_ip"))
        self.assertTrue(should_restart_fixed_node_after_proxy_failure("node1", "fixed_ip"))
        self.assertFalse(should_restart_fixed_node_after_proxy_failure("", "fixed_ip"))

    def test_mark_active_node_proxy_failed(self) -> None:
        nodes = [{"id": "node1", "probe_status": "available"}, {"id": "node2"}]

        active = mark_active_node_proxy_failed(nodes, "node1", error_message="failed")

        self.assertIs(active, nodes[0])
        self.assertEqual(nodes[0]["probe_status"], "unavailable")
        self.assertEqual(nodes[0]["probe_message"], "failed")

    def test_active_node_latency_status(self) -> None:
        nodes = [{"id": "node1", "remote_host": "198.51.100.1", "remote_port": "1194", "ping": "90"}]
        calls: list[tuple[str, int, int]] = []

        def ping(host: str, port: int, fallback: int) -> int:
            calls.append((host, port, fallback))
            return 42

        self.assertEqual(
            active_node_latency_status(
                active_running=True,
                active_node_id="node1",
                is_connecting=False,
                nodes=nodes,
                ping_latency_ms=ping,
                parse_int=parse_int,
                timeout_label="timeout",
                connecting_label="connecting",
                idle_label="idle",
            ),
            "42 ms",
        )
        self.assertEqual(calls, [("198.51.100.1", 1194, 90)])

        self.assertEqual(
            active_node_latency_status(
                active_running=False,
                active_node_id="",
                is_connecting=True,
                nodes=[],
                ping_latency_ms=ping,
                parse_int=parse_int,
                timeout_label="timeout",
                connecting_label="connecting",
                idle_label="idle",
            ),
            "connecting",
        )


if __name__ == "__main__":
    unittest.main()
