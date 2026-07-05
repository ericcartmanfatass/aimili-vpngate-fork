from __future__ import annotations

from typing import Any


def clean_blacklist(raw: Any, *, now: float) -> tuple[dict[str, dict[str, Any]], bool]:
    if not isinstance(raw, dict):
        return {}, True

    cleaned: dict[str, dict[str, Any]] = {}
    changed = False
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            changed = True
            continue
        until = _float_value(entry.get("until"))
        if until and until > now:
            cleaned[str(key)] = entry
        else:
            changed = True
    return cleaned, changed


def blacklist_entry(node: dict[str, Any], *, message: str, now: float, backoff_seconds: int) -> dict[str, Any]:
    node_id = str(node.get("id") or "").strip()
    return {
        "id": node_id,
        "ip": node.get("ip") or node.get("remote_host") or "",
        "country": node.get("country", ""),
        "reason": message,
        "marked_at": now,
        "until": now + backoff_seconds,
    }


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
