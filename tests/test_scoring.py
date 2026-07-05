from __future__ import annotations

import unittest

from aimilivpn.core.models import QualityResult
from aimilivpn.core.scoring import apply_score, score_quality


def result(**updates: object) -> QualityResult:
    data = {
        "node_id": "jp_1",
        "exit_ip": "203.0.113.1",
        "tcp_latency_ms": None,
        "openvpn_success": None,
        "handshake_ms": None,
        "risk_provider": None,
        "risk_score": None,
        "risk_level": None,
        "proxy_detected": None,
        "datacenter_detected": None,
        "country_match": None,
        "checked_at": "2026-06-17T00:00:00Z",
    }
    data.update(updates)
    return QualityResult(**data)  # type: ignore[arg-type]


class ScoringTests(unittest.TestCase):
    def test_score_quality_rewards_fast_successful_low_risk_node(self) -> None:
        breakdown = score_quality(result(
            tcp_latency_ms=50,
            openvpn_success=True,
            handshake_ms=3000,
            risk_score=20,
            country_match=True,
        ))

        self.assertEqual(breakdown.score, 100)
        self.assertEqual(breakdown.label, "Excellent")
        self.assertIn("openvpn handshake ok", breakdown.reasons)

    def test_score_quality_penalizes_high_risk_proxy_datacenter(self) -> None:
        breakdown = score_quality(result(
            tcp_latency_ms=500,
            openvpn_success=True,
            risk_score=90,
            proxy_detected=True,
            datacenter_detected=True,
        ))

        self.assertEqual(breakdown.score, 5)
        self.assertEqual(breakdown.label, "High Risk")

    def test_apply_score_mutates_result_for_storage(self) -> None:
        quality = apply_score(result(tcp_latency_ms=120, openvpn_success=True))

        self.assertEqual(quality.score, 60)
        self.assertEqual(quality.label, "Usable")
        self.assertTrue(quality.reasons)


if __name__ == "__main__":
    unittest.main()
