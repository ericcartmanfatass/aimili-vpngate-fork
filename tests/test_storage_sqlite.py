from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aimilivpn.core.models import QualityResult, RegionProfile, VpnNode
from aimilivpn.core.storage import (
    NodeRepository,
    QualityRepository,
    RegionRepository,
    SettingsRepository,
    SqliteStore,
    build_store,
)


class StorageSqliteTests(unittest.TestCase):
    def build_store(self, tmp: str) -> SqliteStore:
        return SqliteStore(Path(tmp) / "aimilivpn.db")

    def test_build_store_creates_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store("sqlite", sqlite_db_path=Path(tmp) / "aimilivpn.db")

        self.assertIsInstance(store, SqliteStore)

    def test_build_store_requires_sqlite_path(self) -> None:
        with self.assertRaises(ValueError):
            build_store("sqlite")

    def test_node_repository_uses_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.build_store(tmp)
            repo = NodeRepository(Path("nodes.json"), store=store)
            repo.upsert_many([
                VpnNode(id="jp_1", source="vpngate", country="Japan", country_code="JP", ip="203.0.113.1", port=1194, proto="udp")
            ])

            loaded = NodeRepository(Path("nodes.json"), store=store).get("jp_1")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.country_code, "JP")  # type: ignore[union-attr]

    def test_repositories_share_sqlite_store_without_crossing_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.build_store(tmp)
            regions = RegionRepository(Path("regions.json"), store=store)
            settings = SettingsRepository(Path("settings.json"), store=store)
            regions.create(RegionProfile(id="asia", name="Asia", country_codes=["JP"]))
            settings.set("proxy_port", 7928)

            loaded_region = RegionRepository(Path("regions.json"), store=store).get("asia")
            loaded_port = SettingsRepository(Path("settings.json"), store=store).get("proxy_port")

        self.assertIsNotNone(loaded_region)
        self.assertEqual(loaded_region.country_codes, ["JP"])  # type: ignore[union-attr]
        self.assertEqual(loaded_port, 7928)

    def test_quality_repository_latest_uses_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self.build_store(tmp)
            repo = QualityRepository(Path("quality_results.json"), store=store)
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

            result = QualityRepository(Path("quality_results.json"), store=store).latest_for_node("jp_1")

        self.assertIsNotNone(result)
        self.assertEqual(result.score, 90)  # type: ignore[union-attr]
        self.assertEqual(result.checked_at, "2026-06-17T01:00:00Z")  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
