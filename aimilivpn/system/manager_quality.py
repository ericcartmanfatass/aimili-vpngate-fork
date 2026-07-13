from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from aimilivpn.core.config import AppConfig
from aimilivpn.core.models import QualityResult
from aimilivpn.core.storage import QualityRepository, RegionRepository
from aimilivpn.providers.scamalytics import ScamalyticsProvider
from aimilivpn.system import quality_runtime


@dataclass
class ManagerQualityRuntime:
    app_config: AppConfig
    quality_repository: QualityRepository
    region_repository: RegionRepository
    region_target_id: Callable[[str], str]
    read_nodes: Callable[[], list[dict[str, Any]]]
    node_allowed: Callable[[dict[str, Any]], bool]
    bounded_int: Callable[[Any, int, int | None, int | None], int]
    test_multiple_nodes: Callable[[list[str]], list[dict[str, Any]]]
    _scamalytics_provider: ScamalyticsProvider | None = field(default=None, init=False)

    def get_scamalytics_provider(self) -> ScamalyticsProvider | None:
        self._scamalytics_provider = quality_runtime.configured_scamalytics_provider(
            self.app_config,
            self._scamalytics_provider,
        )
        return self._scamalytics_provider

    def enrich_quality_with_scamalytics(
        self,
        result: QualityResult,
        *,
        provider_getter: quality_runtime.ProviderGetter | None = None,
    ) -> QualityResult:
        return quality_runtime.enrich_with_scamalytics(
            result,
            provider_getter or self.get_scamalytics_provider,
        )

    def record_quality_result_from_probe(
        self,
        node: dict[str, Any],
        openvpn_success: bool | None,
        latency_ms: int,
        probe_message: str = "",
        *,
        provider_getter: quality_runtime.ProviderGetter | None = None,
    ) -> QualityResult:
        return quality_runtime.record_from_probe(
            node,
            openvpn_success,
            latency_ms,
            probe_message,
            quality_repository=self.quality_repository,
            provider_getter=provider_getter or self.get_scamalytics_provider,
        )

    def latest_quality_for_node(self, node_id: str) -> QualityResult | None:
        return quality_runtime.latest_for_node(self.quality_repository, node_id)

    def latest_quality_map(self) -> dict[str, QualityResult]:
        return quality_runtime.latest_map(self.quality_repository)

    def check_quality_ip(
        self,
        ip: str,
        *,
        provider_getter: quality_runtime.ProviderGetter | None = None,
    ) -> QualityResult:
        return quality_runtime.check_ip(
            ip,
            provider_getter=provider_getter or self.get_scamalytics_provider,
            quality_repository=self.quality_repository,
        )

    def check_quality_region(self, region_id: str, limit: int = 20) -> dict[str, Any]:
        return quality_runtime.check_region(
            region_id,
            limit,
            region_target_id=self.region_target_id,
            region_repository=self.region_repository,
            quality_repository=self.quality_repository,
            read_nodes=self.read_nodes,
            node_allowed=self.node_allowed,
            bounded_int=self.bounded_int,
            test_multiple_nodes=self.test_multiple_nodes,
        )

    def quality_provider_status(self) -> dict[str, Any]:
        return quality_runtime.provider_status(self.app_config)
