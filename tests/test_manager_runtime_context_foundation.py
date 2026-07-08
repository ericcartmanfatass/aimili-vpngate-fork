from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, sentinel, patch

from aimilivpn.system import manager_runtime_context_foundation as foundation


class ManagerRuntimeContextFoundationTests(unittest.TestCase):
    def test_build_repository_runtime_exposes_all_repositories(self) -> None:
        ctx = SimpleNamespace(
            runtime_paths=sentinel.runtime_paths,
            storage_backend="sqlite",
            sqlite_db_path=Path("aimilivpn.db"),
        )
        repositories = SimpleNamespace(
            node_repository=sentinel.node_repository,
            region_repository=sentinel.region_repository,
            quality_repository=sentinel.quality_repository,
            settings_repository=sentinel.settings_repository,
        )
        repository_runtime = SimpleNamespace(
            facade=sentinel.facade,
            read_nodes=Mock(name="read_nodes"),
            write_nodes=Mock(name="write_nodes"),
            read_regions=Mock(name="read_regions"),
            region_from_payload=Mock(name="region_from_payload"),
            filter_nodes_by_region=Mock(name="filter_nodes_by_region"),
            region_target_id=Mock(name="region_target_id"),
            get_region_routing_target=Mock(name="get_region_routing_target"),
            routing_target_label=Mock(name="routing_target_label"),
            node_matches_country_target=Mock(name="node_matches_country_target"),
            node_matches_routing_region=Mock(name="node_matches_routing_region"),
            filter_nodes_by_routing_region=Mock(name="filter_nodes_by_routing_region"),
            validate_routing_region_target=Mock(name="validate_routing_region_target"),
        )

        with (
            patch.object(foundation.wiring, "build_repositories", return_value=repositories) as build_repositories,
            patch.object(
                foundation.wiring,
                "build_repository_runtime",
                return_value=repository_runtime,
            ) as build_repository_runtime,
        ):
            foundation.build_repository_runtime(ctx)

        build_repositories.assert_called_once_with(
            sentinel.runtime_paths,
            storage_backend="sqlite",
            sqlite_db_path=Path("aimilivpn.db"),
        )
        build_repository_runtime.assert_called_once()
        self.assertIs(ctx.node_repository, sentinel.node_repository)
        self.assertIs(ctx.region_repository, sentinel.region_repository)
        self.assertIs(ctx.quality_repository, sentinel.quality_repository)
        self.assertIs(ctx.settings_repository, sentinel.settings_repository)
        self.assertIs(ctx.repository_facade, sentinel.facade)
        self.assertIs(ctx.read_nodes, repository_runtime.read_nodes)
        self.assertIs(ctx.validate_routing_region_target, repository_runtime.validate_routing_region_target)


if __name__ == "__main__":
    unittest.main()
