from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aimilivpn.core.models import RegionProfile
from aimilivpn.core.storage import NodeRepository, RegionRepository
from aimilivpn.system.repository_facade import RepositoryFacade


def build_facade(root: Path) -> RepositoryFacade:
    return RepositoryFacade(
        node_repository=NodeRepository(root / "nodes.json"),
        region_repository=RegionRepository(root / "regions.json"),
        country_translations={"日本": "Japan"},
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


if __name__ == "__main__":
    unittest.main()
