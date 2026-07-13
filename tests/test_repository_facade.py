from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.core.regions import preview_region
from aimilivpn.core.storage import NodeRepository, QualityRepository, RegionRepository
from aimilivpn.system.repository_facade import RepositoryFacade


def build_facade(root: Path) -> RepositoryFacade:
    return RepositoryFacade(
        node_repository=NodeRepository(root / "nodes.json"),
        region_repository=RegionRepository(root / "regions.json"),
        country_translations={"日本": "Japan"},
        quality_repository=QualityRepository(root / "quality.json"),
    )


class RepositoryFacadeTests(unittest.TestCase):
    def test_read_write_nodes_round_trips_legacy_dicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp))
            nodes = [{"id": "jp_1", "country_short": "JP", "unknown": "kept"}]

            facade.write_nodes(nodes)

            self.assertEqual(facade.read_nodes(), nodes)

    def test_region_from_payload_merges_existing_region(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp))
            existing = RegionProfile(
                id="asia",
                name="Asia",
                country_codes=["JP"],
                include_keywords=["tokyo"],
            )

            region = facade.region_from_payload({"name": "Asia Fast"}, existing)

            self.assertEqual(region.id, "asia")
            self.assertEqual(region.name, "Asia Fast")
            self.assertEqual(region.country_codes, ["JP"])
            self.assertEqual(region.include_keywords, ["tokyo"])

    def test_filter_nodes_by_region_uses_region_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp))
            facade.region_repository.create(
                RegionProfile(
                    id="asia-fast",
                    name="Asia Fast",
                    country_codes=["JP", "KR"],
                    include_keywords=["tokyo"],
                )
            )
            nodes = [
                {"id": "jp_1", "country_short": "JP", "host_name": "tokyo-fast"},
                {"id": "kr_1", "country_short": "KR", "host_name": "seoul"},
            ]

            filtered = facade.filter_nodes_by_region(nodes, "asia-fast")

            self.assertEqual([node["id"] for node in filtered], ["jp_1"])

    def test_routing_region_falls_back_to_legacy_country_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp))

            self.assertTrue(facade.node_matches_routing_region({"country": "日本"}, "Japan"))
            self.assertTrue(facade.node_matches_routing_region({"country_short": "JP"}, "JP"))
            self.assertTrue(facade.node_matches_routing_region({"country": "Japan"}, "country:Japan"))

    def test_validate_routing_region_target_rejects_missing_region(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp))

            with self.assertRaises(ValueError):
                facade.validate_routing_region_target("fixed_region", "region:missing")

    def test_region_filters_use_latest_quality_and_risk_for_all_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facade = build_facade(Path(tmp))
            facade.region_repository.create(RegionProfile(
                id="trusted-jp",
                name="Trusted Japan",
                country_codes=["JP"],
                min_quality_score=70,
                max_risk_score=30,
            ))
            assert facade.quality_repository is not None
            facade.quality_repository.save(QualityResult(
                node_id="jp_good", exit_ip="203.0.113.1", tcp_latency_ms=50,
                openvpn_success=True, handshake_ms=1000, risk_provider="scamalytics",
                risk_score=20, risk_level="low", proxy_detected=False,
                datacenter_detected=False, country_match=True,
                checked_at="2026-07-13T00:00:00Z", score=85,
            ))
            facade.quality_repository.save(QualityResult(
                node_id="jp_risky", exit_ip="203.0.113.2", tcp_latency_ms=50,
                openvpn_success=True, handshake_ms=1000, risk_provider="scamalytics",
                risk_score=80, risk_level="high", proxy_detected=True,
                datacenter_detected=False, country_match=True,
                checked_at="2026-07-13T00:00:00Z", score=85,
            ))
            nodes = [
                {"id": "jp_good", "country_short": "JP"},
                {"id": "jp_risky", "country_short": "JP"},
                {"id": "jp_unknown", "country_short": "JP", "score": 9999},
            ]

            listed = facade.filter_nodes_by_region(nodes, "trusted-jp")
            routed = facade.filter_nodes_by_routing_region(nodes, "region:trusted-jp")
            preview = preview_region(
                facade.region_repository.get("trusted-jp"),  # type: ignore[arg-type]
                nodes,
                facade.quality_repository.list_latest(),
            )

            self.assertEqual([node["id"] for node in listed], ["jp_good"])
            self.assertEqual([node["id"] for node in routed], ["jp_good"])
            self.assertEqual(preview.matched_node_ids, ["jp_good"])


if __name__ == "__main__":
    unittest.main()
