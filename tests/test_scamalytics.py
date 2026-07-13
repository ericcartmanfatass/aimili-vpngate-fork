from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from aimilivpn.core.models import QualityResult
from aimilivpn.core.storage import ProviderCacheRepository
from aimilivpn.providers.scamalytics import (
    ScamalyticsProvider,
    ScamalyticsRateLimited,
    merge_scamalytics_result,
    parse_scamalytics_response,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ScamalyticsTests(unittest.TestCase):
    def test_parse_scamalytics_response_maps_risk_fields(self) -> None:
        result = parse_scamalytics_response(
            "203.0.113.1",
            {
                "ip": "203.0.113.1",
                "score": "12",
                "risk": "low",
                "proxy": False,
                "server": False,
            },
            checked_at="2026-06-17T00:00:00Z",
        )

        self.assertEqual(result.exit_ip, "203.0.113.1")
        self.assertEqual(result.risk_provider, "scamalytics")
        self.assertEqual(result.risk_score, 12)
        self.assertEqual(result.risk_level, "low")
        self.assertFalse(result.proxy_detected)
        self.assertFalse(result.datacenter_detected)
        self.assertEqual(result.checked_at, "2026-06-17T00:00:00Z")

    def test_provider_builds_request_and_uses_cache(self) -> None:
        calls: list[tuple[str, int]] = []

        def opener(request, timeout: int) -> FakeResponse:  # type: ignore[no-untyped-def]
            calls.append((request.full_url, timeout))
            return FakeResponse({"ip": "203.0.113.1", "score": 12, "risk": "low"})

        provider = ScamalyticsProvider(
            "demo-user",
            "demo-key",
            timeout_seconds=5,
            opener=opener,
            clock=lambda: 1000.0,
        )

        first = provider.check_ip("203.0.113.1")
        second = provider.check_ip("203.0.113.1")

        self.assertEqual(first.risk_score, 12)
        self.assertEqual(second.risk_score, 12)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 5)
        query = parse_qs(urlparse(calls[0][0]).query)
        self.assertEqual(query["key"], ["demo-key"])
        self.assertEqual(query["ip"], ["203.0.113.1"])

    def test_provider_rate_limits_uncached_requests(self) -> None:
        current_time = [1000.0]

        def opener(request, timeout: int) -> FakeResponse:  # type: ignore[no-untyped-def]
            return FakeResponse({"ip": "203.0.113.1", "score": 12})

        provider = ScamalyticsProvider(
            "demo-user",
            "demo-key",
            cache_ttl_seconds=0,
            rate_limit_per_minute=1,
            opener=opener,
            clock=lambda: current_time[0],
        )

        provider.check_ip("203.0.113.1")
        with self.assertRaises(ScamalyticsRateLimited):
            provider.check_ip("203.0.113.2")

    def test_provider_cache_survives_provider_restart_without_raw_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = ProviderCacheRepository(Path(tmp) / "provider_cache.json")
            first = ScamalyticsProvider(
                "demo-user",
                "demo-key",
                opener=lambda request, timeout: FakeResponse({"ip": "203.0.113.1", "score": 12}),
                clock=lambda: 1000.0,
                cache_repository=cache,
            )
            first.check_ip("203.0.113.1")
            restarted = ScamalyticsProvider(
                "demo-user",
                "demo-key",
                opener=lambda request, timeout: (_ for _ in ()).throw(AssertionError("network must not be used")),
                clock=lambda: 1001.0,
                cache_repository=cache,
            )

            cached = restarted.check_ip("203.0.113.1")

            self.assertEqual(cached.risk_score, 12)
            self.assertIsNone(cached.raw_response)

    def test_cache_failure_only_reduces_information(self) -> None:
        cache = Mock(spec=ProviderCacheRepository)
        cache.get.side_effect = OSError("cache unavailable")
        cache.put.side_effect = OSError("cache unavailable")
        provider = ScamalyticsProvider(
            "demo-user",
            "demo-key",
            opener=lambda request, timeout: FakeResponse({"ip": "203.0.113.1", "score": 12}),
            clock=lambda: 1000.0,
            cache_repository=cache,
        )

        result = provider.check_ip("203.0.113.1")

        self.assertEqual(result.risk_score, 12)

    def test_merge_scamalytics_result_preserves_probe_fields(self) -> None:
        base = QualityResult(
            node_id="jp_1",
            exit_ip="203.0.113.1",
            tcp_latency_ms=80,
            openvpn_success=True,
            handshake_ms=None,
            risk_provider=None,
            risk_score=None,
            risk_level=None,
            proxy_detected=False,
            datacenter_detected=False,
            country_match=None,
            checked_at="2026-06-17T00:00:00Z",
            raw_response={"probe_message": "ok"},
        )
        risk = parse_scamalytics_response(
            "203.0.113.1",
            {"ip": "203.0.113.1", "score": 88, "risk": "high", "proxy": True, "server": True},
        )

        merged = merge_scamalytics_result(base, risk)

        self.assertEqual(merged.node_id, "jp_1")
        self.assertEqual(merged.tcp_latency_ms, 80)
        self.assertTrue(merged.openvpn_success)
        self.assertEqual(merged.risk_provider, "scamalytics")
        self.assertEqual(merged.risk_score, 88)
        self.assertEqual(merged.risk_level, "high")
        self.assertTrue(merged.proxy_detected)
        self.assertTrue(merged.datacenter_detected)
        self.assertIn("probe_message", merged.raw_response or {})
        self.assertIn("scamalytics", merged.raw_response or {})


if __name__ == "__main__":
    unittest.main()
