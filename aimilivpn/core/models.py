from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VpnNode:
    id: str
    source: str
    country: str | None
    country_code: str | None
    ip: str | None
    port: int | None
    proto: str | None
    hostname: str | None = None
    operator: str | None = None
    raw_score: int | None = None
    latency_ms: int | None = None
    probe_status: str = "not_checked"
    ip_type: str | None = None
    quality: str | None = None
    tags: list[str] = field(default_factory=list)
    last_seen_at: str | None = None
    config_text: str | None = None


@dataclass
class RegionProfile:
    id: str
    name: str
    country_codes: list[str]
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    min_quality_score: int | None = None
    max_risk_score: int | None = None
    enabled: bool = True


@dataclass
class QualityResult:
    node_id: str | None
    exit_ip: str | None
    tcp_latency_ms: int | None
    openvpn_success: bool | None
    handshake_ms: int | None
    risk_provider: str | None
    risk_score: int | None
    risk_level: str | None
    proxy_detected: bool | None
    datacenter_detected: bool | None
    country_match: bool | None
    checked_at: str
    raw_response: dict[str, Any] | None = None
    score: int | None = None
    label: str | None = None
    reasons: list[str] = field(default_factory=list)


def node_from_dict(data: dict[str, Any]) -> VpnNode:
    return VpnNode(
        id=str(data.get("id") or ""),
        source=str(data.get("source") or "vpngate"),
        country=data.get("country"),
        country_code=data.get("country_code") or data.get("country_short"),
        ip=data.get("ip") or data.get("remote_host"),
        port=data.get("port") or data.get("remote_port"),
        proto=data.get("proto"),
        hostname=data.get("hostname") or data.get("host_name"),
        operator=data.get("operator") or data.get("owner"),
        raw_score=data.get("raw_score") or data.get("score"),
        latency_ms=data.get("latency_ms"),
        probe_status=data.get("probe_status", "not_checked"),
        ip_type=data.get("ip_type"),
        quality=data.get("quality"),
        tags=list(data.get("tags") or []),
        last_seen_at=data.get("last_seen_at") or data.get("fetched_at"),
        config_text=data.get("config_text"),
    )


def node_to_dict(node: VpnNode) -> dict[str, Any]:
    return asdict(node)
