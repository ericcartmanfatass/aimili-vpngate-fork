from __future__ import annotations

import unittest
from datetime import datetime, timezone

from aimilivpn.providers.local_probe import LocalProbeProvider, quality_result_to_node_patch


class LocalProbeTests(unittest.TestCase):
    def test_check_node_uses_injected_latency_and_openvpn_probe(self) -> None:
        provider = LocalProbeProvider(
            latency_func=lambda host, port, fallback: 42,
            openvpn_check_func=lambda node: (True, "ready", 2500),
            clock=lambda: datetime(2026, 6, 17, tzinfo=timezone.utc),
        )

        result = provider.check_node({
            "id": "jp_1",
            "remote_host": "203.0.113.1",
            "remote_port": 1194,
            "quality": "normal",
        })

        self.assertEqual(result.node_id, "jp_1")
        self.assertEqual(result.tcp_latency_ms, 42)
        self.assertTrue(result.openvpn_success)
        self.assertEqual(result.handshake_ms, 2500)
        self.assertEqual(result.score, 80)
        self.assertEqual(result.label, "Excellent")
        self.assertEqual(result.raw_response, {"probe_message": "ready"})

    def test_quality_result_to_node_patch_maps_probe_status(self) -> None:
        provider = LocalProbeProvider(
            latency_func=lambda host, port, fallback: fallback,
            openvpn_check_func=lambda node: (False, "timeout", None),
            clock=lambda: datetime(2026, 6, 17, tzinfo=timezone.utc),
        )

        result = provider.check_node({
            "id": "jp_1",
            "ip": "203.0.113.1",
            "port": 443,
            "ping": 120,
            "quality": "datacenter",
            "ip_type": "hosting",
        })
        patch = quality_result_to_node_patch(result)

        self.assertEqual(patch["latency_ms"], 120)
        self.assertEqual(patch["probe_status"], "unavailable")
        self.assertEqual(patch["probe_message"], "timeout")
        self.assertEqual(patch["quality_label"], "High Risk")


if __name__ == "__main__":
    unittest.main()
