from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aimilivpn.core.models import RegionProfile
from aimilivpn.core.regions import InvalidRegion, match_node, region_from_mapping
from aimilivpn.core.storage import NodeRepository, RegionRepository


@dataclass(frozen=True)
class RepositoryFacade:
    node_repository: NodeRepository
    region_repository: RegionRepository
    country_translations: Mapping[str, str]

    def read_nodes(self) -> list[dict[str, Any]]:
        return self.node_repository.list_node_dicts()

    def write_nodes(self, nodes: list[dict[str, Any]]) -> None:
        self.node_repository.replace_all_dicts(nodes)

    def read_regions(self) -> list[RegionProfile]:
        return self.region_repository.list_regions()

    def region_from_payload(
        self,
        payload: dict[str, Any],
        existing: RegionProfile | None = None,
    ) -> RegionProfile:
        return region_from_mapping(payload, existing)

    def filter_nodes_by_region(self, nodes: list[dict[str, Any]], region_id: str) -> list[dict[str, Any]]:
        region = self.region_repository.get(region_id)
        if region is None:
            raise KeyError(region_id)
        return [node for node in nodes if match_node(region, node)]

    def region_target_id(self, target: str) -> str:
        target = str(target or "").strip()
        if target.startswith("region:"):
            return target.removeprefix("region:").strip()
        return target

    def get_region_routing_target(self, target: str) -> RegionProfile | None:
        region_id = self.region_target_id(target)
        if not region_id:
            return None
        return self.region_repository.get(region_id)

    def routing_target_label(self, target: str) -> str:
        target = str(target or "").strip()
        region = self.get_region_routing_target(target)
        if region:
            return region.name
        return target.removeprefix("country:")

    def node_matches_country_target(self, node: dict[str, Any], target: str) -> bool:
        target = str(target or "").strip().removeprefix("country:")
        if not target:
            return True
        country = str(node.get("country") or "")
        translated = self.country_translations.get(country, country)
        country_short = str(node.get("country_short") or "").strip().upper()
        return country == target or translated == target or country_short == target.upper()

    def node_matches_routing_region(self, node: dict[str, Any], target: str) -> bool:
        region = self.get_region_routing_target(target)
        if region:
            try:
                return match_node(region, node)
            except InvalidRegion:
                return False
        return self.node_matches_country_target(node, target)

    def filter_nodes_by_routing_region(self, nodes: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
        if not target:
            return nodes
        return [node for node in nodes if self.node_matches_routing_region(node, target)]

    def validate_routing_region_target(self, routing_mode: str, target: str) -> None:
        if routing_mode != "fixed_region" or not target:
            return
        if str(target).strip().startswith("region:") and self.get_region_routing_target(target) is None:
            raise ValueError("region not found")
