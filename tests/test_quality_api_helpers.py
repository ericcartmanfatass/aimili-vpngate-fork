from __future__ import annotations

import importlib
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from aimilivpn.core.models import QualityResult, RegionProfile


def load_manager(data_dir: str):
    os.environ["VPNGATE_DATA_DIR"] = data_dir
    with redirect_stdout(io.StringIO()):
        if "vpngate_manager" in sys.modules:
            return importlib.reload(sys.modules["vpngate_manager"])
        return importlib.import_module("vpngate_manager")


class QualityApiHelperTests(unittest.TestCase):
    def test_authorized_session_does_not_require_plaintext_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)
            handler = object.__new__(manager.Handler)
            handler.headers = {"Cookie": "session=token-1"}
            manager.active_sessions.clear()
            manager.active_sessions["token-1"] = manager.time.time() + 60

            with patch.object(manager, "load_ui_config", side_effect=AssertionError("plaintext config should not be required")):
                self.assertTrue(manager.Handler.is_authorized(handler))

            manager.active_sessions.clear()

    def test_quality_to_dict_excludes_raw_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)
            quality = QualityResult(
                node_id="jp_1",
                exit_ip="203.0.113.1",
                tcp_latency_ms=80,
                openvpn_success=True,
                handshake_ms=3000,
                risk_provider=None,
                risk_score=None,
                risk_level=None,
                proxy_detected=False,
                datacenter_detected=False,
                country_match=True,
                checked_at="2026-06-17T00:00:00Z",
                raw_response={"secret": "not for clients"},
                score=90,
                label="Excellent",
                reasons=["tcp reachable"],
            )

            payload = manager.quality_to_dict(quality)

            self.assertNotIn("raw_response", payload)
            self.assertEqual(payload["score"], 90)
            self.assertEqual(payload["label"], "Excellent")
            self.assertEqual(payload["reasons"], ["tcp reachable"])

    def test_latest_quality_for_node_reads_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)
            manager.QUALITY_REPOSITORY.save(QualityResult(
                node_id="jp_1",
                exit_ip="203.0.113.1",
                tcp_latency_ms=80,
                openvpn_success=True,
                handshake_ms=3000,
                risk_provider=None,
                risk_score=None,
                risk_level=None,
                proxy_detected=False,
                datacenter_detected=False,
                country_match=True,
                checked_at="2026-06-17T00:00:00Z",
                score=90,
                label="Excellent",
            ))

            quality = manager.latest_quality_for_node("jp_1")

            self.assertIsNotNone(quality)
            self.assertEqual(quality.score, 90)  # type: ignore[union-attr]

    def test_quality_provider_status_hides_scamalytics_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "SCAMALYTICS_USERNAME": "demo-user",
                "SCAMALYTICS_API_KEY": "super-secret",
                "SCAMALYTICS_TIMEOUT_SECONDS": "11",
            }
            with patch.dict(os.environ, env, clear=False):
                manager = load_manager(tmp)
                status = manager.quality_provider_status()

        providers = {item["name"]: item for item in status["providers"]}
        self.assertTrue(providers["local_probe"]["enabled"])
        self.assertTrue(providers["scamalytics"]["configured"])
        self.assertEqual(providers["scamalytics"]["timeout_seconds"], 11)
        self.assertNotIn("api_key", providers["scamalytics"])
        self.assertNotIn("username", providers["scamalytics"])
        self.assertNotIn("super-secret", str(status))

    def test_record_quality_result_enriches_with_scamalytics_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)

            class FakeProvider:
                def check_ip(self, ip: str) -> QualityResult:
                    return QualityResult(
                        node_id=None,
                        exit_ip=ip,
                        tcp_latency_ms=None,
                        openvpn_success=None,
                        handshake_ms=None,
                        risk_provider="scamalytics",
                        risk_score=87,
                        risk_level="high",
                        proxy_detected=True,
                        datacenter_detected=False,
                        country_match=None,
                        checked_at="2026-06-17T00:00:00Z",
                        raw_response={"score": 87},
                    )

            manager.get_scamalytics_provider = lambda: FakeProvider()

            result = manager.record_quality_result_from_probe(
                {"id": "jp_1", "ip": "203.0.113.1"},
                True,
                70,
                "ok",
            )

            latest = manager.QUALITY_REPOSITORY.latest_for_node("jp_1")
            self.assertEqual(result.risk_provider, "scamalytics")
            self.assertEqual(result.risk_score, 87)
            self.assertTrue(result.proxy_detected)
            self.assertIn("scamalytics", result.raw_response or {})
            self.assertIsNotNone(latest)
            self.assertEqual(latest.risk_score, 87)  # type: ignore[union-attr]

    def test_check_quality_ip_saves_scamalytics_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)

            class FakeProvider:
                def check_ip(self, ip: str) -> QualityResult:
                    return QualityResult(
                        node_id=None,
                        exit_ip=ip,
                        tcp_latency_ms=None,
                        openvpn_success=None,
                        handshake_ms=None,
                        risk_provider="scamalytics",
                        risk_score=18,
                        risk_level="low",
                        proxy_detected=False,
                        datacenter_detected=False,
                        country_match=None,
                        checked_at="2026-06-17T00:00:00Z",
                        raw_response={"score": 18},
                    )

            manager.get_scamalytics_provider = lambda: FakeProvider()

            result = manager.check_quality_ip("203.0.113.10")

            self.assertEqual(result.exit_ip, "203.0.113.10")
            self.assertEqual(result.risk_provider, "scamalytics")
            self.assertEqual(result.risk_score, 18)
            saved_items = manager.QUALITY_REPOSITORY.store.read(manager.QUALITY_REPOSITORY.path, [])
            self.assertEqual(len(saved_items), 1)
            self.assertEqual(saved_items[0]["exit_ip"], "203.0.113.10")

    def test_check_quality_region_tests_matching_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)
            manager.REGION_REPOSITORY.create(RegionProfile(
                id="jp-region",
                name="Japan",
                country_codes=["JP"],
                include_keywords=[],
                exclude_keywords=[],
                min_quality_score=None,
                max_risk_score=None,
                enabled=True,
            ))
            manager.write_nodes([
                {"id": "jp_1", "country_short": "JP", "host_name": "tokyo"},
                {"id": "jp_2", "country_short": "JP", "host_name": "osaka"},
                {"id": "us_1", "country_short": "US", "host_name": "new-york"},
            ])
            called: list[list[str]] = []

            def fake_test_multiple_nodes(node_ids: list[str]) -> list[dict[str, object]]:
                called.append(node_ids)
                for node_id in node_ids:
                    manager.QUALITY_REPOSITORY.save(QualityResult(
                        node_id=node_id,
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
                        score=80,
                        label="Usable",
                    ))
                return [{"id": node_id, "probe_status": "available"} for node_id in node_ids]

            manager.test_multiple_nodes = fake_test_multiple_nodes

            summary = manager.check_quality_region("jp-region", limit=1)

            self.assertEqual(summary["total_matches"], 2)
            self.assertEqual(summary["tested_count"], 1)
            self.assertEqual(called, [["jp_1"]])
            self.assertIn("jp_1", summary["qualities"])

    def test_check_quality_region_bootstraps_unknown_quality_then_applies_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = load_manager(tmp)
            manager.REGION_REPOSITORY.create(RegionProfile(
                id="jp-trusted",
                name="Japan trusted",
                country_codes=["JP"],
                min_quality_score=70,
            ))
            manager.write_nodes([{"id": "jp_1", "country_short": "JP", "host_name": "tokyo"}])

            def fake_test(node_ids: list[str]) -> list[dict[str, object]]:
                manager.QUALITY_REPOSITORY.save(QualityResult(
                    node_id="jp_1", exit_ip="203.0.113.1", tcp_latency_ms=80,
                    openvpn_success=True, handshake_ms=None, risk_provider=None,
                    risk_score=None, risk_level=None, proxy_detected=False,
                    datacenter_detected=False, country_match=None,
                    checked_at="2026-07-13T00:00:00Z", score=85, label="Excellent",
                ))
                return [{"id": node_id, "probe_status": "available"} for node_id in node_ids]

            manager.test_multiple_nodes = fake_test
            summary = manager.check_quality_region("jp-trusted", limit=20)

            self.assertEqual(summary["total_candidates"], 1)
            self.assertEqual(summary["total_matches"], 1)
            self.assertEqual(summary["exclusion_reasons"], {})


if __name__ == "__main__":
    unittest.main()
