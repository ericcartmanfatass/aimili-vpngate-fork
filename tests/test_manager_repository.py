from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, sentinel, patch

from aimilivpn.core.models import RegionProfile
from aimilivpn.core.storage import NodeRepository, RegionRepository
from aimilivpn.system.manager_repository import ManagerRepositoryRuntime


class ManagerRepositoryRuntimeTests(unittest.TestCase):
    def make_runtime(self) -> ManagerRepositoryRuntime:
        return ManagerRepositoryRuntime(
            node_repository=NodeRepository(Path("nodes.json")),
            region_repository=RegionRepository(Path("regions.json")),
            country_translations={"Japan": "Japan"},
        )

    def test_facade_is_cached_and_wired(self) -> None:
        runtime = self.make_runtime()

        with patch("aimilivpn.system.manager_repository.RepositoryFacade", return_value=sentinel.facade) as facade_cls:
            first = runtime.facade()
            second = runtime.facade()

        self.assertIs(first, sentinel.facade)
        self.assertIs(second, sentinel.facade)
        facade_cls.assert_called_once_with(
            node_repository=runtime.node_repository,
            region_repository=runtime.region_repository,
            country_translations={"Japan": "Japan"},
        )

    def test_wrappers_delegate_to_cached_facade(self) -> None:
        runtime = self.make_runtime()
        facade = Mock()
        facade.read_nodes.return_value = [{"id": "jp_1"}]
        facade.read_regions.return_value = [RegionProfile(id="asia", name="Asia", country_codes=[])]
        facade.region_from_payload.return_value = sentinel.region
        facade.filter_nodes_by_region.return_value = [{"id": "jp_1"}]
        facade.region_target_id.return_value = "asia"
        facade.get_region_routing_target.return_value = sentinel.target
        facade.routing_target_label.return_value = "Asia"
        facade.node_matches_country_target.return_value = True
        facade.node_matches_routing_region.return_value = True
        facade.filter_nodes_by_routing_region.return_value = [{"id": "jp_1"}]
        runtime._facade = facade

        self.assertEqual(runtime.read_nodes(), [{"id": "jp_1"}])
        runtime.write_nodes([{"id": "jp_2"}])
        self.assertEqual(runtime.read_regions()[0].id, "asia")
        self.assertIs(runtime.region_from_payload({"id": "asia"}), sentinel.region)
        self.assertEqual(runtime.filter_nodes_by_region([], "asia"), [{"id": "jp_1"}])
        self.assertEqual(runtime.region_target_id("region:asia"), "asia")
        self.assertIs(runtime.get_region_routing_target("asia"), sentinel.target)
        self.assertEqual(runtime.routing_target_label("asia"), "Asia")
        self.assertTrue(runtime.node_matches_country_target({}, "JP"))
        self.assertTrue(runtime.node_matches_routing_region({}, "region:asia"))
        self.assertEqual(runtime.filter_nodes_by_routing_region([], "region:asia"), [{"id": "jp_1"}])
        runtime.validate_routing_region_target("fixed_region", "region:asia")

        facade.write_nodes.assert_called_once_with([{"id": "jp_2"}])
        facade.validate_routing_region_target.assert_called_once_with("fixed_region", "region:asia")


if __name__ == "__main__":
    unittest.main()
