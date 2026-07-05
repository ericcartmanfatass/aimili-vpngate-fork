from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import QualityResult


@dataclass(frozen=True)
class ScoreBreakdown:
    score: int
    label: str
    reasons: list[str]


def score_quality(result: QualityResult | dict[str, Any]) -> ScoreBreakdown:
    score = 0
    reasons: list[str] = []

    tcp_latency = _optional_int(_value(result, "tcp_latency_ms"))
    if tcp_latency is not None and tcp_latency > 0:
        score += 15
        reasons.append("tcp reachable")
        if tcp_latency < 100:
            score += 20
            reasons.append("tcp latency < 100ms")
        elif tcp_latency <= 300:
            score += 10
            reasons.append("tcp latency <= 300ms")
        else:
            reasons.append("tcp latency > 300ms")

    openvpn_success = _value(result, "openvpn_success")
    if openvpn_success is True:
        score += 35
        reasons.append("openvpn handshake ok")
    elif openvpn_success is False:
        reasons.append("openvpn handshake failed")

    handshake_ms = _optional_int(_value(result, "handshake_ms"))
    if handshake_ms is not None and handshake_ms > 0 and handshake_ms < 8000:
        score += 10
        reasons.append("openvpn handshake < 8s")

    risk_score = _optional_int(_value(result, "risk_score"))
    if risk_score is not None:
        if risk_score < 30:
            score += 20
            reasons.append("risk score < 30")
        elif risk_score <= 70:
            score += 10
            reasons.append("risk score <= 70")
        else:
            score -= 20
            reasons.append("risk score > 70")

    if _value(result, "country_match") is True:
        score += 10
        reasons.append("country match")

    if _value(result, "datacenter_detected") is True:
        score -= 10
        reasons.append("datacenter detected")

    if _value(result, "proxy_detected") is True:
        score -= 15
        reasons.append("proxy detected")

    score = max(0, min(100, score))
    return ScoreBreakdown(score=score, label=_label(score, risk_score), reasons=reasons)


def apply_score(result: QualityResult) -> QualityResult:
    breakdown = score_quality(result)
    result.score = breakdown.score
    result.label = breakdown.label
    result.reasons = breakdown.reasons
    return result


def _label(score: int, risk_score: int | None) -> str:
    if risk_score is not None and risk_score > 70:
        return "High Risk"
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Usable"
    if score >= 40:
        return "Average"
    if score == 0:
        return "Unknown"
    return "High Risk"


def _value(result: QualityResult | dict[str, Any], key: str) -> Any:
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
