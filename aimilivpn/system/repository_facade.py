from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.core.regions import InvalidRegion, match_node, region_from_mapping
from aimilivpn.core.storage import (
    BlacklistRepository,
    NodeRepository,
    ProviderCacheRepository,
    QualityRepository,
    RegionRepository,
    SettingsRepository,
)


@dataclass(frozen=True)
class RepositoryFacade:
    node_repository: NodeRepository
    region_repository: RegionRepository
    country_translations: Mapping[str, str]
    quality_repository: QualityRepository | None = None
    settings_repository: SettingsRepository | None = None
    blacklist_repository: BlacklistRepository | None = None

    def read_nodes(self) -> list[dict[str, Any]]:
        return self.node_repository.list_node_dicts()

    def write_nodes(self, nodes: list[dict[str, Any]]) -> None:
        self.node_repository.replace_all_dicts(nodes)

    def read_regions(self) -> list[RegionProfile]:
        return self.region_repository.list_regions()

    def get(self, region_id: str) -> RegionProfile | None:
        return self.region_repository.get(region_id)

    def create(self, region: RegionProfile) -> None:
        self.region_repository.create(region)

    def update(self, region_id: str, patch: dict[str, Any]) -> None:
        self.region_repository.update(region_id, patch)

    def delete(self, region_id: str) -> None:
        self.region_repository.delete(region_id)

    def save(self, result: QualityResult) -> None:
        self._quality_repository().save(result)

    def latest_for_node(self, node_id: str) -> QualityResult | None:
        return self._quality_repository().latest_for_node(node_id)

    def list_latest(self) -> dict[str, QualityResult]:
        return self._quality_repository().list_latest()

    def provider_cache(self) -> ProviderCacheRepository:
        return self._quality_repository().provider_cache()

    def get_setting(self, key: str, default: Any = None) -> Any:
        if self.settings_repository is None:
            return default
        return self.settings_repository.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        if self.settings_repository is None:
            raise RuntimeError("settings repository is unavailable")
        self.settings_repository.set(key, value)

    def read_entries(self) -> dict[str, dict[str, Any]]:
        if self.blacklist_repository is None:
            return {}
        return self.blacklist_repository.read_entries()

    def read_raw_entries(self) -> dict[str, Any]:
        if self.blacklist_repository is None:
            return {}
        return self.blacklist_repository.read_raw_entries()

    def write_entries(self, entries: Mapping[str, Mapping[str, Any]]) -> None:
        if self.blacklist_repository is None:
            raise RuntimeError("blacklist repository is unavailable")
        self.blacklist_repository.write_entries(entries)

    def _quality_repository(self) -> QualityRepository:
        if self.quality_repository is None:
            raise RuntimeError("quality repository is unavailable")
        return self.quality_repository

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
        quality_by_node = self.quality_repository.list_latest() if self.quality_repository is not None else {}
        return [
            node for node in nodes
            if match_node(region, node, quality_by_node.get(str(node.get("id") or "")))
        ]

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

    def node_matches_routing_region(
        self,
        node: dict[str, Any],
        target: str,
        quality_by_node: Mapping[str, Any] | None = None,
    ) -> bool:
        region = self.get_region_routing_target(target)
        if region:
            try:
                qualities = quality_by_node
                if qualities is None:
                    qualities = self.quality_repository.list_latest() if self.quality_repository is not None else {}
                return match_node(region, node, qualities.get(str(node.get("id") or "")))
            except InvalidRegion:
                return False
        return self.node_matches_country_target(node, target)

    def filter_nodes_by_routing_region(self, nodes: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
        if not target:
            return nodes
        quality_by_node = self.quality_repository.list_latest() if self.quality_repository is not None else {}
        return [node for node in nodes if self.node_matches_routing_region(node, target, quality_by_node)]

    def validate_routing_region_target(self, routing_mode: str, target: str) -> None:
        if routing_mode != "fixed_region" or not target:
            return
        if str(target).strip().startswith("region:") and self.get_region_routing_target(target) is None:
            raise ValueError("地区不存在")
