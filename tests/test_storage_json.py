from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aimilivpn.core.models import QualityResult, RegionProfile, VpnNode
from aimilivpn.core.regions import InvalidRegion
from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository, SettingsRepository


class StorageJsonTests(unittest.TestCase):
    def test_node_repository_upsert_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = NodeRepository(Path(tmp) / "nodes.json")
            repo.upsert_many([
                VpnNode(id="jp_1", source="vpngate", country="Japan", country_code="JP", ip="203.0.113.1", port=1194, proto="udp")
            ])

            node = repo.get("jp_1")

            self.assertIsNotNone(node)
            self.assertEqual(node.country_code, "JP")

    def test_node_repository_legacy_dicts_preserve_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = NodeRepository(Path(tmp) / "nodes.json")
            repo.replace_all_dicts([
                {
                    "id": "jp_1",
                    "country_short": "JP",
                    "config_text": "client\n",
                    "active": True,
                    "probe_message": "ok",
                }
            ])

            nodes = repo.list_node_dicts()

            self.assertEqual(nodes[0]["active"], True)
            self.assertEqual(nodes[0]["probe_message"], "ok")

    def test_region_repository_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = RegionRepository(Path(tmp) / "regions.json")
            repo.create(RegionProfile(id="asia", name="Asia", country_codes=["JP", "KR"]))
            repo.update("asia", {"enabled": False})

            self.assertFalse(repo.get("asia").enabled)  # type: ignore[union-attr]
            repo.delete("asia")
            self.assertIsNone(repo.get("asia"))

    def test_region_repository_normalizes_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = RegionRepository(Path(tmp) / "regions.json")
            repo.create(RegionProfile(id="asia", name=" Asia ", country_codes=["jp", "JP", "kr"]))

            region = repo.get("asia")

            self.assertIsNotNone(region)
            self.assertEqual(region.name, "Asia")  # type: ignore[union-attr]
            self.assertEqual(region.country_codes, ["JP", "KR"])  # type: ignore[union-attr]

    def test_region_repository_rejects_invalid_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = RegionRepository(Path(tmp) / "regions.json")
            repo.create(RegionProfile(id="asia", name="Asia", country_codes=["JP"]))

            with self.assertRaises(InvalidRegion):
                repo.update("asia", {"min_quality_score": 101})

    def test_region_repository_delete_missing_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = RegionRepository(Path(tmp) / "regions.json")

            with self.assertRaises(KeyError):
                repo.delete("missing")

    def test_settings_repository_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = SettingsRepository(Path(tmp) / "settings.json")
            repo.set("proxy_port", 7928)

            self.assertEqual(repo.get("proxy_port"), 7928)

    def test_quality_repository_tracks_latest_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = QualityRepository(Path(tmp) / "quality.json")
            repo.save(QualityResult(
                node_id="jp_1",
                exit_ip="203.0.113.1",
                tcp_latency_ms=120,
                openvpn_success=True,
                handshake_ms=3000,
                risk_provider=None,
                risk_score=None,
                risk_level=None,
                proxy_detected=False,
                datacenter_detected=False,
                country_match=True,
                checked_at="2026-06-17T00:00:00Z",
                score=60,
                label="Usable",
                reasons=["tcp reachable"],
            ))

            result = repo.latest_for_node("jp_1")

            self.assertIsNotNone(result)
            self.assertEqual(result.score, 60)  # type: ignore[union-attr]
            self.assertEqual(result.label, "Usable")  # type: ignore[union-attr]

    def test_quality_repository_latest_uses_last_saved_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = QualityRepository(Path(tmp) / "quality.json")
            common = {
                "node_id": "jp_1",
                "exit_ip": "203.0.113.1",
                "tcp_latency_ms": 120,
                "openvpn_success": True,
                "handshake_ms": 3000,
                "risk_provider": None,
                "risk_score": None,
                "risk_level": None,
                "proxy_detected": False,
                "datacenter_detected": False,
                "country_match": True,
            }
            repo.save(QualityResult(**common, checked_at="2026-06-17T00:00:00Z", score=60, label="Usable"))
            repo.save(QualityResult(**common, checked_at="2026-06-17T01:00:00Z", score=90, label="Excellent"))

            result = repo.latest_for_node("jp_1")

            self.assertIsNotNone(result)
            self.assertEqual(result.score, 90)  # type: ignore[union-attr]
            self.assertEqual(result.checked_at, "2026-06-17T01:00:00Z")  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
