from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from aimilivpn.core.models import RegionProfile
from aimilivpn.core.storage import NodeRepository, RegionRepository
from aimilivpn.system.repository_facade import RepositoryFacade


@dataclass
class ManagerRepositoryRuntime:
    node_repository: NodeRepository
    region_repository: RegionRepository
    country_translations: Mapping[str, str]
    _facade: RepositoryFacade | None = field(default=None, init=False)

    def facade(self) -> RepositoryFacade:
        if self._facade is None:
            self._facade = RepositoryFacade(
                node_repository=self.node_repository,
                region_repository=self.region_repository,
                country_translations=self.country_translations,
            )
        return self._facade

    def read_nodes(self) -> list[dict[str, Any]]:
        return self.facade().read_nodes()

    def write_nodes(self, nodes: list[dict[str, Any]]) -> None:
        self.facade().write_nodes(nodes)

    def read_regions(self) -> list[RegionProfile]:
        return self.facade().read_regions()

    def region_from_payload(
        self,
        payload: dict[str, Any],
        existing: RegionProfile | None = None,
    ) -> RegionProfile:
        return self.facade().region_from_payload(payload, existing)

    def filter_nodes_by_region(self, nodes: list[dict[str, Any]], region_id: str) -> list[dict[str, Any]]:
        return self.facade().filter_nodes_by_region(nodes, region_id)

    def region_target_id(self, target: str) -> str:
        return self.facade().region_target_id(target)

    def get_region_routing_target(self, target: str) -> RegionProfile | None:
        return self.facade().get_region_routing_target(target)

    def routing_target_label(self, target: str) -> str:
        return self.facade().routing_target_label(target)

    def node_matches_country_target(self, node: dict[str, Any], target: str) -> bool:
        return self.facade().node_matches_country_target(node, target)

    def node_matches_routing_region(self, node: dict[str, Any], target: str) -> bool:
        return self.facade().node_matches_routing_region(node, target)

    def filter_nodes_by_routing_region(self, nodes: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
        return self.facade().filter_nodes_by_routing_region(nodes, target)

    def validate_routing_region_target(self, routing_mode: str, target: str) -> None:
        self.facade().validate_routing_region_target(routing_mode, target)
