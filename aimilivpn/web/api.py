from __future__ import annotations

from typing import Any

from aimilivpn.core.config import AppConfig
from aimilivpn.core.models import QualityResult, RegionProfile


def region_to_dict(region: RegionProfile) -> dict[str, Any]:
    return {
        "id": region.id,
        "name": region.name,
        "country_codes": region.country_codes,
        "include_keywords": region.include_keywords,
        "exclude_keywords": region.exclude_keywords,
        "min_quality_score": region.min_quality_score,
        "max_risk_score": region.max_risk_score,
        "enabled": region.enabled,
    }


def quality_to_dict(result: QualityResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "node_id": result.node_id,
        "exit_ip": result.exit_ip,
        "tcp_latency_ms": result.tcp_latency_ms,
        "openvpn_success": result.openvpn_success,
        "handshake_ms": result.handshake_ms,
        "risk_provider": result.risk_provider,
        "risk_score": result.risk_score,
        "risk_level": result.risk_level,
        "proxy_detected": result.proxy_detected,
        "datacenter_detected": result.datacenter_detected,
        "country_match": result.country_match,
        "checked_at": result.checked_at,
        "score": result.score,
        "label": result.label,
        "reasons": result.reasons,
    }


def quality_provider_status(config: AppConfig) -> dict[str, Any]:
    return {
        "providers": [
            {
                "name": "local_probe",
                "enabled": True,
                "configured": True,
                "supports": ["node"],
            },
            {
                "name": "scamalytics",
                "enabled": config.scamalytics_configured,
                "configured": config.scamalytics_configured,
                "supports": ["ip", "node"],
                "timeout_seconds": config.scamalytics_timeout_seconds,
                "cache_ttl_seconds": config.scamalytics_cache_ttl_seconds,
                "rate_limit_per_minute": config.scamalytics_rate_limit_per_minute,
                "persistent_cache": True,
            },
        ]
    }
