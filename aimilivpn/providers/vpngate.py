from __future__ import annotations

import base64
import csv
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from aimilivpn.core.config import AppConfig
from aimilivpn.core.models import VpnNode
from aimilivpn.core.security import sanitize_ovpn_config


def fetch_vpngate_text(config: AppConfig) -> str:
    request = urllib.request.Request(
        config.api_url,
        headers={
            "User-Agent": "Mozilla/5.0 vpngate-openvpn-manager/2.0",
            "Accept": "text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_vpngate_rows(text: str) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if line and not line.startswith("*")]
    if lines and lines[0].startswith("#"):
        lines[0] = lines[0][1:]
    return list(csv.DictReader(lines))


def decode_config(encoded: str) -> str:
    decoded = base64.b64decode(encoded.encode("ascii"), validate=False).decode("utf-8", errors="replace")
    return sanitize_ovpn_config(decoded)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _remote_parts(config_text: str, fallback_ip: str = "") -> tuple[str, int | None, str | None]:
    host = fallback_ip
    port: int | None = None
    proto: str | None = None
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        parts = line.split()
        if parts[0].lower() == "proto" and len(parts) >= 2:
            proto = parts[1].lower()
        elif parts[0].lower() == "remote" and len(parts) >= 3:
            host = parts[1]
            port = _safe_int(parts[2])
            if len(parts) >= 4:
                proto = parts[3].lower()
    return host, port, proto


def _default_safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("._") or "node"


def row_to_node(row: dict[str, str], config_text: str) -> VpnNode:
    ip = row.get("IP", "")
    country_code = row.get("CountryShort", "")
    remote_host, remote_port, proto = _remote_parts(config_text, ip)
    node_id = "_".join(part for part in [country_code or "XX", ip or remote_host, str(remote_port or 0), proto or "unknown"] if part)
    return VpnNode(
        id=node_id,
        source="vpngate",
        country=row.get("CountryLong") or None,
        country_code=country_code or None,
        ip=ip or remote_host or None,
        port=remote_port,
        proto=proto,
        hostname=row.get("HostName") or None,
        raw_score=_safe_int(row.get("Score")),
        latency_ms=_safe_int(row.get("Ping")),
        last_seen_at=str(int(time.time())),
        config_text=config_text,
    )


def row_to_legacy_node(
    row: dict[str, str],
    config_text: str,
    config_dir: Path,
    *,
    country_translations: dict[str, str] | None = None,
    safe_name_func: Any | None = None,
) -> dict[str, Any]:
    ip = row.get("IP", "")
    country_short = row.get("CountryShort", "")
    remote_host, remote_port, proto = _remote_parts(config_text, ip)
    safe_name = safe_name_func or _default_safe_name
    node_id = safe_name("_".join([country_short or "XX", ip or remote_host, str(remote_port or 0), proto or "unknown"]))
    config_path = config_dir / f"{node_id}.ovpn"
    country_long = row.get("CountryLong", "")
    translations = country_translations or {}
    country = translations.get(country_long, translations.get(country_long.strip(), country_long))
    return {
        "id": node_id,
        "source": "vpngate",
        "country": country,
        "country_short": country_short,
        "host_name": row.get("HostName", ""),
        "ip": ip,
        "score": _safe_int(row.get("Score")) or 0,
        "ping": _safe_int(row.get("Ping")) or 0,
        "speed": _safe_int(row.get("Speed")) or 0,
        "sessions": _safe_int(row.get("NumVpnSessions")) or 0,
        "owner": "",
        "asn": "",
        "as_name": "",
        "location": "",
        "ip_type": "",
        "quality": "",
        "latency_ms": 0,
        "config_file": str(config_path),
        "config_text": config_text,
        "proto": proto or "unknown",
        "remote_host": remote_host,
        "remote_port": remote_port or 0,
        "fetched_at": time.time(),
        "probe_status": "not_checked",
        "probe_message": "",
        "probed_at": 0,
    }


def parse_legacy_candidates(
    text: str,
    config: AppConfig,
    config_dir: Path,
    *,
    country_translations: dict[str, str] | None = None,
    safe_name_func: Any | None = None,
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for row in parse_vpngate_rows(text)[: config.max_scan_rows]:
        country_code = (row.get("CountryShort") or "").strip().upper()
        if config.allowed_countries and country_code not in config.allowed_countries:
            continue
        encoded = row.get("OpenVPN_ConfigData_Base64", "")
        if not encoded:
            continue
        config_text = decode_config(encoded)
        nodes.append(
            row_to_legacy_node(
                row,
                config_text,
                config_dir,
                country_translations=country_translations,
                safe_name_func=safe_name_func,
            )
        )
    return nodes


def parse_legacy_candidates_filtered(
    text: str,
    config_dir: Path,
    *,
    max_scan_rows: int,
    allowed_countries: set[str],
    blacklist: dict[str, dict[str, Any]],
    seen_ips: set[str] | None = None,
    now: float | None = None,
    country_translations: dict[str, str] | None = None,
    safe_name_func: Any | None = None,
) -> tuple[list[dict[str, Any]], set[str], list[str]]:
    seen = seen_ips if seen_ips is not None else set()
    current_time = time.time() if now is None else now
    nodes: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in parse_vpngate_rows(text)[:max_scan_rows]:
        ip = row.get("IP", "")
        if not ip or ip in seen:
            continue
        country_code = (row.get("CountryShort") or "").strip().upper()
        if allowed_countries and country_code not in allowed_countries:
            continue
        encoded = row.get("OpenVPN_ConfigData_Base64", "")
        if not encoded:
            continue
        try:
            config_text = decode_config(encoded)
            node = row_to_legacy_node(
                row,
                config_text,
                config_dir,
                country_translations=country_translations,
                safe_name_func=safe_name_func,
            )
        except Exception as exc:
            warnings.append(str(exc))
            continue
        entry = blacklist.get(str(node.get("id") or ""))
        if entry and _safe_float(entry.get("until")) > current_time:
            continue
        nodes.append(node)
        seen.add(ip)
    return nodes, seen, warnings


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def fetch_candidates(config: AppConfig) -> list[VpnNode]:
    text = fetch_vpngate_text(config)
    nodes: list[VpnNode] = []
    for row in parse_vpngate_rows(text)[: config.max_scan_rows]:
        country_code = (row.get("CountryShort") or "").strip().upper()
        if config.allowed_countries and country_code not in config.allowed_countries:
            continue
        encoded = row.get("OpenVPN_ConfigData_Base64", "")
        if not encoded:
            continue
        config_text = decode_config(encoded)
        nodes.append(row_to_node(row, config_text))
    return nodes
