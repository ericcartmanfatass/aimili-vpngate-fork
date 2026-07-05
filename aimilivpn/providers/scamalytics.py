from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable

from aimilivpn.core.models import QualityResult, VpnNode
from aimilivpn.core.scoring import apply_score

from .quality_base import QualityProvider


class ScamalyticsError(RuntimeError):
    pass


class ScamalyticsRateLimited(ScamalyticsError):
    pass


UrlOpenFunc = Callable[..., Any]


class ScamalyticsProvider(QualityProvider):
    name = "scamalytics"

    def __init__(
        self,
        username: str,
        api_key: str,
        api_url: str = "https://api11.scamalytics.com/{username}/",
        timeout_seconds: int = 8,
        cache_ttl_seconds: int = 86400,
        rate_limit_per_minute: int = 30,
        opener: UrlOpenFunc | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.username = username
        self.api_key = api_key
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.rate_limit_per_minute = rate_limit_per_minute
        self.opener = opener or urllib.request.urlopen
        self.clock = clock or time.time
        self._cache: dict[str, tuple[float, QualityResult]] = {}
        self._request_times: list[float] = []

    @property
    def configured(self) -> bool:
        return bool(self.username and self.api_key)

    def check_node(self, node: VpnNode | dict[str, Any]) -> QualityResult:
        ip = _node_value(node, "ip", "remote_host")
        result = self.check_ip(str(ip or ""))
        result.node_id = str(_node_value(node, "id") or "") or result.node_id
        return result

    def check_ip(self, ip: str) -> QualityResult:
        ip = str(ip or "").strip()
        if not ip:
            raise ScamalyticsError("ip is required")
        if not self.configured:
            raise ScamalyticsError("scamalytics is not configured")

        now = self.clock()
        cached = self._cache.get(ip)
        if cached and now - cached[0] < self.cache_ttl_seconds:
            return replace(cached[1])

        self._enforce_rate_limit(now)
        data = self._fetch(ip)
        result = parse_scamalytics_response(ip, data, checked_at=_utc_now_iso())
        self._cache[ip] = (now, result)
        return replace(result)

    def _fetch(self, ip: str) -> dict[str, Any]:
        url = self._request_url(ip)
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "aimilivpn/quality-scamalytics"},
            method="GET",
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise ScamalyticsError("scamalytics request failed") from exc
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ScamalyticsError("scamalytics returned invalid json") from exc
        if not isinstance(data, dict):
            raise ScamalyticsError("scamalytics returned an invalid payload")
        return data

    def _request_url(self, ip: str) -> str:
        username = urllib.parse.quote(self.username, safe="")
        base = self.api_url.format(username=username)
        separator = "&" if "?" in base else "?"
        return base + separator + urllib.parse.urlencode({"key": self.api_key, "ip": ip})

    def _enforce_rate_limit(self, now: float) -> None:
        self._request_times = [ts for ts in self._request_times if now - ts < 60]
        if len(self._request_times) >= self.rate_limit_per_minute:
            raise ScamalyticsRateLimited("scamalytics rate limit exceeded")
        self._request_times.append(now)


def parse_scamalytics_response(ip: str, data: dict[str, Any], checked_at: str | None = None) -> QualityResult:
    risk_score = _optional_int(_first(data, "score", "risk_score", "fraud_score"))
    risk_level = _first(data, "risk", "risk_level", "risk_label")
    proxy_detected = _any_bool(data, ["proxy", "vpn", "tor", "public_proxy", "web_proxy"])
    datacenter_detected = _any_bool(data, ["server", "hosting", "datacenter", "datacenter_detected"])
    result = QualityResult(
        node_id=None,
        exit_ip=str(data.get("ip") or ip),
        tcp_latency_ms=None,
        openvpn_success=None,
        handshake_ms=None,
        risk_provider="scamalytics",
        risk_score=risk_score,
        risk_level=str(risk_level) if risk_level not in (None, "") else None,
        proxy_detected=proxy_detected,
        datacenter_detected=datacenter_detected,
        country_match=None,
        checked_at=checked_at or _utc_now_iso(),
        raw_response=data,
    )
    return apply_score(result)


def merge_scamalytics_result(base: QualityResult, risk: QualityResult) -> QualityResult:
    base.risk_provider = risk.risk_provider
    base.risk_score = risk.risk_score
    base.risk_level = risk.risk_level
    if risk.proxy_detected is not None:
        base.proxy_detected = bool(base.proxy_detected) or risk.proxy_detected
    if risk.datacenter_detected is not None:
        base.datacenter_detected = bool(base.datacenter_detected) or risk.datacenter_detected
    base.raw_response = {
        **(base.raw_response or {}),
        "scamalytics": risk.raw_response or {},
    }
    return apply_score(base)


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


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if data.get(key) not in (None, ""):
            return data.get(key)
    return None


def _any_bool(data: dict[str, Any], keys: list[str]) -> bool | None:
    values = [_bool_value(data.get(key)) for key in keys if data.get(key) not in (None, "")]
    if not values:
        return None
    return any(values)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
