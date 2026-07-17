from __future__ import annotations

"""Global VPNGate snapshot parsing and safe persistence helpers."""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from aimilivpn.providers.vpngate import decode_config, parse_vpngate_rows, row_to_legacy_node


class GlobalNodeValidationError(ValueError):
    """Raised when a global node snapshot is malformed."""


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "node"


def parse_global_nodes(
    text: str,
    *,
    config_dir: Path,
    max_scan_rows: int = 3000,
    country_translations: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Parse the complete VPNGate response, keeping only one node per IP."""
    if not isinstance(text, str) or not text.strip():
        raise GlobalNodeValidationError("VPNGate 返回为空")
    rows = parse_vpngate_rows(text)
    if not rows:
        raise GlobalNodeValidationError("VPNGate 返回不包含有效表格")
    nodes: list[dict[str, Any]] = []
    seen_ips: set[str] = set()
    warnings = 0
    for row in rows[:max_scan_rows]:
        ip = str(row.get("IP") or "").strip()
        country = str(row.get("CountryShort") or "").strip().upper()
        encoded = str(row.get("OpenVPN_ConfigData_Base64") or "").strip()
        if not ip or ip in seen_ips or not re.fullmatch(r"[A-Z]{2}", country) or not encoded:
            continue
        try:
            config_text = decode_config(encoded)
            node = row_to_legacy_node(
                row,
                config_text,
                config_dir,
                country_translations=country_translations,
                safe_name_func=_safe_name,
            )
        except Exception:
            warnings += 1
            continue
        node["server_ip"] = ip
        node["snapshot_source"] = "vpngate"
        node["snapshot_warning_count"] = warnings
        nodes.append(node)
        seen_ips.add(ip)
    if not nodes:
        raise GlobalNodeValidationError("VPNGate 返回中没有可用节点")
    return nodes


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        os.close(fd)
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        tmp.unlink(missing_ok=True)


def read_global_nodes(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("nodes", [])
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict) and str(item.get("id") or "").strip()]


def _externalize_node_config(node: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    clean = dict(node)
    config_text = clean.pop("config_text", None)
    node_id = _safe_name(str(clean.get("id") or ""))
    if config_text:
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / f"{node_id}.ovpn"
        fd, raw_tmp = tempfile.mkstemp(prefix=f".{config_path.name}.", suffix=".tmp", dir=config_dir)
        tmp = Path(raw_tmp)
        try:
            os.close(fd)
            tmp.write_text(str(config_text), encoding="utf-8")
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp, config_path)
            try:
                config_path.chmod(0o600)
            except OSError:
                pass
        finally:
            tmp.unlink(missing_ok=True)
        clean["config_file"] = str(config_path)
    return clean


def externalize_nodes(nodes: Iterable[dict[str, Any]], config_dir: Path) -> list[dict[str, Any]]:
    return [_externalize_node_config(dict(node), config_dir) for node in nodes if isinstance(node, dict)]


def write_global_nodes(path: Path, nodes: Iterable[dict[str, Any]], *, config_dir: Path, updated_at: float) -> list[dict[str, Any]]:
    clean_nodes = externalize_nodes(nodes, config_dir)
    if not clean_nodes:
        raise GlobalNodeValidationError("不能用空节点快照替换当前节点库")
    _atomic_json_write(
        path,
        {
            "schema_version": 1,
            "source": "vpngate",
            "updated_at": updated_at,
            "node_count": len(clean_nodes),
            "nodes": clean_nodes,
        },
    )
    return clean_nodes


def build_country_index(nodes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for node in nodes:
        code = str(node.get("country_short") or node.get("country_code") or "").strip().upper()
        if not code:
            continue
        item = index.setdefault(code, {"country": code, "name": str(node.get("country") or code), "node_count": 0})
        item["node_count"] = int(item["node_count"]) + 1
    return index


def read_snapshot_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
