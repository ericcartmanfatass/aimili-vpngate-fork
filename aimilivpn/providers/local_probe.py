from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from aimilivpn.core.models import QualityResult, VpnNode
from aimilivpn.core.scoring import apply_score

from .quality_base import QualityProvider

LatencyFunc = Callable[[str, int, int], int]
OpenVPNCheckFunc = Callable[[VpnNode | dict[str, Any]], tuple[bool, str, int | None]]


class LocalProbeProvider(QualityProvider):
    name = "local_probe"

    def __init__(
        self,
        latency_func: LatencyFunc,
        openvpn_check_func: OpenVPNCheckFunc | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.latency_func = latency_func
        self.openvpn_check_func = openvpn_check_func
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def check_node(self, node: VpnNode | dict[str, Any]) -> QualityResult:
        host = str(_node_value(node, "remote_host", "ip") or "")
        port = _optional_int(_node_value(node, "remote_port", "port")) or 0
        fallback_ping = _optional_int(_node_value(node, "ping")) or 0
        latency = 0
        if host and port:
            latency = self.latency_func(host, port, fallback_ping)

        openvpn_success: bool | None = None
        probe_message = ""
        handshake_ms: int | None = None
        if self.openvpn_check_func is not None:
            try:
                openvpn_success, probe_message, handshake_ms = self.openvpn_check_func(node)
            except Exception as exc:
                openvpn_success = False
                probe_message = str(exc)

        result = QualityResult(
            node_id=str(_node_value(node, "id") or ""),
            exit_ip=str(_node_value(node, "ip", "remote_host") or "") or None,
            tcp_latency_ms=latency if latency > 0 else None,
            openvpn_success=openvpn_success,
            handshake_ms=handshake_ms,
            risk_provider=None,
            risk_score=None,
            risk_level=None,
            proxy_detected=_quality_is(node, "proxy"),
            datacenter_detected=_quality_is(node, "datacenter") or _node_value(node, "ip_type") == "hosting",
            country_match=None,
            checked_at=self.clock().astimezone(timezone.utc).isoformat(),
            raw_response={"probe_message": probe_message} if probe_message else None,
        )
        return apply_score(result)


def quality_result_to_node_patch(result: QualityResult) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "quality_score": result.score,
        "quality_label": result.label,
        "quality_reasons": result.reasons,
        "quality_checked_at": result.checked_at,
    }
    if result.tcp_latency_ms is not None:
        patch["latency_ms"] = result.tcp_latency_ms
    if result.openvpn_success is not None:
        patch["probe_status"] = "available" if result.openvpn_success else "unavailable"
    if result.raw_response and result.raw_response.get("probe_message"):
        patch["probe_message"] = result.raw_response["probe_message"]
    return patch


def _node_value(node: VpnNode | dict[str, Any], *keys: str) -> Any:
    if isinstance(node, dict):
        for key in keys:
            if node.get(key) not in (None, ""):
                return node.get(key)
        return None
    for key in keys:
        attr = getattr(node, key, None)
        if attr not in (None, ""):
            return attr
    return None


def _quality_is(node: VpnNode | dict[str, Any], expected: str) -> bool | None:
    quality = _node_value(node, "quality")
    if quality in (None, ""):
        return None
    return str(quality).lower() == expected


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
