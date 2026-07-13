from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from aimilivpn.core.config import AppConfig, load_config
from aimilivpn.core.models import QualityResult, RegionProfile
from aimilivpn.core.regions import match_node, region_exclusion_reason
from aimilivpn.core.scoring import apply_score
from aimilivpn.core.storage import ProviderCacheRepository, QualityRepository, RegionRepository
from aimilivpn.providers.scamalytics import (
    ScamalyticsError,
    ScamalyticsProvider,
    merge_scamalytics_result,
)
from aimilivpn.web.api import quality_provider_status as build_quality_provider_status
from aimilivpn.web.api import quality_to_dict, region_to_dict

ProviderGetter = Callable[[], ScamalyticsProvider | None]


def configured_scamalytics_provider(
    config: AppConfig,
    current: ScamalyticsProvider | None,
    cache_repository: ProviderCacheRepository | None = None,
) -> ScamalyticsProvider | None:
    if not config.scamalytics_configured:
        return None
    if (
        current is None
        or current.username != config.scamalytics_username
        or current.api_key != config.scamalytics_api_key
        or current.api_url != config.scamalytics_api_url
        or current.timeout_seconds != config.scamalytics_timeout_seconds
        or current.cache_ttl_seconds != config.scamalytics_cache_ttl_seconds
        or current.rate_limit_per_minute != config.scamalytics_rate_limit_per_minute
    ):
        return ScamalyticsProvider(
            username=config.scamalytics_username,
            api_key=config.scamalytics_api_key,
            api_url=config.scamalytics_api_url,
            timeout_seconds=config.scamalytics_timeout_seconds,
            cache_ttl_seconds=config.scamalytics_cache_ttl_seconds,
            rate_limit_per_minute=config.scamalytics_rate_limit_per_minute,
            cache_repository=cache_repository,
        )
    return current


def provider_status(config: AppConfig | Path) -> dict[str, Any]:
    resolved = config if isinstance(config, AppConfig) else load_config(config)
    return build_quality_provider_status(resolved)


def enrich_with_scamalytics(result: QualityResult, provider_getter: ProviderGetter) -> QualityResult:
    provider = provider_getter()
    if provider is None or not result.exit_ip:
        return result
    try:
        risk_result = provider.check_ip(result.exit_ip)
        return merge_scamalytics_result(result, risk_result)
    except ScamalyticsError as exc:
        result.raw_response = {
            **(result.raw_response or {}),
            "scamalytics_error": type(exc).__name__,
        }
        return apply_score(result)


def record_from_probe(
    node: dict[str, Any],
    openvpn_success: bool | None,
    latency_ms: int,
    probe_message: str,
    *,
    quality_repository: QualityRepository,
    provider_getter: ProviderGetter,
    clock: Callable[[], datetime] | None = None,
) -> QualityResult:
    quality = str(node.get("quality") or "").strip().lower()
    ip_type = str(node.get("ip_type") or "").strip().lower()
    now = clock or (lambda: datetime.now(timezone.utc))
    result = QualityResult(
        node_id=str(node.get("id") or ""),
        exit_ip=str(node.get("ip") or node.get("remote_host") or "") or None,
        tcp_latency_ms=latency_ms if latency_ms > 0 else None,
        openvpn_success=openvpn_success,
        handshake_ms=None,
        risk_provider=None,
        risk_score=None,
        risk_level=None,
        proxy_detected=True if quality == "proxy" else False if quality else None,
        datacenter_detected=True if quality == "datacenter" or ip_type == "hosting" else False if quality or ip_type else None,
        country_match=None,
        checked_at=now().astimezone(timezone.utc).isoformat(),
        raw_response={"probe_message": probe_message} if probe_message else None,
    )
    result = apply_score(result)
    result = enrich_with_scamalytics(result, provider_getter)
    quality_repository.save(result)
    return result


def latest_for_node(quality_repository: QualityRepository, node_id: str) -> QualityResult | None:
    node_id = str(node_id or "").strip()
    if not node_id:
        return None
    return quality_repository.latest_for_node(node_id)


def latest_map(quality_repository: QualityRepository) -> dict[str, QualityResult]:
    return quality_repository.list_latest()


def check_ip(ip: str, *, provider_getter: ProviderGetter, quality_repository: QualityRepository) -> QualityResult:
    ip = str(ip or "").strip()
    if not ip:
        raise ValueError("ip is required")
    provider = provider_getter()
    if provider is None:
        raise ScamalyticsError("scamalytics is not configured")
    result = provider.check_ip(ip)
    quality_repository.save(result)
    return result


def check_region(
    region_id: str,
    limit: int,
    *,
    region_target_id: Callable[[str], str],
    region_repository: RegionRepository,
    quality_repository: QualityRepository,
    read_nodes: Callable[[], list[dict[str, Any]]],
    node_allowed: Callable[[dict[str, Any]], bool],
    bounded_int: Callable[[Any, int, int | None, int | None], int],
    test_multiple_nodes: Callable[[list[str]], list[dict[str, Any]]],
) -> dict[str, Any]:
    region_id = region_target_id(region_id)
    if not region_id:
        raise ValueError("region_id is required")
    region = region_repository.get(region_id)
    if region is None:
        raise KeyError(region_id)

    all_nodes = read_nodes()
    quality_by_node = latest_map(quality_repository)
    selection_region = replace(region, min_quality_score=None, max_risk_score=None)
    candidates = matching_region_nodes(selection_region, all_nodes, quality_by_node, node_allowed)
    limit = bounded_int(limit, 20, 1, 100)
    node_ids = [str(node.get("id") or "") for node in candidates[:limit] if node.get("id")]
    tested_nodes = test_multiple_nodes(node_ids) if node_ids else []
    quality_by_node = latest_map(quality_repository)
    nodes = matching_region_nodes(region, all_nodes, quality_by_node, node_allowed)
    exclusions: dict[str, int] = {}
    for node in candidates:
        reason = region_exclusion_reason(region, node, quality_by_node.get(str(node.get("id") or "")))
        if reason is not None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
    return {
        "region": region_to_dict(region),
        "total_matches": len(nodes),
        "total_candidates": len(candidates),
        "tested_count": len(tested_nodes),
        "limit": limit,
        "nodes": tested_nodes,
        "exclusion_reasons": exclusions,
        "qualities": {
            node_id: quality_to_dict(latest_for_node(quality_repository, node_id))
            for node_id in node_ids
        },
    }


def matching_region_nodes(
    region: RegionProfile,
    nodes: list[dict[str, Any]],
    quality_by_node: dict[str, QualityResult],
    node_allowed: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    return [
        node for node in nodes
        if node_allowed(node)
        and match_node(region, node, quality_by_node.get(str(node.get("id") or "")))
    ]
