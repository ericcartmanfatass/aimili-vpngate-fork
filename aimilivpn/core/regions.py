from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import QualityResult, RegionProfile, VpnNode


class InvalidRegion(ValueError):
    """Raised when a region profile is invalid."""


@dataclass(frozen=True)
class RegionPreview:
    region_id: str
    total_nodes: int
    matched_nodes: int
    matched_node_ids: list[str]
    exclusion_reasons: dict[str, int]


_REGION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def validate_region(region: RegionProfile) -> None:
    if not _REGION_ID_RE.match(region.id or ""):
        raise InvalidRegion("region id must use lowercase letters, digits, and single hyphens")
    if "--" in region.id or region.id.endswith("-"):
        raise InvalidRegion("region id must not contain consecutive or trailing hyphens")
    if not region.name or len(region.name.strip()) > 80:
        raise InvalidRegion("region name must be 1-80 characters")
    if not region.country_codes:
        raise InvalidRegion("region must include at least one country code")

    normalized_codes = [code.strip().upper() for code in region.country_codes]
    for code in normalized_codes:
        if not re.match(r"^[A-Z]{2}$", code):
            raise InvalidRegion(f"invalid country code: {code}")

    for label, keywords in [("include", region.include_keywords), ("exclude", region.exclude_keywords)]:
        if len(keywords) > 40:
            raise InvalidRegion(f"too many {label} keywords")
        for keyword in keywords:
            if len(keyword.strip()) > 80:
                raise InvalidRegion(f"{label} keyword is too long")

    for name, value in [
        ("min_quality_score", region.min_quality_score),
        ("max_risk_score", region.max_risk_score),
    ]:
        if value is not None and not (0 <= value <= 100):
            raise InvalidRegion(f"{name} must be between 0 and 100")


def normalized_region(region: RegionProfile) -> RegionProfile:
    validate_region(region)
    return RegionProfile(
        id=region.id.strip(),
        name=region.name.strip(),
        country_codes=sorted({code.strip().upper() for code in region.country_codes}),
        include_keywords=[item.strip() for item in region.include_keywords if item.strip()],
        exclude_keywords=[item.strip() for item in region.exclude_keywords if item.strip()],
        min_quality_score=region.min_quality_score,
        max_risk_score=region.max_risk_score,
        enabled=bool(region.enabled),
    )


def region_from_mapping(data: dict[str, Any], existing: RegionProfile | None = None) -> RegionProfile:
    base = existing.__dict__.copy() if existing else {}
    base.update(data)
    return RegionProfile(
        id=str(base.get("id") or "").strip(),
        name=str(base.get("name") or "").strip(),
        country_codes=_string_list(base.get("country_codes")),
        include_keywords=_string_list(base.get("include_keywords")),
        exclude_keywords=_string_list(base.get("exclude_keywords")),
        min_quality_score=_optional_int(base.get("min_quality_score")),
        max_risk_score=_optional_int(base.get("max_risk_score")),
        enabled=_bool_value(base.get("enabled", True)),
    )


def match_node(
    region: RegionProfile,
    node: VpnNode | dict[str, Any],
    quality: QualityResult | dict[str, Any] | None = None,
) -> bool:
    return region_exclusion_reason(region, node, quality) is None


def region_exclusion_reason(
    region: RegionProfile,
    node: VpnNode | dict[str, Any],
    quality: QualityResult | dict[str, Any] | None = None,
) -> str | None:
    validate_region(region)
    if not region.enabled:
        return "region_disabled"

    country_code = _node_value(node, "country_code", "country_short")
    if country_code and country_code.upper() not in {code.upper() for code in region.country_codes}:
        return "country_not_allowed"
    if not country_code:
        return "country_unknown"

    searchable = _search_text(node)
    include_keywords = [item.strip().lower() for item in region.include_keywords if item.strip()]
    exclude_keywords = [item.strip().lower() for item in region.exclude_keywords if item.strip()]

    if include_keywords and not any(keyword in searchable for keyword in include_keywords):
        return "include_keyword_missing"
    if exclude_keywords and any(keyword in searchable for keyword in exclude_keywords):
        return "exclude_keyword_matched"

    quality_score = _quality_score(node, quality)
    if region.min_quality_score is not None:
        if quality_score is None:
            return "quality_not_tested"
        if quality_score < region.min_quality_score:
            return "quality_below_minimum"

    risk_score = _quality_value(quality, "risk_score")
    if region.max_risk_score is not None:
        if risk_score is None:
            return "risk_not_tested"
        if int(risk_score) > region.max_risk_score:
            return "risk_above_maximum"

    return None


def preview_region(
    region: RegionProfile,
    nodes: list[VpnNode | dict[str, Any]],
    quality_by_node: dict[str, QualityResult | dict[str, Any]] | None = None,
) -> RegionPreview:
    quality_by_node = quality_by_node or {}
    matched: list[str] = []
    exclusion_reasons: dict[str, int] = {}
    for node in nodes:
        node_id = str(_node_value(node, "id") or "")
        quality = quality_by_node.get(node_id)
        reason = region_exclusion_reason(region, node, quality)
        if reason is None:
            matched.append(node_id)
        else:
            exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1
    return RegionPreview(
        region_id=region.id,
        total_nodes=len(nodes),
        matched_nodes=len(matched),
        matched_node_ids=matched,
        exclusion_reasons=exclusion_reasons,
    )


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


def _quality_value(quality: QualityResult | dict[str, Any] | None, key: str) -> Any:
    if quality is None:
        return None
    if isinstance(quality, dict):
        return quality.get(key)
    return getattr(quality, key, None)


def _search_text(node: VpnNode | dict[str, Any]) -> str:
    fields = [
        "country",
        "country_code",
        "country_short",
        "hostname",
        "host_name",
        "operator",
        "owner",
        "location",
        "as_name",
        "ip_type",
        "quality",
    ]
    return " ".join(str(_node_value(node, field) or "") for field in fields).lower()


def _quality_score(node: VpnNode | dict[str, Any], quality: QualityResult | dict[str, Any] | None) -> int | None:
    for value in [
        _quality_value(quality, "score"),
        _node_value(node, "quality_score"),
    ]:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(value)
